"""Compatibility facade for provider-neutral GeoVision object storage."""

from __future__ import annotations

import mimetypes
from pathlib import Path
import re
from typing import Any, BinaryIO, Optional

from app.core.integration import IntegrationResult
from app.core.time import utc_now
from app.modules.datasets.ports import ObjectStorageProvider, StoredObject


class StorageService:
    """GeoVision storage operations backed by an injected provider."""

    def __init__(self, provider: ObjectStorageProvider | None = None) -> None:
        if provider is None:
            from app.integrations.storage import create_object_storage_provider

            provider = create_object_storage_provider()
        self.provider = provider

    @property
    def provider_name(self) -> str:
        return self.provider.provider_name

    @property
    def bucket(self) -> Optional[str]:
        return getattr(self.provider, "bucket", None)

    @property
    def region(self) -> Optional[str]:
        return getattr(self.provider, "region", None)

    @property
    def endpoint_url(self) -> Optional[str]:
        return getattr(self.provider, "endpoint_url", None)

    @property
    def client(self) -> Any:
        return getattr(self.provider, "client", None)

    @staticmethod
    def _value(result: IntegrationResult[Any]) -> Any:
        if result.ok:
            return result.value
        failure = result.failure
        message = failure.message if failure else "object-storage operation failed"
        raise RuntimeError(message)

    def generate_key(
        self,
        company_id: str,
        site_id: str,
        dataset_id: str,
        filename: str,
    ) -> str:
        """Generate the existing provider-independent dataset object key."""

        safe_filename = "".join(
            character for character in filename if character.isalnum() or character in "._-"
        )
        timestamp = utc_now().strftime("%Y%m%d_%H%M%S")
        return (
            f"companies/{company_id}/sites/{site_id}/datasets/"
            f"{dataset_id}/{timestamp}_{safe_filename}"
        )

    def generate_dataset_key(
        self,
        *,
        organization_id: str,
        asset_id: str,
        mission_id: str | None,
        dataset_id: str,
        file_id: str,
        area: str,
        filename: str,
    ) -> str:
        """Build a stable, provider-independent key for canonical datasets."""

        identifiers = {
            "organization_id": organization_id,
            "asset_id": asset_id,
            "dataset_id": dataset_id,
            "file_id": file_id,
        }
        for label, value in identifiers.items():
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", value or ""):
                raise ValueError(f"invalid {label}")
        mission_segment = mission_id or "standalone"
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", mission_segment):
            raise ValueError("invalid mission_id")
        normalized_area = area.strip().lower()
        if normalized_area not in {"raw", "processed", "derived", "reports"}:
            raise ValueError("invalid object area")
        safe_filename = "".join(
            character
            for character in Path(filename).name
            if character.isalnum() or character in "._-"
        )
        if not safe_filename:
            raise ValueError("invalid filename")
        return (
            f"organizations/{organization_id}/assets/{asset_id}/missions/"
            f"{mission_segment}/datasets/{dataset_id}/{normalized_area}/"
            f"{file_id}_{safe_filename}"
        )

    def upload_file(
        self,
        file_obj: BinaryIO,
        key: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> tuple[str, int, str, str]:
        stored: StoredObject = self._value(
            self.provider.put_file(file_obj, key, content_type, metadata)
        )
        return stored.key, stored.size_bytes, stored.md5_hash, stored.sha256_hash

    def upload_bytes(
        self,
        data: bytes,
        key: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> tuple[str, int, str, str]:
        stored: StoredObject = self._value(
            self.provider.put_bytes(data, key, content_type, metadata)
        )
        return stored.key, stored.size_bytes, stored.md5_hash, stored.sha256_hash

    def get_presigned_url(
        self,
        key: str,
        expires_in: int = 3600,
        for_upload: bool = False,
    ) -> str:
        return self._value(self.provider.presign(key, expires_in, for_upload))

    def delete_file(self, key: str) -> bool:
        return bool(self._value(self.provider.delete(key)))

    def file_exists(self, key: str) -> bool:
        return bool(self._value(self.provider.exists(key)))

    def stat_file(self, key: str) -> Optional[dict[str, Any]]:
        value = self._value(self.provider.stat(key))
        return dict(value) if value is not None else None

    def get_file_info(self, key: str) -> Optional[dict[str, Any]]:
        return self.stat_file(key)

    def object_uri(self, key: str) -> str:
        resolver = getattr(self.provider, "object_uri", None)
        if callable(resolver):
            return str(resolver(key))
        return f"{self.provider_name}://{key}"

    def download_file(self, key: str) -> bytes:
        try:
            return self._value(self.provider.get_bytes(key))
        except RuntimeError as exc:
            raise RuntimeError(f"Ficheiro não encontrado no armazenamento: {exc}") from exc

    def generate_document_key(
        self,
        company_id: str,
        doc_id: str,
        filename: str,
    ) -> str:
        safe_name = "".join(
            character for character in filename if character.isalnum() or character in "._- "
        ).strip()
        return f"documents/{company_id}/{doc_id}_{safe_name}"


def is_s3_key(path: Optional[str]) -> bool:
    """Retain the legacy storage-key check while providers are generalized."""

    return bool(path and not path.startswith("/"))


_storage_service: Optional[StorageService] = None


def get_storage_service(
    provider: ObjectStorageProvider | None = None,
) -> StorageService:
    """Resolve the configured service, or wrap an explicitly injected provider."""

    global _storage_service
    if provider is not None:
        return StorageService(provider)
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service


FILE_TYPE_MAP = {
    ".tif": "geotiff",
    ".tiff": "geotiff",
    ".las": "pointcloud_las",
    ".laz": "pointcloud_laz",
    ".e57": "pointcloud_e57",
    ".ply": "pointcloud_ply",
    ".xyz": "pointcloud_ply",
    ".obj": "model_obj",
    ".fbx": "model_fbx",
    ".shp": "shapefile",
    ".geojson": "geojson",
    ".json": "geojson",
    ".dxf": "dxf",
    ".dwg": "dwg",
    ".pdf": "pdf",
    ".csv": "csv",
    ".docx": "docx",
    ".doc": "docx",
    ".jpg": "image_jpg",
    ".jpeg": "image_jpg",
    ".png": "image_png",
}


def detect_file_type(filename: str) -> str:
    return FILE_TYPE_MAP.get(Path(filename).suffix.lower(), "other")


def detect_mime_type(filename: str) -> str:
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or "application/octet-stream"


__all__ = [
    "FILE_TYPE_MAP",
    "StorageService",
    "detect_file_type",
    "detect_mime_type",
    "get_storage_service",
    "is_s3_key",
]
