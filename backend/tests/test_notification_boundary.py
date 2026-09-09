"""Focused tests for the provider-neutral notification boundary."""

from __future__ import annotations

import base64
import stat
from dataclasses import dataclass, field

from app import mail
from app.core.config import Settings
from app.core.integration import IntegrationResult, IntegrationStatus
from app.integrations.notifications import create_notification_provider
from app.integrations.notifications.file import FileNotificationProvider
from app.integrations.notifications.smtp import SmtpNotificationProvider
from app.modules.notifications.ports import NotificationMessage
from app.modules.notifications.services import NotificationService


@dataclass
class RecordingNotificationProvider:
    provider_name: str = "fake_notifications"
    messages: list[NotificationMessage] = field(default_factory=list)

    def send(self, message: NotificationMessage) -> IntegrationResult[None]:
        self.messages.append(message)
        return IntegrationResult.succeeded(
            provider=self.provider_name,
            operation="send",
        )


class RaisingNotificationProvider:
    provider_name = "fake_notifications"

    def send(self, message: NotificationMessage) -> IntegrationResult[None]:
        del message
        raise RuntimeError("password=do-not-expose provider-payload=private")


def _settings(**overrides: object) -> Settings:
    values = {
        "env": "test",
        "notification_provider": "auto",
        "smtp_host": None,
        "smtp_from": None,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_notification_service_uses_an_explicit_fake_provider():
    provider = RecordingNotificationProvider()
    service = NotificationService(provider)

    result = service.send_email(
        recipient="person@example.com",
        subject="Test subject",
        plain_text="Plain body",
        html="<p>HTML body</p>",
        metadata={"kind": "test"},
    )

    assert result.ok is True
    assert result.provider == provider.provider_name
    assert provider.messages == [
        NotificationMessage(
            recipient="person@example.com",
            subject="Test subject",
            plain_text="Plain body",
            html="<p>HTML body</p>",
            metadata={"kind": "test"},
        )
    ]


def test_legacy_mail_helper_keeps_its_tuple_contract_with_a_fake_provider(monkeypatch):
    provider = RecordingNotificationProvider()
    monkeypatch.setattr(mail, "create_notification_provider", lambda: provider)

    outcome = mail.send_payment_confirmation(
        "buyer@example.com",
        "GV-42",
        "1250",
    )

    assert outcome == (True, "Email enviado")
    assert len(provider.messages) == 1
    assert provider.messages[0].recipient == "buyer@example.com"
    assert provider.messages[0].subject == "GeoVision – Pagamento confirmado (GV-42)"
    assert "1250 AOA" in provider.messages[0].plain_text


def test_provider_exception_is_normalized_without_exposing_its_payload():
    result = NotificationService(RaisingNotificationProvider()).send_email(
        recipient="person@example.com",
        subject="Test subject",
        plain_text="Plain body",
    )

    assert result.ok is False
    assert result.failure is not None
    assert result.failure.code == "notification_delivery_failed"
    assert "do-not-expose" not in result.failure.message
    assert "provider-payload" not in result.failure.message


def test_local_auto_provider_logs_only_delivery_metadata(tmp_path):
    log_path = tmp_path / "email.log"
    provider = create_notification_provider(_settings(), log_path=log_path)

    result = NotificationService(provider).send_email(
        recipient="person@example.com",
        subject="Reset requested",
        plain_text="secret reset token must not be logged",
    )

    assert result.status is IntegrationStatus.SIMULATED
    logged = log_path.read_text(encoding="utf-8")
    assert "person@example.com" in logged
    assert "Reset requested" in logged
    assert "secret reset token" not in logged
    assert stat.S_IMODE(log_path.stat().st_mode) == 0o600


def test_legacy_file_success_reports_the_injected_provider_path(tmp_path):
    log_path = tmp_path / "injected-email.log"
    provider = FileNotificationProvider(log_path=log_path)

    outcome = mail._send_email(
        "person@example.com",
        "Test subject",
        "Plain body",
        provider=provider,
    )

    assert outcome == (True, f"SMTP não configurado – log escrito em {log_path}")


def test_partial_smtp_authentication_is_rejected(tmp_path):
    partial_credentials = (
        ("configured-user", None),
        (None, "configured-password"),
    )

    for index, (username, password) in enumerate(partial_credentials):
        config = _settings(
            smtp_host="smtp.example.com",
            smtp_from="notifications@example.com",
            smtp_user=username,
            smtp_password=password,
        )
        log_path = tmp_path / f"email-{index}.log"
        provider = create_notification_provider(config, log_path=log_path)

        result = NotificationService(provider).send_email(
            recipient="person@example.com",
            subject="Should not be logged",
            plain_text="Should not be delivered",
        )

        assert result.status is IntegrationStatus.NOT_CONFIGURED
        assert result.failure is not None
        assert result.failure.code == "smtp_auth_not_configured"
        assert log_path.exists() is False
        assert config.safe_summary()["configured"]["smtp"] is False


def test_staging_without_smtp_fails_closed_instead_of_writing_a_file(tmp_path):
    encryption_key = base64.urlsafe_b64encode(b"x" * 32).decode()
    config = _settings(
        env="staging",
        secret_key="s" * 40,
        encryption_key=encryption_key,
    )
    log_path = tmp_path / "email.log"
    provider = create_notification_provider(config, log_path=log_path)

    result = NotificationService(provider).send_email(
        recipient="person@example.com",
        subject="Should not be logged",
        plain_text="Should not be delivered",
    )

    assert result.status is IntegrationStatus.NOT_CONFIGURED
    assert result.failure is not None
    assert result.failure.code == "smtp_not_configured"
    assert log_path.exists() is False


def test_staging_smtp_requires_starttls(tmp_path):
    encryption_key = base64.urlsafe_b64encode(b"x" * 32).decode()
    config = _settings(
        env="staging",
        secret_key="s" * 40,
        encryption_key=encryption_key,
        smtp_host="smtp.example.com",
        smtp_from="notifications@example.com",
        smtp_use_tls=False,
    )
    log_path = tmp_path / "email.log"
    provider = create_notification_provider(config, log_path=log_path)

    result = NotificationService(provider).send_email(
        recipient="person@example.com",
        subject="Should not be delivered",
        plain_text="Should not be delivered",
    )

    assert result.status is IntegrationStatus.NOT_CONFIGURED
    assert result.failure is not None
    assert result.failure.code == "smtp_tls_required"
    assert log_path.exists() is False


def test_smtp_starttls_uses_a_verifying_ssl_context(monkeypatch):
    context = object()
    calls: list[object] = []

    class FakeSmtp:
        def __init__(self, **kwargs):
            del kwargs

        def __enter__(self):
            return self

        def __exit__(self, *args):
            del args

        def ehlo(self):
            pass

        def starttls(self, *, context):
            calls.append(context)

        def send_message(self, message):
            del message

    monkeypatch.setattr(
        "app.integrations.notifications.smtp.ssl.create_default_context",
        lambda: context,
    )
    provider = SmtpNotificationProvider(
        host="smtp.example.com",
        port=587,
        sender="notifications@example.com",
        username=None,
        password=None,
        use_tls=True,
        timeout_seconds=5,
        smtp_factory=FakeSmtp,
    )

    result = NotificationService(provider).send_email(
        recipient="person@example.com",
        subject="TLS test",
        plain_text="TLS test",
    )

    assert result.status is IntegrationStatus.SUCCEEDED
    assert calls == [context]
