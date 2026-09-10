"""Provider ports owned by the monitoring domain."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional, Protocol, runtime_checkable

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

    def operational_context(
        self,
        request: Mapping[str, Any],
    ) -> IntegrationResult[Mapping[str, Any]]: ...


__all__ = [
    "MaritimeProvider",
    "WeatherMetric",
    "WeatherProvider",
    "WeatherRequest",
    "WeatherSnapshot",
]
