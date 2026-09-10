"""SQLAlchemy persistence binding for the durable notification worker."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import hmac
import json
import logging
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.integration import IntegrationFailure, sanitize_integration_message
from app.core.observability import get_logger, log_event
from app.models import (
    AccountMember,
    CompanyUser,
    Notification,
    NotificationDelivery,
    NotificationEndpoint,
    NotificationPreference,
    User,
)
from app.modules.notifications.delivery_ports import (
    DeliveryChannel,
    ExternalDeliveryMessage,
)
from app.modules.notifications.domain import severity_allows
from app.modules.economics.schemas import ProviderUsageCreate
from app.modules.economics.services import record_provider_usage
from app.workers.notification_delivery_runner import (
    DeliveryClaim,
    DeliveryLease,
    Revalidation,
    RevalidationStatus,
)


class PayloadDecoder(Protocol):
    def __call__(self, ciphertext: str | None) -> str | None: ...


logger = get_logger(__name__)


def _clear_claim(row: NotificationDelivery) -> None:
    row.claimed_by = None
    row.claimed_at = None
    row.lease_expires_at = None


def _effective_preference(
    db: Session,
    *,
    notification: Notification,
) -> NotificationPreference | None:
    if not notification.recipient_user_id:
        return None
    rows = (
        db.query(NotificationPreference)
        .filter(
            NotificationPreference.user_id == notification.recipient_user_id,
            NotificationPreference.category == notification.category,
            NotificationPreference.scope_key.in_(
                (notification.organization_id, "GLOBAL")
            ),
        )
        .all()
    )
    by_scope = {row.scope_key: row for row in rows}
    return by_scope.get(notification.organization_id) or by_scope.get("GLOBAL")


def _channel_enabled(preference: NotificationPreference, channel: str) -> bool:
    return bool(
        {
            "PUSH": preference.push_enabled,
            "EMAIL": preference.email_enabled,
            "SMS": preference.sms_enabled,
        }.get(channel, False)
    )


def _parse_clock(value: str) -> tuple[int, int]:
    hour, minute = value.split(":", 1)
    parsed = int(hour), int(minute)
    if not (0 <= parsed[0] <= 23 and 0 <= parsed[1] <= 59):
        raise ValueError("quiet hours are invalid")
    return parsed


def _quiet_hours_end(
    preference: NotificationPreference,
    *,
    now: datetime,
) -> datetime | None:
    if not preference.quiet_hours_start or not preference.quiet_hours_end:
        return None
    try:
        zone = ZoneInfo(preference.timezone or "UTC")
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    aware_utc = (
        now.replace(tzinfo=timezone.utc)
        if now.tzinfo is None
        else now.astimezone(timezone.utc)
    )
    local_now = aware_utc.astimezone(zone)
    start_hour, start_minute = _parse_clock(preference.quiet_hours_start)
    end_hour, end_minute = _parse_clock(preference.quiet_hours_end)
    start_minutes = start_hour * 60 + start_minute
    end_minutes = end_hour * 60 + end_minute
    current_minutes = local_now.hour * 60 + local_now.minute

    if start_minutes == end_minutes:
        in_quiet_hours = True
        end_day = local_now.date() + timedelta(days=1)
    elif start_minutes < end_minutes:
        in_quiet_hours = start_minutes <= current_minutes < end_minutes
        end_day = local_now.date()
    else:
        in_quiet_hours = current_minutes >= start_minutes or current_minutes < end_minutes
        end_day = (
            local_now.date() + timedelta(days=1)
            if current_minutes >= start_minutes
            else local_now.date()
        )
    if not in_quiet_hours:
        return None
    local_end = datetime(
        end_day.year,
        end_day.month,
        end_day.day,
        end_hour,
        end_minute,
        tzinfo=zone,
    )
    return local_end.astimezone(timezone.utc).replace(tzinfo=None)


class SqlAlchemyNotificationDeliveryRepository:
    """Short-transaction repository used by the independent worker process."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        payload_decoder: PayloadDecoder,
    ) -> None:
        self._session_factory = session_factory
        self._payload_decoder = payload_decoder

    def claim_batch(
        self,
        *,
        worker_id: str,
        now: datetime,
        batch_size: int,
        lease_seconds: int,
    ) -> Sequence[DeliveryClaim]:
        claims: list[DeliveryClaim] = []
        with self._session_factory() as db, db.begin():
            stale = (
                db.execute(
                    select(NotificationDelivery)
                    .where(
                        NotificationDelivery.status == "PROCESSING",
                        NotificationDelivery.lease_expires_at.is_not(None),
                        NotificationDelivery.lease_expires_at <= now,
                    )
                    .with_for_update(skip_locked=True)
                )
                .scalars()
                .all()
            )
            for row in stale:
                _clear_claim(row)
                row.updated_at = now
                if row.attempts >= row.max_attempts:
                    row.status = "DEAD_LETTER"
                    row.dead_lettered_at = now
                    row.last_error_code = "notification_delivery_lease_expired"
                    row.last_error_message = "notification delivery lease expired"
                else:
                    row.status = "RETRY"
                    row.next_attempt_at = now

            due = (
                db.execute(
                    select(NotificationDelivery)
                    .where(
                        NotificationDelivery.status.in_(("PENDING", "RETRY")),
                        NotificationDelivery.attempts < NotificationDelivery.max_attempts,
                        or_(
                            NotificationDelivery.next_attempt_at.is_(None),
                            NotificationDelivery.next_attempt_at <= now,
                        ),
                    )
                    .order_by(
                        NotificationDelivery.next_attempt_at.asc(),
                        NotificationDelivery.created_at.asc(),
                        NotificationDelivery.id.asc(),
                    )
                    .limit(max(1, min(batch_size, 500)))
                    .with_for_update(skip_locked=True)
                )
                .scalars()
                .all()
            )
            for row in due:
                row.status = "PROCESSING"
                row.claimed_by = worker_id[:100]
                row.claimed_at = now
                row.lease_expires_at = now + timedelta(seconds=max(30, lease_seconds))
                row.next_attempt_at = None
                row.attempts += 1
                row.updated_at = now
                claims.append(
                    DeliveryClaim(
                        delivery_id=row.id,
                        attempts=row.attempts,
                        max_attempts=row.max_attempts,
                    )
                )
        return claims

    @staticmethod
    def _claimed_row(
        db: Session,
        *,
        delivery_id: str,
        worker_id: str,
        now: datetime,
    ) -> NotificationDelivery | None:
        row = db.execute(
            select(NotificationDelivery)
            .where(NotificationDelivery.id == delivery_id)
            .with_for_update()
        ).scalar_one_or_none()
        if (
            row is None
            or row.status != "PROCESSING"
            or row.claimed_by != worker_id[:100]
            or row.lease_expires_at is None
            or row.lease_expires_at <= now
        ):
            return None
        return row

    @staticmethod
    def _suppress(row: NotificationDelivery, now: datetime, code: str) -> Revalidation:
        row.status = "SUPPRESSED"
        row.last_error_code = code
        row.last_error_message = "notification delivery suppressed by current policy"
        row.updated_at = now
        _clear_claim(row)
        return Revalidation(RevalidationStatus.SUPPRESSED)

    @staticmethod
    def _dead_letter(
        row: NotificationDelivery,
        now: datetime,
        code: str,
    ) -> Revalidation:
        row.status = "DEAD_LETTER"
        row.dead_lettered_at = now
        row.last_error_code = code
        row.last_error_message = "notification delivery data is invalid"
        row.updated_at = now
        _clear_claim(row)
        return Revalidation(RevalidationStatus.DEAD_LETTERED)

    @staticmethod
    def _active_recipient(
        db: Session,
        notification: Notification,
    ) -> User | None:
        user = (
            db.get(User, notification.recipient_user_id)
            if notification.recipient_user_id
            else None
        )
        if user is None or not user.is_active:
            return None
        membership = (
            db.query(CompanyUser)
            .filter(
                CompanyUser.company_id == notification.organization_id,
                CompanyUser.user_id == user.id,
                CompanyUser.is_active.is_(True),
                CompanyUser.status == "active",
            )
            .one_or_none()
        )
        if membership is None:
            return None
        if notification.workspace_id:
            workspace_membership = db.get(
                AccountMember,
                (notification.workspace_id, user.id),
            )
            if workspace_membership is None or workspace_membership.status != "active":
                return None
        return user

    def _payload(self, row: NotificationDelivery) -> dict[str, str]:
        if not row.payload_ciphertext:
            return {}
        if row.payload_ciphertext.startswith("plain:"):
            raise ValueError("plaintext notification payloads are forbidden")
        try:
            decoded = self._payload_decoder(row.payload_ciphertext)
        except Exception as exc:
            raise ValueError("encrypted notification payload could not be decoded") from exc
        if not isinstance(decoded, str):
            raise ValueError("encrypted notification payload could not be decoded")
        digest = hashlib.sha256(decoded.encode("utf-8")).hexdigest()
        if not row.payload_sha256 or not hmac.compare_digest(digest, row.payload_sha256):
            raise ValueError("encrypted notification payload digest does not match")
        value = json.loads(decoded)
        if not isinstance(value, dict):
            raise ValueError("encrypted notification payload must be an object")
        allowed = {"destination", "title", "body"}
        if not set(value).issubset(allowed):
            raise ValueError("encrypted notification payload has unsupported fields")
        if not all(isinstance(item, str) for item in value.values()):
            raise ValueError("encrypted notification payload fields must be text")
        return value

    def _endpoint_handle(self, endpoint: NotificationEndpoint) -> str:
        ciphertext = endpoint.handle_ciphertext
        if not ciphertext or ciphertext.startswith("plain:"):
            raise ValueError("plaintext notification endpoints are forbidden")
        try:
            decoded = self._payload_decoder(ciphertext)
        except Exception as exc:
            raise ValueError("notification endpoint could not be decoded") from exc
        if not isinstance(decoded, str):
            raise ValueError("notification endpoint could not be decoded")
        normalized = decoded.strip()
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(digest, endpoint.handle_digest):
            raise ValueError("notification endpoint digest does not match")
        return normalized

    def revalidate(
        self,
        *,
        worker_id: str,
        delivery_id: str,
        now: datetime,
    ) -> Revalidation:
        with self._session_factory() as db, db.begin():
            row = self._claimed_row(
                db,
                delivery_id=delivery_id,
                worker_id=worker_id,
                now=now,
            )
            if row is None:
                return Revalidation(RevalidationStatus.CLAIM_LOST)
            notification = db.get(Notification, row.notification_id)
            if notification is None:
                return self._dead_letter(row, now, "notification_missing")

            user = None
            if notification.recipient_kind == "USER":
                user = self._active_recipient(db, notification)
                if user is None:
                    return self._suppress(row, now, "notification_recipient_inactive")
                preference = _effective_preference(db, notification=notification)
                if preference is not None:
                    if not _channel_enabled(preference, row.channel) or not severity_allows(
                        actual=notification.severity,
                        minimum=preference.minimum_severity,
                    ):
                        return self._suppress(
                            row, now, "notification_preference_suppressed"
                        )
                    try:
                        quiet_until = _quiet_hours_end(preference, now=now)
                    except (TypeError, ValueError):
                        return self._dead_letter(
                            row, now, "notification_preference_invalid"
                        )
                    if quiet_until is not None:
                        row.status = "RETRY"
                        row.next_attempt_at = quiet_until
                        row.attempts = max(0, row.attempts - 1)
                        row.updated_at = now
                        _clear_claim(row)
                        return Revalidation(RevalidationStatus.DEFERRED)
            elif notification.recipient_kind != "PRE_ACCOUNT":
                return self._dead_letter(row, now, "notification_recipient_invalid")

            try:
                channel = DeliveryChannel(row.channel)
                payload = self._payload(row)
                if channel is DeliveryChannel.PUSH:
                    endpoint = (
                        db.get(NotificationEndpoint, row.endpoint_id)
                        if row.endpoint_id
                        else None
                    )
                    if (
                        endpoint is None
                        or endpoint.status != "ACTIVE"
                        or endpoint.user_id != notification.recipient_user_id
                        or endpoint.organization_id not in (None, notification.organization_id)
                    ):
                        return self._suppress(
                            row, now, "notification_endpoint_unavailable"
                        )
                    normalized_endpoint_provider = endpoint.provider.replace("-", "_")
                    normalized_delivery_provider = row.provider.replace("-", "_")
                    if (
                        normalized_delivery_provider not in {"fake", "file"}
                        and normalized_endpoint_provider != normalized_delivery_provider
                    ):
                        return self._suppress(
                            row, now, "notification_endpoint_provider_changed"
                        )
                    destination = endpoint.installation_id
                    provider_handle = self._endpoint_handle(endpoint)
                    platform = endpoint.platform
                else:
                    destination = payload.get("destination") or (user.email if user else "")
                    provider_handle = None
                    platform = None
                message = ExternalDeliveryMessage(
                    delivery_id=row.id,
                    notification_id=notification.id,
                    idempotency_key=row.idempotency_key,
                    channel=channel,
                    destination=destination,
                    title=payload.get("title", notification.title),
                    body=payload.get("body", notification.body),
                    platform=platform,
                    provider_handle=provider_handle,
                )
            except (TypeError, ValueError):
                return self._dead_letter(row, now, "notification_payload_invalid")
            return Revalidation(
                RevalidationStatus.READY,
                DeliveryLease(
                    message=message,
                    provider_name=row.provider,
                    attempts=row.attempts,
                    max_attempts=row.max_attempts,
                ),
            )

    def mark_delivered(
        self,
        *,
        worker_id: str,
        lease: DeliveryLease,
        provider_message_id: str | None,
        now: datetime,
    ) -> bool:
        with self._session_factory() as db, db.begin():
            row = self._claimed_row(
                db,
                delivery_id=lease.message.delivery_id,
                worker_id=worker_id,
                now=now,
            )
            if row is None:
                return False
            row.status = "DELIVERED"
            row.provider_message_id = (
                sanitize_integration_message(provider_message_id)[:200]
                if provider_message_id
                else None
            )
            row.last_error_code = None
            row.last_error_message = None
            row.delivered_at = now
            row.dead_lettered_at = None
            row.updated_at = now
            _clear_claim(row)
            notification = db.get(Notification, row.notification_id)
            if notification is not None:
                try:
                    with db.begin_nested():
                        record_provider_usage(
                            db,
                            payload=ProviderUsageCreate(
                                organization_id=notification.organization_id,
                                workspace_id=notification.workspace_id,
                                notification_delivery_id=row.id,
                                provider=row.provider,
                                service=f"{row.channel.lower()}_delivery",
                                usage_type="notification_delivery",
                                quantity=Decimal("1"),
                                unit="message",
                                occurred_at=now,
                                provider_reference=row.provider_message_id,
                                idempotency_key=f"notification:{row.id}:usage:delivered",
                                metadata={
                                    "channel": row.channel,
                                    "attempts": row.attempts,
                                },
                            ),
                        )
                except Exception as exc:
                    log_event(
                        logger,
                        logging.WARNING,
                        "notification.usage_metering.failed",
                        organization_id=notification.organization_id,
                        workspace_id=notification.workspace_id,
                        notification_delivery_id=row.id,
                        provider=row.provider,
                        error_type=exc.__class__.__name__,
                    )
            return True

    def mark_failed(
        self,
        *,
        worker_id: str,
        lease: DeliveryLease,
        failure: IntegrationFailure,
        terminal: bool,
        retry_at: datetime | None,
        now: datetime,
    ) -> bool:
        with self._session_factory() as db, db.begin():
            row = self._claimed_row(
                db,
                delivery_id=lease.message.delivery_id,
                worker_id=worker_id,
                now=now,
            )
            if row is None:
                return False
            row.status = "DEAD_LETTER" if terminal else "RETRY"
            row.next_attempt_at = None if terminal else retry_at
            row.last_error_code = failure.code[:80]
            row.last_error_message = sanitize_integration_message(failure.message)
            row.dead_lettered_at = now if terminal else None
            row.updated_at = now
            _clear_claim(row)
            return True

    def requeue_dead_letter(self, delivery_id: str, *, now: datetime) -> bool:
        with self._session_factory() as db, db.begin():
            row = db.execute(
                select(NotificationDelivery)
                .where(NotificationDelivery.id == delivery_id)
                .with_for_update()
            ).scalar_one_or_none()
            if row is None or row.status != "DEAD_LETTER":
                return False
            row.status = "RETRY"
            row.attempts = 0
            row.next_attempt_at = now
            row.dead_lettered_at = None
            row.last_error_code = None
            row.last_error_message = None
            row.updated_at = now
            _clear_claim(row)
            return True


__all__ = ["PayloadDecoder", "SqlAlchemyNotificationDeliveryRepository"]
