"""Replaceable operational-domain event publisher.

Phase 10 persists events in the same database transaction as the job change.
Phase 13 can replace ``LocalDomainEventPublisher`` with a broker/outbox adapter
without changing job application services.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import uuid
from typing import Any, Mapping, Protocol

from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models import OperationalDomainEvent


@dataclass(frozen=True, slots=True)
class OperationalEvent:
    aggregate_type: str
    aggregate_id: str
    event_type: str
    payload: Mapping[str, Any]
    idempotency_key: str


class DomainEventPublisher(Protocol):
    """Port implemented by local storage now and a message adapter later."""

    def publish(self, db: Session, event: OperationalEvent) -> OperationalDomainEvent:
        ...


class LocalDomainEventPublisher:
    provider_name = "local-transactional-ledger"

    def publish(self, db: Session, event: OperationalEvent) -> OperationalDomainEvent:
        existing = (
            db.query(OperationalDomainEvent)
            .filter(OperationalDomainEvent.idempotency_key == event.idempotency_key)
            .one_or_none()
        )
        if existing is not None:
            return existing
        now = utc_now()
        row = OperationalDomainEvent(
            id=str(uuid.uuid4()),
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            event_type=event.event_type,
            payload_json=json.dumps(
                dict(event.payload),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
                default=str,
            ),
            idempotency_key=event.idempotency_key,
            publish_attempts=1,
            occurred_at=now,
            published_at=now,
        )
        db.add(row)
        return row


local_event_publisher = LocalDomainEventPublisher()


def publish_operational_event(
    db: Session,
    *,
    aggregate_id: str,
    event_type: str,
    payload: Mapping[str, Any],
    idempotency_key: str,
    publisher: DomainEventPublisher | None = None,
) -> OperationalDomainEvent:
    return (publisher or local_event_publisher).publish(
        db,
        OperationalEvent(
            aggregate_type="fulfilment_job",
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
            idempotency_key=idempotency_key,
        ),
    )


__all__ = [
    "DomainEventPublisher",
    "LocalDomainEventPublisher",
    "OperationalEvent",
    "local_event_publisher",
    "publish_operational_event",
]
