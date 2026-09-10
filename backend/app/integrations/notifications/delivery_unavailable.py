"""Fail-closed adapter for unavailable external notification channels."""

from __future__ import annotations

from app.core.integration import IntegrationFailure, IntegrationResult, IntegrationStatus
from app.modules.notifications.delivery_ports import (
    DeliveryAcknowledgement,
    ExternalDeliveryMessage,
)


class UnavailableDeliveryProvider:
    def __init__(
        self,
        *,
        provider_name: str,
        failure_code: str = "notification_provider_not_configured",
        retryable: bool = False,
    ) -> None:
        self.provider_name = provider_name
        self._failure_code = failure_code
        self._retryable = retryable

    def deliver(
        self,
        message: ExternalDeliveryMessage,
    ) -> IntegrationResult[DeliveryAcknowledgement]:
        del message
        return IntegrationResult.failed(
            provider=self.provider_name,
            operation="deliver",
            status=(
                IntegrationStatus.RETRYING
                if self._retryable
                else IntegrationStatus.NOT_CONFIGURED
            ),
            failure=IntegrationFailure(
                code=self._failure_code,
                message="notification delivery provider is unavailable",
                retryable=self._retryable,
            ),
        )


__all__ = ["UnavailableDeliveryProvider"]
