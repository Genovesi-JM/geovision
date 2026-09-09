"""Fail-closed notification provider used for invalid runtime configuration."""

from __future__ import annotations

from app.core.integration import (
    IntegrationFailure,
    IntegrationResult,
    IntegrationStatus,
)
from app.modules.notifications.ports import NotificationMessage


class UnavailableNotificationProvider:
    """Return a normalized configuration failure without attempting delivery."""

    def __init__(
        self,
        *,
        provider_name: str,
        failure_code: str,
        failure_message: str,
    ) -> None:
        self.provider_name = provider_name
        self._failure_code = failure_code
        self._failure_message = failure_message

    def send(self, message: NotificationMessage) -> IntegrationResult[None]:
        del message
        return IntegrationResult.failed(
            provider=self.provider_name,
            operation="send",
            status=IntegrationStatus.NOT_CONFIGURED,
            failure=IntegrationFailure(
                code=self._failure_code,
                message=self._failure_message,
                retryable=False,
            ),
        )


__all__ = ["UnavailableNotificationProvider"]
