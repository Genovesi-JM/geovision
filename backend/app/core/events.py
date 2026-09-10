"""Provider-neutral event envelopes and ports shared by GeoVision modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
import re
from typing import Any, Mapping, Optional, Protocol
from uuid import UUID, uuid4

from .integration import IntegrationResult
from .time import utc_now


_EVENT_NAME = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
DEFAULT_EVENT_TOPIC = "geovision.domain.v1"


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """Immutable, versioned event envelope with end-to-end tracing metadata."""

    name: str
    aggregate_type: str
    aggregate_id: str
    payload: Mapping[str, Any]
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=utc_now)
    topic: str = DEFAULT_EVENT_TOPIC
    schema_version: int = 1
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    idempotency_key: Optional[str] = None

    def __post_init__(self) -> None:
        if not _EVENT_NAME.fullmatch(self.name):
            raise ValueError("event name must be a lowercase dotted identifier")
        if not self.aggregate_type.strip() or not self.aggregate_id.strip():
            raise ValueError("event aggregate type and ID must not be empty")
        if self.schema_version < 1:
            raise ValueError("event schema version must be positive")
        if not self.topic.strip():
            raise ValueError("event topic must not be empty")
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))
        object.__setattr__(
            self,
            "correlation_id",
            (self.correlation_id or str(self.event_id)).strip(),
        )


class EventPublisher(Protocol):
    """Port implemented by an in-process or durable event publisher."""

    def publish(self, event: DomainEvent) -> None:
        """Publish an event or raise an implementation-specific exception."""


class TransactionalEventPublisher(Protocol):
    """Port that stores an event in the caller's domain transaction."""

    provider_name: str

    def publish(self, transaction: Any, event: DomainEvent) -> Any:
        """Persist the event without committing the caller's transaction."""


@dataclass(frozen=True, slots=True)
class QueueMessage:
    """Provider-neutral message delivered by a durable queue adapter."""

    topic: str
    payload: Mapping[str, Any]
    message_id: str
    idempotency_key: Optional[str] = None
    correlation_id: Optional[str] = None
    subject: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


class QueuePublisher(Protocol):
    """Port for queue delivery; Phase 13 owns durable semantics and adapters."""

    provider_name: str

    def publish(self, message: QueueMessage) -> IntegrationResult[None]:
        """Publish a message and return a normalized delivery result."""


class NullEventPublisher:
    """Explicit no-op publisher for modules that have not enabled events yet."""

    def publish(self, event: DomainEvent) -> None:
        del event


class InMemoryEventPublisher:
    """Deterministic test double; production workflows use the DB outbox."""

    provider_name = "in_memory"

    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    def publish(self, event: DomainEvent) -> None:
        self.events.append(event)


__all__ = [
    "DEFAULT_EVENT_TOPIC",
    "DomainEvent",
    "EventPublisher",
    "InMemoryEventPublisher",
    "NullEventPublisher",
    "QueueMessage",
    "QueuePublisher",
    "TransactionalEventPublisher",
]
