"""Provider-neutral notification application service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from app.core.integration import IntegrationFailure, IntegrationResult

from .ports import NotificationMessage, NotificationProvider


@dataclass(slots=True)
class NotificationService:
    """Deliver notification intents through an explicitly supplied provider."""

    provider: NotificationProvider

    def send(self, message: NotificationMessage) -> IntegrationResult[None]:
        """Return a normalized outcome even if a provider violates the port contract."""

        try:
            return self.provider.send(message)
        except Exception:
            provider_name = str(
                getattr(self.provider, "provider_name", "notification")
            ).strip()
            return IntegrationResult.failed(
                provider=provider_name or "notification",
                operation="send",
                failure=IntegrationFailure(
                    code="notification_delivery_failed",
                    message="notification delivery failed unexpectedly",
                    retryable=False,
                ),
            )

    def send_email(
        self,
        *,
        recipient: str,
        subject: str,
        plain_text: str,
        html: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> IntegrationResult[None]:
        """Build an email notification intent and deliver it through the port."""

        return self.send(
            NotificationMessage(
                recipient=recipient,
                subject=subject,
                plain_text=plain_text,
                html=html,
                metadata=metadata or {},
            )
        )


__all__ = ["NotificationService"]
