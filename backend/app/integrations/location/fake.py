"""Deterministic location provider for local tests and demonstrations."""

from __future__ import annotations

import math

from app.core.integration import IntegrationFailure, IntegrationResult
from app.modules.assets.location_ports import (
    GeoCoordinate,
    PlaceSuggestion,
    ResolvedPlace,
    RouteEstimate,
)


_PLACES = {
    "fake-luanda": ResolvedPlace(
        provider_reference="fake-luanda",
        display_name="Luanda",
        formatted_address="Luanda, Angola",
        coordinate=GeoCoordinate(latitude=-8.838333, longitude=13.234444),
    ),
    "fake-madrid": ResolvedPlace(
        provider_reference="fake-madrid",
        display_name="Madrid",
        formatted_address="Madrid, Spain",
        coordinate=GeoCoordinate(latitude=40.4168, longitude=-3.7038),
    ),
}


class DeterministicLocationProvider:
    provider_name = "deterministic"
    configured = True

    def autocomplete(
        self,
        *,
        query: str,
        session_token: str,
        language_code: str,
        region_code: str | None = None,
        bias: GeoCoordinate | None = None,
    ) -> IntegrationResult[tuple[PlaceSuggestion, ...]]:
        del session_token, language_code, region_code, bias
        normalized = query.strip().casefold()
        suggestions = tuple(
            PlaceSuggestion(
                provider_reference=place.provider_reference,
                primary_text=place.display_name,
                secondary_text=place.formatted_address,
            )
            for place in _PLACES.values()
            if normalized in place.display_name.casefold()
            or normalized in place.formatted_address.casefold()
        )
        return IntegrationResult.simulated(
            provider=self.provider_name,
            operation="autocomplete",
            value=suggestions,
        )

    def resolve_place(
        self,
        *,
        provider_reference: str,
        session_token: str,
        language_code: str,
    ) -> IntegrationResult[ResolvedPlace]:
        del session_token, language_code
        place = _PLACES.get(provider_reference)
        if place is None:
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation="resolve_place",
                failure=IntegrationFailure(
                    code="place_not_found",
                    message="The selected place is unavailable",
                ),
            )
        return IntegrationResult.simulated(
            provider=self.provider_name,
            operation="resolve_place",
            value=place,
        )

    def compute_route(
        self,
        *,
        origin: GeoCoordinate,
        destination: GeoCoordinate,
        language_code: str,
    ) -> IntegrationResult[RouteEstimate]:
        del language_code
        distance = _haversine_meters(origin, destination)
        road_distance = max(0, round(distance * 1.2))
        duration = round(road_distance / 12.5)  # deterministic 45 km/h
        return IntegrationResult.simulated(
            provider=self.provider_name,
            operation="compute_route",
            value=RouteEstimate(
                distance_meters=road_distance,
                duration_seconds=duration,
                traffic_aware=False,
            ),
        )


def _haversine_meters(origin: GeoCoordinate, destination: GeoCoordinate) -> float:
    radius = 6_371_000.0
    lat1, lat2 = math.radians(origin.latitude), math.radians(destination.latitude)
    delta_lat = math.radians(destination.latitude - origin.latitude)
    delta_lon = math.radians(destination.longitude - origin.longitude)
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


__all__ = ["DeterministicLocationProvider"]
