"""Explicit unavailable satellite adapter for disabled/future providers."""

from __future__ import annotations

from typing import Any, Mapping

from app.core.integration import IntegrationFailure, IntegrationResult, IntegrationStatus
from app.modules.datasets.ports import (
    SatelliteDownloadedAsset,
    SatelliteSceneDescriptor,
    SatelliteSearchRequest,
)


class UnavailableSatelliteProvider:
    def __init__(self, provider_name: str, reason: str) -> None:
        self.provider_name = provider_name
        self.reason = reason

    def _result(self, operation: str):
        return IntegrationResult.failed(
            provider=self.provider_name,
            operation=operation,
            status=IntegrationStatus.NOT_CONFIGURED,
            failure=IntegrationFailure("provider_not_configured", self.reason),
        )

    def search(
        self,
        request: SatelliteSearchRequest | Mapping[str, Any],
    ) -> IntegrationResult[tuple[SatelliteSceneDescriptor, ...]]:
        del request
        return self._result("search")

    def download_asset(
        self,
        scene: SatelliteSceneDescriptor,
        asset_key: str,
        *,
        max_bytes: int,
    ) -> IntegrationResult[SatelliteDownloadedAsset]:
        del scene, asset_key, max_bytes
        return self._result("download_asset")
