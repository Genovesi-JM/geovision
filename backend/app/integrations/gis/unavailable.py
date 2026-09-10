"""Fail-closed GIS provider used for disabled and future adapters."""

from __future__ import annotations

from typing import Any, Mapping

from app.core.integration import (
    IntegrationFailure,
    IntegrationResult,
    IntegrationStatus,
    TimeoutPolicy,
)
from app.modules.assets.ports import GISLayerQuery, GISLayerResult


class UnavailableGISProvider:
    """Return normalized failures without retaining or contacting credentials."""

    adapter_version = "unavailable-gis-v1"

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

    def query_layers(
        self,
        request: GISLayerQuery | Mapping[str, Any],
    ) -> IntegrationResult[GISLayerResult | Mapping[str, Any]]:
        del request
        return IntegrationResult.failed(
            provider=self.provider_name,
            operation="query_layers",
            status=IntegrationStatus.NOT_CONFIGURED,
            failure=IntegrationFailure(
                code=self.failure_code,
                message=self.reason,
                retryable=False,
            ),
        )


__all__ = ["UnavailableGISProvider"]
