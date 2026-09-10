"""Named future asset-management adapters with no network behavior."""

from __future__ import annotations

from app.core.integration import TimeoutPolicy

from .unavailable import UnavailableAssetManagementProvider


class SeequentAssetManagementScaffold(UnavailableAssetManagementProvider):
    provider_name = "seequent"

    def __init__(
        self,
        *,
        credentials_configured: bool,
        timeout_policy: TimeoutPolicy,
    ) -> None:
        reason = (
            "Seequent credentials are present, but live connectivity has not been "
            "implemented or approved"
            if credentials_configured
            else "Seequent credentials are not configured and live connectivity has "
            "not been implemented or approved"
        )
        super().__init__(
            self.provider_name,
            reason,
            failure_code=(
                "adapter_unavailable"
                if credentials_configured
                else "provider_not_configured"
            ),
            credentials_configured=credentials_configured,
            timeout_policy=timeout_policy,
        )


class MineEnterpriseSystemScaffold(UnavailableAssetManagementProvider):
    provider_name = "mine_enterprise"

    def __init__(self, *, timeout_policy: TimeoutPolicy) -> None:
        super().__init__(
            self.provider_name,
            (
                "A concrete mine enterprise system, customer sandbox, and "
                "authentication contract have not been selected"
            ),
            failure_code="provider_not_configured",
            credentials_configured=False,
            timeout_policy=timeout_policy,
        )


class _RegistryBackedAssetManagementScaffold(UnavailableAssetManagementProvider):
    display_name: str
    provider_name: str

    def __init__(self, *, timeout_policy: TimeoutPolicy) -> None:
        super().__init__(
            self.provider_name,
            (
                f"{self.display_name} requires the Phase 32 customer integration "
                "registry, an approved sandbox, and a reviewed authentication and "
                "asset-mapping contract; live connectivity is unavailable"
            ),
            failure_code="provider_not_configured",
            credentials_configured=False,
            timeout_policy=timeout_policy,
        )


class SAPEAMAssetManagementScaffold(_RegistryBackedAssetManagementScaffold):
    display_name = "SAP Enterprise Asset Management"
    provider_name = "sap_eam"


class IBMMaximoAssetManagementScaffold(_RegistryBackedAssetManagementScaffold):
    display_name = "IBM Maximo"
    provider_name = "ibm_maximo"


class Dynamics365AssetManagementScaffold(_RegistryBackedAssetManagementScaffold):
    display_name = "Dynamics 365 Asset Management"
    provider_name = "dynamics_365_asset_management"


class CustomerCMMSAssetManagementScaffold(_RegistryBackedAssetManagementScaffold):
    display_name = "Customer CMMS"
    provider_name = "customer_cmms"


__all__ = [
    "CustomerCMMSAssetManagementScaffold",
    "Dynamics365AssetManagementScaffold",
    "IBMMaximoAssetManagementScaffold",
    "MineEnterpriseSystemScaffold",
    "SAPEAMAssetManagementScaffold",
    "SeequentAssetManagementScaffold",
]
