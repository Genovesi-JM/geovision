"""Focused tests for provider-neutral external notification adapters."""

from __future__ import annotations

from datetime import datetime
import json

import httpx

from app.core.config import RuntimeEnvironment, settings
from app.integrations.notifications.azure_notification_hubs import (
    AzureNotificationHubsPushProvider,
)
from app.integrations.notifications.delivery_factory import (
    create_external_delivery_provider,
)
from app.integrations.notifications.delivery_file import FileDeliveryProvider
from app.integrations.notifications.delivery_smtp import SmtpDeliveryProvider
from app.modules.notifications.delivery_ports import (
    DeliveryChannel,
    ExternalDeliveryMessage,
)


def _message(
    channel: DeliveryChannel,
    *,
    destination: str = "installation-1",
    platform: str | None = None,
    provider_handle: str | None = None,
) -> ExternalDeliveryMessage:
    return ExternalDeliveryMessage(
        delivery_id="delivery-1",
        notification_id="notification-1",
        idempotency_key="event-1:user-1:push",
        channel=channel,
        destination=destination,
        title="Your results are ready",
        body="Open the report for Asset 42.",
        platform=platform,
        provider_handle=provider_handle,
    )


def test_delivery_message_repr_hides_private_destination():
    message = _message(DeliveryChannel.EMAIL, destination="private@example.com")

    assert "private@example.com" not in repr(message)
    assert "Asset 42" not in repr(message)


def test_file_sink_never_persists_recipient_or_message_content(tmp_path):
    path = tmp_path / "deliveries.log"
    provider = FileDeliveryProvider(
        log_path=path,
        clock=lambda: datetime(2026, 9, 10, 12, 0, 0),
    )

    outcome = provider.deliver(
        _message(DeliveryChannel.EMAIL, destination="private@example.com")
    )

    assert outcome.ok
    persisted = path.read_text(encoding="utf-8")
    assert "delivery-1" in persisted
    assert "notification-1" in persisted
    assert "private@example.com" not in persisted
    assert "Your results" not in persisted
    assert "Asset 42" not in persisted


def test_deployed_runtime_rejects_fake_delivery_provider():
    config = settings.model_copy(update={"env": RuntimeEnvironment.PRODUCTION})
    provider = create_external_delivery_provider(
        provider_name="fake",
        channel=DeliveryChannel.PUSH,
        config=config,
    )

    outcome = provider.deliver(_message(DeliveryChannel.PUSH))

    assert not outcome.ok
    assert outcome.failure.code == "notification_provider_not_allowed"


class _Response:
    def __init__(self, status_code: int, headers: dict[str, str] | None = None):
        self.status_code = status_code
        self.headers = headers or {}


def test_azure_push_sends_only_notification_identity_as_application_data():
    request: dict[str, object] = {}

    def post(url, **kwargs):
        request.update(url=url, **kwargs)
        return _Response(201, {"TrackingId": "provider-message-1"})

    provider = AzureNotificationHubsPushProvider(
        namespace="geovision-notifications",
        hub_name="customer-app",
        sas_key_name="send-policy",
        sas_key="top-secret-provider-key",
        post=post,
        epoch_seconds=lambda: 1_800_000_000,
    )

    outcome = provider.deliver(_message(DeliveryChannel.PUSH))

    assert outcome.ok
    assert json.loads(request["content"]) == {"notification_id": "notification-1"}
    serialized = request["content"].decode("utf-8")
    assert "delivery-1" not in serialized
    assert "installation-1" not in serialized
    assert "Your results" not in serialized
    assert "Asset 42" not in serialized
    headers = request["headers"]
    assert headers["ServiceBusNotification-Format"] == "template"
    assert headers["ServiceBusNotification-Tags"] == "$InstallationId:{installation-1}"
    assert "top-secret-provider-key" not in headers["Authorization"]
    assert outcome.value.provider_message_id == "provider-message-1"


