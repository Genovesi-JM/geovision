"""Privacy-safe local delivery sink for development environments."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Callable

from app.core.integration import IntegrationFailure, IntegrationResult
from app.core.time import utc_now
from app.modules.notifications.delivery_ports import (
    DeliveryAcknowledgement,
    ExternalDeliveryMessage,
)


def _safe_token(value: str) -> str:
    return "".join(
        character
        for character in value
        if character.isalnum() or character in "-_:."
    )[:255]


class FileDeliveryProvider:
    """Append delivery IDs only; never write destinations or notification text."""

    provider_name = "file"

    def __init__(
        self,
        *,
        log_path: Path,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._log_path = Path(log_path)
        self._clock = clock

    @property
    def log_path(self) -> Path:
        return self._log_path

    def deliver(
        self,
        message: ExternalDeliveryMessage,
    ) -> IntegrationResult[DeliveryAcknowledgement]:
        try:
            descriptor = os.open(
                self._log_path,
                os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                0o600,
            )
            with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
                os.fchmod(handle.fileno(), 0o600)
                handle.write(
                    "timestamp={} delivery={} notification={} channel={}\n".format(
                        self._clock().isoformat(),
                        _safe_token(message.delivery_id),
                        _safe_token(message.notification_id),
                        message.channel.value,
                    )
                )
        except Exception:
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation="deliver",
                failure=IntegrationFailure(
                    code="notification_file_unavailable",
                    message="local delivery sink is unavailable",
                    retryable=False,
                ),
            )
        return IntegrationResult.simulated(
            provider=self.provider_name,
            operation="deliver",
            value=DeliveryAcknowledgement(
                provider_message_id=f"file:{message.delivery_id}"
            ),
        )


__all__ = ["FileDeliveryProvider"]
