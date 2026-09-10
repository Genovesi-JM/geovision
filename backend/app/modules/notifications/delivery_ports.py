"""Provider-neutral contracts for durable external notification delivery.

The notification domain owns the message shape.  Concrete SMTP and push
providers live under :mod:`app.integrations.notifications` and cannot leak
provider-specific identifiers into GeoVision's notification identity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from app.core.integration import IntegrationResult
from app.modules.notifications.domain import NotificationChannel as DeliveryChannel


@dataclass(frozen=True, slots=True)
class ExternalDeliveryMessage:
    """One claimed delivery, detached from any database transaction.

    ``destination`` is deliberately excluded from repr because email addresses
    and mobile installation handles are private routing data.  Push providers
    must transmit only ``notification_id`` as application data; contextual
    targets are resolved and authorized by the API when the app opens it.
    """

    delivery_id: str
    notification_id: str
    idempotency_key: str
    channel: DeliveryChannel
    destination: str = field(repr=False)
    title: str = ""
    body: str = field(default="", repr=False)
    platform: str | None = None
    provider_handle: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        for label, value in (
            ("delivery_id", self.delivery_id),
            ("notification_id", self.notification_id),
            ("idempotency_key", self.idempotency_key),
            ("destination", self.destination),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{label} must not be empty")
            if any(ord(character) < 32 for character in value):
                raise ValueError(f"{label} must not contain control characters")
        if len(self.idempotency_key) > 255:
            raise ValueError("idempotency_key is too long")
        if (self.platform is None) != (self.provider_handle is None):
            raise ValueError("push platform and provider handle must be supplied together")
        if self.platform is not None:
            normalized_platform = self.platform.strip().upper()
            if normalized_platform not in {"IOS", "ANDROID"}:
                raise ValueError("push platform is unsupported")
            object.__setattr__(self, "platform", normalized_platform)
        if self.provider_handle is not None:
            normalized_handle = self.provider_handle.strip()
            if not (16 <= len(normalized_handle) <= 4096):
                raise ValueError("push provider handle is invalid")
            if any(ord(character) < 32 for character in normalized_handle):
                raise ValueError("push provider handle contains control characters")
            object.__setattr__(self, "provider_handle", normalized_handle)
        if len(self.title) > 500 or len(self.body) > 20_000:
            raise ValueError("notification content exceeds the delivery limit")
        if any(ord(character) < 32 for character in self.title):
            raise ValueError("notification title must not contain control characters")
        if any(
            ord(character) < 32 and character not in "\r\n\t"
            for character in self.body
        ):
            raise ValueError("notification body contains invalid control characters")


@dataclass(frozen=True, slots=True)
class DeliveryAcknowledgement:
    """Safe provider acknowledgement persisted only as an external reference."""

    provider_message_id: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        value = self.provider_message_id
        if value is not None:
            normalized = str(value).strip()
            if not normalized or len(normalized) > 500:
                raise ValueError("provider_message_id is invalid")
            if any(ord(character) < 32 for character in normalized):
                raise ValueError("provider_message_id contains control characters")
            object.__setattr__(self, "provider_message_id", normalized)


@runtime_checkable
class ExternalDeliveryProvider(Protocol):
    provider_name: str

    def deliver(
        self,
        message: ExternalDeliveryMessage,
    ) -> IntegrationResult[DeliveryAcknowledgement]: ...


__all__ = [
    "DeliveryAcknowledgement",
    "DeliveryChannel",
    "ExternalDeliveryMessage",
    "ExternalDeliveryProvider",
]
