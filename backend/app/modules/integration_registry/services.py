"""Tenant-safe persistence and lifecycle services for external integrations."""

from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
from typing import Any
import uuid
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.event_names import EventNames
from app.core.integration import sanitize_integration_message
from app.core.time import utc_now
from app.models import (
    Account,
    AccountMember,
    Company,
    CompanyEntitlement,
    FeatureFlagOverride,
    IntegrationConnection,
    IntegrationSyncEvent,
    IntegrationSyncRun,
    User,
)
from app.modules.audit.services import record_audit_event
from app.services.event_outbox import enqueue_domain_event

from .domain import (
    FEATURE_FLAG_PREFIXES,
    FeatureFlagEvaluator,
    FeatureFlagTarget,
    IntegrationRegistryError,
    normalize_identifier,
    required_sync_capability,
)
from .schemas import (
    FeatureFlagOverrideOut,
    FeatureFlagOverridePut,
    FeatureFlagResolutionOut,
    IntegrationConnectionCreate,
    IntegrationConnectionOut,
    IntegrationConnectionUpdate,
    IntegrationHealthOut,
    IntegrationSyncEventOut,
    IntegrationSyncRetryRequest,
    IntegrationSyncRunCreate,
    IntegrationSyncRunOut,
)


_CONNECTION_STATUS_OUT = {
    "CONFIGURING": "pending_configuration",
    "ACTIVE": "active",
    "DEGRADED": "degraded",
    "DISCONNECTED": "disconnected",
}
_HEALTH_STATUS_OUT = {
    "UNKNOWN": "unknown",
    "HEALTHY": "healthy",
    "DEGRADED": "degraded",
    "UNHEALTHY": "unavailable",
}
_RETRYABLE_OUTCOMES = frozenset({"timeout", "rate_limited", "unavailable"})
_CIRCUIT_FAILURE_OUTCOMES = frozenset({"timeout", "unavailable"})
_FAILURE_SUMMARIES = {
    "timeout": "The integration did not respond within the configured timeout",
    "rate_limited": "The integration rate limit has been reached",
    "unavailable": "The integration is temporarily unavailable",
    "invalid_request": "The normalized integration request was rejected",
}
_INTEGRATION_ENTITLEMENT_TIERS = frozenset(
    {"professional", "growth", "scale", "enterprise", "custom"}
)


def _json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _decode_object(value: str | None) -> dict[str, Any]:
    try:
        result = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return result if isinstance(result, dict) else {}


def _decode_list(value: str | None) -> list[str]:
    try:
        result = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(result, list):
        return []
    return sorted({str(item) for item in result if isinstance(item, str)})


def _request_sha256(payload: IntegrationSyncRunCreate) -> str:
    body = payload.model_dump(mode="json", exclude_none=False)
    return hashlib.sha256(_json(body).encode("utf-8")).hexdigest()


def _safe_failure(code: str, summary: str) -> tuple[str, str]:
    normalized_code = normalize_identifier(code, field="failure_code")[:80]
    return normalized_code, sanitize_integration_message(summary)[:500]


def integration_entitled(
    db: Session,
    *,
    organization_id: str,
    now: datetime | None = None,
) -> bool:
    """Return whether the organization has a current integration-capable tier."""

    organization = db.get(Company, organization_id)
    if organization is None or str(organization.status).casefold() not in {
        "active",
        "trial",
    }:
        return False
    entitlement = (
        db.query(CompanyEntitlement)
        .filter(CompanyEntitlement.company_id == organization_id)
        .one_or_none()
    )
    tier = (
        str(
            entitlement.tier
            if entitlement is not None
            else organization.subscription_plan
        )
        .strip()
        .casefold()
    )
    if tier not in _INTEGRATION_ENTITLEMENT_TIERS:
        return False
    if (
        entitlement is not None
        and entitlement.valid_until is not None
        and entitlement.valid_until < (now or utc_now())
    ):
        return False
    return True


def _event(
    db: Session,
    *,
    name: str,
    aggregate_type: str,
    aggregate_id: str,
    idempotency_key: str,
    organization_id: str,
    workspace_id: str | None,
    payload: dict[str, Any] | None = None,
    correlation_id: str | None = None,
) -> None:
    safe_payload: dict[str, Any] = {
        "organization_id": organization_id,
        "workspace_id": workspace_id,
        **(payload or {}),
    }
    enqueue_domain_event(
        db,
        name=name,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        payload=safe_payload,
    )


def _audit(
    db: Session,
    *,
    actor: User,
    action: str,
    resource_type: str,
    resource_id: str,
    organization_id: str,
    workspace_id: str | None,
    details: dict[str, Any] | None = None,
) -> None:
    record_audit_event(
        db,
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        organization_id=organization_id,
        workspace_id=workspace_id,
        details=details,
    )


def _workspace(
    db: Session,
    *,
    organization_id: str,
    workspace_id: str,
) -> Account:
    row = (
        db.query(Account)
        .filter(
            Account.id == workspace_id,
            Account.organization_id == organization_id,
            Account.status == "active",
        )
        .one_or_none()
    )
    if row is None:
        raise IntegrationRegistryError(
            "workspace_not_found",
            "Workspace is not accessible",
            status_code=404,
        )
    return row


def _member(
    db: Session,
    *,
    workspace_id: str,
    user_id: str,
) -> AccountMember:
    row = (
        db.query(AccountMember)
        .filter(
            AccountMember.account_id == workspace_id,
            AccountMember.user_id == user_id,
            AccountMember.status == "active",
        )
        .one_or_none()
    )
    if row is None:
        raise IntegrationRegistryError(
            "workspace_member_not_found",
            "Workspace member is not accessible",
            status_code=404,
        )
    return row


def _connection_query(
    db: Session,
    *,
    organization_id: str,
    active_workspace_id: str | None,
    actor_user_id: str,
):
    query = db.query(IntegrationConnection).filter(
        IntegrationConnection.organization_id == organization_id,
        or_(
            IntegrationConnection.user_id.is_(None),
            IntegrationConnection.user_id == actor_user_id,
        ),
    )
    if active_workspace_id:
        query = query.filter(
            or_(
                IntegrationConnection.workspace_id.is_(None),
                IntegrationConnection.workspace_id == active_workspace_id,
            )
        )
    else:
        query = query.filter(IntegrationConnection.workspace_id.is_(None))
    return query


def get_connection(
    db: Session,
    *,
    connection_id: str,
    organization_id: str,
    active_workspace_id: str | None,
    actor_user_id: str,
) -> IntegrationConnection:
    row = (
        _connection_query(
            db,
            organization_id=organization_id,
            active_workspace_id=active_workspace_id,
            actor_user_id=actor_user_id,
        )
        .filter(IntegrationConnection.id == connection_id)
        .one_or_none()
    )
    if row is None:
        raise IntegrationRegistryError(
            "integration_connection_not_found",
            "Integration connection is not accessible",
            status_code=404,
        )
    return row


