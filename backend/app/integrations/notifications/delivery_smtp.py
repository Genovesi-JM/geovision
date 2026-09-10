"""SMTP email adapter for durable notification deliveries."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from typing import Any, Callable

from email_validator import EmailNotValidError, validate_email

from app.core.integration import IntegrationFailure, IntegrationResult
from app.modules.notifications.delivery_ports import (
    DeliveryAcknowledgement,
    DeliveryChannel,
    ExternalDeliveryMessage,
)


class SmtpDeliveryProvider:
    provider_name = "smtp"

    def __init__(
        self,
        *,
        host: str,
        port: int,
        sender: str,
        username: str | None,
        password: str | None,
        use_tls: bool,
        timeout_seconds: float,
        smtp_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._sender = sender
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._timeout_seconds = timeout_seconds
        self._smtp_factory = smtp_factory or smtplib.SMTP

    def deliver(
        self,
        message: ExternalDeliveryMessage,
    ) -> IntegrationResult[DeliveryAcknowledgement]:
        if message.channel is not DeliveryChannel.EMAIL:
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation="deliver",
                failure=IntegrationFailure(
                    code="notification_channel_unsupported",
                    message="SMTP supports email deliveries only",
                    retryable=False,
                ),
            )
        try:
            destination = validate_email(
                message.destination,
                check_deliverability=False,
            ).normalized
        except EmailNotValidError:
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation="deliver",
                failure=IntegrationFailure(
                    code="notification_recipient_invalid",
                    message="email notification recipient is invalid",
                    retryable=False,
                ),
            )
        try:
            email = EmailMessage()
            email["Subject"] = message.title
            email["From"] = self._sender
            email["To"] = destination
            email["X-GeoVision-Delivery-ID"] = message.delivery_id
            email.set_content(message.body)
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
                operation="deliver",
                failure=IntegrationFailure(
                    code="notification_authentication_failed",
                    message="SMTP authentication failed",
                    retryable=False,
                ),
            )
        except smtplib.SMTPRecipientsRefused:
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation="deliver",
                failure=IntegrationFailure(
                    code="notification_recipient_rejected",
                    message="SMTP rejected the notification recipient",
                    retryable=False,
                ),
            )
        except Exception:
            # Server replies and exception strings can contain destinations,
            # credentials, or network topology. Persist a fixed diagnostic.
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation="deliver",
                failure=IntegrationFailure(
                    code="notification_delivery_failed",
                    message="SMTP notification delivery failed",
                    retryable=True,
                ),
            )
        return IntegrationResult.succeeded(
            provider=self.provider_name,
            operation="deliver",
            value=DeliveryAcknowledgement(),
        )


__all__ = ["SmtpDeliveryProvider"]
