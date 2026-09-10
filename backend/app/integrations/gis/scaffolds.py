"""Named future GIS adapters that deliberately perform no network I/O."""

from __future__ import annotations

from app.core.integration import TimeoutPolicy

from .unavailable import UnavailableGISProvider


class ArcGISProviderScaffold(UnavailableGISProvider):
    provider_name = "arcgis"

    def __init__(
        self,
        *,
        credentials_configured: bool,
        timeout_policy: TimeoutPolicy,
    ) -> None:
        reason = (
            "ArcGIS credentials are present, but live connectivity has not been "
            "implemented or approved"
            if credentials_configured
            else "ArcGIS credentials are not configured and live connectivity has "
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


__all__ = ["ArcGISProviderScaffold"]
