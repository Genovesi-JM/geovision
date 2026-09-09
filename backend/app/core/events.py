"""Small provider-neutral event contracts shared by GeoVision modules.

Phase 1 defines only the dependency boundary. Durable persistence, queues, and
Azure adapters belong to later playbook phases.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping, Protocol
from uuid import UUID, uuid4

from .time import utc_now


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """Immutable event envelope that never exposes a provider identifier."""

    name: str
    aggregate_type: str
    aggregate_id: str
    payload: Mapping[str, Any]
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


class EventPublisher(Protocol):
    """Port implemented by an in-process or durable event publisher."""

    def publish(self, event: DomainEvent) -> None:
        """Publish an event or raise an implementation-specific exception."""


class NullEventPublisher:
    """Explicit no-op publisher for modules that have not enabled events yet."""

    def publish(self, event: DomainEvent) -> None:
        del event


__all__ = ["DomainEvent", "EventPublisher", "NullEventPublisher"]