def test_azure_push_idempotently_registers_native_installation_before_send():
    registration: dict[str, object] = {}
    sent: dict[str, object] = {}

    def put(url, **kwargs):
        registration.update(url=url, **kwargs)
        return _Response(200)

    def post(url, **kwargs):
        sent.update(url=url, **kwargs)
        return _Response(201)

    provider = AzureNotificationHubsPushProvider(
        namespace="geovision-notifications",
        hub_name="customer-app",
        sas_key_name="send-policy",
        sas_key="top-secret-provider-key",
        put=put,
        post=post,
        epoch_seconds=lambda: 1_800_000_000,
    )

    outcome = provider.deliver(
        _message(
            DeliveryChannel.PUSH,
            platform="ANDROID",
            provider_handle="fcm-provider-handle-1234567890",
        )
    )

    assert outcome.ok
    installation = json.loads(registration["content"])
    assert installation["installationId"] == "installation-1"
    assert installation["platform"] == "fcmv1"
    assert installation["pushChannel"] == "fcm-provider-handle-1234567890"
    template = json.loads(installation["templates"]["geovision"]["body"])
    assert template == {
        "message": {"data": {"notification_id": "$(notification_id)"}}
    }
    assert json.loads(sent["content"]) == {"notification_id": "notification-1"}
    assert "fcm-provider-handle" not in sent["content"].decode("utf-8")
    assert "top-secret-provider-key" not in registration["headers"]["Authorization"]


def test_azure_push_normalizes_transient_failures_without_response_body():
    provider = AzureNotificationHubsPushProvider(
        namespace="geovision-notifications",
        hub_name="customer-app",
        sas_key_name="send-policy",
        sas_key="secret",
        post=lambda *args, **kwargs: _Response(
            429,
            {"Retry-After": "45", "Provider-Secret": "must-not-leak"},
        ),
    )

    outcome = provider.deliver(_message(DeliveryChannel.PUSH))

    assert not outcome.ok
    assert outcome.failure.retryable is True
    assert outcome.failure.retry_after_seconds == 45
    assert "must-not-leak" not in outcome.failure.message


def test_azure_push_transport_exception_is_safe_and_retryable():
    def timeout(*args, **kwargs):
        raise httpx.ReadTimeout("Bearer provider-secret")

    provider = AzureNotificationHubsPushProvider(
        namespace="geovision-notifications",
        hub_name="customer-app",
        sas_key_name="send-policy",
        sas_key="secret",
        post=timeout,
    )

    outcome = provider.deliver(_message(DeliveryChannel.PUSH))

    assert outcome.failure.retryable is True
    assert "provider-secret" not in outcome.failure.message


class _SmtpClient:
    def __init__(self, *args, **kwargs):
        self.message = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def ehlo(self):
        return None

    def starttls(self, *, context):
        return None

    def login(self, username, password):
        return None

    def send_message(self, message):
        self.message = message


def test_smtp_delivery_adds_stable_delivery_identity(monkeypatch):
    client = _SmtpClient()
    monkeypatch.setattr(
        "app.integrations.notifications.delivery_smtp.ssl.create_default_context",
        lambda: object(),
    )
    provider = SmtpDeliveryProvider(
        host="mail.example.com",
        port=587,
        sender="notifications@example.com",
        username="mailer",
        password="secret",
        use_tls=True,
        timeout_seconds=10,
        smtp_factory=lambda **kwargs: client,
    )

    outcome = provider.deliver(
        _message(DeliveryChannel.EMAIL, destination="customer@example.com")
    )

    assert outcome.ok
    assert client.message["X-GeoVision-Delivery-ID"] == "delivery-1"
    assert client.message["To"] == "customer@example.com"


def test_smtp_rejects_push_without_opening_a_connection():
    provider = SmtpDeliveryProvider(
        host="mail.example.com",
        port=587,
        sender="notifications@example.com",
        username=None,
        password=None,
        use_tls=True,
        timeout_seconds=10,
        smtp_factory=lambda **kwargs: (_ for _ in ()).throw(AssertionError()),
    )

    outcome = provider.deliver(_message(DeliveryChannel.PUSH))

    assert not outcome.ok
    assert outcome.failure.code == "notification_channel_unsupported"
    assert outcome.failure.retryable is False
