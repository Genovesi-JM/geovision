"""Lazy object-storage provider selection."""

from __future__ import annotations

from app.core.config import Settings, settings
from app.core.integration import IntegrationConfigurationError
from app.modules.datasets.ports import ObjectStorageProvider


def create_object_storage_provider(config: Settings = settings) -> ObjectStorageProvider:
    provider_name = config.object_storage_provider
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

    # Keep the SDK outside import paths used by fake providers and domains.
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
