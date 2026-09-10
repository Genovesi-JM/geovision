"""Provider ports owned by the monitoring domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Optional, Protocol, runtime_checkable
from uuid import UUID

from app.core.integration import IntegrationResult


@dataclass(frozen=True, slots=True)
class WeatherRequest:
    latitude: float
    longitude: float
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    max_distance_km: float = 150.0


@dataclass(frozen=True, slots=True)
class WeatherMetric:
    metric: str
    value: float
    unit: str
    quality: str = "observed"


@dataclass(frozen=True, slots=True)
class WeatherSnapshot:
    source_reference: str
    source_name: Optional[str]
    observed_at: datetime
    latitude: Optional[float]
    longitude: Optional[float]
    distance_km: Optional[float]
    metrics: tuple[WeatherMetric, ...]
    provenance: Mapping[str, Any]


class MaritimeSourceKind(str, Enum):
    """Semantics of one provider value; kinds must never be conflated."""

    OBSERVED = "observed"
    MODEL = "model"
    FORECAST = "forecast"
    AIS = "ais"


@dataclass(frozen=True, slots=True)
class MaritimeContextRequest:
    """Bounded context query tied to an authoritative GeoVision asset UUID."""

    internal_id: UUID
    latitude: float
    longitude: float
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    max_distance_km: float = 100.0
    limit: int = 100


@dataclass(frozen=True, slots=True)
class MaritimeContextReading:
    """Provider context with explicit source, time, location, and use limits."""

    provider_reference: str
    valid_at: datetime
    station_reference: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    metric: str
    value: float | str
    unit: str
    quality: str
    source: str
    source_kind: MaritimeSourceKind
    license_id: str
    license_url: Optional[str]
    attribution: str
    provenance: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class MaritimeContextResult:
    """Normalized maritime context that cannot claim operational authority."""

    internal_id: UUID
    readings: tuple[MaritimeContextReading, ...]
    measurements_authoritative: bool = field(default=False, init=False)
    context_only: bool = field(default=True, init=False)
    navigation_authority: bool = field(default=False, init=False)
    diagnostic_authority: bool = field(default=False, init=False)


@runtime_checkable
class WeatherProvider(Protocol):
    provider_name: str
    adapter_version: str

    def observations(
        self,
        request: WeatherRequest | Mapping[str, Any],
    ) -> IntegrationResult[tuple[WeatherSnapshot, ...]]: ...

    def forecast(
        self,
        request: WeatherRequest | Mapping[str, Any],
    ) -> IntegrationResult[tuple[WeatherSnapshot, ...]]: ...


@runtime_checkable
class MaritimeProvider(Protocol):
    provider_name: str
    adapter_version: str

    def operational_context(
        self,
        request: MaritimeContextRequest | Mapping[str, Any],
    ) -> IntegrationResult[MaritimeContextResult | Mapping[str, Any]]: ...


__all__ = [
    "MaritimeContextReading",
    "MaritimeContextRequest",
    "MaritimeContextResult",
    "MaritimeProvider",
    "MaritimeSourceKind",
    "WeatherMetric",
    "WeatherProvider",
    "WeatherRequest",
    "WeatherSnapshot",
]
