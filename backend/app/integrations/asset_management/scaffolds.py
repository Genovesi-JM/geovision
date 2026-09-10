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


__all__ = ["MineEnterpriseSystemScaffold", "SeequentAssetManagementScaffold"]
