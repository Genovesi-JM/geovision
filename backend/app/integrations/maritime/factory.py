"""Fail-closed maritime provider selection at the composition boundary."""

from __future__ import annotations

from app.core.config import Settings, settings
from app.core.integration import TimeoutPolicy
from app.modules.monitoring.ports import MaritimeProvider


def _timeout_policy(config: Settings) -> TimeoutPolicy:
    return TimeoutPolicy(
        connect_seconds=config.integration_connect_timeout_seconds,
        read_seconds=config.integration_read_timeout_seconds,
        write_seconds=config.integration_read_timeout_seconds,
        pool_seconds=config.integration_connect_timeout_seconds,
    )


def create_maritime_provider(
    config: Settings = settings,
    provider_name: str | None = None,
) -> MaritimeProvider:
    raw_name = config.maritime_provider if provider_name is None else provider_name
    selected = str(raw_name).strip().lower().replace("-", "_") or "none"
    timeout_policy = _timeout_policy(config)

    if selected in {"fake", "deterministic"}:
        if not config.is_deployed:
            from .fake import DeterministicMaritimeProvider

            return DeterministicMaritimeProvider()
        from .unavailable import UnavailableMaritimeProvider

        return UnavailableMaritimeProvider(
            "fake",
            "Deterministic maritime fixtures are disabled in deployed environments",
            failure_code="fixture_disabled",
            timeout_policy=timeout_policy,
        )

    from .scaffolds import (
        KplerMaritimeScaffold,
        MarineTrafficMaritimeScaffold,
        PuertosDelEstadoMaritimeScaffold,
    )

    scaffolds = {
        "marinetraffic": MarineTrafficMaritimeScaffold,
        "kpler": KplerMaritimeScaffold,
        "puertos_del_estado": PuertosDelEstadoMaritimeScaffold,
    }
    if selected in scaffolds:
        return scaffolds[selected](timeout_policy=timeout_policy)

    from .unavailable import UnavailableMaritimeProvider

    if selected in {"none", "null"}:
        return UnavailableMaritimeProvider(
            selected,
            "Maritime context is disabled",
            failure_code="integration_disabled",
            timeout_policy=timeout_policy,
        )
    return UnavailableMaritimeProvider(
        selected,
        f"Maritime provider '{selected}' is not supported",
        failure_code="unsupported_provider",
        timeout_policy=timeout_policy,
    )


__all__ = ["create_maritime_provider"]
