"""Lazy notification-provider selection from typed application settings."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from app.core.config import Settings, settings
from app.modules.notifications.ports import NotificationProvider


def default_email_log_path() -> Path:
    """Return the historical local fallback path used by ``app.mail``."""

    return Path(__file__).resolve().parents[3] / "email_log.txt"


def _secret_text(value: Any) -> Optional[str]:
    """Unwrap secret settings only at the concrete provider boundary."""

    if value is None:
        return None
    get_secret_value = getattr(value, "get_secret_value", None)
    if callable(get_secret_value):
        return str(get_secret_value())
    return str(value)


def _unavailable(
    *,
    provider_name: str,
    failure_code: str,
    failure_message: str,
) -> NotificationProvider:
    from .unavailable import UnavailableNotificationProvider

    return UnavailableNotificationProvider(
        provider_name=provider_name,
        failure_code=failure_code,
        failure_message=failure_message,
    )


def create_notification_provider(
    config: Settings = settings,
    *,
    log_path: Optional[Path] = None,
) -> NotificationProvider:
    """Build the selected provider without importing unused implementations."""

    provider_name = config.notification_provider or "auto"
    password = _secret_text(config.smtp_password)
    username_configured = bool(config.smtp_user and config.smtp_user.strip())
    password_configured = bool(password)
    authentication_complete = username_configured == password_configured
    smtp_configured = config.smtp_configuration_complete

    if (
        provider_name in {"auto", "smtp"}
        and username_configured != password_configured
    ):
        return _unavailable(
            provider_name="smtp",
            failure_code="smtp_auth_not_configured",
            failure_message="SMTP authentication configuration is incomplete",
        )

    if (
        provider_name in {"auto", "smtp"}
        and smtp_configured
        and config.is_deployed
        and not config.smtp_use_tls
    ):
        return _unavailable(
            provider_name="smtp",
            failure_code="smtp_tls_required",
            failure_message="SMTP STARTTLS is required in deployed environments",
        )

    if provider_name in {"auto", "smtp"} and smtp_configured:
        from .smtp import SmtpNotificationProvider

        return SmtpNotificationProvider(
            host=config.smtp_host.strip(),
            port=config.smtp_port,
            sender=config.smtp_from.strip(),
            username=config.smtp_user,
            password=password,
            use_tls=config.smtp_use_tls,
            timeout_seconds=config.smtp_timeout_seconds,
        )

    if provider_name == "auto" and not config.is_deployed:
        from .file import FileNotificationProvider

        return FileNotificationProvider(log_path=log_path or default_email_log_path())

    if provider_name in {"file", "log", "local_file"}:
        if config.is_deployed:
            return _unavailable(
                provider_name="smtp",
                failure_code="notification_provider_not_allowed",
                failure_message=(
                    "local notification delivery is disabled in deployed environments"
                ),
            )

        from .file import FileNotificationProvider

        return FileNotificationProvider(log_path=log_path or default_email_log_path())

    if provider_name in {"auto", "smtp"}:
        return _unavailable(
            provider_name="smtp",
            failure_code="smtp_not_configured",
            failure_message="SMTP notification delivery is not configured",
        )

    if provider_name in {"none", "disabled", "null"}:
        return _unavailable(
            provider_name="notification",
            failure_code="notification_provider_disabled",
            failure_message="notification delivery is disabled",
        )

    return _unavailable(
        provider_name="notification",
        failure_code="unsupported_notification_provider",
        failure_message="the configured notification provider is unsupported",
    )


__all__ = ["create_notification_provider", "default_email_log_path"]
