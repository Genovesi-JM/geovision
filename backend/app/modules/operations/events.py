"""Operational compatibility facade over the canonical transactional outbox."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from sqlalchemy.orm import Session

from app.models import OperationalDomainEvent
from app.services.event_outbox import enqueue_domain_event


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
    provider_name = "database-outbox"

    def publish(self, db: Session, event: OperationalEvent) -> OperationalDomainEvent:
        return enqueue_domain_event(
            db,
            name=event.event_type,
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            idempotency_key=event.idempotency_key,
            correlation_id=event.aggregate_id,
            payload=event.payload,
        )


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
