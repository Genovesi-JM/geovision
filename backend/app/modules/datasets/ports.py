"""Provider ports owned by the datasets domain."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, BinaryIO, Mapping, Optional, Protocol, runtime_checkable

from app.core.integration import IntegrationResult


@dataclass(frozen=True, slots=True)
class StoredObject:
    key: str
    size_bytes: int
    md5_hash: str
    sha256_hash: str


@dataclass(frozen=True, slots=True)
class SatelliteSearchRequest:
    geometry: Mapping[str, Any]
    starts_at: datetime
    ends_at: datetime
    collection: str = "sentinel-2-l2a"
    max_cloud_cover_percent: float = 60.0
    limit: int = 10


@dataclass(frozen=True, slots=True)
class SatelliteAssetDescriptor:
    key: str
    href: str
    media_type: Optional[str] = None
    title: Optional[str] = None
    roles: tuple[str, ...] = ()
    bands: tuple[str, ...] = ()
    size_bytes: Optional[int] = None
    requires_authentication: bool = False


@dataclass(frozen=True, slots=True)
class SatelliteSceneDescriptor:
    provider_reference: str
    collection: str
    acquired_at: datetime
    published_at: Optional[datetime]
    cloud_cover_percent: Optional[float]
    resolution_meters: Optional[float]
    crs: Optional[str]
    bands: tuple[str, ...]
    bbox: tuple[float, float, float, float] | tuple[()]
    geometry: Optional[Mapping[str, Any]]
    assets: tuple[SatelliteAssetDescriptor, ...]
    source_link: Optional[str]
    provenance: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class SatelliteDownloadedAsset:
    scene_reference: str
    asset_key: str
    filename: str
    media_type: str
    content: bytes


@runtime_checkable
class ObjectStorageProvider(Protocol):
    provider_name: str

    def put_file(
        self,
        file_obj: BinaryIO,
        key: str,
        content_type: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> IntegrationResult[StoredObject]: ...

    def put_bytes(
        self,
        data: bytes,
        key: str,
        content_type: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> IntegrationResult[StoredObject]: ...

    def presign(
        self,
        key: str,
        expires_in: int = 3600,
        for_upload: bool = False,
    ) -> IntegrationResult[str]: ...

    def delete(self, key: str) -> IntegrationResult[bool]: ...
    def exists(self, key: str) -> IntegrationResult[bool]: ...
    def stat(self, key: str) -> IntegrationResult[Optional[Mapping[str, Any]]]: ...
    def get_bytes(self, key: str) -> IntegrationResult[bytes]: ...


@runtime_checkable
class SatelliteProvider(Protocol):
    provider_name: str

    def search(
        self,
        request: SatelliteSearchRequest | Mapping[str, Any],
    ) -> IntegrationResult[tuple[SatelliteSceneDescriptor, ...]]: ...

    def download_asset(
        self,
        scene: SatelliteSceneDescriptor,
        asset_key: str,
        *,
        max_bytes: int,
    ) -> IntegrationResult[SatelliteDownloadedAsset]: ...


__all__ = [
    "ObjectStorageProvider",
    "SatelliteAssetDescriptor",
    "SatelliteDownloadedAsset",
    "SatelliteProvider",
    "SatelliteSceneDescriptor",
    "SatelliteSearchRequest",
    "StoredObject",
]
