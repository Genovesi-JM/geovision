"""Fail-closed GIS provider selection at the composition boundary."""

from __future__ import annotations

from app.core.config import Settings, settings
from app.core.integration import RetryPolicy, TimeoutPolicy
from app.modules.assets.ports import GISProvider


def _timeout_policy(config: Settings) -> TimeoutPolicy:
    return TimeoutPolicy(
        connect_seconds=config.integration_connect_timeout_seconds,
        read_seconds=config.integration_read_timeout_seconds,
        write_seconds=config.integration_read_timeout_seconds,
        pool_seconds=config.integration_connect_timeout_seconds,
    )


def _retry_policy(config: Settings) -> RetryPolicy:
    return RetryPolicy(
        max_attempts=config.integration_retry_attempts,
        initial_delay_seconds=config.integration_retry_initial_seconds,
        max_delay_seconds=config.integration_retry_max_seconds,
    )


def create_gis_provider(
    config: Settings = settings,
    provider_name: str | None = None,
) -> GISProvider:
    raw_name = config.gis_provider if provider_name is None else provider_name
    selected = str(raw_name).strip().lower().replace("-", "_") or "none"
    timeout_policy = _timeout_policy(config)

    if selected in {"fake", "deterministic"}:
        if not config.is_deployed:
            from .fake import FakeGISProvider

            return FakeGISProvider()
        from .unavailable import UnavailableGISProvider

        return UnavailableGISProvider(
            "fake",
            "Deterministic GIS fixtures are disabled in deployed environments",
            failure_code="fixture_disabled",
            timeout_policy=timeout_policy,
        )
    if selected == "arcgis":
        from .scaffolds import ArcGISProviderScaffold

        return ArcGISProviderScaffold(
            credentials_configured=config.arcgis_configuration_complete,
            timeout_policy=timeout_policy,
        )
    if selected == "miteco":
        from .miteco import MitecoOgcFeaturesProvider

        return MitecoOgcFeaturesProvider(
            base_url=config.miteco_ogc_features_base_url,
            timeout_policy=timeout_policy,
            retry_policy=_retry_policy(config),
            max_features=config.miteco_gis_max_features,
            max_response_bytes=config.miteco_gis_max_response_bytes,
        )

    from .unavailable import UnavailableGISProvider

    if selected in {"none", "null"}:
        return UnavailableGISProvider(
            selected,
            "GIS layer queries are disabled",
            failure_code="integration_disabled",
            timeout_policy=timeout_policy,
        )
    return UnavailableGISProvider(
        selected,
        f"GIS provider '{selected}' is not supported",
        failure_code="unsupported_provider",
        timeout_policy=timeout_policy,
    )


__all__ = ["create_gis_provider"]
