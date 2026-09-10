"""Inbox, preference, and endpoint application services."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.encryption import encrypt
from app.core.time import utc_now
from app.models import (
    AuditLog,
    Notification,
    NotificationEndpoint,
    NotificationPreference,
    User,
)
from app.modules.identity.domain import AuthorizationContext

from .domain import NotificationEndpointStatus, NotificationError, severity_allows
from .schemas import NotificationEndpointUpsert, NotificationPreferenceUpdate
from .security import notification_scope_visible


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _audit(
    db: Session,
    *,
    actor: User,
    action: str,
    resource_type: str,
    resource_id: str,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=actor.id,
            user_email=actor.email,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=_json(details or {}),
        )
    )


def notification_payload(row: Notification) -> dict[str, Any]:
    return {
        "id": row.id,
        "organization_id": row.organization_id,
        "workspace_id": row.workspace_id,
        "category": row.category,
        "notification_type": row.notification_type,
        "title": row.title,
        "body": row.body,
        "severity": row.severity,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "occurrence_count": row.occurrence_count,
        "first_occurred_at": row.first_occurred_at,
        "last_occurred_at": row.last_occurred_at,
        "read_at": row.read_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def preference_payload(row: NotificationPreference) -> dict[str, Any]:
    return {
        "id": row.id,
        "organization_id": row.organization_id,
        "scope_key": row.scope_key,
        "category": row.category,
        "in_app_enabled": row.in_app_enabled,
        "push_enabled": row.push_enabled,
        "email_enabled": row.email_enabled,
        "sms_enabled": row.sms_enabled,
        "minimum_severity": row.minimum_severity,
        "quiet_hours_start": row.quiet_hours_start,
        "quiet_hours_end": row.quiet_hours_end,
        "timezone": row.timezone,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def endpoint_payload(row: NotificationEndpoint) -> dict[str, Any]:
    return {
        "id": row.id,
        "organization_id": row.organization_id,
        "installation_id": row.installation_id,
        "platform": row.platform,
        "provider": row.provider,
        "status": row.status,
        "last_seen_at": row.last_seen_at or row.last_registered_at,
        "lifecycle_version": row.lifecycle_version,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def effective_preference(
    db: Session,
    *,
    user_id: str,
    organization_id: str,
    category: str,
) -> NotificationPreference | None:
    rows = (
        db.query(NotificationPreference)
        .filter(
            NotificationPreference.user_id == user_id,
            NotificationPreference.category == category,
            NotificationPreference.scope_key.in_((organization_id, "GLOBAL")),
        )
        .all()
    )
    by_scope = {row.scope_key: row for row in rows}
    return by_scope.get(organization_id) or by_scope.get("GLOBAL")


def _in_app_visible(db: Session, row: Notification) -> bool:
    if not row.recipient_user_id:
        return False
    preference = effective_preference(
        db,
        user_id=row.recipient_user_id,
        organization_id=row.organization_id,
        category=row.category,
    )
    return bool(
        preference is None
        or (
            preference.in_app_enabled
            and severity_allows(
                actual=row.severity,
                minimum=preference.minimum_severity,
            )
        )
    )


def visible_notifications(
    db: Session,
    *,
    context: AuthorizationContext,
    organization_id: str | None = None,
    workspace_id: str | None = None,
    category: str | None = None,
    unread_only: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Notification], int, int]:
    query = db.query(Notification).filter(
        Notification.recipient_kind == "USER",
        Notification.recipient_user_id == context.user_id,
    )
    if organization_id:
        query = query.filter(Notification.organization_id == organization_id)
    if workspace_id:
        query = query.filter(Notification.workspace_id == workspace_id)
    if category:
        query = query.filter(Notification.category == category)
    rows = query.order_by(
        Notification.last_occurred_at.desc(), Notification.id.desc()
    ).all()
    visible = [
        row
        for row in rows
        if notification_scope_visible(db, context=context, notification=row)
        and _in_app_visible(db, row)
    ]
    unread = sum(row.read_at is None for row in visible)
    if unread_only:
        visible = [row for row in visible if row.read_at is None]
    total = len(visible)
    return visible[offset : offset + limit], total, unread


def get_visible_notification(
    db: Session,
    *,
    context: AuthorizationContext,
    notification_id: str,
) -> Notification:
    row = db.get(Notification, notification_id)
    if (
        row is None
        or not notification_scope_visible(db, context=context, notification=row)
        or not _in_app_visible(db, row)
    ):
        raise NotificationError("notification_not_found", "Notification was not found")
    return row


def get_scoped_notification(
    db: Session,
    *,
    context: AuthorizationContext,
    notification_id: str,
) -> Notification:
    """Authorize a delivery/deep-link row even if inbox display is disabled."""

    row = db.get(Notification, notification_id)
    if row is None or not notification_scope_visible(
        db, context=context, notification=row
    ):
        raise NotificationError("notification_not_found", "Notification was not found")
    return row


def mark_notification_read(
    db: Session,
    *,
    context: AuthorizationContext,
    actor: User,
    notification_id: str,
) -> Notification:
    row = get_visible_notification(
        db, context=context, notification_id=notification_id
    )
    if row.read_at is None:
        row.read_at = utc_now()
        row.updated_at = row.read_at
        _audit(
            db,
            actor=actor,
            action="notification.read",
            resource_type="notification",
            resource_id=row.id,
            details={"organization_id": row.organization_id},
        )
    return row


def mark_all_notifications_read(
    db: Session,
    *,
    context: AuthorizationContext,
    actor: User,
    organization_id: str | None = None,
) -> int:
    rows, _, _ = visible_notifications(
        db,
        context=context,
        organization_id=organization_id,
        limit=10_000,
    )
    now = utc_now()
    changed = 0
    for row in rows:
        if row.read_at is None:
            row.read_at = now
            row.updated_at = now
            changed += 1
    if changed:
        _audit(
            db,
            actor=actor,
            action="notification.read_all",
            resource_type="notification_inbox",
            resource_id=actor.id,
            details={"organization_id": organization_id, "count": changed},
        )
    return changed


def list_preferences(
    db: Session, *, context: AuthorizationContext
) -> list[NotificationPreference]:
    return (
        db.query(NotificationPreference)
        .filter(NotificationPreference.user_id == context.user_id)
        .order_by(
            NotificationPreference.scope_key.asc(),
            NotificationPreference.category.asc(),
        )
        .all()
    )


def upsert_preference(
    db: Session,
    *,
    context: AuthorizationContext,
    actor: User,
    data: NotificationPreferenceUpdate,
) -> NotificationPreference:
    if data.organization_id:
        probe = Notification(
            recipient_user_id=context.user_id,
            recipient_kind="USER",
            organization_id=data.organization_id,
            workspace_id=None,
        )
        if not notification_scope_visible(db, context=context, notification=probe):
            raise NotificationError("organization_not_found", "Organization was not found")
    scope_key = data.organization_id or "GLOBAL"
    row = (
        db.query(NotificationPreference)
        .filter(
            NotificationPreference.user_id == context.user_id,
            NotificationPreference.scope_key == scope_key,
            NotificationPreference.category == data.category.value,
        )
        .one_or_none()
    )
    now = utc_now()
    if row is None:
        row = NotificationPreference(
            id=str(uuid.uuid4()),
            user_id=context.user_id,
            organization_id=data.organization_id,
            scope_key=scope_key,
            category=data.category.value,
            created_at=now,
        )
        db.add(row)
    row.in_app_enabled = data.in_app_enabled
    row.push_enabled = data.push_enabled
    row.email_enabled = data.email_enabled
    row.sms_enabled = data.sms_enabled
    row.minimum_severity = data.minimum_severity.value
    row.quiet_hours_start = data.quiet_hours_start
    row.quiet_hours_end = data.quiet_hours_end
    row.timezone = data.timezone
    row.updated_at = now
    db.flush()
    _audit(
        db,
        actor=actor,
        action="notification.preference_updated",
        resource_type="notification_preference",
        resource_id=row.id,
        details={"scope_key": scope_key, "category": row.category},
    )
    return row


def register_endpoint(
    db: Session,
    *,
    context: AuthorizationContext,
    actor: User,
    installation_id: str,
    data: NotificationEndpointUpsert,
    config: Settings = settings,
    protector=encrypt,
) -> NotificationEndpoint:
    installation = installation_id.strip()
    if not installation or len(installation) > 200:
        raise NotificationError("invalid_installation", "Installation ID is invalid")
    if data.organization_id:
        probe = Notification(
            recipient_user_id=context.user_id,
            recipient_kind="USER",
            organization_id=data.organization_id,
            workspace_id=None,
        )
        if not notification_scope_visible(db, context=context, notification=probe):
            raise NotificationError("organization_not_found", "Organization was not found")
    row = (
        db.query(NotificationEndpoint)
        .filter(NotificationEndpoint.installation_id == installation)
        .one_or_none()
    )
    if row is not None and row.user_id != context.user_id:
        raise NotificationError("endpoint_not_found", "Notification endpoint was not found")
    now = utc_now()
    if row is not None and data.expected_lifecycle_version is not None:
        if row.lifecycle_version != data.expected_lifecycle_version:
            raise NotificationError("version_conflict", "Endpoint changed since it was last read")
    if not config.encryption_key_is_valid:
        raise NotificationError(
            "endpoint_protection_failed",
            "Endpoint registration requires configured credential encryption",
        )
    protected = protector(data.handle)
    if not protected or protected.startswith("plain:"):
        raise NotificationError("endpoint_protection_failed", "Endpoint could not be protected")
    provider = data.provider.strip().lower().replace("-", "_")
    if provider not in {"azure_notification_hubs", "fake", "file"}:
        raise NotificationError(
            "unsupported_endpoint_provider",
            "Notification endpoint provider is not supported",
        )
    if config.is_deployed and provider != "azure_notification_hubs":
        raise NotificationError(
            "unsupported_endpoint_provider",
            "Local notification endpoint providers are disabled in this environment",
        )
    digest = hashlib.sha256(data.handle.encode("utf-8")).hexdigest()
    if row is None:
        row = NotificationEndpoint(
            id=str(uuid.uuid4()),
            user_id=context.user_id,
            installation_id=installation,
            lifecycle_version=1,
            created_at=now,
        )
        db.add(row)
    else:
        row.lifecycle_version += 1
    row.organization_id = data.organization_id
    row.platform = data.platform.value
    row.provider = provider
    row.handle_ciphertext = protected
    row.handle_digest = digest
    row.encryption_key_id = "geovision-fernet-v1"
    row.status = NotificationEndpointStatus.ACTIVE.value
    row.last_registered_at = now
    row.last_seen_at = now
    row.revoked_at = None
    row.updated_at = now
    db.flush()
    _audit(
        db,
        actor=actor,
        action="notification.endpoint_registered",
        resource_type="notification_endpoint",
        resource_id=row.id,
        details={
            "installation_id_sha256": hashlib.sha256(installation.encode()).hexdigest(),
            "platform": row.platform,
            "provider": row.provider,
        },
    )
    return row


def revoke_endpoint(
    db: Session,
    *,
    context: AuthorizationContext,
    actor: User,
    installation_id: str,
) -> bool:
    row = (
        db.query(NotificationEndpoint)
        .filter(
            NotificationEndpoint.installation_id == installation_id,
            NotificationEndpoint.user_id == context.user_id,
        )
        .one_or_none()
    )
    if row is None:
        return False
    if row.status != NotificationEndpointStatus.REVOKED.value:
        row.status = NotificationEndpointStatus.REVOKED.value
        row.handle_ciphertext = "revoked"
        row.handle_digest = hashlib.sha256(
            f"revoked:{row.id}:{uuid.uuid4()}".encode()
        ).hexdigest()
        row.revoked_at = utc_now()
        row.updated_at = row.revoked_at
        row.lifecycle_version += 1
        _audit(
            db,
            actor=actor,
            action="notification.endpoint_revoked",
            resource_type="notification_endpoint",
            resource_id=row.id,
        )
    return True


def suppress_pending_deliveries(
    db: Session,
    *,
    notifications: Iterable[Notification],
) -> None:
    """Compatibility hook used by future bulk preference jobs."""

    for notification in notifications:
        notification.updated_at = utc_now()


__all__ = [
    "effective_preference",
    "endpoint_payload",
    "get_visible_notification",
    "get_scoped_notification",
    "list_preferences",
    "mark_all_notifications_read",
    "mark_notification_read",
    "notification_payload",
    "preference_payload",
    "register_endpoint",
    "revoke_endpoint",
    "upsert_preference",
    "visible_notifications",
]
