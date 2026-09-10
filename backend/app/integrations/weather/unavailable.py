"""Explicit disabled/future weather adapter."""

from __future__ import annotations

from typing import Any, Mapping

from app.core.integration import IntegrationFailure, IntegrationResult, IntegrationStatus
from app.modules.monitoring.ports import WeatherRequest, WeatherSnapshot


class UnavailableWeatherProvider:
    adapter_version = "unavailable-unversioned"

    def __init__(self, provider_name: str, reason: str) -> None:
        self.provider_name = provider_name
        self.reason = reason

    def _result(self, operation: str) -> IntegrationResult[tuple[WeatherSnapshot, ...]]:
        return IntegrationResult.failed(
            provider=self.provider_name,
            operation=operation,
            status=IntegrationStatus.NOT_CONFIGURED,
            failure=IntegrationFailure("provider_not_configured", self.reason),
        )

    def observations(
        self,
        request: WeatherRequest | Mapping[str, Any],
    ) -> IntegrationResult[tuple[WeatherSnapshot, ...]]:
        del request
        return self._result("observations")

    def forecast(
        self,
        request: WeatherRequest | Mapping[str, Any],
    ) -> IntegrationResult[tuple[WeatherSnapshot, ...]]:
        del request
        return self._result("forecast")
