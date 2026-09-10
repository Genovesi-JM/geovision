"""Fail-closed maritime provider used for disabled and future adapters."""

from __future__ import annotations

from typing import Any, Mapping

from app.core.integration import (
    IntegrationFailure,
    IntegrationResult,
    IntegrationStatus,
    TimeoutPolicy,
)
from app.modules.monitoring.ports import (
    MaritimeContextRequest,
    MaritimeContextResult,
)


class UnavailableMaritimeProvider:
    """Return a normalized failure without retaining input or performing I/O."""

    adapter_version = "unavailable-maritime-v1"

    def __init__(
        self,
        provider_name: str,
        reason: str,
        *,
        failure_code: str = "provider_not_configured",
        timeout_policy: TimeoutPolicy | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.reason = reason
        self.failure_code = failure_code
        self.timeout_policy = timeout_policy or TimeoutPolicy()

    def operational_context(
        self,
        request: MaritimeContextRequest | Mapping[str, Any],
    ) -> IntegrationResult[MaritimeContextResult | Mapping[str, Any]]:
        del request
        return IntegrationResult.failed(
            provider=self.provider_name,
            operation="operational_context",
            status=IntegrationStatus.NOT_CONFIGURED,
            failure=IntegrationFailure(
                code=self.failure_code,
                message=self.reason,
                retryable=False,
            ),
        )


__all__ = ["UnavailableMaritimeProvider"]
