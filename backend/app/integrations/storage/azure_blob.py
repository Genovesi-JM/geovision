"""Azure Blob Storage implementation of the datasets object-storage port."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from typing import Any, BinaryIO, Callable, Mapping, Optional
from urllib.parse import quote

from app.core.integration import (
    IntegrationConfigurationError,
    IntegrationFailure,
    IntegrationResult,
    IntegrationStatus,
    IntegrationUnavailableError,
)
from app.modules.datasets.ports import StoredObject


_CHUNK_SIZE = 1024 * 1024


def _measure(file_obj: BinaryIO) -> tuple[int, str, str]:
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    size_bytes = 0
    file_obj.seek(0)
    while chunk := file_obj.read(_CHUNK_SIZE):
        size_bytes += len(chunk)
        md5.update(chunk)
        sha256.update(chunk)
    file_obj.seek(0)
    return size_bytes, md5.hexdigest(), sha256.hexdigest()


class AzureBlobStorageProvider:
    """Stream objects to one private Azure container and issue scoped SAS URLs."""

    provider_name = "azure_blob"

    def __init__(
        self,
        *,
        container: str,
        account_url: Optional[str] = None,
        connection_string: Optional[str] = None,
        account_name: Optional[str] = None,
        account_key: Optional[str] = None,
        use_managed_identity: bool = False,
        managed_identity_client_id: Optional[str] = None,
        service_client: Any = None,
        sas_factory: Optional[Callable[..., str]] = None,
    ) -> None:
        if not container or "/" in container:
            raise IntegrationConfigurationError(
                provider=self.provider_name,
                operation="initialize",
                message="Azure storage container is invalid",
            )
        connection_values = self._connection_values(connection_string)
        self.container = container
        self.account_url = (account_url or "").rstrip("/") or None
        self.account_name = (
            account_name
            or connection_values.get("accountname")
            or self._account_name_from_url(self.account_url)
        )
        self._account_key = account_key or connection_values.get("accountkey")
        self._sas_factory = sas_factory
        try:
            if service_client is not None:
                self.service_client = service_client
            else:
                from azure.storage.blob import BlobServiceClient

                if connection_string:
                    self.service_client = BlobServiceClient.from_connection_string(
                        connection_string
                    )
                elif self.account_url:
                    credential: Any = account_key
                    if not credential:
                        if use_managed_identity:
                            from azure.identity import ManagedIdentityCredential

                            credential = ManagedIdentityCredential(
                                client_id=managed_identity_client_id
                            )
                        else:
                            from azure.identity import DefaultAzureCredential

                            credential = DefaultAzureCredential()
                    self.service_client = BlobServiceClient(
                        account_url=self.account_url,
                        credential=credential,
                    )
                else:
                    raise IntegrationConfigurationError(
                        provider=self.provider_name,
                        operation="initialize",
                        message=(
                            "Azure storage requires an account URL or connection string"
                        ),
                    )
            self.container_client = self.service_client.get_container_client(container)
            self.account_name = self.account_name or getattr(
                self.service_client, "account_name", None
            )
            self.account_url = self.account_url or str(
                getattr(self.service_client, "url", "") or ""
            ).rstrip("/") or None
        except IntegrationConfigurationError:
            raise
        except Exception as exc:
            raise IntegrationUnavailableError(
                provider=self.provider_name,
                operation="initialize",
                message="Azure Blob client initialization failed",
            ) from exc

    @staticmethod
    def _account_name_from_url(account_url: Optional[str]) -> Optional[str]:
        if not account_url:
            return None
        from urllib.parse import urlsplit

        host = urlsplit(account_url).hostname or ""
        return host.split(".", 1)[0] or None

    @staticmethod
    def _connection_values(connection_string: Optional[str]) -> dict[str, str]:
        values: dict[str, str] = {}
        for component in (connection_string or "").split(";"):
            if "=" not in component:
                continue
            name, value = component.split("=", 1)
            if name.strip() and value.strip():
                values[name.strip().lower()] = value.strip()
        return values

    def _failed(self, operation: str, error: Exception):
        status_code = getattr(error, "status_code", None)
        error_code = str(getattr(error, "error_code", "") or "").lower()
        code = "storage_unavailable"
        message = "Azure Blob request failed"
        retryable = True
        status = IntegrationStatus.RETRYING
        if status_code == 404 or error_code in {"blobnotfound", "containernotfound"}:
            code = "storage_not_found"
            message = "Azure Blob object was not found"
            retryable = False
            status = IntegrationStatus.FAILED
        elif status_code in {401, 403} or error_code in {
            "authenticationfailed",
            "authorizationfailure",
            "authorizationpermissionmismatch",
        }:
            code = "storage_authentication_failed"
            message = "Azure Blob authentication failed"
            retryable = False
            status = IntegrationStatus.FAILED
        elif status_code is not None and int(status_code) < 500:
            code = "storage_invalid_request"
            message = "Azure Blob rejected the request"
            retryable = False
            status = IntegrationStatus.FAILED
        return IntegrationResult.failed(
            provider=self.provider_name,
            operation=operation,
            status=status,
            failure=IntegrationFailure(
                code=code,
                message=message,
                retryable=retryable,
            ),
        )

    def put_file(
        self,
        file_obj: BinaryIO,
        key: str,
        content_type: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> IntegrationResult[StoredObject]:
        try:
            size_bytes, md5_hash, sha256_hash = _measure(file_obj)
            kwargs: dict[str, Any] = {
                "overwrite": True,
                "metadata": (
                    {name: str(value) for name, value in metadata.items()}
                    if metadata
                    else None
                ),
                "length": size_bytes,
            }
            if content_type:
                from azure.storage.blob import ContentSettings

                kwargs["content_settings"] = ContentSettings(content_type=content_type)
            self.container_client.upload_blob(name=key, data=file_obj, **kwargs)
        except Exception as exc:
            return self._failed("put_file", exc)
        return IntegrationResult.succeeded(
            provider=self.provider_name,
            operation="put_file",
            value=StoredObject(
                key=key,
                size_bytes=size_bytes,
                md5_hash=md5_hash,
                sha256_hash=sha256_hash,
            ),
        )

    def put_bytes(
        self,
        data: bytes,
        key: str,
        content_type: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> IntegrationResult[StoredObject]:
        from io import BytesIO

        return self.put_file(BytesIO(data), key, content_type, metadata)

    def presign(
        self,
        key: str,
        expires_in: int = 3600,
        for_upload: bool = False,
    ) -> IntegrationResult[str]:
        try:
            now = datetime.now(timezone.utc)
            expiry = now + timedelta(seconds=expires_in)
            if self._sas_factory is not None:
                sas = self._sas_factory(
                    account_name=self.account_name,
                    container_name=self.container,
                    blob_name=key,
                    account_key=self._account_key,
                    permission="cw" if for_upload else "r",
                    start=now - timedelta(minutes=5),
                    expiry=expiry,
                )
            else:
                from azure.storage.blob import BlobSasPermissions, generate_blob_sas

                permission = (
                    BlobSasPermissions(create=True, write=True)
                    if for_upload
                    else BlobSasPermissions(read=True)
                )
                arguments: dict[str, Any] = {
                    "account_name": self.account_name,
                    "container_name": self.container,
                    "blob_name": key,
                    "permission": permission,
                    "start": now - timedelta(minutes=5),
                    "expiry": expiry,
                }
                if self._account_key:
                    arguments["account_key"] = self._account_key
                else:
                    arguments["user_delegation_key"] = (
                        self.service_client.get_user_delegation_key(
                            key_start_time=arguments["start"],
                            key_expiry_time=expiry,
                        )
                    )
                sas = generate_blob_sas(**arguments)
            if not self.account_name:
                raise ValueError("Azure storage account name is unavailable")
            base = self.account_url or f"https://{self.account_name}.blob.core.windows.net"
            url = f"{base}/{self.container}/{quote(key, safe='/')}?{sas}"
        except Exception as exc:
            return self._failed("presign", exc)
        return IntegrationResult.succeeded(
            provider=self.provider_name,
            operation="presign",
            value=url,
        )

    def delete(self, key: str) -> IntegrationResult[bool]:
        try:
            self.container_client.delete_blob(key, delete_snapshots="include")
        except Exception as exc:
            if getattr(exc, "status_code", None) == 404:
                return IntegrationResult.succeeded(
                    provider=self.provider_name,
                    operation="delete",
                    value=True,
                )
            return self._failed("delete", exc)
        return IntegrationResult.succeeded(
            provider=self.provider_name,
            operation="delete",
            value=True,
        )

    def exists(self, key: str) -> IntegrationResult[bool]:
        try:
            value = bool(self.container_client.get_blob_client(key).exists())
        except Exception as exc:
            return self._failed("exists", exc)
        return IntegrationResult.succeeded(
            provider=self.provider_name,
            operation="exists",
            value=value,
        )

    def stat(self, key: str) -> IntegrationResult[Optional[Mapping[str, Any]]]:
        try:
            properties = self.container_client.get_blob_client(key).get_blob_properties()
            content_settings = getattr(properties, "content_settings", None)
            content_md5 = getattr(content_settings, "content_md5", None)
            value: Optional[Mapping[str, Any]] = {
                "size_bytes": getattr(properties, "size", None),
                "content_type": getattr(
                    content_settings,
                    "content_type",
                    None,
                ),
                "md5_hash": (
                    bytes(content_md5).hex()
                    if isinstance(content_md5, (bytes, bytearray))
                    else None
                ),
                "last_modified": getattr(properties, "last_modified", None),
                "metadata": getattr(properties, "metadata", {}) or {},
            }
        except Exception as exc:
            if getattr(exc, "status_code", None) == 404:
                value = None
            else:
                return self._failed("stat", exc)
        return IntegrationResult.succeeded(
            provider=self.provider_name,
            operation="stat",
            value=value,
        )

    def get_bytes(self, key: str) -> IntegrationResult[bytes]:
        try:
            value = self.container_client.download_blob(key).readall()
        except Exception as exc:
            return self._failed("get_bytes", exc)
        return IntegrationResult.succeeded(
            provider=self.provider_name,
            operation="get_bytes",
            value=value,
        )

    def object_uri(self, key: str) -> str:
        return f"azure://{self.container}/{key}"


__all__ = ["AzureBlobStorageProvider"]
