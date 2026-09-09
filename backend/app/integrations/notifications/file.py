"""Local file fallback for notification delivery."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Callable

from app.core.integration import IntegrationFailure, IntegrationResult
from app.core.time import utc_now
from app.modules.notifications.ports import NotificationMessage


def _single_line(value: str) -> str:
    """Keep the development log append-only even for untrusted headers."""

    return value.replace("\r", " ").replace("\n", " ")


class FileNotificationProvider:
    """Record delivery metadata locally without persisting message bodies."""

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

    def send(self, message: NotificationMessage) -> IntegrationResult[None]:
        try:
            timestamp = self._clock().isoformat()
            recipient = _single_line(message.recipient)
            subject = _single_line(message.subject)
            descriptor = os.open(
                self._log_path,
                os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                0o600,
            )
            with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
                os.fchmod(handle.fileno(), 0o600)
                handle.write(f"[{timestamp}] to={recipient} subject={subject}\n")
        except Exception:
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation="send",
                failure=IntegrationFailure(
                    code="notification_log_failed",
                    message="local notification log is unavailable",
                    retryable=False,
                ),
            )

        return IntegrationResult.simulated(
            provider=self.provider_name,
            operation="send",
        )


__all__ = ["FileNotificationProvider"]
