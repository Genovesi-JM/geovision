"""Deterministic weather adapter used by local acceptance tests."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from app.core.integration import IntegrationFailure, IntegrationResult
from app.modules.monitoring.ports import WeatherMetric, WeatherRequest, WeatherSnapshot


class DeterministicWeatherProvider:
    provider_name = "fake"

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.observation_calls = 0

    def observations(
        self,
        request: WeatherRequest | Mapping[str, Any],
    ) -> IntegrationResult[tuple[WeatherSnapshot, ...]]:
        self.observation_calls += 1
        if self.fail:
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation="observations",
                failure=IntegrationFailure("fixture_failure", "Deterministic weather failure", retryable=True),
            )
        if isinstance(request, WeatherRequest):
            latitude, longitude = request.latitude, request.longitude
            observed_at = request.ends_at
        else:
            latitude = float(request["latitude"])
            longitude = float(request["longitude"])
            observed_at = request.get("ends_at")
        if not isinstance(observed_at, datetime):
            observed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        if observed_at.tzinfo:
            observed_at = observed_at.astimezone(timezone.utc).replace(tzinfo=None)
        snapshot = WeatherSnapshot(
            source_reference="fixture-station",
            source_name="GeoVision deterministic weather station",
            observed_at=observed_at,
            latitude=latitude,
            longitude=longitude,
            distance_km=0.0,
            metrics=(
                WeatherMetric("air_temperature", 22.5, "degC"),
                WeatherMetric("relative_humidity", 64.0, "%"),
                WeatherMetric("precipitation", 0.0, "mm"),
                WeatherMetric("wind_speed", 2.2, "m/s"),
            ),
            provenance={"provider": "deterministic"},
        )
        return IntegrationResult.simulated(
            provider=self.provider_name,
            operation="observations",
            value=(snapshot,),
        )

    def forecast(
        self,
        request: WeatherRequest | Mapping[str, Any],
    ) -> IntegrationResult[tuple[WeatherSnapshot, ...]]:
        return self.observations(request)
