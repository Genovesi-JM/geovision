"""Named future construction adapters that deliberately perform no network I/O."""

from __future__ import annotations

from app.core.integration import TimeoutPolicy

from .unavailable import UnavailableConstructionProvider


def _reason(display_name: str, credentials_configured: bool) -> str:
    if credentials_configured:
        return (
            f"{display_name} credentials are present, but live connectivity has not "
            "been implemented or approved"
        )
    return (
        f"{display_name} credentials are not configured and live connectivity has "
        "not been implemented or approved"
    )


class _VendorConstructionScaffold(UnavailableConstructionProvider):
    display_name: str
    provider_name: str

    def __init__(
        self,
        *,
        credentials_configured: bool,
        timeout_policy: TimeoutPolicy,
    ) -> None:
        super().__init__(
            self.provider_name,
            _reason(self.display_name, credentials_configured),
            failure_code=(
                "adapter_unavailable"
                if credentials_configured
                else "provider_not_configured"
            ),
            credentials_configured=credentials_configured,
            timeout_policy=timeout_policy,
        )


class AutodeskAPSConstructionScaffold(_VendorConstructionScaffold):
    display_name = "Autodesk APS"
    provider_name = "autodesk_aps"


class ProcoreConstructionScaffold(_VendorConstructionScaffold):
    display_name = "Procore"
    provider_name = "procore"


class BentleyITwinConstructionScaffold(_VendorConstructionScaffold):
    display_name = "Bentley iTwin"
    provider_name = "bentley_itwin"


class TrimbleConstructionScaffold(_VendorConstructionScaffold):
    display_name = "Trimble"
    provider_name = "trimble"


__all__ = [
    "AutodeskAPSConstructionScaffold",
    "BentleyITwinConstructionScaffold",
    "ProcoreConstructionScaffold",
    "TrimbleConstructionScaffold",
]