def connection_out(row: IntegrationConnection) -> IntegrationConnectionOut:
    return IntegrationConnectionOut(
        id=row.id,
        organization_id=row.organization_id,
        workspace_id=row.workspace_id,
        member_user_id=row.user_id,
        connection_key=row.connection_key,
        provider_family=row.provider_family.lower(),
        provider_code=row.provider_code.lower(),
        display_name=row.display_name,
        status=_CONNECTION_STATUS_OUT.get(row.status, row.status.lower()),
        enabled=row.enabled,
        endpoint_configured=bool(row.endpoint_url),
        configuration_configured=bool(row.configuration_reference),
        credential_configured=bool(row.credential_reference),
        webhook_secret_configured=bool(row.webhook_secret_reference),
        capabilities=_decode_list(row.capabilities_json),
        last_sync_started_at=row.last_sync_started_at,
        last_sync_succeeded_at=row.last_sync_succeeded_at,
        last_sync_failed_at=row.last_sync_failed_at,
        last_error_code=row.last_error_code,
        last_error_summary=row.last_error_summary,
        health_status=_HEALTH_STATUS_OUT.get(
            row.health_status, row.health_status.lower()
        ),
        health_checked_at=row.health_checked_at,
        timeout_seconds=row.timeout_seconds,
        retry_max_attempts=row.retry_max_attempts,
        retry_base_seconds=row.retry_base_seconds,
        rate_limit_per_minute=row.rate_limit_per_minute,
        circuit_state=row.circuit_breaker_state.lower(),
        circuit_failure_threshold=row.circuit_breaker_failure_threshold,
        circuit_failure_count=row.circuit_breaker_failure_count,
        circuit_opened_at=row.circuit_breaker_opened_at,
        version=row.lifecycle_version,
        created_at=row.created_at,
        updated_at=row.updated_at,
        disconnected_at=row.disconnected_at,
    )


