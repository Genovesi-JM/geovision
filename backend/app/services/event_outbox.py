"""Transactional outbox, idempotent inbox, and provider-neutral dispatcher."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
import json
import uuid
from typing import Any

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.events import DomainEvent, QueueMessage, QueuePublisher
from app.core.integration import IntegrationError, sanitize_integration_message
from app.core.time import utc_now
from app.models import (
    EventConsumerReceipt,
    EventDeliveryAttempt,
    EventOutbox,
)


MAX_EVENT_PAYLOAD_BYTES = 192 * 1024
EventHandler = Callable[[Session, DomainEvent], None]


class EventOutboxError(RuntimeError):
    """Safe application error raised by the durable event boundary."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        self.code = code
        self.safe_message = sanitize_integration_message(message)
        self.retryable = retryable
        super().__init__(f"{code}: {self.safe_message}")


class EventConsumerRegistry:
    """Explicit event-to-consumer composition without provider dependencies."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[tuple[str, EventHandler]]] = defaultdict(list)

    def register(
        self,
        event_name: str,
        consumer_name: str,
        handler: EventHandler,
    ) -> None:
        identity = (consumer_name, handler)
        if identity not in self._handlers[event_name]:
            self._handlers[event_name].append(identity)

    def handlers_for(self, event_name: str) -> tuple[tuple[str, EventHandler], ...]:
        return tuple(self._handlers.get(event_name, ()))


class OutboxEventPublisher:
    """Store events in the caller's open SQL transaction; never commits."""

    provider_name = "database_outbox"

    def publish(self, transaction: Session, event: DomainEvent) -> EventOutbox:
        event_id = str(event.event_id)
        idempotency_key = (event.idempotency_key or event_id).strip()
        existing = (
            transaction.query(EventOutbox)
            .filter(EventOutbox.idempotency_key == idempotency_key)
            .one_or_none()
        )
        if existing is not None:
            if (
                existing.event_type != event.name
                or existing.aggregate_type != event.aggregate_type
                or existing.aggregate_id != event.aggregate_id
            ):
                raise EventOutboxError(
                    "idempotency_conflict",
                    "Event idempotency key is already bound to another fact",
                )
            return existing
        if transaction.get(EventOutbox, event_id) is not None:
            raise EventOutboxError(
                "event_id_conflict", "Event ID is already bound to another event"
            )

        payload_json = json.dumps(
            dict(event.payload),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        )
        if len(payload_json.encode("utf-8")) > MAX_EVENT_PAYLOAD_BYTES:
            raise EventOutboxError(
                "event_payload_too_large",
                "Event payload exceeds the durable transport envelope limit",
            )
        row = EventOutbox(
            id=event_id,
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            event_type=event.name,
            payload_json=payload_json,
            idempotency_key=idempotency_key,
            topic=event.topic,
            schema_version=event.schema_version,
            correlation_id=event.correlation_id,
            causation_id=event.causation_id,
            status="pending",
            publish_attempts=0,
            occurred_at=event.occurred_at,
        )
        transaction.add(row)
        return row


outbox_event_publisher = OutboxEventPublisher()


def enqueue_domain_event(
    db: Session,
    *,
    name: str,
    aggregate_type: str,
    aggregate_id: str,
    payload: Mapping[str, Any] | None = None,
    idempotency_key: str | None = None,
    event_id: uuid.UUID | None = None,
    occurred_at: datetime | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    topic: str | None = None,
    publisher: OutboxEventPublisher | None = None,
) -> EventOutbox:
    """Enqueue a domain fact without committing the surrounding transaction."""

    event = DomainEvent(
        name=name,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload or {},
        event_id=event_id or uuid.uuid4(),
        occurred_at=occurred_at or utc_now(),
        topic=topic or settings.event_topic,
        correlation_id=correlation_id,
        causation_id=causation_id,
        idempotency_key=idempotency_key,
    )
    return (publisher or outbox_event_publisher).publish(db, event)


def event_from_row(row: EventOutbox) -> DomainEvent:
    try:
        payload = json.loads(row.payload_json or "{}")
    except (TypeError, ValueError) as exc:
        raise EventOutboxError(
            "invalid_event_payload", "Persisted event payload is not valid JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise EventOutboxError(
            "invalid_event_payload", "Persisted event payload must be an object"
        )
    try:
        event_id = uuid.UUID(row.id)
    except ValueError as exc:
        raise EventOutboxError(
            "invalid_event_id", "Persisted event ID is not a UUID"
        ) from exc
    return DomainEvent(
        name=row.event_type,
        aggregate_type=row.aggregate_type,
        aggregate_id=row.aggregate_id,
        payload=payload,
        event_id=event_id,
        occurred_at=row.occurred_at,
        topic=row.topic,
        schema_version=row.schema_version,
        correlation_id=row.correlation_id,
        causation_id=row.causation_id,
        idempotency_key=row.idempotency_key,
    )


