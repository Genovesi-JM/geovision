"""Provider-neutral place discovery and routing contracts."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Protocol, runtime_checkable

from app.core.integration import IntegrationResult


@dataclass(frozen=True, slots=True)
class GeoCoordinate:
    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.latitude) or not math.isfinite(self.longitude):
            raise ValueError("coordinates must be finite")
        if not -90 <= self.latitude <= 90:
            raise ValueError("latitude is outside EPSG:4326")
        if not -180 <= self.longitude <= 180:
            raise ValueError("longitude is outside EPSG:4326")


@dataclass(frozen=True, slots=True)
class PlaceSuggestion:
    provider_reference: str
    primary_text: str
    secondary_text: str = ""


@dataclass(frozen=True, slots=True)
class ResolvedPlace:
    provider_reference: str
    display_name: str
    formatted_address: str
    coordinate: GeoCoordinate


@dataclass(frozen=True, slots=True)
class RouteEstimate:
    distance_meters: int
    duration_seconds: int
    encoded_polyline: str | None = None
    traffic_aware: bool = False


@runtime_checkable
class LocationProvider(Protocol):
    provider_name: str

    def autocomplete(
        self,
        *,
        query: str,
        session_token: str,
        language_code: str,
        region_code: str | None = None,
        bias: GeoCoordinate | None = None,
    ) -> IntegrationResult[tuple[PlaceSuggestion, ...]]: ...

    def resolve_place(
        self,
        *,
        provider_reference: str,
        session_token: str,
        language_code: str,
    ) -> IntegrationResult[ResolvedPlace]: ...

    def compute_route(
        self,
        *,
        origin: GeoCoordinate,
        destination: GeoCoordinate,
        language_code: str,
    ) -> IntegrationResult[RouteEstimate]: ...


__all__ = [
    "GeoCoordinate",
    "LocationProvider",
    "PlaceSuggestion",
    "ResolvedPlace",
    "RouteEstimate",
]
