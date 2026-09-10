"""Idempotent event-to-notification materialization and rate aggregation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.encryption import encrypt
from app.core.event_names import EventNames
from app.core.events import DomainEvent
from app.core.time import utc_now
from app.models import (
    AccountMember,
    Action,
    Asset,
    AuditLog,
    Company,
    CompanyUser,
    FulfilmentJob,
    Invitation,
    IotAlert,
    IotDevice,
    Notification,
    NotificationDelivery,
    NotificationEndpoint,
    NotificationEventLink,
    Order,
    Report,
    User,
)
from app.modules.organizations.domain import MembershipStatus
from app.services.event_outbox import enqueue_domain_event

from .domain import NotificationSeverity, severity_allows
from .inbox import effective_preference


AGGREGATION_WINDOW = timedelta(minutes=15)


@dataclass(frozen=True, slots=True)
class NotificationIntent:
    organization_id: str
    workspace_id: str | None
    category: str
    notification_type: str
    title: str
    body: str
    severity: str
    target_type: str
    target_id: str | None
    aggregation_key: str | None = None
    preferred_recipient_user_id: str | None = None
    fallback_to_scope: bool = False


@dataclass(frozen=True, slots=True)
class MaterializationResult:
    notification_ids: tuple[str, ...]
    created: int = 0
    aggregated: int = 0
    suppressed: int = 0


def _email_provider(config: Settings = settings) -> str:
    selected = str(config.notification_provider or "auto").strip().lower()
    if selected == "auto":
        if config.smtp_configuration_complete:
            return "smtp"
        return "file" if not config.is_deployed else "disabled"
    if selected in {"file", "log", "local_file"}:
        return "file"
    if selected == "smtp":
        return "smtp"
    if selected in {"none", "disabled", "null"}:
        return "disabled"
    return "disabled"


def _severity(value: str | None) -> str:
    normalized = str(value or "INFO").strip().upper()
    aliases = {"LOW": "INFO", "MEDIUM": "WATCH", "HIGH": "WARNING", "URGENT": "CRITICAL"}
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in {item.value for item in NotificationSeverity} else "INFO"


def _recipients(
    db: Session,
    *,
    organization_id: str,
    workspace_id: str | None,
    preferred_user_id: str | None,
) -> list[User]:
    query = (
        db.query(User)
        .join(
            CompanyUser,
            (CompanyUser.user_id == User.id)
            & (CompanyUser.company_id == organization_id),
        )
        .filter(
            User.is_active.is_(True),
            CompanyUser.is_active.is_(True),
            CompanyUser.status == MembershipStatus.ACTIVE.value,
        )
    )
    if workspace_id:
        query = query.join(
            AccountMember,
            (AccountMember.user_id == User.id)
            & (AccountMember.account_id == workspace_id),
        ).filter(AccountMember.status == MembershipStatus.ACTIVE.value)
    if preferred_user_id:
        query = query.filter(User.id == preferred_user_id)
    return query.order_by(User.id.asc()).distinct().all()


def _intent_from_event(db: Session, event: DomainEvent) -> NotificationIntent | None:
    payload = dict(event.payload)
    if event.name == EventNames.REPORT_PUBLISHED:
        report = db.get(Report, str(payload.get("report_id") or event.aggregate_id))
        if report is None or report.status != "PUBLISHED":
            return None
        return NotificationIntent(
            organization_id=report.organization_id,
            workspace_id=report.workspace_id,
            category="REPORT",
            notification_type="report.results_ready",
            title="Your results are ready",
            body=f"GeoVision published {report.title}.",
            severity="INFO",
            target_type="REPORT",
            target_id=report.id,
        )
    if event.name == EventNames.ACTION_REQUESTED:
        action = db.get(Action, str(payload.get("action_id") or event.aggregate_id))
        if action is None or action.status not in {"OPEN", "IN_PROGRESS"}:
            return None
        return NotificationIntent(
            organization_id=action.organization_id,
            workspace_id=action.workspace_id,
            category="ACTION",
            notification_type="action.review_requested",
            title=action.title,
            body="A GeoVision action is ready for review.",
            severity=_severity(action.priority),
            target_type="ACTION",
            target_id=action.id,
            aggregation_key=f"action:{action.id}:open",
            preferred_recipient_user_id=action.assigned_to_user_id,
            fallback_to_scope=True,
        )
    if event.name == EventNames.DEVICE_OFFLINE_DETECTED:
        device = db.get(IotDevice, str(payload.get("device_id") or event.aggregate_id))
        if device is None:
            return None
        asset = db.get(Asset, device.core_asset_id) if device.core_asset_id else None
        return NotificationIntent(
            organization_id=device.company_id,
            workspace_id=asset.workspace_id if asset else None,
            category="DEVICE",
            notification_type="device.offline",
            title="Device offline",
            body="A field device stopped reporting. Open the asset to review its status.",
            severity="WARNING",
            target_type="ASSET" if asset else "NONE",
            target_id=asset.id if asset else None,
            aggregation_key=f"device:{device.id}:offline",
        )
    if event.name == EventNames.DEVICE_ALERT_TRIGGERED:
        alert = db.get(IotAlert, str(payload.get("alert_id") or event.aggregate_id))
        device = db.get(IotDevice, alert.device_id) if alert else None
        asset = db.get(Asset, device.core_asset_id) if device and device.core_asset_id else None
        if alert is None or device is None:
            return None
        return NotificationIntent(
            organization_id=alert.company_id,
            workspace_id=asset.workspace_id if asset else None,
            category="DEVICE",
            notification_type="device.alert_triggered",
            title="Critical field alert" if _severity(alert.severity) == "CRITICAL" else "Field alert",
            body=alert.message[:500],
            severity=_severity(alert.severity),
            target_type="ASSET" if asset else "NONE",
            target_id=asset.id if asset else None,
            aggregation_key=f"device:{device.id}:alert:{alert.rule_id}",
        )
    if event.name in {EventNames.ORDER_CREATED, EventNames.ORDER_STATE_CHANGED}:
        order = db.get(Order, str(payload.get("order_id") or event.aggregate_id))
        organization_id = (order.organization_id or order.company_id) if order else None
        if order is None or not organization_id or payload.get("customer_visible") is False:
            return None
        target_state = str(payload.get("to") or order.fulfilment_status).replace("_", " ").lower()
        return NotificationIntent(
            organization_id=organization_id,
            workspace_id=order.workspace_id,
            category="ORDER",
            notification_type=("order.created" if event.name == EventNames.ORDER_CREATED else "order.status_updated"),
            title=("Order received" if event.name == EventNames.ORDER_CREATED else "Order status updated"),
            body=f"Your GeoVision order is {target_state}.",
            severity="INFO",
            target_type="ORDER",
            target_id=order.id,
            preferred_recipient_user_id=order.user_id,
        )
    if event.name in {
        EventNames.FULFILMENT_JOB_SCHEDULE_CHANGED,
        EventNames.FULFILMENT_JOB_STATE_CHANGED,
    }:
        job = db.get(FulfilmentJob, str(payload.get("job_id") or event.aggregate_id))
        order = db.get(Order, job.order_id) if job else None
        organization_id = (order.organization_id or order.company_id) if order else None
        if job is None or order is None or not organization_id:
            return None
        scheduled = event.name == EventNames.FULFILMENT_JOB_SCHEDULE_CHANGED
        return NotificationIntent(
            organization_id=organization_id,
            workspace_id=order.workspace_id,
            category="SERVICE",
            notification_type="service.schedule_updated" if scheduled else "service.status_updated",
            title="Service schedule updated" if scheduled else "Service status updated",
            body=(
                "Your GeoVision service schedule changed."
                if scheduled
                else f"Your GeoVision service is {job.state.replace('_', ' ').lower()}."
            ),
            severity="INFO",
            # Customer clients already authorize and render the owning order;
            # the internal fulfilment-job identifier is never exposed as a
            # customer navigation capability.
            target_type="ORDER",
            target_id=order.id,
            preferred_recipient_user_id=order.user_id,
        )
    if event.name == EventNames.SHIPMENT_STATE_CHANGED:
        order = db.get(Order, str(payload.get("order_id") or event.aggregate_id))
        organization_id = (order.organization_id or order.company_id) if order else None
        if order is None or not organization_id:
            return None
        return NotificationIntent(
            organization_id=organization_id,
            workspace_id=order.workspace_id,
            category="SHIPMENT",
            notification_type="shipment.status_updated",
            title="Shipment status updated",
            body="Your GeoVision delivery status changed.",
            severity="INFO",
            target_type="SHIPMENT",
            target_id=order.id,
            preferred_recipient_user_id=order.user_id,
        )
    if event.name == EventNames.INVITATION_CREATED:
        invitation = db.get(Invitation, str(payload.get("invitation_id") or event.aggregate_id))
        membership = db.get(CompanyUser, invitation.membership_id) if invitation else None
        if invitation is None or membership is None or not membership.user_id:
            return None
        return NotificationIntent(
            organization_id=invitation.organization_id,
            workspace_id=invitation.workspace_id,
            category="INVITATION",
            notification_type="invitation.created",
            title="GeoVision workspace invitation",
            body="You were invited to an existing GeoVision workspace.",
            severity="INFO",
            target_type="INVITATION",
            target_id=invitation.id,
            preferred_recipient_user_id=membership.user_id,
        )
    return None


def _queue_delivery(
    db: Session,
    *,
    notification: Notification,
    channel: str,
    provider: str,
    status: str,
    endpoint_id: str | None = None,
    payload_ciphertext: str | None = None,
    payload_sha256: str | None = None,
) -> NotificationDelivery:
    row = NotificationDelivery(
        id=str(uuid.uuid4()),
        notification_id=notification.id,
        endpoint_id=endpoint_id,
        channel=channel,
        provider=provider,
        status=status,
        idempotency_key=(
            f"notification:{notification.id}:{channel.lower()}:{endpoint_id or 'primary'}"
        ),
        payload_ciphertext=payload_ciphertext,
        payload_key_id="geovision-fernet-v1" if payload_ciphertext else None,
        payload_sha256=payload_sha256,
        attempts=0,
        max_attempts=5,
        next_attempt_at=utc_now() if status == "PENDING" else None,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db.add(row)
    return row


def _queue_user_deliveries(
    db: Session,
    *,
    notification: Notification,
    user: User,
    config: Settings,
) -> int:
    preference = effective_preference(
        db,
        user_id=user.id,
        organization_id=notification.organization_id,
        category=notification.category,
    )
    above_minimum = preference is None or severity_allows(
        actual=notification.severity, minimum=preference.minimum_severity
    )
    suppressed = 0
    email_provider = _email_provider(config)
    email_enabled = (
        email_provider != "disabled"
        and above_minimum
        and (preference is None or preference.email_enabled)
    )
    _queue_delivery(
        db,
        notification=notification,
        channel="EMAIL",
        provider=email_provider,
        status="PENDING" if email_enabled else "SUPPRESSED",
    )
    suppressed += int(not email_enabled)
    endpoints = (
        db.query(NotificationEndpoint)
        .filter(
            NotificationEndpoint.user_id == user.id,
            NotificationEndpoint.status == "ACTIVE",
            or_(
                NotificationEndpoint.organization_id.is_(None),
                NotificationEndpoint.organization_id == notification.organization_id,
            ),
        )
        .order_by(NotificationEndpoint.id.asc())
        .all()
    )
    push_enabled = above_minimum and (preference is None or preference.push_enabled)
    for endpoint in endpoints:
        _queue_delivery(
            db,
            notification=notification,
            channel="PUSH",
            provider=endpoint.provider,
            endpoint_id=endpoint.id,
            status="PENDING" if push_enabled else "SUPPRESSED",
        )
        suppressed += int(not push_enabled)
    return suppressed


def _materialize_for_user(
    db: Session,
    *,
    event: DomainEvent,
    intent: NotificationIntent,
    user: User,
    config: Settings,
) -> tuple[Notification, bool, bool, int]:
    # Serialize rate-window decisions per recipient on PostgreSQL. Without this
    # lock, two different high-frequency events could both observe an empty
    # window and create duplicate inbox rows before either transaction commits.
    if intent.aggregation_key and db.get_bind().dialect.name == "postgresql":
        db.execute(select(User.id).where(User.id == user.id).with_for_update())

    event_id = str(event.event_id)
    recipient_key = f"user:{user.id}"
    prior_link = (
        db.query(NotificationEventLink)
        .filter(
            NotificationEventLink.event_id == event_id,
            NotificationEventLink.recipient_key == recipient_key,
        )
        .one_or_none()
    )
    if prior_link is not None:
        existing = db.get(Notification, prior_link.notification_id)
        if existing is None:  # Defensive: FK/cascade should make this impossible.
            raise RuntimeError("notification event link lost its notification")
        return existing, False, False, 0

    existing = (
        db.query(Notification)
        .filter(
            Notification.organization_id == intent.organization_id,
            Notification.recipient_key == recipient_key,
            Notification.deduplication_key == f"event:{event_id}",
        )
        .one_or_none()
    )
    if existing is not None:
        db.add(
            NotificationEventLink(
                id=str(uuid.uuid4()),
                notification_id=existing.id,
                event_id=event_id,
                recipient_key=recipient_key,
            )
        )
        db.flush()
        return existing, False, False, 0

    now = event.occurred_at
    aggregate = None
    if intent.aggregation_key:
        aggregate = (
            db.query(Notification)
            .filter(
                Notification.organization_id == intent.organization_id,
                Notification.recipient_key == recipient_key,
                Notification.aggregation_key == intent.aggregation_key,
                Notification.aggregation_window_ends_at.is_not(None),
                Notification.aggregation_window_ends_at >= now,
            )
            .order_by(Notification.last_occurred_at.desc())
            .first()
        )
    if aggregate is not None:
        aggregate.occurrence_count += 1
        aggregate.last_occurred_at = max(aggregate.last_occurred_at, now)
        aggregate.aggregation_window_ends_at = max(
            aggregate.aggregation_window_ends_at, now + AGGREGATION_WINDOW
        )
        aggregate.read_at = None
        aggregate.updated_at = utc_now()
        db.add(
            NotificationEventLink(
                id=str(uuid.uuid4()),
                notification_id=aggregate.id,
                event_id=event_id,
                recipient_key=recipient_key,
            )
        )
        return aggregate, False, True, 0

    created_at = utc_now()
    row = Notification(
        id=str(uuid.uuid4()),
        organization_id=intent.organization_id,
        workspace_id=intent.workspace_id,
        recipient_user_id=user.id,
        recipient_kind="USER",
        recipient_key=recipient_key,
        category=intent.category,
        notification_type=intent.notification_type,
        title=intent.title[:240],
        body=intent.body[:4_000],
        severity=intent.severity,
        target_type=intent.target_type,
        target_id=intent.target_id,
        correlation_id=event.correlation_id,
        deduplication_key=f"event:{event_id}",
        aggregation_key=intent.aggregation_key,
        occurrence_count=1,
        first_occurred_at=now,
        last_occurred_at=now,
        aggregation_window_ends_at=(now + AGGREGATION_WINDOW if intent.aggregation_key else None),
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(row)
    db.flush()
    db.add(
        NotificationEventLink(
            id=str(uuid.uuid4()),
            notification_id=row.id,
            event_id=event_id,
            recipient_key=recipient_key,
        )
    )
    suppressed = _queue_user_deliveries(
        db, notification=row, user=user, config=config
    )
    db.add(
        AuditLog(
            action="notification.created",
            resource_type="notification",
            resource_id=row.id,
            details=json.dumps(
                {
                    "organization_id": row.organization_id,
                    "workspace_id": row.workspace_id,
                    "recipient_user_id": row.recipient_user_id,
                    "source_event_id": event_id,
                    "notification_type": row.notification_type,
                    "target_type": row.target_type,
                    "target_id": row.target_id,
                },
                sort_keys=True,
            ),
        )
    )
    return row, True, False, suppressed


def materialize_notification_event(
    db: Session,
    event: DomainEvent,
    *,
    config: Settings = settings,
) -> MaterializationResult:
    intent = _intent_from_event(db, event)
    if intent is None:
        return MaterializationResult(())
    users = _recipients(
        db,
        organization_id=intent.organization_id,
        workspace_id=intent.workspace_id,
        preferred_user_id=intent.preferred_recipient_user_id,
    )
    # Assignment may point to internal staff. Fall back to the customer scope
    # instead of leaking customer notifications to an unrelated assignee.
    if (
        not users
        and intent.preferred_recipient_user_id
        and intent.fallback_to_scope
    ):
        users = _recipients(
            db,
            organization_id=intent.organization_id,
            workspace_id=intent.workspace_id,
            preferred_user_id=None,
        )
    ids: list[str] = []
    created = aggregated = suppressed = 0
    for user in users:
        row, was_created, was_aggregated, delivery_suppressed = _materialize_for_user(
            db,
            event=event,
            intent=intent,
            user=user,
            config=config,
        )
        ids.append(row.id)
        created += int(was_created)
        aggregated += int(was_aggregated)
        suppressed += delivery_suppressed
    db.flush()
    return MaterializationResult(tuple(ids), created, aggregated, suppressed)


def stage_invitation_notification(
    db: Session,
    *,
    invitation: Invitation,
    accept_url: str,
    mobile_deep_link: str,
    config: Settings = settings,
) -> Notification:
    """Persist an invitation email while its one-time secret is still available.

    The public notification/event rows contain only typed IDs. The token-bearing
    URLs are encrypted as one worker payload and are never copied into events,
    logs, notification text, or provider metadata.
    """

    event_row = enqueue_domain_event(
        db,
        name=EventNames.INVITATION_CREATED,
        aggregate_type="invitation",
        aggregate_id=invitation.id,
        idempotency_key=f"invitation:{invitation.id}:created",
        correlation_id=invitation.organization_id,
        payload={
            "invitation_id": invitation.id,
            "organization_id": invitation.organization_id,
            "workspace_id": invitation.workspace_id,
            "membership_id": invitation.membership_id,
            "target_type": invitation.target_type,
            "target_id": invitation.target_id,
        },
    )
    recipient_key = f"invitation:{invitation.id}"
    existing = (
        db.query(Notification)
        .filter(
            Notification.organization_id == invitation.organization_id,
            Notification.recipient_key == recipient_key,
            Notification.deduplication_key == f"event:{event_row.id}",
        )
        .one_or_none()
    )
    if existing is not None:
        return existing
    organization = db.get(Company, invitation.organization_id)
    organization_name = organization.name if organization else "GeoVision"
    now = utc_now()
    row = Notification(
        id=str(uuid.uuid4()),
        organization_id=invitation.organization_id,
        workspace_id=invitation.workspace_id,
        recipient_user_id=None,
        recipient_kind="PRE_ACCOUNT",
        recipient_key=recipient_key,
        category="INVITATION",
        notification_type="invitation.created",
        title="GeoVision workspace invitation",
        body=f"You were invited to an existing {organization_name} workspace.",
        severity="INFO",
        target_type="INVITATION",
        target_id=invitation.id,
        correlation_id=invitation.organization_id,
        deduplication_key=f"event:{event_row.id}",
        occurrence_count=1,
        first_occurred_at=now,
        last_occurred_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    db.add(
        NotificationEventLink(
            id=str(uuid.uuid4()),
            notification_id=row.id,
            event_id=event_row.id,
            recipient_key=recipient_key,
        )
    )
    private_payload = json.dumps(
        {
            "destination": invitation.target_email,
            "title": row.title,
            "body": (
                f"{row.body}\n\nOpen in the portal: {accept_url}\n"
                f"Open in the GeoVision app: {mobile_deep_link}"
            ),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    # A one-time invitation token must never use the development helper's
    # ``plain:`` fallback. Keep the event/inbox history but explicitly suppress
    # external delivery until durable encryption is configured.
    email_provider = _email_provider(config)
    if not config.encryption_key_is_valid or email_provider == "disabled":
        _queue_delivery(
            db,
            notification=row,
            channel="EMAIL",
            provider=email_provider,
            status="SUPPRESSED",
        )
    else:
        protected = encrypt(private_payload)
        if not protected or protected.startswith("plain:"):
            raise RuntimeError("invitation delivery payload could not be protected")
        _queue_delivery(
            db,
            notification=row,
            channel="EMAIL",
            provider=email_provider,
            status="PENDING",
            payload_ciphertext=protected,
            payload_sha256=hashlib.sha256(private_payload.encode("utf-8")).hexdigest(),
        )
    return row


def claim_invitation_notification(
    db: Session,
    *,
    invitation: Invitation,
    user: User,
) -> Notification | None:
    """Attach the pre-account history row after the intended user accepts."""

    row = (
        db.query(Notification)
        .filter(
            Notification.organization_id == invitation.organization_id,
            Notification.recipient_key == f"invitation:{invitation.id}",
            Notification.target_type == "INVITATION",
            Notification.target_id == invitation.id,
        )
        .one_or_none()
    )
    if row is None:
        return None
    if row.recipient_user_id not in (None, user.id):
        raise RuntimeError("invitation notification is bound to another identity")
    new_key = f"user:{user.id}"
    row.recipient_kind = "USER"
    row.recipient_user_id = user.id
    row.recipient_key = new_key
    row.updated_at = utc_now()
    for link in (
        db.query(NotificationEventLink)
        .filter(NotificationEventLink.notification_id == row.id)
        .all()
    ):
        link.recipient_key = new_key
    return row


NOTIFICATION_EVENT_NAMES = (
    EventNames.INVITATION_CREATED,
    EventNames.REPORT_PUBLISHED,
    EventNames.ACTION_REQUESTED,
    EventNames.DEVICE_ALERT_TRIGGERED,
    EventNames.DEVICE_OFFLINE_DETECTED,
    EventNames.FULFILMENT_JOB_SCHEDULE_CHANGED,
    EventNames.FULFILMENT_JOB_STATE_CHANGED,
    EventNames.ORDER_CREATED,
    EventNames.ORDER_STATE_CHANGED,
    EventNames.SHIPMENT_STATE_CHANGED,
)


__all__ = [
    "AGGREGATION_WINDOW",
    "MaterializationResult",
    "NOTIFICATION_EVENT_NAMES",
    "NotificationIntent",
    "claim_invitation_notification",
    "materialize_notification_event",
    "stage_invitation_notification",
]
