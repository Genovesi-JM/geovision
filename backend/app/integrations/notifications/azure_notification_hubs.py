"""Azure Notification Hubs adapter for APNs/FCM registration templates."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
from typing import Any, Callable
from urllib.parse import quote, quote_plus

import httpx

from app.core.integration import IntegrationFailure, IntegrationResult, IntegrationStatus
from app.modules.notifications.delivery_ports import (
    DeliveryAcknowledgement,
    DeliveryChannel,
    ExternalDeliveryMessage,
)


_NAMESPACE = re.compile(r"^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$")
_HUB_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_INSTALLATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")


class AzureNotificationHubsPushProvider:
    """Send a template notification to one registered installation.

    The wire payload contains only ``notification_id``.  No asset/report/action
    identifiers or provider handle are placed in application data, so a push
    tap must resolve its destination through GeoVision's authorized API.
    """

    provider_name = "azure_notification_hubs"

    def __init__(
        self,
        *,
        namespace: str,
        hub_name: str,
        sas_key_name: str,
        sas_key: str,
        timeout_seconds: float = 10.0,
        post: Callable[..., Any] | None = None,
        put: Callable[..., Any] | None = None,
        epoch_seconds: Callable[[], float] = time.time,
    ) -> None:
        normalized_namespace = namespace.strip().lower()
        suffix = ".servicebus.windows.net"
        if normalized_namespace.endswith(suffix):
            normalized_namespace = normalized_namespace[: -len(suffix)]
        if not _NAMESPACE.fullmatch(normalized_namespace):
            raise ValueError("invalid Azure Notification Hubs namespace")
        if not _HUB_NAME.fullmatch(hub_name.strip()):
            raise ValueError("invalid Azure Notification Hubs hub name")
        if not sas_key_name.strip() or not sas_key.strip():
            raise ValueError("Azure Notification Hubs credentials are incomplete")
        self._namespace = normalized_namespace
        self._hub_name = hub_name.strip()
        self._sas_key_name = sas_key_name.strip()
        self._sas_key = sas_key.strip()
        self._timeout_seconds = timeout_seconds
        self._post = post or httpx.post
        self._put = put or httpx.put
        self._epoch_seconds = epoch_seconds

    @property
    def _resource_uri(self) -> str:
        return (
            f"https://{self._namespace}.servicebus.windows.net/"
            f"{self._hub_name}/messages/"
        )

    def _authorization(self, resource_uri: str) -> str:
        expiry = int(self._epoch_seconds()) + 300
        resource = quote_plus(resource_uri.lower())
        to_sign = f"{resource}\n{expiry}".encode("utf-8")
        signature = quote_plus(
            base64.b64encode(
                hmac.new(self._sas_key.encode("utf-8"), to_sign, hashlib.sha256).digest()
            ).decode("ascii")
        )
        return (
            f"SharedAccessSignature sr={resource}&sig={signature}&se={expiry}"
            f"&skn={quote_plus(self._sas_key_name)}"
        )

    @staticmethod
    def _installation_template(platform: str) -> str:
        if platform == "IOS":
            return json.dumps(
                {
                    "aps": {"content-available": 1},
                    "notification_id": "$(notification_id)",
                },
                separators=(",", ":"),
            )
        if platform == "ANDROID":
            return json.dumps(
                {
                    "message": {
                        "data": {"notification_id": "$(notification_id)"}
                    }
                },
                separators=(",", ":"),
            )
        raise ValueError("unsupported push platform")

    def _ensure_installation(
        self,
        message: ExternalDeliveryMessage,
    ) -> IntegrationResult[DeliveryAcknowledgement] | None:
        if message.platform is None or message.provider_handle is None:
            # Compatibility for installations managed by an existing native
            # Notification Hubs SDK. New GeoVision clients always supply both.
            return None
        try:
            body = {
                "installationId": message.destination,
                "platform": "apns" if message.platform == "IOS" else "fcmv1",
                "pushChannel": message.provider_handle,
                "templates": {
                    "geovision": {
                        "body": self._installation_template(message.platform),
                        "tags": [],
                    }
                },
            }
        except ValueError:
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation="register_installation",
                failure=IntegrationFailure(
                    code="notification_endpoint_invalid",
                    message="push endpoint platform is invalid",
                    retryable=False,
                ),
            )
        installation_uri = (
            f"https://{self._namespace}.servicebus.windows.net/"
            f"{self._hub_name}/installations/{quote(message.destination, safe='')}"
        )
        try:
            response = self._put(
                f"{installation_uri}?api-version=2015-01",
                headers={
                    "Authorization": self._authorization(installation_uri),
                    "Content-Type": "application/json;charset=utf-8",
                    "x-ms-version": "2015-01",
                    "X-GeoVision-Delivery-ID": message.delivery_id,
                },
                content=json.dumps(
                    body,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8"),
                timeout=self._timeout_seconds,
            )
        except (httpx.TimeoutException, httpx.TransportError):
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation="register_installation",
                status=IntegrationStatus.RETRYING,
                failure=IntegrationFailure(
                    code="notification_push_unavailable",
                    message="push provider is temporarily unavailable",
                    retryable=True,
                ),
            )
        except Exception:
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation="register_installation",
                status=IntegrationStatus.RETRYING,
                failure=IntegrationFailure(
                    code="notification_push_failed",
                    message="push installation registration failed",
                    retryable=True,
                ),
            )
        if response.status_code in {200, 201, 204}:
            return None
        retryable = response.status_code in {408, 425, 429} or response.status_code >= 500
        return IntegrationResult.failed(
            provider=self.provider_name,
            operation="register_installation",
            status=(IntegrationStatus.RETRYING if retryable else IntegrationStatus.FAILED),
            failure=IntegrationFailure(
                code=(
                    "notification_push_unavailable"
                    if retryable
                    else "notification_endpoint_rejected"
                ),
                message=(
                    "push provider is temporarily unavailable"
                    if retryable
                    else "push provider rejected the endpoint"
                ),
                retryable=retryable,
                retry_after_seconds=(self._retry_after(response) if retryable else None),
            ),
        )

    @staticmethod
    def _retry_after(response: Any) -> float | None:
        value = response.headers.get("Retry-After")
        if not value:
            return None
        try:
            return min(max(float(value), 0.0), 3600.0)
        except (TypeError, ValueError):
            return None

    def deliver(
        self,
        message: ExternalDeliveryMessage,
    ) -> IntegrationResult[DeliveryAcknowledgement]:
        if message.channel is not DeliveryChannel.PUSH:
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation="deliver",
                failure=IntegrationFailure(
                    code="notification_channel_unsupported",
                    message="Azure Notification Hubs supports push deliveries only",
                    retryable=False,
                ),
            )
        if not _INSTALLATION_ID.fullmatch(message.destination):
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation="deliver",
                failure=IntegrationFailure(
                    code="notification_endpoint_invalid",
                    message="push installation identifier is invalid",
                    retryable=False,
                ),
            )

        registration_failure = self._ensure_installation(message)
        if registration_failure is not None:
            return registration_failure

        payload = json.dumps(
            {"notification_id": message.notification_id},
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        headers = {
            "Authorization": self._authorization(self._resource_uri),
            "Content-Type": "application/json;charset=utf-8",
            "ServiceBusNotification-Format": "template",
            "ServiceBusNotification-Tags": f"$InstallationId:{{{message.destination}}}",
            "X-GeoVision-Delivery-ID": message.delivery_id,
        }
        try:
            response = self._post(
                f"{self._resource_uri}?api-version=2015-01",
                headers=headers,
                content=payload.encode("utf-8"),
                timeout=self._timeout_seconds,
            )
        except (httpx.TimeoutException, httpx.TransportError):
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation="deliver",
                status=IntegrationStatus.RETRYING,
                failure=IntegrationFailure(
                    code="notification_push_unavailable",
                    message="push provider is temporarily unavailable",
                    retryable=True,
                ),
            )
        except Exception:
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation="deliver",
                status=IntegrationStatus.RETRYING,
                failure=IntegrationFailure(
                    code="notification_push_failed",
                    message="push delivery failed",
                    retryable=True,
                ),
            )

        if 200 <= response.status_code < 300:
            provider_message_id = response.headers.get("TrackingId")
            try:
                acknowledgement = DeliveryAcknowledgement(provider_message_id)
            except ValueError:
                acknowledgement = DeliveryAcknowledgement()
            return IntegrationResult.accepted(
                provider=self.provider_name,
                operation="deliver",
                value=acknowledgement,
            )

        retryable = response.status_code in {408, 425, 429} or response.status_code >= 500
        return IntegrationResult.failed(
            provider=self.provider_name,
            operation="deliver",
            status=(IntegrationStatus.RETRYING if retryable else IntegrationStatus.FAILED),
            failure=IntegrationFailure(
                code=(
                    "notification_push_rejected"
                    if not retryable
                    else "notification_push_unavailable"
                ),
                message=(
                    "push provider rejected the delivery"
                    if not retryable
                    else "push provider is temporarily unavailable"
                ),
                retryable=retryable,
                retry_after_seconds=(self._retry_after(response) if retryable else None),
            ),
        )


__all__ = ["AzureNotificationHubsPushProvider"]