def serialize_event(event: DomainEvent) -> dict[str, Any]:
    """Return the stable wire envelope used by every queue adapter."""

    occurred = event.occurred_at.isoformat()
    if event.occurred_at.tzinfo is None:
        occurred += "Z"
    return {
        "specversion": "1.0",
        "id": str(event.event_id),
        "type": event.name,
        "source": "geovision",
        "subject": f"{event.aggregate_type}/{event.aggregate_id}",
        "time": occurred,
        "datacontenttype": "application/json",
        "data": dict(event.payload),
        "geovision": {
            "topic": event.topic,
            "schema_version": event.schema_version,
            "aggregate_type": event.aggregate_type,
            "aggregate_id": event.aggregate_id,
            "correlation_id": event.correlation_id,
            "causation_id": event.causation_id,
            "idempotency_key": event.idempotency_key,
        },
    }


def deserialize_event(payload: Mapping[str, Any]) -> DomainEvent:
    """Validate the stable queue envelope before it reaches a consumer."""

    extension = payload.get("geovision")
    data = payload.get("data")
    if payload.get("specversion") != "1.0" or not isinstance(extension, Mapping):
        raise EventOutboxError("invalid_envelope", "Unsupported event envelope")
    if not isinstance(data, Mapping):
        raise EventOutboxError("invalid_envelope", "Event data must be an object")
    try:
        event_id = uuid.UUID(str(payload["id"]))
        occurred_at = datetime.fromisoformat(str(payload["time"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError) as exc:
        raise EventOutboxError("invalid_envelope", "Event identity or time is invalid") from exc
    if occurred_at.tzinfo is not None:
        occurred_at = occurred_at.astimezone(timezone.utc).replace(tzinfo=None)
    return DomainEvent(
        name=str(payload.get("type") or ""),
        aggregate_type=str(extension.get("aggregate_type") or ""),
        aggregate_id=str(extension.get("aggregate_id") or ""),
        payload=dict(data),
        event_id=event_id,
        occurred_at=occurred_at,
        topic=str(extension.get("topic") or settings.event_topic),
        schema_version=int(extension.get("schema_version") or 1),
        correlation_id=str(extension.get("correlation_id") or event_id),
        causation_id=(
            str(extension["causation_id"])
            if extension.get("causation_id") is not None
            else None
        ),
        idempotency_key=(
            str(extension["idempotency_key"])
            if extension.get("idempotency_key") is not None
            else None
        ),
    )


def consume_once(
    db: Session,
    *,
    consumer_name: str,
    event: DomainEvent,
    handler: EventHandler,
) -> bool:
    """Run a DB consumer once; its receipt commits with its side effects."""

    event_id = str(event.event_id)
    existing = (
        db.query(EventConsumerReceipt.id)
        .filter(
            EventConsumerReceipt.consumer_name == consumer_name,
            EventConsumerReceipt.event_id == event_id,
        )
        .first()
    )
    if existing is not None:
        return False
    try:
        with db.begin_nested():
            db.add(
                EventConsumerReceipt(
                    consumer_name=consumer_name,
                    event_id=event_id,
                    event_type=event.name,
                    correlation_id=event.correlation_id,
                )
            )
            db.flush()
    except IntegrityError:
        return False
    handler(db, event)
    return True


def deliver_to_local_consumers(
    db: Session,
    event: DomainEvent,
    registry: EventConsumerRegistry,
) -> tuple[int, int]:
    processed = duplicates = 0
    for consumer_name, handler in registry.handlers_for(event.name):
        if consume_once(
            db,
            consumer_name=consumer_name,
            event=event,
            handler=handler,
        ):
            processed += 1
        else:
            duplicates += 1
    return processed, duplicates


def _release_stale_claims(db: Session, config: Settings, now: datetime) -> None:
    stale_before = now - timedelta(seconds=config.event_worker_claim_timeout_seconds)
    (
        db.query(EventOutbox)
        .filter(
            EventOutbox.status == "processing",
            EventOutbox.claimed_at.is_not(None),
            EventOutbox.claimed_at < stale_before,
        )
        .update(
            {
                EventOutbox.status: "retry",
                EventOutbox.claimed_by: None,
                EventOutbox.claimed_at: None,
                EventOutbox.next_attempt_at: now,
            },
            synchronize_session=False,
        )
    )


def claim_pending_events(
    db: Session,
    *,
    worker_id: str,
    limit: int,
    config: Settings = settings,
) -> list[str]:
    """Claim due events, using SKIP LOCKED on PostgreSQL and a local fallback."""

    now = utc_now()
    _release_stale_claims(db, config, now)
    query = (
        db.query(EventOutbox)
        .filter(
            EventOutbox.status.in_(("pending", "retry")),
            or_(
                EventOutbox.next_attempt_at.is_(None),
                EventOutbox.next_attempt_at <= now,
            ),
        )
        .order_by(EventOutbox.occurred_at.asc(), EventOutbox.id.asc())
        .limit(limit)
    )
    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    rows = query.all()
    for row in rows:
        row.status = "processing"
        row.claimed_by = worker_id
        row.claimed_at = now
    db.commit()
    return [row.id for row in rows]


def _retry_delay(attempt: int, config: Settings) -> float:
    return min(
        config.event_retry_max_seconds,
        config.event_retry_initial_seconds * (2 ** max(attempt - 1, 0)),
    )


def _record_outcome(
    db: Session,
    *,
    row: EventOutbox,
    worker_id: str,
    provider: str,
    outcome: str,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    db.add(
        EventDeliveryAttempt(
            event_id=row.id,
            worker_id=worker_id,
            provider=provider,
            attempt_number=row.publish_attempts,
            outcome=outcome,
            error_code=error_code,
            error_message=error_message,
        )
    )


def _failure_details(exc: Exception) -> tuple[str, str, bool]:
    if isinstance(exc, EventOutboxError):
        return exc.code, exc.safe_message, exc.retryable
    if isinstance(exc, IntegrationError):
        return exc.code, exc.safe_message, exc.retryable
    return "event_delivery_failed", sanitize_integration_message(exc), True


def dispatch_pending_events(
    db: Session,
    *,
    worker_id: str,
    registry: EventConsumerRegistry,
    config: Settings = settings,
    queue_publisher: QueuePublisher | None = None,
    limit: int | None = None,
) -> dict[str, int]:
    """Deliver one claimed batch and persist success, retry, or dead-letter state."""

    batch_size = limit or config.event_worker_batch_size
    event_ids = claim_pending_events(
        db,
        worker_id=worker_id,
        limit=batch_size,
        config=config,
    )
    stats = {
        "claimed": len(event_ids),
        "published": 0,
        "retried": 0,
        "dead_lettered": 0,
        "duplicate_consumers": 0,
    }
    provider = config.queue_provider
    for event_id in event_ids:
        try:
            row = db.get(EventOutbox, event_id)
            if row is None or row.status != "processing" or row.claimed_by != worker_id:
                db.rollback()
                continue
            event = event_from_row(row)
            row.publish_attempts += 1
            if provider in {"database", "in_memory"}:
                _, duplicates = deliver_to_local_consumers(db, event, registry)
                stats["duplicate_consumers"] += duplicates
            else:
                if queue_publisher is None:
                    from app.integrations.events.factory import create_queue_publisher

                    queue_publisher = create_queue_publisher(config)
                result = queue_publisher.publish(
                    QueueMessage(
                        topic=config.service_bus_topic,
                        payload=serialize_event(event),
                        message_id=str(event.event_id),
                        idempotency_key=event.idempotency_key,
                        correlation_id=event.correlation_id,
                        subject=event.name,
                    )
                )
                if not result.ok:
                    failure = result.failure
                    raise EventOutboxError(
                        failure.code if failure else "queue_publish_failed",
                        failure.message if failure else "Queue rejected event",
                        retryable=failure.retryable if failure else True,
                    )
            row.status = "published"
            row.published_at = utc_now()
            row.next_attempt_at = None
            row.last_error = None
            row.claimed_by = None
            row.claimed_at = None
            _record_outcome(
                db,
                row=row,
                worker_id=worker_id,
                provider=provider,
                outcome="published",
            )
            db.commit()
            stats["published"] += 1
        except Exception as exc:
            db.rollback()
            row = db.get(EventOutbox, event_id)
            if row is None:
                continue
            row.publish_attempts += 1
            code, message, retryable = _failure_details(exc)
            # A malformed/poison event is terminal immediately. Transient
            # failures are bounded by the configured maximum attempts.
            terminal = (
                not retryable
                or row.publish_attempts >= config.event_worker_max_attempts
            )
            row.status = "dead_letter" if terminal else "retry"
            row.last_error = message
            row.next_attempt_at = (
                None
                if terminal
                else utc_now() + timedelta(seconds=_retry_delay(row.publish_attempts, config))
            )
            row.dead_lettered_at = utc_now() if terminal else None
            row.claimed_by = None
            row.claimed_at = None
            _record_outcome(
                db,
                row=row,
                worker_id=worker_id,
                provider=provider,
                outcome="dead_letter" if terminal else "retry",
                error_code=code,
                error_message=message,
            )
            db.commit()
            stats["dead_lettered" if terminal else "retried"] += 1
    return stats


def requeue_dead_letter(db: Session, event_id: str) -> EventOutbox | None:
    row = db.get(EventOutbox, event_id)
    if row is None or row.status != "dead_letter":
        return None
    row.status = "retry"
    row.publish_attempts = 0
    row.next_attempt_at = utc_now()
    row.last_error = None
    row.dead_lettered_at = None
    row.claimed_by = None
    row.claimed_at = None
    return row


__all__ = [
    "EventConsumerRegistry",
    "EventOutboxError",
    "MAX_EVENT_PAYLOAD_BYTES",
    "OutboxEventPublisher",
    "claim_pending_events",
    "consume_once",
    "deliver_to_local_consumers",
    "deserialize_event",
    "dispatch_pending_events",
    "enqueue_domain_event",
    "event_from_row",
    "outbox_event_publisher",
    "requeue_dead_letter",
    "serialize_event",
]
