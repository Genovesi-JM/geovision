"""Provider ports owned by the monitoring domain."""

from typing import Any, Mapping, Protocol, runtime_checkable

from app.core.integration import IntegrationResult


@runtime_checkable
class WeatherProvider(Protocol):
    provider_name: str

    def forecast(self, request: Mapping[str, Any]) -> IntegrationResult[Mapping[str, Any]]: ...


@runtime_checkable
class MaritimeProvider(Protocol):
    provider_name: str

    def operational_context(
        self,
        request: Mapping[str, Any],
    ) -> IntegrationResult[Mapping[str, Any]]: ...


__all__ = ["MaritimeProvider", "WeatherProvider"]
