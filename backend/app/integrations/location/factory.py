"""Fail-closed location provider selection."""

from __future__ import annotations

from app.core.config import Settings, settings
from app.modules.assets.location_ports import LocationProvider


def create_location_provider(
    config: Settings = settings,
    provider_name: str | None = None,
) -> LocationProvider:
    selected = str(provider_name or config.location_provider).strip().lower()
    selected = selected.replace("-", "_") or "none"
    if selected in {"fake", "deterministic"}:
        if not config.is_deployed:
            from .fake import DeterministicLocationProvider

            return DeterministicLocationProvider()
        from .unavailable import UnavailableLocationProvider

        return UnavailableLocationProvider(
            selected,
            "Deterministic location fixtures are disabled when deployed",
        )
    if selected in {"google", "google_maps"} and config.google_maps_server_api_key:
        from .google_maps import GoogleMapsLocationProvider

        return GoogleMapsLocationProvider(
            api_key=config.google_maps_server_api_key,
            connect_timeout_seconds=config.integration_connect_timeout_seconds,
            read_timeout_seconds=config.integration_read_timeout_seconds,
        )

    from .unavailable import UnavailableLocationProvider

    if selected in {"google", "google_maps"}:
        return UnavailableLocationProvider(
            selected, "Google Maps server key is missing"
        )
    if selected in {"none", "null"}:
        return UnavailableLocationProvider(selected, "Location services are disabled")
    return UnavailableLocationProvider(
        selected,
        f"Location provider '{selected}' is not supported",
    )


__all__ = ["create_location_provider"]
