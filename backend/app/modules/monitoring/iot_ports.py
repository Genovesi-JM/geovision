"""Provider-neutral cloud telemetry boundary owned by monitoring."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class CloudTelemetryEvent:
    """Normalized cloud delivery before GeoVision schema validation."""

    provider_code: str
    provider_event_id: str
    provider_device_id: str
    occurred_at: datetime
    envelope: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class CloudTelemetryBatch:
    validation_code: str | None
    events: tuple[CloudTelemetryEvent, ...]


@runtime_checkable
class CloudTelemetryProvider(Protocol):
    provider_name: str

    def parse_delivery(
        self,
        payload: object,
        *,
        headers: Mapping[str, str],
    ) -> CloudTelemetryBatch: ...


__all__ = ["CloudTelemetryBatch", "CloudTelemetryEvent", "CloudTelemetryProvider"]
