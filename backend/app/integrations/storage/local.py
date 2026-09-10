"""Private filesystem implementation of the object-storage port for local use."""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path, PurePosixPath
import tempfile
import time
from typing import Any, BinaryIO, Mapping, Optional
from urllib.parse import urlencode

from app.core.integration import IntegrationFailure, IntegrationResult
from app.modules.datasets.ports import StoredObject


_CHUNK_SIZE = 1024 * 1024


class LocalObjectStorageProvider:
    """Stream objects into a private root and mint short-lived API URLs."""

    provider_name = "local"

    def __init__(
        self,
        *,
        root: Path | str,
        public_base_url: str,
        signing_secret: str,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.public_base_url = public_base_url.rstrip("/")
        self._signing_secret = signing_secret.encode("utf-8")

    def _path(self, key: str) -> Path:
        candidate = PurePosixPath(str(key))
        if (
            not key
            or candidate.is_absolute()
            or ".." in candidate.parts
            or "\\" in key
            or any(not part or part == "." for part in candidate.parts)
        ):
            raise ValueError("invalid object key")
        path = (self.root / Path(*candidate.parts)).resolve()
        if path != self.root and self.root not in path.parents:
            raise ValueError("object key escapes storage root")
        return path

    def _failed(self, operation: str, code: str = "storage_error"):
        return IntegrationResult.failed(
            provider=self.provider_name,
            operation=operation,
            failure=IntegrationFailure(
                code=code,
                message="local object-storage operation failed",
                retryable=False,
            ),
        )

    def put_file(
        self,
        file_obj: BinaryIO,
        key: str,
        content_type: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> IntegrationResult[StoredObject]:
        del content_type, metadata
        temporary_path: Path | None = None
        try:
            target = self._path(key)
            target.parent.mkdir(parents=True, exist_ok=True)
            md5 = hashlib.md5()
            sha256 = hashlib.sha256()
            size_bytes = 0
            file_obj.seek(0)
            with tempfile.NamedTemporaryFile(
                dir=target.parent,
                prefix=".geovision-upload-",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                while chunk := file_obj.read(_CHUNK_SIZE):
                    size_bytes += len(chunk)
                    md5.update(chunk)
                    sha256.update(chunk)
                    temporary.write(chunk)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, target)
            temporary_path = None
            stored = StoredObject(
                key=key,
                size_bytes=size_bytes,
                md5_hash=md5.hexdigest(),
                sha256_hash=sha256.hexdigest(),
            )
            return IntegrationResult.succeeded(
                provider=self.provider_name,
                operation="put_file",
                value=stored,
            )
        except (OSError, ValueError):
            return self._failed("put_file")
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def put_bytes(
        self,
        data: bytes,
        key: str,
        content_type: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> IntegrationResult[StoredObject]:
        from io import BytesIO

        return self.put_file(BytesIO(data), key, content_type, metadata)

    def _signature(self, *, key: str, expires: int, for_upload: bool) -> str:
        method = "PUT" if for_upload else "GET"
        message = f"{method}\n{key}\n{expires}".encode("utf-8")
        return hmac.new(self._signing_secret, message, hashlib.sha256).hexdigest()

    def presign(
        self,
        key: str,
        expires_in: int = 3600,
        for_upload: bool = False,
    ) -> IntegrationResult[str]:
        try:
            self._path(key)
            expires = int(time.time()) + int(expires_in)
            query = urlencode(
                {
                    "key": key,
                    "expires": expires,
                    "upload": "1" if for_upload else "0",
                    "signature": self._signature(
                        key=key,
                        expires=expires,
                        for_upload=for_upload,
                    ),
                }
            )
            url = f"{self.public_base_url}/datasets/storage/local?{query}"
            return IntegrationResult.succeeded(
                provider=self.provider_name,
                operation="presign",
                value=url,
            )
        except (TypeError, ValueError):
            return self._failed("presign", "storage_invalid_request")

    def validate_signature(
        self,
        *,
        key: str,
        expires: int,
        for_upload: bool,
        signature: str,
    ) -> bool:
        if expires < int(time.time()):
            return False
        expected = self._signature(
            key=key,
            expires=expires,
            for_upload=for_upload,
        )
        return hmac.compare_digest(expected, signature)

    def delete(self, key: str) -> IntegrationResult[bool]:
        try:
            self._path(key).unlink(missing_ok=True)
        except (OSError, ValueError):
            return self._failed("delete")
        return IntegrationResult.succeeded(
            provider=self.provider_name,
            operation="delete",
            value=True,
        )

    def exists(self, key: str) -> IntegrationResult[bool]:
        try:
            value = self._path(key).is_file()
        except ValueError:
            return self._failed("exists", "storage_invalid_request")
        return IntegrationResult.succeeded(
            provider=self.provider_name,
            operation="exists",
            value=value,
        )

    def stat(self, key: str) -> IntegrationResult[Optional[Mapping[str, Any]]]:
        try:
            path = self._path(key)
            if path.is_file():
                md5 = hashlib.md5()
                sha256 = hashlib.sha256()
                with path.open("rb") as stored:
                    while chunk := stored.read(_CHUNK_SIZE):
                        md5.update(chunk)
                        sha256.update(chunk)
                value: Optional[Mapping[str, Any]] = {
                    "size_bytes": path.stat().st_size,
                    "md5_hash": md5.hexdigest(),
                    "sha256_hash": sha256.hexdigest(),
                }
            else:
                value = None
        except (OSError, ValueError):
            return self._failed("stat")
        return IntegrationResult.succeeded(
            provider=self.provider_name,
            operation="stat",
            value=value,
        )

    def get_bytes(self, key: str) -> IntegrationResult[bytes]:
        try:
            value = self._path(key).read_bytes()
        except FileNotFoundError:
            return self._failed("get_bytes", "storage_not_found")
        except (OSError, ValueError):
            return self._failed("get_bytes")
        return IntegrationResult.succeeded(
            provider=self.provider_name,
            operation="get_bytes",
            value=value,
        )

    def path_for(self, key: str) -> Path:
        """Return a checked path for the authenticated local streaming route."""

        return self._path(key)

    def object_uri(self, key: str) -> str:
        self._path(key)
        return f"local://{key}"


__all__ = ["LocalObjectStorageProvider"]
