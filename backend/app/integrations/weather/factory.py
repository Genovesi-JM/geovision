"""Weather provider composition without domain-to-vendor imports."""

from __future__ import annotations

from app.core.config import Settings, settings
from app.modules.monitoring.ports import WeatherProvider

from .aemet import AemetOpenDataProvider
from .azure_maps import AzureMapsWeatherProvider
from .fake import DeterministicWeatherProvider
from .unavailable import UnavailableWeatherProvider


def create_weather_provider(
    *, provider_name: str | None = None, config: Settings = settings
) -> WeatherProvider:
    selected = (provider_name or config.weather_provider).strip().lower().replace("-", "_")
    if selected in {"fake", "deterministic"}:
        return DeterministicWeatherProvider()
    if selected in {"aemet", "aemet_opendata"}:
        if not config.aemet_api_key:
            return UnavailableWeatherProvider("aemet", "AEMET_API_KEY is not configured")
        return AemetOpenDataProvider(
            base_url=config.aemet_base_url,
            api_key=config.aemet_api_key,
            connect_timeout_seconds=config.integration_connect_timeout_seconds,
            read_timeout_seconds=config.integration_read_timeout_seconds,
            retry_attempts=config.integration_retry_attempts,
            retry_initial_seconds=config.integration_retry_initial_seconds,
            retry_max_seconds=config.integration_retry_max_seconds,
        )
    if selected in {"azure_maps", "azure_maps_weather"}:
        return AzureMapsWeatherProvider()
    reason = (
        "Weather acquisition is disabled"
        if selected in {"none", "null"}
        else f"Weather provider '{selected}' is not implemented"
    )
    return UnavailableWeatherProvider(selected or "none", reason)


__all__ = ["create_weather_provider"]
