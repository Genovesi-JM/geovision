"""Unavailable asset-management adapter with normalized safe failures."""

from __future__ import annotations

from typing import Any, Mapping

from app.core.integration import (
    IntegrationFailure,
    IntegrationResult,
    IntegrationStatus,
    TimeoutPolicy,
)
from app.modules.assets.ports import (
    AssetSynchronizationReceipt,
    AssetSynchronizationRequest,
)


class UnavailableAssetManagementProvider:
    """Return explicit failures without retaining credentials or doing I/O."""

    adapter_version = "unavailable-asset-management-v1"

    def __init__(
        self,
        provider_name: str,
        reason: str,
        *,
        failure_code: str = "provider_not_configured",
        credentials_configured: bool = False,
        timeout_policy: TimeoutPolicy | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.reason = reason
        self.failure_code = failure_code
        self.credentials_configured = credentials_configured
        self.timeout_policy = timeout_policy or TimeoutPolicy()

    def synchronize_asset(
        self,
        request: AssetSynchronizationRequest | Mapping[str, Any],
        *,
        idempotency_key: str,
    ) -> IntegrationResult[AssetSynchronizationReceipt | Mapping[str, Any]]:
        del request, idempotency_key
        return IntegrationResult.failed(
            provider=self.provider_name,
            operation="synchronize_asset",
            status=IntegrationStatus.NOT_CONFIGURED,
            failure=IntegrationFailure(
                code=self.failure_code,
                message=self.reason,
                retryable=False,
            ),
        )


__all__ = ["UnavailableAssetManagementProvider"]
