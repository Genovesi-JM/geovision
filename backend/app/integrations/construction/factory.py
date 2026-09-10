"""Fail-closed construction provider selection at the composition boundary."""

from __future__ import annotations

from app.core.config import Settings, settings
from app.core.integration import TimeoutPolicy
from app.modules.operations.ports import ConstructionProvider


def _timeout_policy(config: Settings) -> TimeoutPolicy:
    return TimeoutPolicy(
        connect_seconds=config.integration_connect_timeout_seconds,
        read_seconds=config.integration_read_timeout_seconds,
        write_seconds=config.integration_read_timeout_seconds,
        pool_seconds=config.integration_connect_timeout_seconds,
    )


def create_construction_provider(
    config: Settings = settings,
    provider_name: str | None = None,
) -> ConstructionProvider:
    raw_name = config.construction_provider if provider_name is None else provider_name
    selected = str(raw_name).strip().lower().replace("-", "_") or "none"
    timeout_policy = _timeout_policy(config)

    if selected in {"fake", "deterministic"}:
        if not config.is_deployed:
            from .fake import FakeConstructionProvider

            return FakeConstructionProvider()
        from .unavailable import UnavailableConstructionProvider

        return UnavailableConstructionProvider(
            "fake",
            "Deterministic construction fixtures are disabled in deployed environments",
            failure_code="fixture_disabled",
            timeout_policy=timeout_policy,
        )

    from .scaffolds import (
        AutodeskAPSConstructionScaffold,
        BentleyITwinConstructionScaffold,
        ProcoreConstructionScaffold,
        TrimbleConstructionScaffold,
    )

    scaffolds = {
        "autodesk_aps": (
            AutodeskAPSConstructionScaffold,
            config.autodesk_aps_configuration_complete,
        ),
        "procore": (
            ProcoreConstructionScaffold,
            config.procore_configuration_complete,
        ),
        "bentley_itwin": (
            BentleyITwinConstructionScaffold,
            config.bentley_itwin_configuration_complete,
        ),
        "trimble": (
            TrimbleConstructionScaffold,
            config.trimble_configuration_complete,
        ),
    }
    if selected in scaffolds:
        scaffold_type, credentials_configured = scaffolds[selected]
        return scaffold_type(
            credentials_configured=credentials_configured,
            timeout_policy=timeout_policy,
        )

    from .unavailable import UnavailableConstructionProvider

    if selected in {"none", "null"}:
        return UnavailableConstructionProvider(
            selected,
            "Construction-system synchronization is disabled",
            failure_code="integration_disabled",
            timeout_policy=timeout_policy,
        )
    return UnavailableConstructionProvider(
        selected,
        f"Construction provider '{selected}' is not supported",
        failure_code="unsupported_provider",
        timeout_policy=timeout_policy,
    )


__all__ = ["create_construction_provider"]
