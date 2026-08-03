from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class NotificationAdapter(Protocol):
    id: str

    def send(self, event: dict) -> None: ...


class LogNotificationAdapter:
    """Safe local/test channel; emits no personal data outside the process."""

    id = "log"

    def send(self, event: dict) -> None:
        logger.warning("IoT alert [%s] %s", event.get("severity"), event.get("message"))


class CredentialRequiredAdapter:
    def __init__(self, adapter_id: str) -> None:
        self.id = adapter_id

    def send(self, event: dict) -> None:
        raise RuntimeError(f"{self.id} credentials are not configured")


notification_adapters = {
    "log": LogNotificationAdapter(),
    "email": CredentialRequiredAdapter("email"),
    "telegram": CredentialRequiredAdapter("telegram"),
    "push": CredentialRequiredAdapter("push"),
    "sms": CredentialRequiredAdapter("sms"),
    "whatsapp": CredentialRequiredAdapter("whatsapp"),
}
