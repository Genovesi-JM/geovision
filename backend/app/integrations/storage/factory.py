"""Lazy object-storage provider selection."""

from __future__ import annotations

from urllib.parse import urlsplit

from app.core.config import Settings, settings
from app.core.integration import IntegrationConfigurationError
from app.modules.datasets.ports import ObjectStorageProvider


def create_object_storage_provider(config: Settings = settings) -> ObjectStorageProvider:
    provider_name = config.object_storage_provider
    if provider_name == "local":
        if config.is_deployed:
            raise IntegrationConfigurationError(
                provider=provider_name,
                operation="initialize",
                message="local object storage is not allowed in deployed environments",
            )
        from .local import LocalObjectStorageProvider

        return LocalObjectStorageProvider(
            root=config.local_storage_root,
            public_base_url=config.backend_base,
            signing_secret=config.secret_key,
        )

    if provider_name in {"azure", "azure_blob"}:
        if not (
            config.azure_storage_connection_string
            or config.azure_storage_account_url
        ):
            raise IntegrationConfigurationError(
                provider="azure_blob",
                operation="initialize",
                message="Azure storage account URL or connection string is required",
            )
        if bool(config.azure_storage_account_name) != bool(
            config.azure_storage_account_key
        ):
            raise IntegrationConfigurationError(
                provider="azure_blob",
                operation="initialize",
                message="Azure account-name/key credentials are incomplete",
            )
        if config.azure_storage_account_url:
            parsed = urlsplit(config.azure_storage_account_url)
            allowed_schemes = {"https"} if config.is_deployed else {"http", "https"}
            if (
                parsed.scheme not in allowed_schemes
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise IntegrationConfigurationError(
                    provider="azure_blob",
                    operation="initialize",
                    message="Azure storage account URL is invalid",
                )
        from .azure_blob import AzureBlobStorageProvider

        return AzureBlobStorageProvider(
            container=config.azure_storage_container,
            account_url=config.azure_storage_account_url,
            connection_string=config.azure_storage_connection_string,
            account_name=config.azure_storage_account_name,
            account_key=config.azure_storage_account_key,
            use_managed_identity=config.is_deployed,
            managed_identity_client_id=config.azure_managed_identity_client_id,
        )

    if provider_name not in {"s3", "s3_compatible"}:
        raise IntegrationConfigurationError(
            provider=provider_name or "object_storage",
            operation="initialize",
            message="unsupported object-storage provider",
        )
    if bool(config.s3_access_key_id) != bool(config.s3_secret_access_key):
        raise IntegrationConfigurationError(
            provider=provider_name,
            operation="initialize",
            message="explicit object-storage credentials are incomplete",
        )

    # Keep provider SDKs outside import paths used by fake providers and domains.
    from .s3 import S3ObjectStorageProvider

    return S3ObjectStorageProvider(
        bucket=config.effective_s3_bucket,
        region=config.s3_region,
        endpoint_url=config.s3_endpoint_url,
        access_key_id=config.s3_access_key_id,
        secret_access_key=config.s3_secret_access_key,
        retry_attempts=config.integration_retry_attempts,
        connect_timeout_seconds=config.integration_connect_timeout_seconds,
        read_timeout_seconds=config.integration_read_timeout_seconds,
    )


__all__ = ["create_object_storage_provider"]