def sync_run_out(row: IntegrationSyncRun) -> IntegrationSyncRunOut:
    return IntegrationSyncRunOut(
        id=row.id,
        connection_id=row.connection_id,
        organization_id=row.organization_id,
        workspace_id=row.workspace_id,
        direction=row.direction.lower(),
        operation=row.operation,
        trigger=row.trigger_type.lower(),
        status=row.status.lower(),
        idempotency_key=row.idempotency_key,
        payload_sha256=row.payload_sha256,
        correlation_id=row.correlation_id,
        attempt_count=row.attempt_count,
        max_attempts=row.max_attempts,
        next_retry_at=row.next_retry_at,
        failure_code=row.failure_code,
        failure_summary=row.failure_summary,
        started_at=row.started_at,
        completed_at=row.finished_at,
        requested_by_user_id=row.requested_by_user_id,
        version=row.lifecycle_version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def sync_event_out(row: IntegrationSyncEvent) -> IntegrationSyncEventOut:
    return IntegrationSyncEventOut(
        id=row.id,
        sync_run_id=row.run_id,
        connection_id=row.connection_id,
        organization_id=row.organization_id,
        workspace_id=row.workspace_id,
        direction=row.direction.lower(),
        operation=row.operation,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        external_reference=row.external_reference,
        idempotency_key=row.idempotency_key,
        payload_sha256=row.payload_sha256,
        status=row.status.lower(),
        attempt_count=row.attempt_count,
        next_retry_at=row.next_retry_at,
        failure_code=row.failure_code,
        failure_summary=row.failure_summary,
        started_at=row.last_attempt_at,
        completed_at=row.processed_at,
        version=row.lifecycle_version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def flag_out(row: FeatureFlagOverride) -> FeatureFlagOverrideOut:
    return FeatureFlagOverrideOut(
        id=row.id,
        organization_id=row.organization_id,
        workspace_id=row.workspace_id,
        member_user_id=row.user_id,
        flag_key=row.flag_key,
        enabled=row.enabled,
        source=row.source.lower(),
        configuration_reference=row.configuration_reference,
        etag=row.etag,
        configuration_version=row.configuration_version,
        version=row.lifecycle_version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_connections(
    db: Session,
    *,
    organization_id: str,
    active_workspace_id: str | None,
    actor_user_id: str,
    provider_family: str | None = None,
    include_disconnected: bool = False,
) -> list[IntegrationConnection]:
    query = _connection_query(
        db,
        organization_id=organization_id,
        active_workspace_id=active_workspace_id,
        actor_user_id=actor_user_id,
    )
    if provider_family:
        query = query.filter(
            IntegrationConnection.provider_family == provider_family.strip().upper()
        )
    if not include_disconnected:
        query = query.filter(IntegrationConnection.status != "DISCONNECTED")
    return query.order_by(
        IntegrationConnection.created_at.asc(), IntegrationConnection.id.asc()
    ).all()


def create_connection(
    db: Session,
    *,
    payload: IntegrationConnectionCreate,
    actor: User,
    organization_id: str,
    active_workspace_id: str | None,
) -> IntegrationConnection:
    if payload.workspace_id:
        _workspace(
            db,
            organization_id=organization_id,
            workspace_id=payload.workspace_id,
        )
        if active_workspace_id and payload.workspace_id != active_workspace_id:
            raise IntegrationRegistryError(
                "workspace_not_found",
                "Workspace is not accessible",
                status_code=404,
            )
    if payload.member_user_id:
        if not payload.workspace_id:
            raise IntegrationRegistryError(
                "workspace_required",
                "A member-scoped connection requires a workspace",
            )
        _member(
            db,
            workspace_id=payload.workspace_id,
            user_id=payload.member_user_id,
        )
    existing = (
        db.query(IntegrationConnection.id)
        .filter(
            IntegrationConnection.organization_id == organization_id,
            IntegrationConnection.connection_key == payload.connection_key,
        )
        .first()
    )
    if existing is not None:
        raise IntegrationRegistryError(
            "connection_key_conflict",
            "The connection key is already in use",
            status_code=409,
        )
    row = IntegrationConnection(
        organization_id=organization_id,
        workspace_id=payload.workspace_id,
        user_id=payload.member_user_id,
        connection_key=payload.connection_key,
        provider_family=_enum_value(payload.provider_family).upper(),
        provider_code=payload.provider_code.upper(),
        display_name=payload.display_name,
        status="CONFIGURING",
        enabled=False,
        endpoint_url=payload.endpoint_url,
        configuration_reference=payload.configuration_reference,
        settings_json=payload.settings,
        credential_reference=payload.credential_reference,
        webhook_secret_reference=payload.webhook_secret_reference,
        capabilities_json=payload.capabilities,
        health_status="UNKNOWN",
        timeout_seconds=payload.timeout_seconds,
        retry_max_attempts=payload.retry_max_attempts,
        retry_base_seconds=payload.retry_base_seconds,
        rate_limit_per_minute=payload.rate_limit_per_minute,
        circuit_breaker_state="CLOSED",
        circuit_breaker_failure_threshold=payload.circuit_failure_threshold,
        circuit_breaker_failure_count=0,
        lifecycle_version=1,
        created_by_user_id=actor.id,
        updated_by_user_id=actor.id,
    )
    db.add(row)
    db.flush()
    _audit(
        db,
        actor=actor,
        action="integration.connection.created",
        resource_type="integration_connection",
        resource_id=row.id,
        organization_id=organization_id,
        workspace_id=row.workspace_id,
        details={
            "provider_family": row.provider_family,
            "provider_code": row.provider_code,
            "capabilities": _decode_list(row.capabilities_json),
            "credential_configured": bool(row.credential_reference),
            "configuration_configured": bool(row.configuration_reference),
        },
    )
    _event(
        db,
        name=EventNames.INTEGRATION_CONNECTION_CREATED,
        aggregate_type="integration_connection",
        aggregate_id=row.id,
        idempotency_key=f"integration-connection:{row.id}:created",
        organization_id=organization_id,
        workspace_id=row.workspace_id,
        payload={
            "connection_id": row.id,
            "provider_family": row.provider_family,
            "provider_code": row.provider_code,
            "lifecycle_version": row.lifecycle_version,
        },
    )
    return row


def update_connection(
    db: Session,
    *,
    row: IntegrationConnection,
    payload: IntegrationConnectionUpdate,
    actor: User,
) -> IntegrationConnection:
    if row.status == "DISCONNECTED":
        raise IntegrationRegistryError(
            "connection_disconnected",
            "A disconnected connection cannot be changed",
            status_code=409,
        )
    if row.lifecycle_version != payload.expected_version:
        raise IntegrationRegistryError(
            "connection_version_conflict",
            "The integration connection changed; refresh and retry",
            status_code=409,
        )
    changes = payload.model_dump(exclude_unset=True, exclude={"expected_version"})
    changed_fields: list[str] = []
    direct_fields = {
        "display_name",
        "endpoint_url",
        "configuration_reference",
        "credential_reference",
        "webhook_secret_reference",
        "timeout_seconds",
        "retry_max_attempts",
        "retry_base_seconds",
        "rate_limit_per_minute",
    }
    for field in direct_fields:
        if field in changes and getattr(row, field) != changes[field]:
            setattr(row, field, changes[field])
            changed_fields.append(field)
            if field == "rate_limit_per_minute":
                row.rate_limit_remaining = changes[field]
                row.rate_limit_reset_at = None
    if "settings" in changes:
        serialized = _json(changes["settings"] or {})
        if row.settings_json != serialized:
            row.settings_json = changes["settings"] or {}
            changed_fields.append("settings")
    if "capabilities" in changes:
        capabilities = sorted(set(changes["capabilities"] or []))
        if _decode_list(row.capabilities_json) != capabilities:
            row.capabilities_json = capabilities
            changed_fields.append("capabilities")
    if "circuit_failure_threshold" in changes:
        threshold = changes["circuit_failure_threshold"]
        if row.circuit_breaker_failure_threshold != threshold:
            row.circuit_breaker_failure_threshold = threshold
            changed_fields.append("circuit_failure_threshold")
    if not changed_fields:
        return row
    row.lifecycle_version += 1
    row.updated_by_user_id = actor.id
    _audit(
        db,
        actor=actor,
        action="integration.connection.updated",
        resource_type="integration_connection",
        resource_id=row.id,
        organization_id=row.organization_id,
        workspace_id=row.workspace_id,
        details={
            "changed_fields": sorted(changed_fields),
            "credential_configured": bool(row.credential_reference),
            "configuration_configured": bool(row.configuration_reference),
            "lifecycle_version": row.lifecycle_version,
        },
    )
    _event(
        db,
        name=EventNames.INTEGRATION_CONNECTION_UPDATED,
        aggregate_type="integration_connection",
        aggregate_id=row.id,
        idempotency_key=(
            f"integration-connection:{row.id}:updated:{row.lifecycle_version}"
        ),
        organization_id=row.organization_id,
        workspace_id=row.workspace_id,
        payload={
            "connection_id": row.id,
            "changed_fields": sorted(changed_fields),
            "lifecycle_version": row.lifecycle_version,
        },
    )
    return row


def set_connection_enabled(
    db: Session,
    *,
    row: IntegrationConnection,
    enabled: bool,
    expected_version: int,
    actor: User,
    reason: str | None = None,
) -> IntegrationConnection:
    if row.lifecycle_version != expected_version:
        raise IntegrationRegistryError(
            "connection_version_conflict",
            "The integration connection changed; refresh and retry",
            status_code=409,
        )
    if row.status == "DISCONNECTED":
        raise IntegrationRegistryError(
            "connection_disconnected",
            "A disconnected connection cannot be re-enabled",
            status_code=409,
        )
    if enabled:
        if row.provider_code != "FAKE":
            raise IntegrationRegistryError(
                "provider_not_approved",
                "Live provider connectivity has no approved sandbox and remains unavailable",
                status_code=409,
            )
        if settings.is_deployed:
            raise IntegrationRegistryError(
                "fixture_disabled",
                "Deterministic integration fixtures are disabled in deployed environments",
                status_code=409,
            )
        if not _decode_list(row.capabilities_json):
            raise IntegrationRegistryError(
                "capability_required",
                "At least one integration capability is required",
                status_code=409,
            )
        row.enabled = True
        row.status = "ACTIVE"
        row.health_status = "UNKNOWN"
        action = "enabled"
        event_name = EventNames.INTEGRATION_CONNECTION_ENABLED
    else:
        row.enabled = False
        row.status = "CONFIGURING"
        row.health_status = "UNKNOWN"
        row.circuit_breaker_state = "CLOSED"
        row.circuit_breaker_failure_count = 0
        row.circuit_breaker_opened_at = None
        action = "disabled"
        event_name = EventNames.INTEGRATION_CONNECTION_DISABLED
    row.lifecycle_version += 1
    row.updated_by_user_id = actor.id
    _audit(
        db,
        actor=actor,
        action=f"integration.connection.{action}",
        resource_type="integration_connection",
        resource_id=row.id,
        organization_id=row.organization_id,
        workspace_id=row.workspace_id,
        details={
            "reason": reason,
            "lifecycle_version": row.lifecycle_version,
        },
    )
    _event(
        db,
        name=event_name,
        aggregate_type="integration_connection",
        aggregate_id=row.id,
        idempotency_key=(
            f"integration-connection:{row.id}:{action}:{row.lifecycle_version}"
        ),
        organization_id=row.organization_id,
        workspace_id=row.workspace_id,
        payload={
            "connection_id": row.id,
            "lifecycle_version": row.lifecycle_version,
        },
    )
    return row


def disconnect_connection(
    db: Session,
    *,
    row: IntegrationConnection,
    expected_version: int,
    actor: User,
    reason: str | None = None,
) -> IntegrationConnection:
    if row.lifecycle_version != expected_version:
        raise IntegrationRegistryError(
            "connection_version_conflict",
            "The integration connection changed; refresh and retry",
            status_code=409,
        )
    if row.status == "DISCONNECTED":
        return row
    now = utc_now()
    row.enabled = False
    row.status = "DISCONNECTED"
    row.health_status = "UNKNOWN"
    row.health_checked_at = now
    row.credential_reference = None
    row.webhook_secret_reference = None
    row.circuit_breaker_state = "CLOSED"
    row.circuit_breaker_failure_count = 0
    row.circuit_breaker_opened_at = None
    row.rate_limit_remaining = None
    row.rate_limit_reset_at = None
    row.disconnected_at = now
    row.disconnected_by_user_id = actor.id
    row.updated_by_user_id = actor.id
    row.lifecycle_version += 1
    pending_runs = (
        db.query(IntegrationSyncRun)
        .filter(
            IntegrationSyncRun.connection_id == row.id,
            IntegrationSyncRun.organization_id == row.organization_id,
            IntegrationSyncRun.status.in_({"PENDING", "RUNNING", "RETRY_SCHEDULED"}),
        )
        .all()
    )
    for run in pending_runs:
        run.status = "CANCELLED"
        run.next_retry_at = None
        run.failure_code = None
        run.failure_summary = None
        run.finished_at = now
        run.lifecycle_version += 1
    pending_events = (
        db.query(IntegrationSyncEvent)
        .filter(
            IntegrationSyncEvent.connection_id == row.id,
            IntegrationSyncEvent.organization_id == row.organization_id,
            IntegrationSyncEvent.status.in_(
                {"PENDING", "PROCESSING", "RETRY_SCHEDULED"}
            ),
        )
        .all()
    )
    for sync_event in pending_events:
        sync_event.status = "SKIPPED"
        sync_event.next_retry_at = None
        sync_event.failure_code = None
        sync_event.failure_summary = None
        sync_event.processed_at = now
        sync_event.lifecycle_version += 1
    _audit(
        db,
        actor=actor,
        action="integration.connection.disconnected",
        resource_type="integration_connection",
        resource_id=row.id,
        organization_id=row.organization_id,
        workspace_id=row.workspace_id,
        details={
            "reason": reason,
            "credential_reference_revoked": True,
            "webhook_reference_revoked": True,
            "cancelled_sync_runs": len(pending_runs),
            "skipped_sync_events": len(pending_events),
            "lifecycle_version": row.lifecycle_version,
        },
    )
    _event(
        db,
        name=EventNames.INTEGRATION_CONNECTION_DISCONNECTED,
        aggregate_type="integration_connection",
        aggregate_id=row.id,
        idempotency_key=(
            f"integration-connection:{row.id}:disconnected:{row.lifecycle_version}"
        ),
        organization_id=row.organization_id,
        workspace_id=row.workspace_id,
        payload={
            "connection_id": row.id,
            "cancelled_sync_runs": len(pending_runs),
            "lifecycle_version": row.lifecycle_version,
        },
    )
    return row


def check_connection_health(
    db: Session,
    *,
    row: IntegrationConnection,
    actor: User,
) -> IntegrationHealthOut:
    now = utc_now()
    provider_available = False
    reason_code: str | None = None
    if row.status == "DISCONNECTED" or not row.enabled:
        row.health_status = "UNKNOWN"
        reason_code = "connection_disabled"
    elif row.circuit_breaker_state == "OPEN":
        row.health_status = "UNHEALTHY"
        row.status = "DEGRADED"
        reason_code = "circuit_open"
    elif row.provider_code == "FAKE" and not settings.is_deployed:
        row.health_status = "HEALTHY"
        row.status = "ACTIVE"
        provider_available = True
    else:
        row.health_status = "UNHEALTHY"
        row.status = "DEGRADED"
        reason_code = "provider_not_approved"
    row.health_checked_at = now
    _audit(
        db,
        actor=actor,
        action="integration.connection.health_checked",
        resource_type="integration_connection",
        resource_id=row.id,
        organization_id=row.organization_id,
        workspace_id=row.workspace_id,
        details={
            "health_status": row.health_status,
            "provider_available": provider_available,
            "reason_code": reason_code,
        },
    )
    return IntegrationHealthOut(
        connection_id=row.id,
        status=_CONNECTION_STATUS_OUT.get(row.status, row.status.lower()),
        health_status=_HEALTH_STATUS_OUT.get(
            row.health_status, row.health_status.lower()
        ),
        enabled=row.enabled,
        provider_available=provider_available,
        circuit_state=row.circuit_breaker_state.lower(),
        checked_at=now,
        reason_code=reason_code,
    )


def _flag_key(value: str) -> str:
    normalized = normalize_identifier(value, field="flag_key")
    if not any(normalized.startswith(prefix) for prefix in FEATURE_FLAG_PREFIXES):
        raise IntegrationRegistryError(
            "feature_flag_key_invalid",
            "Feature flag keys must use an integration or sector rollout namespace",
        )
    return normalized


def put_feature_flag_override(
    db: Session,
    *,
    flag_key: str,
    payload: FeatureFlagOverridePut,
    actor: User,
    organization_id: str,
    active_workspace_id: str | None,
) -> tuple[FeatureFlagOverride, bool]:
    normalized_key = _flag_key(flag_key)
    if active_workspace_id and payload.workspace_id != active_workspace_id:
        raise IntegrationRegistryError(
            "workspace_not_found",
            "Workspace is not accessible",
            status_code=404,
        )
    _workspace(
        db,
        organization_id=organization_id,
        workspace_id=payload.workspace_id,
    )
    if payload.member_user_id:
        _member(
            db,
            workspace_id=payload.workspace_id,
            user_id=payload.member_user_id,
        )
    query = db.query(FeatureFlagOverride).filter(
        FeatureFlagOverride.organization_id == organization_id,
        FeatureFlagOverride.workspace_id == payload.workspace_id,
        FeatureFlagOverride.flag_key == normalized_key,
    )
    if payload.member_user_id:
        query = query.filter(FeatureFlagOverride.user_id == payload.member_user_id)
    else:
        query = query.filter(FeatureFlagOverride.user_id.is_(None))
    source = (
        "AZURE_APP_CONFIGURATION"
        if payload.source in {"azure_app_configuration", "azure"}
        else "GEOVISION"
    )
    values = {
        "enabled": payload.enabled,
        "source": source,
        "configuration_reference": payload.configuration_reference,
        "etag": payload.etag,
        "configuration_version": payload.configuration_version,
        "updated_by_user_id": actor.id,
        "updated_at": utc_now(),
    }
    created = False
    if payload.expected_version is not None:
        updated = query.filter(
            FeatureFlagOverride.lifecycle_version == payload.expected_version
        ).update(
            {
                **values,
                "lifecycle_version": payload.expected_version + 1,
            },
            synchronize_session=False,
        )
        if updated != 1:
            row = query.populate_existing().one_or_none()
            if row is None:
                raise IntegrationRegistryError(
                    "feature_flag_version_conflict",
                    "The feature flag override does not exist",
                    status_code=409,
                )
            raise IntegrationRegistryError(
                "feature_flag_version_conflict",
                "The feature flag override changed; refresh and retry",
                status_code=409,
            )
        row = query.populate_existing().one()
    else:
        row = query.one_or_none()
        if row is not None:
            raise IntegrationRegistryError(
                "feature_flag_version_conflict",
                "The feature flag override changed; refresh and retry",
                status_code=409,
            )
        created = True
        row = FeatureFlagOverride(
            organization_id=organization_id,
            workspace_id=payload.workspace_id,
            user_id=payload.member_user_id,
            flag_key=normalized_key,
            enabled=payload.enabled,
            source=source,
            configuration_reference=payload.configuration_reference,
            etag=payload.etag,
            configuration_version=payload.configuration_version,
            lifecycle_version=1,
            created_by_user_id=actor.id,
            updated_by_user_id=actor.id,
        )
        db.add(row)
        db.flush()
    _audit(
        db,
        actor=actor,
        action=(
            "integration.feature_flag.created"
            if created
            else "integration.feature_flag.updated"
        ),
        resource_type="feature_flag_override",
        resource_id=row.id,
        organization_id=organization_id,
        workspace_id=row.workspace_id,
        details={
            "flag_key": row.flag_key,
            "scope": "member" if row.user_id else "workspace",
            "enabled": row.enabled,
            "source": row.source,
            "lifecycle_version": row.lifecycle_version,
        },
    )
    return row, created


def list_feature_flag_overrides(
    db: Session,
    *,
    organization_id: str,
    active_workspace_id: str | None,
    workspace_id: str | None = None,
) -> list[FeatureFlagOverride]:
    selected_workspace = workspace_id or active_workspace_id
    if not selected_workspace:
        return []
    if active_workspace_id and selected_workspace != active_workspace_id:
        raise IntegrationRegistryError(
            "workspace_not_found",
            "Workspace is not accessible",
            status_code=404,
        )
    _workspace(
        db,
        organization_id=organization_id,
        workspace_id=selected_workspace,
    )
    return (
        db.query(FeatureFlagOverride)
        .filter(
            FeatureFlagOverride.organization_id == organization_id,
            FeatureFlagOverride.workspace_id == selected_workspace,
        )
        .order_by(
            FeatureFlagOverride.flag_key.asc(),
            FeatureFlagOverride.user_id.asc(),
            FeatureFlagOverride.id.asc(),
        )
        .all()
    )


def resolve_feature_flag(
    db: Session,
    *,
    flag_key: str,
    organization_id: str,
    workspace_id: str,
    member_user_id: str | None,
    authorized: bool,
    entitled: bool,
    evaluator: FeatureFlagEvaluator | None = None,
) -> FeatureFlagResolutionOut:
    normalized_key = _flag_key(flag_key)
    _workspace(
        db,
        organization_id=organization_id,
        workspace_id=workspace_id,
    )
    if not authorized or not entitled:
        return FeatureFlagResolutionOut(
            flag_key=normalized_key,
            enabled=False,
            source="access_gate",
            scope="default",
            workspace_id=workspace_id,
            member_user_id=member_user_id,
        )
    if member_user_id:
        _member(db, workspace_id=workspace_id, user_id=member_user_id)
        row = (
            db.query(FeatureFlagOverride)
            .filter(
                FeatureFlagOverride.organization_id == organization_id,
                FeatureFlagOverride.workspace_id == workspace_id,
                FeatureFlagOverride.user_id == member_user_id,
                FeatureFlagOverride.flag_key == normalized_key,
            )
            .one_or_none()
        )
        if row is not None:
            return FeatureFlagResolutionOut(
                flag_key=normalized_key,
                enabled=row.enabled,
                source=row.source.lower(),
                scope="member",
                workspace_id=workspace_id,
                member_user_id=member_user_id,
            )
    row = (
        db.query(FeatureFlagOverride)
        .filter(
            FeatureFlagOverride.organization_id == organization_id,
            FeatureFlagOverride.workspace_id == workspace_id,
            FeatureFlagOverride.user_id.is_(None),
            FeatureFlagOverride.flag_key == normalized_key,
        )
        .one_or_none()
    )
    if row is not None:
        return FeatureFlagResolutionOut(
            flag_key=normalized_key,
            enabled=row.enabled,
            source=row.source.lower(),
            scope="workspace",
            workspace_id=workspace_id,
            member_user_id=member_user_id,
        )
    try:
        target = FeatureFlagTarget(
            organization_id=UUID(organization_id),
            workspace_id=UUID(workspace_id),
            user_id=UUID(member_user_id) if member_user_id else None,
        )
        if evaluator is None:
            enabled = False
            source = "fail_closed"
        else:
            enabled = evaluator.allows_rollout(
                normalized_key,
                target=target,
                authorized=authorized,
                entitled=entitled,
            )
            health = evaluator.health()
            source = "azure_app_configuration" if health.available else "fail_closed"
    except (TypeError, ValueError):
        enabled = False
        source = "fail_closed"
    return FeatureFlagResolutionOut(
        flag_key=normalized_key,
        enabled=enabled,
        source=source,
        scope="default",
        workspace_id=workspace_id,
        member_user_id=member_user_id,
    )


def delete_feature_flag_override(
    db: Session,
    *,
    override_id: str,
    expected_version: int,
    actor: User,
    organization_id: str,
    active_workspace_id: str | None,
) -> None:
    query = db.query(FeatureFlagOverride).filter(
        FeatureFlagOverride.id == override_id,
        FeatureFlagOverride.organization_id == organization_id,
    )
    if active_workspace_id:
        query = query.filter(FeatureFlagOverride.workspace_id == active_workspace_id)
    row = query.one_or_none()
    if row is None:
        raise IntegrationRegistryError(
            "feature_flag_override_not_found",
            "Feature flag override is not accessible",
            status_code=404,
        )
    deleted = query.filter(
        FeatureFlagOverride.lifecycle_version == expected_version
    ).delete(synchronize_session=False)
    if deleted != 1:
        raise IntegrationRegistryError(
            "feature_flag_version_conflict",
            "The feature flag override changed; refresh and retry",
            status_code=409,
        )
    _audit(
        db,
        actor=actor,
        action="integration.feature_flag.deleted",
        resource_type="feature_flag_override",
        resource_id=row.id,
        organization_id=organization_id,
        workspace_id=row.workspace_id,
        details={
            "flag_key": row.flag_key,
            "scope": "member" if row.user_id else "workspace",
        },
    )


def _retry_delay_seconds(
    *, attempt_count: int, base_seconds: int, retry_after_seconds: int | None
) -> int:
    exponential = min(base_seconds * (2 ** max(attempt_count - 1, 0)), 86_400)
    if retry_after_seconds is None:
        return exponential
    return min(max(exponential, retry_after_seconds), 86_400)


def _integration_flag(row: IntegrationConnection) -> str:
    return (
        f"geovision.integrations.{row.provider_family.lower()}."
        f"{row.provider_code.lower()}"
    )


def _sync_workspace_id(
    row: IntegrationConnection,
    *,
    active_workspace_id: str | None,
) -> str:
    if row.workspace_id:
        if active_workspace_id and row.workspace_id != active_workspace_id:
            raise IntegrationRegistryError(
                "integration_connection_not_found",
                "Integration connection is not accessible",
                status_code=404,
            )
        return row.workspace_id
    if active_workspace_id:
        return active_workspace_id
    raise IntegrationRegistryError(
        "workspace_required",
        "Integration synchronization requires an active workspace",
        status_code=409,
    )


def _lock_sync_connection(
    db: Session,
    *,
    row: IntegrationConnection,
) -> IntegrationConnection:
    """Serialize mutable rate-limit and circuit transitions on PostgreSQL."""

    locked = (
        db.query(IntegrationConnection)
        .filter(
            IntegrationConnection.id == row.id,
            IntegrationConnection.organization_id == row.organization_id,
        )
        .populate_existing()
        .with_for_update()
        .one_or_none()
    )
    if locked is None:
        raise IntegrationRegistryError(
            "integration_connection_not_found",
            "Integration connection is not accessible",
            status_code=404,
        )
    return locked


def _assert_operation_allowed(
    row: IntegrationConnection,
    *,
    direction: object,
    operation: str,
) -> None:
    try:
        required_capability = required_sync_capability(
            row.provider_family,
            direction,
            operation,
        )
    except ValueError as exc:
        raise IntegrationRegistryError(
            "sync_operation_not_supported",
            "The sync operation and direction are not registered for this provider family",
            status_code=422,
        ) from exc
    if required_capability not in _decode_list(row.capabilities_json):
        raise IntegrationRegistryError(
            "integration_capability_missing",
            "The integration connection does not grant the capability required by this sync",
            status_code=403,
        )


def _assert_sync_allowed(
    db: Session,
    *,
    row: IntegrationConnection,
    actor: User,
    active_workspace_id: str | None,
    now: datetime,
    feature_flag_evaluator: FeatureFlagEvaluator | None,
) -> str:
    if (
        row.status == "DISCONNECTED"
        or not row.enabled
        or row.status
        not in {
            "ACTIVE",
            "DEGRADED",
        }
    ):
        raise IntegrationRegistryError(
            "connection_disabled",
            "The integration connection is not enabled",
            status_code=409,
        )
    workspace_id = _sync_workspace_id(
        row,
        active_workspace_id=active_workspace_id,
    )
    resolution = resolve_feature_flag(
        db,
        flag_key=_integration_flag(row),
        organization_id=row.organization_id,
        workspace_id=workspace_id,
        member_user_id=actor.id,
        authorized=True,
        entitled=integration_entitled(
            db,
            organization_id=row.organization_id,
            now=now,
        ),
        evaluator=feature_flag_evaluator,
    )
    if not resolution.enabled:
        raise IntegrationRegistryError(
            "integration_feature_disabled",
            "The integration rollout flag is disabled for this workspace member",
            status_code=409,
        )
    if row.rate_limit_reset_at:
        if row.rate_limit_reset_at > now:
            raise IntegrationRegistryError(
                "integration_rate_limited",
                "The integration rate limit has not reset",
                status_code=429,
            )
        row.rate_limit_remaining = row.rate_limit_per_minute
        row.rate_limit_reset_at = None
    if row.circuit_breaker_state == "HALF_OPEN":
        raise IntegrationRegistryError(
            "integration_circuit_half_open",
            "The integration circuit already has a recovery probe in progress",
            status_code=503,
        )
    if row.circuit_breaker_state == "OPEN":
        cooldown = min(
            row.retry_base_seconds
            * (2 ** max(row.circuit_breaker_failure_threshold - 1, 0)),
            3_600,
        )
        if row.circuit_breaker_opened_at and (
            row.circuit_breaker_opened_at + timedelta(seconds=cooldown) > now
        ):
            raise IntegrationRegistryError(
                "integration_circuit_open",
                "The integration circuit is open",
                status_code=503,
            )
        row.circuit_breaker_state = "HALF_OPEN"
    return workspace_id


def _apply_outcome(
    db: Session,
    *,
    connection: IntegrationConnection,
    run: IntegrationSyncRun,
    sync_event: IntegrationSyncEvent,
    outcome: str,
    retry_after_seconds: int | None,
    now: datetime,
) -> None:
    previous_circuit = connection.circuit_breaker_state
    run.attempt_count += 1
    run.last_attempt_at = now
    sync_event.attempt_count += 1
    sync_event.last_attempt_at = now
    connection.last_sync_started_at = now
    if outcome == "success":
        run.status = "SUCCEEDED"
        run.failure_code = None
        run.failure_summary = None
        run.next_retry_at = None
        run.finished_at = now
        sync_event.status = "SUCCEEDED"
        sync_event.failure_code = None
        sync_event.failure_summary = None
        sync_event.next_retry_at = None
        sync_event.processed_at = now
        if not sync_event.external_reference:
            sync_event.external_reference = "fixture-" + str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"geovision:{connection.id}:{sync_event.idempotency_key}",
                )
            )
        connection.status = "ACTIVE"
        connection.health_status = "HEALTHY"
        connection.health_checked_at = now
        connection.last_sync_succeeded_at = now
        connection.last_error_at = None
        connection.last_error_code = None
        connection.last_error_summary = None
        connection.circuit_breaker_state = "CLOSED"
        connection.circuit_breaker_failure_count = 0
        connection.circuit_breaker_opened_at = None
        if previous_circuit in {"OPEN", "HALF_OPEN"}:
            _event(
                db,
                name=EventNames.INTEGRATION_CIRCUIT_CLOSED,
                aggregate_type="integration_connection",
                aggregate_id=connection.id,
                idempotency_key=(
                    f"integration-connection:{connection.id}:circuit-closed:"
                    f"{run.id}:{run.attempt_count}"
                ),
                organization_id=connection.organization_id,
                workspace_id=run.workspace_id,
                payload={"connection_id": connection.id, "sync_run_id": run.id},
                correlation_id=run.correlation_id,
            )
        terminal_event = EventNames.INTEGRATION_SYNC_SUCCEEDED
    else:
        code, summary = _safe_failure(
            outcome, _FAILURE_SUMMARIES.get(outcome, "The integration sync failed")
        )
        retryable = outcome in _RETRYABLE_OUTCOMES
        connection.last_sync_failed_at = now
        connection.last_error_at = now
        connection.last_error_code = code
        connection.last_error_summary = summary
        connection.health_checked_at = now
        connection.status = "DEGRADED"
        if retryable:
            connection.health_status = "DEGRADED"
        if outcome in _CIRCUIT_FAILURE_OUTCOMES:
            connection.circuit_breaker_failure_count += 1
        if retryable and run.attempt_count < run.max_attempts:
            delay = _retry_delay_seconds(
                attempt_count=run.attempt_count,
                base_seconds=connection.retry_base_seconds,
                retry_after_seconds=retry_after_seconds,
            )
            retry_at = now + timedelta(seconds=delay)
            run.status = "RETRY_SCHEDULED"
            run.failure_code = code
            run.failure_summary = summary
            run.next_retry_at = retry_at
            sync_event.status = "RETRY_SCHEDULED"
            sync_event.failure_code = code
            sync_event.failure_summary = summary
            sync_event.next_retry_at = retry_at
            terminal_event = EventNames.INTEGRATION_RETRY_SCHEDULED
        elif retryable:
            run.status = "DEAD_LETTERED"
            run.failure_code = code
            run.failure_summary = summary
            run.next_retry_at = None
            run.finished_at = now
            sync_event.status = "DEAD_LETTERED"
            sync_event.failure_code = code
            sync_event.failure_summary = summary
            sync_event.next_retry_at = None
            sync_event.processed_at = now
            connection.health_status = "UNHEALTHY"
            terminal_event = EventNames.INTEGRATION_DEAD_LETTERED
        else:
            run.status = "FAILED"
            run.failure_code = code
            run.failure_summary = summary
            run.next_retry_at = None
            run.finished_at = now
            sync_event.status = "FAILED"
            sync_event.failure_code = code
            sync_event.failure_summary = summary
            sync_event.next_retry_at = None
            sync_event.processed_at = now
            terminal_event = EventNames.INTEGRATION_SYNC_FAILED
        if (
            outcome in _CIRCUIT_FAILURE_OUTCOMES
            and connection.circuit_breaker_failure_count
            >= connection.circuit_breaker_failure_threshold
        ):
            connection.circuit_breaker_state = "OPEN"
            connection.circuit_breaker_opened_at = now
            connection.health_status = "UNHEALTHY"
            _event(
                db,
                name=EventNames.INTEGRATION_CIRCUIT_OPENED,
                aggregate_type="integration_connection",
                aggregate_id=connection.id,
                idempotency_key=(
                    f"integration-connection:{connection.id}:circuit-opened:"
                    f"{run.id}:{run.attempt_count}"
                ),
                organization_id=connection.organization_id,
                workspace_id=run.workspace_id,
                payload={
                    "connection_id": connection.id,
                    "sync_run_id": run.id,
                    "failure_code": code,
                },
                correlation_id=run.correlation_id,
            )
        elif previous_circuit == "HALF_OPEN":
            # A non-transport response proves that the provider is reachable.
            # Rate limiting remains enforced independently by its persisted
            # reset timestamp below.
            connection.circuit_breaker_state = "CLOSED"
            connection.circuit_breaker_failure_count = 0
            connection.circuit_breaker_opened_at = None
            _event(
                db,
                name=EventNames.INTEGRATION_CIRCUIT_CLOSED,
                aggregate_type="integration_connection",
                aggregate_id=connection.id,
                idempotency_key=(
                    f"integration-connection:{connection.id}:circuit-closed:"
                    f"{run.id}:{run.attempt_count}"
                ),
                organization_id=connection.organization_id,
                workspace_id=run.workspace_id,
                payload={"connection_id": connection.id, "sync_run_id": run.id},
                correlation_id=run.correlation_id,
            )
    if outcome == "rate_limited":
        delay = _retry_delay_seconds(
            attempt_count=run.attempt_count,
            base_seconds=connection.retry_base_seconds,
            retry_after_seconds=retry_after_seconds,
        )
        connection.rate_limit_remaining = 0
        connection.rate_limit_reset_at = now + timedelta(seconds=delay)
    elif connection.rate_limit_per_minute is not None:
        if connection.rate_limit_remaining is None:
            connection.rate_limit_remaining = connection.rate_limit_per_minute
        connection.rate_limit_remaining = max(connection.rate_limit_remaining - 1, 0)
        if connection.rate_limit_remaining == 0:
            connection.rate_limit_reset_at = now + timedelta(minutes=1)
    run.lifecycle_version += 1
    sync_event.lifecycle_version += 1
    _event(
        db,
        name=terminal_event,
        aggregate_type="integration_sync_run",
        aggregate_id=run.id,
        idempotency_key=(
            f"integration-sync:{run.id}:{run.attempt_count}:{run.status.lower()}"
        ),
        organization_id=run.organization_id,
        workspace_id=run.workspace_id,
        payload={
            "connection_id": connection.id,
            "sync_run_id": run.id,
            "direction": run.direction,
            "operation": run.operation,
            "status": run.status,
            "attempt_count": run.attempt_count,
            "failure_code": run.failure_code,
        },
        correlation_id=run.correlation_id,
    )


def request_sync_run(
    db: Session,
    *,
    connection: IntegrationConnection,
    payload: IntegrationSyncRunCreate,
    actor: User,
    active_workspace_id: str | None,
    feature_flag_evaluator: FeatureFlagEvaluator | None,
) -> tuple[IntegrationSyncRun, bool]:
    connection = _lock_sync_connection(db, row=connection)
    workspace_id = _sync_workspace_id(
        connection,
        active_workspace_id=active_workspace_id,
    )
    request_hash = _request_sha256(payload)
    existing = (
        db.query(IntegrationSyncRun)
        .filter(
            IntegrationSyncRun.connection_id == connection.id,
            IntegrationSyncRun.organization_id == connection.organization_id,
            IntegrationSyncRun.workspace_id == workspace_id,
            IntegrationSyncRun.idempotency_key == payload.idempotency_key,
        )
        .one_or_none()
    )
    if existing is not None:
        if existing.payload_sha256 != request_hash:
            raise IntegrationRegistryError(
                "sync_idempotency_conflict",
                "The idempotency key is already bound to a different request",
                status_code=409,
            )
        return existing, False
    now = utc_now()
    allowed_workspace_id = _assert_sync_allowed(
        db,
        row=connection,
        actor=actor,
        active_workspace_id=active_workspace_id,
        now=now,
        feature_flag_evaluator=feature_flag_evaluator,
    )
    if allowed_workspace_id != workspace_id:
        raise IntegrationRegistryError(
            "workspace_not_found",
            "Workspace is not accessible",
            status_code=404,
        )
    _assert_operation_allowed(
        connection,
        direction=payload.direction,
        operation=payload.operation,
    )
    if connection.provider_code != "FAKE" or settings.is_deployed:
        raise IntegrationRegistryError(
            "provider_not_approved",
            "No approved live provider environment is available",
            status_code=409,
        )
    correlation_id = payload.correlation_id or str(uuid.uuid4())
    run = IntegrationSyncRun(
        connection_id=connection.id,
        organization_id=connection.organization_id,
        workspace_id=workspace_id,
        direction=_enum_value(payload.direction).upper(),
        operation=payload.operation,
        trigger_type=_enum_value(payload.trigger).upper(),
        status="PENDING",
        idempotency_key=payload.idempotency_key,
        payload_sha256=request_hash,
        correlation_id=correlation_id,
        attempt_count=0,
        max_attempts=connection.retry_max_attempts,
        requested_by_user_id=actor.id,
        lifecycle_version=1,
    )
    db.add(run)
    db.flush()
    raw_resource_type = payload.payload.get("resource_type")
    raw_resource_id = payload.payload.get("resource_id")
    resource_type = (
        normalize_identifier(str(raw_resource_type), field="resource_type")
        if raw_resource_type is not None and raw_resource_id is not None
        else None
    )
    resource_id = (
        str(raw_resource_id).strip()[:160]
        if resource_type is not None and str(raw_resource_id).strip()
        else None
    )
    if resource_type is not None and resource_id is None:
        raise IntegrationRegistryError(
            "sync_resource_invalid",
            "resource_type and resource_id must be supplied together",
        )
    sync_event = IntegrationSyncEvent(
        run_id=run.id,
        connection_id=connection.id,
        organization_id=connection.organization_id,
        workspace_id=workspace_id,
        direction=run.direction,
        operation=run.operation,
        resource_type=resource_type,
        resource_id=resource_id,
        idempotency_key=f"{payload.idempotency_key}:event",
        payload_sha256=request_hash,
        status="PROCESSING",
        attempt_count=0,
        max_attempts=run.max_attempts,
        occurred_at=now,
        lifecycle_version=1,
    )
    db.add(sync_event)
    db.flush()
    run.status = "RUNNING"
    run.started_at = now
    run.lifecycle_version += 1
    _audit(
        db,
        actor=actor,
        action="integration.sync.requested",
        resource_type="integration_sync_run",
        resource_id=run.id,
        organization_id=run.organization_id,
        workspace_id=run.workspace_id,
        details={
            "connection_id": connection.id,
            "direction": run.direction,
            "operation": run.operation,
            "trigger": run.trigger_type,
            "payload_sha256": run.payload_sha256,
        },
    )
    _event(
        db,
        name=EventNames.INTEGRATION_SYNC_REQUESTED,
        aggregate_type="integration_sync_run",
        aggregate_id=run.id,
        idempotency_key=f"integration-sync:{run.id}:requested",
        organization_id=run.organization_id,
        workspace_id=run.workspace_id,
        payload={
            "connection_id": connection.id,
            "sync_run_id": run.id,
            "direction": run.direction,
            "operation": run.operation,
        },
        correlation_id=correlation_id,
    )
    _event(
        db,
        name=EventNames.INTEGRATION_SYNC_STARTED,
        aggregate_type="integration_sync_run",
        aggregate_id=run.id,
        idempotency_key=f"integration-sync:{run.id}:started:1",
        organization_id=run.organization_id,
        workspace_id=run.workspace_id,
        payload={
            "connection_id": connection.id,
            "sync_run_id": run.id,
            "direction": run.direction,
            "operation": run.operation,
        },
        correlation_id=correlation_id,
    )
    outcome = _enum_value(payload.simulation_outcome or "success")
    _apply_outcome(
        db,
        connection=connection,
        run=run,
        sync_event=sync_event,
        outcome=outcome,
        retry_after_seconds=payload.retry_after_seconds,
        now=now,
    )
    return run, True


def retry_sync_run(
    db: Session,
    *,
    connection: IntegrationConnection,
    run_id: str,
    payload: IntegrationSyncRetryRequest,
    actor: User,
    active_workspace_id: str | None,
    feature_flag_evaluator: FeatureFlagEvaluator | None,
) -> IntegrationSyncRun:
    connection = _lock_sync_connection(db, row=connection)
    workspace_id = _sync_workspace_id(
        connection,
        active_workspace_id=active_workspace_id,
    )
    run = (
        db.query(IntegrationSyncRun)
        .filter(
            IntegrationSyncRun.id == run_id,
            IntegrationSyncRun.connection_id == connection.id,
            IntegrationSyncRun.organization_id == connection.organization_id,
            IntegrationSyncRun.workspace_id == workspace_id,
        )
        .one_or_none()
    )
    if run is None:
        raise IntegrationRegistryError(
            "sync_run_not_found",
            "Integration sync run is not accessible",
            status_code=404,
        )
    if run.lifecycle_version != payload.expected_version:
        raise IntegrationRegistryError(
            "sync_run_version_conflict",
            "The sync run changed; refresh and retry",
            status_code=409,
        )
    now = utc_now()
    if run.status != "RETRY_SCHEDULED":
        raise IntegrationRegistryError(
            "sync_run_not_retryable",
            "The sync run is not awaiting a retry",
            status_code=409,
        )
    if run.next_retry_at and run.next_retry_at > now:
        raise IntegrationRegistryError(
            "sync_retry_not_due",
            "The integration retry is not due yet",
            status_code=409,
        )
    _assert_sync_allowed(
        db,
        row=connection,
        actor=actor,
        active_workspace_id=active_workspace_id,
        now=now,
        feature_flag_evaluator=feature_flag_evaluator,
    )
    _assert_operation_allowed(
        connection,
        direction=run.direction,
        operation=run.operation,
    )
    sync_event = (
        db.query(IntegrationSyncEvent)
        .filter(
            IntegrationSyncEvent.run_id == run.id,
            IntegrationSyncEvent.connection_id == connection.id,
            IntegrationSyncEvent.organization_id == connection.organization_id,
            IntegrationSyncEvent.workspace_id == workspace_id,
        )
        .one()
    )
    run.status = "RUNNING"
    run.next_retry_at = None
    sync_event.status = "PROCESSING"
    sync_event.next_retry_at = None
    _apply_outcome(
        db,
        connection=connection,
        run=run,
        sync_event=sync_event,
        outcome=_enum_value(payload.simulation_outcome),
        retry_after_seconds=payload.retry_after_seconds,
        now=now,
    )
    _audit(
        db,
        actor=actor,
        action="integration.sync.retried",
        resource_type="integration_sync_run",
        resource_id=run.id,
        organization_id=run.organization_id,
        workspace_id=run.workspace_id,
        details={
            "connection_id": connection.id,
            "attempt_count": run.attempt_count,
            "status": run.status,
            "failure_code": run.failure_code,
        },
    )
    return run


def list_sync_runs(
    db: Session,
    *,
    connection: IntegrationConnection,
    active_workspace_id: str | None,
    limit: int = 100,
) -> list[IntegrationSyncRun]:
    workspace_id = _sync_workspace_id(
        connection,
        active_workspace_id=active_workspace_id,
    )
    return (
        db.query(IntegrationSyncRun)
        .filter(
            IntegrationSyncRun.connection_id == connection.id,
            IntegrationSyncRun.organization_id == connection.organization_id,
            IntegrationSyncRun.workspace_id == workspace_id,
        )
        .order_by(IntegrationSyncRun.created_at.desc(), IntegrationSyncRun.id.desc())
        .limit(limit)
        .all()
    )


def list_sync_events(
    db: Session,
    *,
    connection: IntegrationConnection,
    active_workspace_id: str | None,
    run_id: str | None = None,
    limit: int = 200,
) -> list[IntegrationSyncEvent]:
    workspace_id = _sync_workspace_id(
        connection,
        active_workspace_id=active_workspace_id,
    )
    query = db.query(IntegrationSyncEvent).filter(
        IntegrationSyncEvent.connection_id == connection.id,
        IntegrationSyncEvent.organization_id == connection.organization_id,
        IntegrationSyncEvent.workspace_id == workspace_id,
    )
    if run_id:
        belongs = (
            db.query(IntegrationSyncRun.id)
            .filter(
                IntegrationSyncRun.id == run_id,
                IntegrationSyncRun.connection_id == connection.id,
                IntegrationSyncRun.organization_id == connection.organization_id,
                IntegrationSyncRun.workspace_id == workspace_id,
            )
            .first()
        )
        if belongs is None:
            raise IntegrationRegistryError(
                "sync_run_not_found",
                "Integration sync run is not accessible",
                status_code=404,
            )
        query = query.filter(IntegrationSyncEvent.run_id == run_id)
    return (
        query.order_by(
            IntegrationSyncEvent.created_at.desc(), IntegrationSyncEvent.id.desc()
        )
        .limit(limit)
        .all()
    )


__all__ = [
    "check_connection_health",
    "connection_out",
    "create_connection",
    "delete_feature_flag_override",
    "disconnect_connection",
    "flag_out",
    "get_connection",
    "list_connections",
    "list_feature_flag_overrides",
    "list_sync_events",
    "list_sync_runs",
    "put_feature_flag_override",
    "request_sync_run",
    "resolve_feature_flag",
    "retry_sync_run",
    "set_connection_enabled",
    "sync_event_out",
    "sync_run_out",
    "update_connection",
]
