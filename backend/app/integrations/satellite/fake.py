"""Deterministic satellite adapter used by local acceptance tests."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from app.core.integration import IntegrationFailure, IntegrationResult
from app.modules.datasets.ports import (
    SatelliteAssetDescriptor,
    SatelliteDownloadedAsset,
    SatelliteSceneDescriptor,
    SatelliteSearchRequest,
)


class DeterministicSatelliteProvider:
    provider_name = "fake"

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.search_calls = 0

    def search(
        self,
        request: SatelliteSearchRequest | Mapping[str, Any],
    ) -> IntegrationResult[tuple[SatelliteSceneDescriptor, ...]]:
        self.search_calls += 1
        if self.fail:
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation="search",
                failure=IntegrationFailure("fixture_failure", "Deterministic satellite failure", retryable=True),
            )
        if isinstance(request, SatelliteSearchRequest):
            acquired_at = request.ends_at
            collection = request.collection
            geometry = request.geometry
        else:
            acquired_at = request.get("ends_at")
            if not isinstance(acquired_at, datetime):
                acquired_at = datetime.now(timezone.utc).replace(tzinfo=None)
            collection = str(request.get("collection") or "sentinel-2-l2a")
            geometry = request.get("geometry") if isinstance(request.get("geometry"), Mapping) else None
        acquired_at = acquired_at.astimezone(timezone.utc).replace(tzinfo=None) if acquired_at.tzinfo else acquired_at
        scene = SatelliteSceneDescriptor(
            provider_reference=f"fixture-{acquired_at:%Y%m%d}",
            collection=collection,
            acquired_at=acquired_at,
            published_at=acquired_at,
            cloud_cover_percent=4.0,
            resolution_meters=10.0,
            crs="EPSG:4326",
            bands=("B02", "B03", "B04", "B08"),
            bbox=(),
            geometry=geometry,
            assets=(
                SatelliteAssetDescriptor(
                    key="thumbnail",
                    href="https://download.dataspace.copernicus.eu/fixture.jpg",
                    media_type="image/jpeg",
                    title="Deterministic quicklook",
                    roles=("thumbnail",),
                    size_bytes=12,
                ),
            ),
            source_link="https://stac.dataspace.copernicus.eu/v1/fixture",
            provenance={"provider": "deterministic", "catalog_standard": "STAC 1.1.0"},
        )
        return IntegrationResult.simulated(
            provider=self.provider_name,
            operation="search",
            value=(scene,),
        )
    def download_asset(
        self,
        scene: SatelliteSceneDescriptor,
        asset_key: str,
        *,
        max_bytes: int,
    ) -> IntegrationResult[SatelliteDownloadedAsset]:
        content = b"fixture-jpeg"
        if len(content) > max_bytes:
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation="download_asset",
                failure=IntegrationFailure("asset_too_large", "Fixture exceeds download limit"),
            )
        return IntegrationResult.simulated(
            provider=self.provider_name,
            operation="download_asset",
            value=SatelliteDownloadedAsset(
                scene_reference=scene.provider_reference,
                asset_key=asset_key,
                filename="satellite-quicklook.jpg",
                media_type="image/jpeg",
                content=content,
            ),
        )
