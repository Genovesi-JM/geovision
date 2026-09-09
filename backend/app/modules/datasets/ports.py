"""Provider ports owned by the datasets domain."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, BinaryIO, Mapping, Optional, Protocol, runtime_checkable

from app.core.integration import IntegrationResult


@dataclass(frozen=True, slots=True)
class StoredObject:
    key: str
    size_bytes: int
    md5_hash: str
    sha256_hash: str


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

    def search(self, request: Mapping[str, Any]) -> IntegrationResult[Mapping[str, Any]]: ...


__all__ = ["ObjectStorageProvider", "SatelliteProvider", "StoredObject"]
