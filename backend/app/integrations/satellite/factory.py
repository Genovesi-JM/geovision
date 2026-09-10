"""Satellite provider composition without domain-to-vendor imports."""

from __future__ import annotations

from app.core.config import Settings, settings
from app.modules.datasets.ports import SatelliteProvider

from .copernicus import CopernicusStacProvider
from .fake import DeterministicSatelliteProvider
from .unavailable import UnavailableSatelliteProvider


def create_satellite_provider(
    *, provider_name: str | None = None, config: Settings = settings
) -> SatelliteProvider:
    selected = (provider_name or config.satellite_provider).strip().lower().replace("-", "_")
    if selected in {"fake", "deterministic"}:
        return DeterministicSatelliteProvider()
    if selected in {"copernicus", "cdse", "sentinel"}:
        return CopernicusStacProvider(
            base_url=config.copernicus_stac_base_url,
            access_token=config.copernicus_access_token,
            allowed_download_hosts=config.copernicus_download_host_list,
            connect_timeout_seconds=config.integration_connect_timeout_seconds,
            read_timeout_seconds=config.integration_read_timeout_seconds,
            retry_attempts=config.integration_retry_attempts,
            retry_initial_seconds=config.integration_retry_initial_seconds,
            retry_max_seconds=config.integration_retry_max_seconds,
        )
    reason = (
        "Satellite acquisition is disabled"
        if selected in {"none", "null"}
        else f"Satellite provider '{selected}' is a documented future adapter"
    )
    return UnavailableSatelliteProvider(selected or "none", reason)


__all__ = ["create_satellite_provider"]
