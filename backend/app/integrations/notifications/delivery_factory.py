"""Lazy provider selection for durable external notification deliveries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.config import Settings, settings
from app.modules.notifications.delivery_ports import (
    DeliveryChannel,
    ExternalDeliveryProvider,
)


def default_delivery_log_path() -> Path:
    return Path(__file__).resolve().parents[3] / "notification_delivery_log.txt"


def _secret(value: Any) -> str | None:
    if value is None:
        return None
    reveal = getattr(value, "get_secret_value", None)
    return str(reveal() if callable(reveal) else value)


def _unavailable(
    provider_name: str,
    code: str = "notification_provider_not_configured",
) -> ExternalDeliveryProvider:
    from .delivery_unavailable import UnavailableDeliveryProvider

    return UnavailableDeliveryProvider(
        provider_name=provider_name,
        failure_code=code,
    )


def create_external_delivery_provider(
    *,
    provider_name: str,
    channel: DeliveryChannel | str,
    config: Settings = settings,
    log_path: Path | None = None,
) -> ExternalDeliveryProvider:
    """Create the provider pinned on a persisted delivery row.

    ``getattr`` defaults let older deployments fail closed while the Phase 20
    settings migration rolls out.  Nothing reads provider credentials directly
    from process environment variables.
    """

    try:
        normalized_channel = DeliveryChannel(str(getattr(channel, "value", channel)).upper())
    except ValueError:
        return _unavailable("notification", "notification_channel_unsupported")
    selected = str(provider_name or "").strip().lower().replace("-", "_")

    if selected == "fake":
        if config.is_deployed:
            return _unavailable("fake", "notification_provider_not_allowed")
        from .delivery_fake import FakeDeliveryProvider

        return FakeDeliveryProvider()

    if selected in {"file", "log", "local_file"}:
        if config.is_deployed:
            return _unavailable("file", "notification_provider_not_allowed")
        from .delivery_file import FileDeliveryProvider

        return FileDeliveryProvider(log_path=log_path or default_delivery_log_path())

    if selected == "smtp":
        if normalized_channel is not DeliveryChannel.EMAIL:
            return _unavailable("smtp", "notification_channel_unsupported")
        username = (config.smtp_user or "").strip() or None
        password = _secret(config.smtp_password)
        if bool(username) != bool(password) or not config.smtp_configuration_complete:
            return _unavailable("smtp")
        if config.is_deployed and not config.smtp_use_tls:
            return _unavailable("smtp", "smtp_tls_required")
        from .delivery_smtp import SmtpDeliveryProvider

        return SmtpDeliveryProvider(
            host=config.smtp_host.strip(),
            port=config.smtp_port,
            sender=config.smtp_from.strip(),
            username=username,
            password=password,
            use_tls=config.smtp_use_tls,
            timeout_seconds=config.smtp_timeout_seconds,
        )

    if selected in {"azure_notification_hubs", "azure_notification_hub"}:
        if normalized_channel is not DeliveryChannel.PUSH:
            return _unavailable(
                "azure_notification_hubs", "notification_channel_unsupported"
            )
        namespace = str(
            getattr(config, "azure_notification_hubs_namespace", "") or ""
        ).strip()
        hub_name = str(
            getattr(config, "azure_notification_hubs_hub_name", "") or ""
        ).strip()
        key_name = str(
            getattr(config, "azure_notification_hubs_sas_key_name", "") or ""
        ).strip()
        key = _secret(getattr(config, "azure_notification_hubs_sas_key", None))
        if not all((namespace, hub_name, key_name, key)):
            return _unavailable("azure_notification_hubs")
        from .azure_notification_hubs import AzureNotificationHubsPushProvider

        try:
            return AzureNotificationHubsPushProvider(
                namespace=namespace,
                hub_name=hub_name,
                sas_key_name=key_name,
                sas_key=key,
                timeout_seconds=float(
                    getattr(config, "notification_delivery_timeout_seconds", 10.0)
                ),
            )
        except ValueError:
            return _unavailable(
                "azure_notification_hubs", "notification_provider_configuration_invalid"
            )

    if selected in {"none", "disabled", "null", "sms"}:
        return _unavailable(selected or "notification")
    return _unavailable("notification", "unsupported_notification_provider")


__all__ = ["create_external_delivery_provider", "default_delivery_log_path"]
