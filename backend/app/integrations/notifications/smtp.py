"""SMTP implementation of the notifications domain port."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from typing import Any, Callable, Optional

from app.core.integration import IntegrationFailure, IntegrationResult
from app.modules.notifications.ports import NotificationMessage


class SmtpNotificationProvider:
    """Deliver email notifications through a configured SMTP server."""

    provider_name = "smtp"

    def __init__(
        self,
        *,
        host: str,
        port: int,
        sender: str,
        username: Optional[str],
        password: Optional[str],
        use_tls: bool,
        timeout_seconds: float,
        smtp_factory: Optional[Callable[..., Any]] = None,
    ) -> None:
        self._host = host
        self._port = port
        self._sender = sender
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._timeout_seconds = timeout_seconds
        self._smtp_factory = smtp_factory or smtplib.SMTP

    def send(self, message: NotificationMessage) -> IntegrationResult[None]:
        try:
            email = EmailMessage()
            email["Subject"] = message.subject
            email["From"] = self._sender
            email["To"] = message.recipient
            email.set_content(message.plain_text)
            if message.html:
                email.add_alternative(message.html, subtype="html")

            with self._smtp_factory(
                host=self._host,
                port=self._port,
                timeout=self._timeout_seconds,
            ) as client:
                client.ehlo()
                if self._use_tls:
                    client.starttls(context=ssl.create_default_context())
                    client.ehlo()
                if self._username and self._password:
                    client.login(self._username, self._password)
                client.send_message(email)
        except smtplib.SMTPAuthenticationError:
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation="send",
                failure=IntegrationFailure(
                    code="notification_authentication_failed",
                    message="SMTP authentication failed",
                    retryable=False,
                ),
            )
        except Exception:
            # SMTP exceptions can embed server replies and connection details.
            # Return a stable diagnostic instead of exposing provider payloads.
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation="send",
                failure=IntegrationFailure(
                    code="notification_delivery_failed",
                    message="SMTP notification delivery failed",
                    retryable=True,
                ),
            )

        return IntegrationResult.succeeded(
            provider=self.provider_name,
            operation="send",
        )


__all__ = ["SmtpNotificationProvider"]
