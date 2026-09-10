"""Fail-closed asset-management provider selection."""

from __future__ import annotations

from app.core.config import Settings, settings
from app.core.integration import TimeoutPolicy
from app.modules.assets.ports import AssetManagementProvider


def _timeout_policy(config: Settings) -> TimeoutPolicy:
    return TimeoutPolicy(
        connect_seconds=config.integration_connect_timeout_seconds,
        read_seconds=config.integration_read_timeout_seconds,
        write_seconds=config.integration_read_timeout_seconds,
        pool_seconds=config.integration_connect_timeout_seconds,
    )


def create_asset_management_provider(
    config: Settings = settings,
    provider_name: str | None = None,
) -> AssetManagementProvider:
    raw_name = (
        config.asset_management_provider if provider_name is None else provider_name
    )
    selected = str(raw_name).strip().lower().replace("-", "_") or "none"
    timeout_policy = _timeout_policy(config)

    if selected in {"fake", "deterministic"}:
        if not config.is_deployed:
            from .fake import FakeAssetManagementProvider

            return FakeAssetManagementProvider()
        from .unavailable import UnavailableAssetManagementProvider

        return UnavailableAssetManagementProvider(
            "fake",
            "Deterministic asset-management fixtures are disabled in deployed environments",
            failure_code="fixture_disabled",
            timeout_policy=timeout_policy,
        )

    if selected == "seequent":
        from .scaffolds import SeequentAssetManagementScaffold

        return SeequentAssetManagementScaffold(
            credentials_configured=config.seequent_configuration_complete,
            timeout_policy=timeout_policy,
        )
    if selected == "mine_enterprise":
        from .scaffolds import MineEnterpriseSystemScaffold

        return MineEnterpriseSystemScaffold(timeout_policy=timeout_policy)

    from .scaffolds import (
        CustomerCMMSAssetManagementScaffold,
        Dynamics365AssetManagementScaffold,
        IBMMaximoAssetManagementScaffold,
        SAPEAMAssetManagementScaffold,
    )

    registry_scaffolds = {
        "sap_eam": SAPEAMAssetManagementScaffold,
        "ibm_maximo": IBMMaximoAssetManagementScaffold,
        "dynamics_365_asset_management": Dynamics365AssetManagementScaffold,
        "customer_cmms": CustomerCMMSAssetManagementScaffold,
    }
    if selected in registry_scaffolds:
        return registry_scaffolds[selected](timeout_policy=timeout_policy)

    from .unavailable import UnavailableAssetManagementProvider

    if selected in {"none", "null"}:
        return UnavailableAssetManagementProvider(
            selected,
            "Asset-management synchronization is disabled",
            failure_code="integration_disabled",
            timeout_policy=timeout_policy,
        )
    return UnavailableAssetManagementProvider(
        selected,
        f"Asset-management provider '{selected}' is not supported",
        failure_code="unsupported_provider",
        timeout_policy=timeout_policy,
    )


__all__ = ["create_asset_management_provider"]
