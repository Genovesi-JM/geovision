"""Phase 2 configuration and provider-boundary acceptance tests."""

from __future__ import annotations

import ast
import asyncio
import base64
import hashlib
import json
import sys
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO, Mapping, Optional

import pytest
from pydantic import ValidationError

from app.core.config import RuntimeEnvironment, Settings
from app.core.integration import (
    IntegrationFailure,
    IntegrationResult,
    IntegrationStatus,
    RetryPolicy,
    sanitize_integration_message,
)
from app.core.references import ExternalReference
from app.models import Company, Integration, IntegrationOutbox
from app.modules.datasets.ports import ObjectStorageProvider, StoredObject
from app.services.erp_sync import enqueue_erp_event, process_pending
from app.services.storage import StorageService


APP_ROOT = Path(__file__).resolve().parents[1] / "app"
PHASE_34_OPENAPI_SHA256 = (
    "5cc2ed8578608c3d2316bb452aa87c6ba5b4dc88d127a9eb8ea19be21331d0c4"
)
TEST_FERNET_KEY = base64.urlsafe_b64encode(b"g" * 32).decode()
DEPLOYED_FRONTEND_BASE = "https://geovisionops.com"
DEPLOYED_BACKEND_BASE = "https://api.geovisionops.com"


class FakeObjectStorageProvider:
    provider_name = "memory"

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    @staticmethod
    def _stored(key: str, data: bytes) -> StoredObject:
        return StoredObject(
            key=key,
            size_bytes=len(data),
            md5_hash=hashlib.md5(data).hexdigest(),
            sha256_hash=hashlib.sha256(data).hexdigest(),
        )

    def put_file(
        self,
        file_obj: BinaryIO,
        key: str,
        content_type: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> IntegrationResult[StoredObject]:
        del content_type, metadata
        data = file_obj.read()
        self.objects[key] = data
        return IntegrationResult.succeeded(
            provider=self.provider_name,
            operation="put_file",
            value=self._stored(key, data),
        )

    def put_bytes(
        self,
        data: bytes,
        key: str,
        content_type: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> IntegrationResult[StoredObject]:
        del content_type, metadata
        self.objects[key] = data
        return IntegrationResult.succeeded(
            provider=self.provider_name,
            operation="put_bytes",
            value=self._stored(key, data),
        )

    def presign(
        self,
        key: str,
        expires_in: int = 3600,
        for_upload: bool = False,
    ) -> IntegrationResult[str]:
        del expires_in, for_upload
        return IntegrationResult.succeeded(
            provider=self.provider_name,
            operation="presign",
            value=f"memory://{key}",
        )

    def delete(self, key: str) -> IntegrationResult[bool]:
        existed = self.objects.pop(key, None) is not None
        return IntegrationResult.succeeded(
            provider=self.provider_name,
            operation="delete",
            value=existed,
        )

    def exists(self, key: str) -> IntegrationResult[bool]:
        return IntegrationResult.succeeded(
            provider=self.provider_name,
            operation="exists",
            value=key in self.objects,
        )

    def stat(self, key: str) -> IntegrationResult[Optional[Mapping[str, Any]]]:
        data = self.objects.get(key)
        value = None if data is None else {"size_bytes": len(data)}
        return IntegrationResult.succeeded(
            provider=self.provider_name,
            operation="stat",
            value=value,
        )

    def get_bytes(self, key: str) -> IntegrationResult[bytes]:
        return IntegrationResult.succeeded(
            provider=self.provider_name,
            operation="get_bytes",
            value=self.objects[key],
        )


class FakeERPProvider:
    provider_name = "fake_erp"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def upsert(
        self,
        document_type: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
    ) -> IntegrationResult[str]:
        del payload
        self.calls.append((document_type, idempotency_key))
        return IntegrationResult.accepted(
            provider=self.provider_name,
            operation="upsert",
            value=f"FAKE-{len(self.calls)}",
        )

    def health(self) -> Mapping[str, Any]:
        return {"provider": self.provider_name, "configured": True}


class NonRetryableERPProvider(FakeERPProvider):
    def upsert(
        self,
        document_type: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
    ) -> IntegrationResult[str]:
        del payload
        self.calls.append((document_type, idempotency_key))
        return IntegrationResult.failed(
            provider=self.provider_name,
            operation="upsert",
            failure=IntegrationFailure(
                code="invalid_payload",
                message="ERP provider rejected the payload",
                retryable=False,
            ),
        )


class RetryableERPProvider(FakeERPProvider):
    def upsert(
        self,
        document_type: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
    ) -> IntegrationResult[str]:
        del payload
        self.calls.append((document_type, idempotency_key))
        return IntegrationResult.failed(
            provider=self.provider_name,
            operation="upsert",
            status=IntegrationStatus.RETRYING,
            failure=IntegrationFailure(
                code="timeout",
                message="ERP provider timed out",
                retryable=True,
            ),
        )


def test_environment_profiles_and_deployed_secret_guards(monkeypatch):
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    production = Settings(
        _env_file=None,
        env="production",
        secret_key="phase-two-production-secret-key-value",
        encryption_key=TEST_FERNET_KEY,
        frontend_base=DEPLOYED_FRONTEND_BASE,
        backend_base=DEPLOYED_BACKEND_BASE,
    )
    staging = Settings(
        _env_file=None,
        env="stage",
        secret_key="phase-two-staging-secret-key-value",
        encryption_key=TEST_FERNET_KEY,
        frontend_base=DEPLOYED_FRONTEND_BASE,
        backend_base=DEPLOYED_BACKEND_BASE,
    )

    assert production.env is RuntimeEnvironment.PRODUCTION
    assert production.environment_name == "prod"
    assert staging.env is RuntimeEnvironment.STAGING
    assert staging.is_deployed is True

    monkeypatch.setenv("ENVIRONMENT", "production")
    legacy_alias = Settings(
        _env_file=None,
        secret_key="phase-two-production-secret-key-value",
        encryption_key=TEST_FERNET_KEY,
        frontend_base=DEPLOYED_FRONTEND_BASE,
        backend_base=DEPLOYED_BACKEND_BASE,
    )
    assert legacy_alias.env is RuntimeEnvironment.PRODUCTION

    monkeypatch.setenv("ENV", "dev")
    with pytest.raises(ValidationError, match="must not select different profiles"):
        Settings(
            _env_file=None,
            secret_key="phase-two-production-secret-key-value",
            encryption_key=TEST_FERNET_KEY,
        )

    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(
            _env_file=None,
            env="prod",
            secret_key="CHANGE_ME",
            encryption_key=TEST_FERNET_KEY,
            frontend_base=DEPLOYED_FRONTEND_BASE,
            backend_base=DEPLOYED_BACKEND_BASE,
        )
    with pytest.raises(ValidationError, match="ENCRYPTION_KEY"):
        Settings(
            _env_file=None,
            env="staging",
            secret_key="phase-two-staging-secret-key-value",
            encryption_key="not-a-fernet-key",
            frontend_base=DEPLOYED_FRONTEND_BASE,
            backend_base=DEPLOYED_BACKEND_BASE,
        )


def test_deployed_public_origins_accept_dedicated_https_hosts():
    config = Settings(
        _env_file=None,
        env="prod",
        secret_key="phase-three-production-signing-secret-value",
        encryption_key=TEST_FERNET_KEY,
        frontend_base=DEPLOYED_FRONTEND_BASE,
        backend_base=DEPLOYED_BACKEND_BASE,
    )

    assert config.frontend_base == DEPLOYED_FRONTEND_BASE
    assert config.backend_base == DEPLOYED_BACKEND_BASE


@pytest.mark.parametrize("field_name", ("frontend_base", "backend_base"))
@pytest.mark.parametrize(
    "invalid_url",
    (
        "http://geovisionops.com",
        "https://user:password@geovisionops.com",
        "https://geovisionops.com?token=private",
        "https://geovisionops.com#private",
    ),
    ids=("http", "userinfo", "query", "fragment"),
)
def test_deployed_public_origins_reject_unsafe_urls(field_name, invalid_url):
    values = {
        "_env_file": None,
        "env": "prod",
        "secret_key": "phase-three-production-signing-secret-value",
        "encryption_key": TEST_FERNET_KEY,
        "frontend_base": DEPLOYED_FRONTEND_BASE,
        "backend_base": DEPLOYED_BACKEND_BASE,
    }
    values[field_name] = invalid_url

    with pytest.raises(ValidationError, match=field_name.upper()):
        Settings(**values)


def test_config_debugging_redacts_credentials_and_connection_urls():
    sentinel = "phase-two-super-secret-sentinel"
    config = Settings(
        _env_file=None,
        secret_key=sentinel,
        encryption_key=TEST_FERNET_KEY,
        openai_api_key=sentinel,
        smtp_password=sentinel,
        stripe_secret_key=sentinel,
        mqtt_password=sentinel,
        database_url=f"postgresql://user:{sentinel}@db.example/geovision",
        frontend_base="https://user:password@example.test/private?token=hidden",
    )

    debug_outputs = (
        repr(config),
        json.dumps(config.model_dump(), default=str),
        config.model_dump_json(),
        json.dumps(config.safe_summary()),
    )
    assert all(sentinel not in output for output in debug_outputs)
    assert all("user:password" not in output for output in debug_outputs)
    assert config.safe_summary()["frontend_base"] == "https://example.test"
    assert config.safe_summary()["database_driver"] == "postgresql"


def test_invalid_deployed_config_errors_do_not_echo_secret_inputs():
    sentinels = (
        "smtp-password-validation-sentinel",
        "openai-key-validation-sentinel",
    )
    with pytest.raises(ValidationError) as caught:
        Settings(
            _env_file=None,
            env="prod",
            secret_key="phase-two-production-secret-key-value",
            encryption_key="invalid-fernet-key",
            frontend_base=DEPLOYED_FRONTEND_BASE,
            backend_base=DEPLOYED_BACKEND_BASE,
            smtp_password=sentinels[0],
            openai_api_key=sentinels[1],
        )

    rendered_error = f"{caught.value!s}\n{caught.value!r}"
    assert all(sentinel not in rendered_error for sentinel in sentinels)


def test_external_reference_never_replaces_internal_uuid():
    internal_id = uuid.uuid4()
    reference = ExternalReference(
        internal_id=internal_id,
        provider="ERP Next",
        resource_type="Sales Order",
        value="provider/id:opaque-42",
    )

    assert reference.internal_id == internal_id
    assert reference.provider == "erp_next"
    assert reference.resource_type == "sales_order"
    assert reference.value == "provider/id:opaque-42"
    assert reference.as_record()["internal_id"] == str(internal_id)
    assert reference.as_record()["external_reference"] != str(internal_id)


def test_integration_results_errors_and_retry_rules_are_normalized():
    secret = "credential-value"
    message = sanitize_integration_message(
        f"Authorization: Bearer {secret}\npassword={secret}",
    )
    assert secret not in message

    serialized_messages = (
        '{"password":"secret-value"}',
        "{'api_key': 'secret-value'}",
        "client_secret: secret-value",
        "smtp_credentials=secret-value",
        "Authorization: Basic dXNlcjpTRUNSRVQ=",
        "Authorization: token ERPKEY:ERPSECRET",
        "Proxy-Authorization: Basic dXNlcjpTRUNSRVQ=",
        "api key = SECRET-VALUE",
    )
    assert all(
        marker not in sanitize_integration_message(value)
        for value in serialized_messages
        for marker in (
            "secret-value",
            "dXNlcjpTRUNSRVQ=",
            "ERPKEY:ERPSECRET",
            "SECRET-VALUE",
        )
    )

    failure = IntegrationFailure(
        code="Provider Timeout",
        message=message,
        retryable=True,
    )
    result = IntegrationResult.failed(
        provider="weather",
        operation="forecast",
        failure=failure,
        status=IntegrationStatus.RETRYING,
    )
    policy = RetryPolicy(max_attempts=3, initial_delay_seconds=1, max_delay_seconds=4)

    assert result.ok is False
    assert result.terminal is False
    assert failure.code == "provider_timeout"
    assert policy.allows_retry(
        attempts_made=1,
        failure=failure,
        operation_is_idempotent=True,
    )
    assert not policy.allows_retry(
        attempts_made=1,
        failure=failure,
        operation_is_idempotent=False,
    )
    assert policy.allows_retry(
        attempts_made=1,
        failure=failure,
        operation_is_idempotent=False,
        idempotency_key="dedupe-key",
    )


def test_storage_service_accepts_fake_without_importing_s3_sdk():
    s3_was_loaded = "app.integrations.storage.s3" in sys.modules
    provider = FakeObjectStorageProvider()
    assert isinstance(provider, ObjectStorageProvider)
    service = StorageService(provider)

    uploaded = service.upload_file(
        BytesIO(b"geovision"), "datasets/internal-uuid/item.tif"
    )

    assert uploaded[0] == "datasets/internal-uuid/item.tif"
    assert uploaded[1] == len(b"geovision")
    assert service.download_file(uploaded[0]) == b"geovision"
    assert service.file_exists(uploaded[0]) is True
    assert ("app.integrations.storage.s3" in sys.modules) is s3_was_loaded


def test_erp_sync_accepts_fake_without_importing_real_adapter(db_session):
    erpnext_was_loaded = "app.integrations.erp.erpnext" in sys.modules
    db_session.query(IntegrationOutbox).delete()
    db_session.commit()
    aggregate_id = str(uuid.uuid4())
    event = enqueue_erp_event(
        db_session,
        company_id=None,
        aggregate_type="order",
        aggregate_id=aggregate_id,
        event_type="order.created",
        payload={"total": 42},
        version=uuid.uuid4().hex,
        provider="fake_erp",
    )
    db_session.commit()
    provider = FakeERPProvider()

    result = process_pending(db_session, limit=1000, provider=provider)
    db_session.refresh(event)

    assert result["failed"] == 0
    assert event.aggregate_id == aggregate_id
    assert event.external_id == "FAKE-1"
    assert event.external_id != event.aggregate_id
    assert provider.calls == [("order", event.idempotency_key)]
    assert ("app.integrations.erp.erpnext" in sys.modules) is erpnext_was_loaded


def test_erp_sync_does_not_reprocess_terminal_failures(db_session):
    db_session.query(IntegrationOutbox).delete()
    db_session.commit()
    event = enqueue_erp_event(
        db_session,
        company_id=None,
        aggregate_type="order",
        aggregate_id=str(uuid.uuid4()),
        event_type="order.created",
        payload={"invalid": True},
        version=uuid.uuid4().hex,
        provider="fake_erp",
    )
    db_session.commit()
    provider = NonRetryableERPProvider()
    policy = RetryPolicy(
        max_attempts=3,
        initial_delay_seconds=0,
        max_delay_seconds=0,
    )

    first = process_pending(
        db_session,
        limit=1000,
        provider=provider,
        retry_policy=policy,
    )
    second = process_pending(
        db_session,
        limit=1000,
        provider=provider,
        retry_policy=policy,
    )
    db_session.refresh(event)

    assert first == {"processed": 1, "completed": 0, "failed": 1}
    assert second == {"processed": 0, "completed": 0, "failed": 0}
    assert event.status == "failed_terminal"
    assert event.next_attempt_at is None
    assert event.attempts == 1
    assert len(provider.calls) == 1


def test_erp_sync_processes_legacy_failed_rows_and_respects_queued_provider(db_session):
    db_session.query(IntegrationOutbox).delete()
    db_session.commit()
    legacy = IntegrationOutbox(
        company_id=None,
        provider="fake_erp",
        aggregate_type="order",
        aggregate_id=str(uuid.uuid4()),
        event_type="order.created",
        payload_json='{"total": 42}',
        idempotency_key=f"legacy-{uuid.uuid4().hex}",
        status="failed",
        attempts=1,
        next_attempt_at=None,
    )
    queued_for_other_provider = IntegrationOutbox(
        company_id=None,
        provider="other_erp",
        aggregate_type="order",
        aggregate_id=str(uuid.uuid4()),
        event_type="order.created",
        payload_json='{"total": 84}',
        idempotency_key=f"other-{uuid.uuid4().hex}",
        status="pending",
        attempts=0,
    )
    db_session.add_all([legacy, queued_for_other_provider])
    db_session.commit()

    provider = FakeERPProvider()
    result = process_pending(db_session, limit=1000, provider=provider)
    db_session.refresh(legacy)
    db_session.refresh(queued_for_other_provider)

    assert result == {"processed": 1, "completed": 1, "failed": 0}
    assert legacy.status == "completed"
    assert queued_for_other_provider.status == "pending"
    assert queued_for_other_provider.provider == "other_erp"


def test_erp_sync_schedules_retryable_failures_without_immediate_reprocessing(
    db_session,
):
    db_session.query(IntegrationOutbox).delete()
    db_session.commit()
    event = enqueue_erp_event(
        db_session,
        company_id=None,
        aggregate_type="order",
        aggregate_id=str(uuid.uuid4()),
        event_type="order.created",
        payload={"total": 42},
        version=uuid.uuid4().hex,
        provider="fake_erp",
    )
    db_session.commit()
    provider = RetryableERPProvider()
    policy = RetryPolicy(
        max_attempts=3,
        initial_delay_seconds=60,
        max_delay_seconds=60,
    )

    first = process_pending(
        db_session,
        limit=1000,
        provider=provider,
        retry_policy=policy,
    )
    second = process_pending(
        db_session,
        limit=1000,
        provider=provider,
        retry_policy=policy,
    )
    db_session.refresh(event)

    assert first == {"processed": 1, "completed": 0, "failed": 1}
    assert second == {"processed": 0, "completed": 0, "failed": 0}
    assert event.status == "failed"
    assert event.next_attempt_at is not None
    assert event.attempts == 1
    assert len(provider.calls) == 1


def test_erpnext_classifies_http_and_timeout_failures(monkeypatch):
    from email.message import Message
    from urllib.error import HTTPError

    from app.core.integration import (
        IntegrationAuthenticationError,
        IntegrationRateLimitError,
        IntegrationTimeoutError,
        IntegrationUnavailableError,
        IntegrationValidationError,
    )
    from app.integrations.erp import erpnext

    adapter = erpnext.ErpNextAdapter(
        "https://erp.example.test",
        "api-key",
        "api-secret",
    )
    cases = (
        (401, IntegrationAuthenticationError, False),
        (422, IntegrationValidationError, False),
        (408, IntegrationTimeoutError, True),
        (500, IntegrationUnavailableError, True),
    )
    for status_code, error_type, retryable in cases:

        def raise_http_error(request, timeout, code=status_code):
            del timeout
            raise HTTPError(
                request.full_url, code, "provider response", Message(), None
            )

        monkeypatch.setattr(erpnext, "urlopen", raise_http_error)
        with pytest.raises(error_type) as caught:
            adapter._request("GET", "/api/resource/Sales%20Order")
        assert caught.value.retryable is retryable

    headers = Message()
    headers["Retry-After"] = "7"

    def raise_rate_limit(request, timeout):
        del timeout
        raise HTTPError(request.full_url, 429, "provider response", headers, None)

    monkeypatch.setattr(erpnext, "urlopen", raise_rate_limit)
    with pytest.raises(IntegrationRateLimitError) as rate_limited:
        adapter._request("GET", "/api/resource/Sales%20Order")
    assert rate_limited.value.retry_after_seconds == 7
    assert rate_limited.value.retryable is True

    def raise_timeout(request, timeout):
        del request, timeout
        raise TimeoutError("password=must-not-escape")

    monkeypatch.setattr(erpnext, "urlopen", raise_timeout)
    with pytest.raises(IntegrationTimeoutError) as timed_out:
        adapter.upsert("Sales Order", {}, "idempotency-key")
    assert "must-not-escape" not in str(timed_out.value)
    assert timed_out.value.retryable is False


def test_erp_routes_report_safe_configuration_failures(monkeypatch, db_session):
    from types import SimpleNamespace

    from fastapi import HTTPException

    from app.core.integration import IntegrationConfigurationError
    from app.routers import integrations as routes

    secret = "erp-route-secret"

    def unavailable_adapter():
        raise IntegrationConfigurationError(
            provider="mock",
            operation="initialize",
            message=f"password={secret}",
        )

    monkeypatch.setattr(routes, "get_erp_adapter", unavailable_adapter)
    monkeypatch.setattr(
        routes,
        "_get_user_company_id",
        lambda user, db: "phase-two-company",
    )

    status_result = routes.status(user=SimpleNamespace(), db=db_session)
    assert status_result["provider"] == "mock"
    assert status_result["code"] == "not_configured"
    assert secret not in status_result["reason"]

    def unavailable_process(db):
        del db
        return unavailable_adapter()

    monkeypatch.setattr(routes, "process_pending", unavailable_process)
    with pytest.raises(HTTPException) as unavailable:
        routes.sync(user=SimpleNamespace(role="admin"), db=db_session)
    assert unavailable.value.status_code == 503
    assert secret not in str(unavailable.value.detail)


def test_payment_orchestrator_accepts_fake_without_importing_gateway_clients(
    db_session,
):
    adapters_were_loaded = "app.integrations.payments.adapters" in sys.modules
    from app.integrations.payments.normalized import as_billing_payment_provider
    from app.models import Payment
    from app.modules.billing.ports import PaymentProvider as BillingPaymentProvider
    from app.services.payments import (
        Currency,
        PaymentOrchestrator,
        PaymentProvider,
        PaymentResult,
        PaymentStatus,
        RefundResult,
    )

    class FakePaymentAdapter:
        provider_name = "fake_payment"

        def __init__(self) -> None:
            self.create_calls = 0

        async def create_payment(self, intent):
            self.create_calls += 1
            return PaymentResult(
                success=True,
                payment_id=intent.id,
                status=PaymentStatus.PENDING,
                provider_reference="external-payment-42",
            )

        async def check_status(self, provider_reference: str):
            del provider_reference
            return PaymentStatus.PENDING

        async def refund(self, provider_reference: str, amount: int | None = None):
            del provider_reference
            return RefundResult(True, "fake-refund", amount or 0, "accepted")

        def verify_webhook(self, payload: bytes, signature: str) -> bool:
            del payload, signature
            return True

    adapter = FakePaymentAdapter()
    orchestrator = PaymentOrchestrator(
        db_session,
        adapters={PaymentProvider.VISA_MASTERCARD: adapter},
    )
    idempotency_key = f"phase2-{uuid.uuid4().hex}"
    company_id = str(uuid.uuid4())
    order_id = str(uuid.uuid4())

    first = asyncio.run(
        orchestrator.create_payment(
            company_id=company_id,
            order_id=order_id,
            amount=4200,
            currency=Currency.EUR,
            provider=PaymentProvider.VISA_MASTERCARD,
            description="Provider boundary test",
            idempotency_key=idempotency_key,
        )
    )
    second = asyncio.run(
        orchestrator.create_payment(
            company_id=company_id,
            order_id=order_id,
            amount=4200,
            currency=Currency.EUR,
            provider=PaymentProvider.VISA_MASTERCARD,
            description="Provider boundary test retry",
            idempotency_key=idempotency_key,
        )
    )
    row = db_session.get(Payment, first.payment_id)

    assert str(uuid.UUID(first.payment_id)) == first.payment_id
    assert second.payment_id == first.payment_id
    assert adapter.create_calls == 1
    assert row is not None
    assert row.id == first.payment_id
    assert row.provider_reference == "external-payment-42"
    assert row.provider_reference != row.id

    normalized = as_billing_payment_provider(FakePaymentAdapter())
    assert isinstance(normalized, BillingPaymentProvider)
    normalized_result = asyncio.run(
        normalized.create_payment(
            {
                "id": str(uuid.uuid4()),
                "company_id": str(uuid.uuid4()),
                "order_id": str(uuid.uuid4()),
                "amount": 4200,
                "currency": Currency.EUR,
                "provider": PaymentProvider.VISA_MASTERCARD,
                "description": "Normalized provider test",
            }
        )
    )
    assert normalized_result.status is IntegrationStatus.ACCEPTED
    assert normalized_result.value["provider_reference"] == "external-payment-42"
    assert ("app.integrations.payments.adapters" in sys.modules) is adapters_were_loaded


def test_normalized_payment_preserves_retryable_provider_unavailable():
    from app.integrations.payments.normalized import as_billing_payment_provider
    from app.services.payments import (
        Currency,
        PaymentProvider,
        PaymentResult,
        PaymentStatus,
        RefundResult,
    )

    class TemporarilyUnavailableAdapter:
        provider_name = "temporarily_unavailable"

        async def create_payment(self, intent):
            return PaymentResult(
                success=False,
                payment_id=intent.id,
                status=PaymentStatus.FAILED,
                error_code="provider_unavailable",
                error_message="vendor-specific network failure",
            )

        async def check_status(self, provider_reference: str):
            del provider_reference
            return PaymentStatus.FAILED

        async def refund(self, provider_reference: str, amount: int | None = None):
            del provider_reference
            return RefundResult(False, "", amount or 0, "failed")

        def verify_webhook(self, payload: bytes, signature: str) -> bool:
            del payload, signature
            return False

    normalized = as_billing_payment_provider(TemporarilyUnavailableAdapter())
    result = asyncio.run(
        normalized.create_payment(
            {
                "id": str(uuid.uuid4()),
                "company_id": str(uuid.uuid4()),
                "order_id": str(uuid.uuid4()),
                "amount": 4200,
                "currency": Currency.EUR,
                "provider": PaymentProvider.VISA_MASTERCARD,
                "description": "Transient provider failure test",
            }
        )
    )

    assert result.status is IntegrationStatus.FAILED
    assert result.failure is not None
    assert result.failure.code == "provider_unavailable"
    assert result.failure.retryable is True
    assert "vendor-specific" not in result.failure.message


def test_payment_boundaries_fail_closed_without_exposing_adapter_errors(db_session):
    from app.integrations.payments.normalized import as_billing_payment_provider
    from app.models import Payment
    from app.services.payments import (
        Currency,
        PaymentOrchestrator,
        PaymentProvider,
        PaymentStatus,
    )

    secret = "payment-adapter-secret"

    class RaisingPaymentAdapter:
        provider_name = "raising_payment"

        async def create_payment(self, intent):
            del intent
            raise RuntimeError(f'{{"client_secret":"{secret}"}}')

        async def check_status(self, provider_reference: str):
            del provider_reference
            raise RuntimeError(f"api_key={secret}")

        async def refund(self, provider_reference: str, amount: int | None = None):
            del provider_reference, amount
            raise RuntimeError(f"password={secret}")

        def verify_webhook(self, payload: bytes, signature: str) -> bool:
            del payload, signature
            raise RuntimeError(f"token={secret}")

    adapter = RaisingPaymentAdapter()
    normalized = as_billing_payment_provider(adapter)
    request = {
        "id": str(uuid.uuid4()),
        "company_id": str(uuid.uuid4()),
        "order_id": str(uuid.uuid4()),
        "amount": 4200,
        "currency": Currency.EUR,
        "provider": PaymentProvider.VISA_MASTERCARD,
        "description": "Exception boundary test",
    }

    outcomes = (
        asyncio.run(normalized.create_payment(request)),
        asyncio.run(normalized.check_status("external-reference")),
        asyncio.run(normalized.refund("external-reference")),
    )

    assert all(outcome.status is IntegrationStatus.FAILED for outcome in outcomes)
    assert all(outcome.failure is not None for outcome in outcomes)
    assert all(secret not in outcome.failure.message for outcome in outcomes)
    assert normalized.verify_webhook(b"{}", "signature") is False

    orchestrator = PaymentOrchestrator(
        db_session,
        adapters={PaymentProvider.VISA_MASTERCARD: adapter},
    )
    legacy_result = asyncio.run(
        orchestrator.create_payment(
            company_id=request["company_id"],
            order_id=request["order_id"],
            amount=request["amount"],
            currency=Currency.EUR,
            provider=PaymentProvider.VISA_MASTERCARD,
            description=request["description"],
            idempotency_key=f"phase2-error-{uuid.uuid4().hex}",
        )
    )
    row = db_session.get(Payment, legacy_result.payment_id)

    assert legacy_result.status is PaymentStatus.FAILED
    assert legacy_result.error_message == "Payment provider is unavailable"
    assert secret not in legacy_result.error_message
    assert row is not None and row.status == PaymentStatus.FAILED.value
    webhook = asyncio.run(
        orchestrator.handle_webhook(
            PaymentProvider.VISA_MASTERCARD,
            b"{}",
            "signature",
        )
    )
    assert webhook == {"status": "error", "message": "Invalid signature"}

    pending_row = Payment(
        company_id=str(uuid.uuid4()),
        order_id=str(uuid.uuid4()),
        amount=4200,
        currency="EUR",
        provider=PaymentProvider.VISA_MASTERCARD.value,
        status=PaymentStatus.PENDING.value,
        provider_reference="pending-reference",
    )
    completed_row = Payment(
        company_id=str(uuid.uuid4()),
        order_id=str(uuid.uuid4()),
        amount=4200,
        currency="EUR",
        provider=PaymentProvider.VISA_MASTERCARD.value,
        status=PaymentStatus.COMPLETED.value,
        provider_reference="completed-reference",
    )
    db_session.add_all([pending_row, completed_row])
    db_session.commit()

    assert (
        asyncio.run(orchestrator.check_status(pending_row.id)) is PaymentStatus.PENDING
    )
    refund = asyncio.run(orchestrator.refund(completed_row.id))
    assert refund.success is False
    assert refund.error_message == "Payment provider is unavailable"
    assert secret not in refund.error_message


def test_legacy_payment_result_repr_hides_provider_secrets():
    from app.services.payments import PaymentResult, PaymentStatus

    sentinel = "payment-result-secret"
    result = PaymentResult(
        success=True,
        payment_id=str(uuid.uuid4()),
        status=PaymentStatus.PENDING,
        client_secret=sentinel,
        raw_response={"api_key": sentinel},
    )

    assert sentinel not in repr(result)


def test_legacy_service_exports_remain_lazy_and_compatible():
    s3_was_loaded = "app.integrations.storage.s3" in sys.modules
    adapters_were_loaded = "app.integrations.payments.adapters" in sys.modules
    from app.services import (
        PaymentOrchestrator,
        RiskEngine,
        StorageService,
        get_payment_orchestrator,
        get_risk_engine,
        get_storage_service,
    )

    assert all(
        value is not None
        for value in (
            PaymentOrchestrator,
            RiskEngine,
            StorageService,
            get_payment_orchestrator,
            get_risk_engine,
            get_storage_service,
        )
    )
    assert ("app.integrations.storage.s3" in sys.modules) is s3_was_loaded
    assert ("app.integrations.payments.adapters" in sys.modules) is adapters_were_loaded


def test_s3_provider_uses_shared_timeout_and_attempt_conventions(monkeypatch):
    from app.integrations.storage import s3 as s3_module

    captured: dict[str, Any] = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(s3_module.boto3, "client", fake_client)
    provider = s3_module.S3ObjectStorageProvider(
        bucket="phase-two-test",
        region="eu-west-1",
        endpoint_url=None,
        access_key_id=None,
        secret_access_key=None,
        retry_attempts=4,
        connect_timeout_seconds=2.5,
        read_timeout_seconds=11.0,
    )

    config = captured["config"]
    assert config.connect_timeout == 2.5
    assert config.read_timeout == 11.0
    assert config.retries == {"total_max_attempts": 4, "mode": "standard"}
    service = StorageService(provider)
    assert service.bucket == "phase-two-test"
    assert service.region == "eu-west-1"
    assert service.endpoint_url is None
    assert service.client is provider.client


def test_s3_provider_normalizes_unexpected_upload_exceptions():
    from app.integrations.storage.s3 import S3ObjectStorageProvider

    secret = "raw-storage-secret"

    class RaisingClient:
        def upload_fileobj(self, *args, **kwargs):
            del args, kwargs
            raise RuntimeError(f"password={secret}")

    provider = S3ObjectStorageProvider(
        bucket="phase-two-test",
        region="eu-west-1",
        endpoint_url=None,
        access_key_id=None,
        secret_access_key=None,
        retry_attempts=3,
        connect_timeout_seconds=2.5,
        read_timeout_seconds=11.0,
        client=RaisingClient(),
    )

    result = provider.put_file(BytesIO(b"geovision"), "dataset/file.tif")

    assert result.status is IntegrationStatus.FAILED
    assert result.failure is not None and result.failure.retryable is False
    assert secret not in result.failure.message


def test_s3_provider_classifies_sdk_failures_and_hides_constructor_errors(monkeypatch):
    from boto3.exceptions import S3UploadFailedError
    from botocore.exceptions import (
        ClientError,
        NoCredentialsError,
        ParamValidationError,
    )

    from app.core.integration import IntegrationUnavailableError
    from app.integrations.storage import s3 as s3_module

    secret = "s3-provider-secret"

    class AccessDeniedClient:
        def get_object(self, **kwargs):
            del kwargs
            raise ClientError(
                {
                    "Error": {
                        "Code": "AccessDenied",
                        "Message": f"password={secret}",
                    }
                },
                "GetObject",
            )

    denied_provider = s3_module.S3ObjectStorageProvider(
        bucket="phase-two-test",
        region="eu-west-1",
        endpoint_url=None,
        access_key_id=None,
        secret_access_key=None,
        retry_attempts=3,
        connect_timeout_seconds=2.5,
        read_timeout_seconds=11.0,
        client=AccessDeniedClient(),
    )
    denied = denied_provider.get_bytes("dataset/file.tif")
    assert denied.status is IntegrationStatus.FAILED
    assert denied.failure is not None
    assert denied.failure.code == "storage_authentication_failed"
    assert denied.failure.retryable is False
    assert secret not in denied.failure.message

    class UploadFailureClient:
        def upload_fileobj(self, *args, **kwargs):
            del args, kwargs
            raise S3UploadFailedError(f"api_key={secret}")

    upload_provider = s3_module.S3ObjectStorageProvider(
        bucket="phase-two-test",
        region="eu-west-1",
        endpoint_url=None,
        access_key_id=None,
        secret_access_key=None,
        retry_attempts=3,
        connect_timeout_seconds=2.5,
        read_timeout_seconds=11.0,
        client=UploadFailureClient(),
    )
    upload = upload_provider.put_file(BytesIO(b"geovision"), "dataset/file.tif")
    assert upload.status is IntegrationStatus.RETRYING
    assert upload.failure is not None and upload.failure.retryable is True
    assert secret not in upload.failure.message

    class MissingCredentialsClient:
        def get_object(self, **kwargs):
            del kwargs
            raise NoCredentialsError()

    missing_provider = s3_module.S3ObjectStorageProvider(
        bucket="phase-two-test",
        region="eu-west-1",
        endpoint_url=None,
        access_key_id=None,
        secret_access_key=None,
        retry_attempts=3,
        connect_timeout_seconds=2.5,
        read_timeout_seconds=11.0,
        client=MissingCredentialsClient(),
    )
    missing = missing_provider.get_bytes("dataset/file.tif")
    assert missing.status is IntegrationStatus.NOT_CONFIGURED
    assert missing.failure is not None and missing.failure.retryable is False

    class InvalidRequestClient:
        def get_object(self, **kwargs):
            del kwargs
            raise ParamValidationError(report=f"password={secret}")

    invalid_provider = s3_module.S3ObjectStorageProvider(
        bucket="phase-two-test",
        region="eu-west-1",
        endpoint_url=None,
        access_key_id=None,
        secret_access_key=None,
        retry_attempts=3,
        connect_timeout_seconds=2.5,
        read_timeout_seconds=11.0,
        client=InvalidRequestClient(),
    )
    invalid = invalid_provider.get_bytes("dataset/file.tif")
    assert invalid.status is IntegrationStatus.FAILED
    assert invalid.failure is not None
    assert invalid.failure.code == "storage_invalid_request"
    assert invalid.failure.retryable is False
    assert secret not in invalid.failure.message

    def fail_client(**kwargs):
        del kwargs
        raise RuntimeError(f"client_secret={secret}")

    monkeypatch.setattr(s3_module.boto3, "client", fail_client)
    with pytest.raises(IntegrationUnavailableError) as constructor_error:
        s3_module.S3ObjectStorageProvider(
            bucket="phase-two-test",
            region="eu-west-1",
            endpoint_url=None,
            access_key_id=None,
            secret_access_key=None,
            retry_attempts=3,
            connect_timeout_seconds=2.5,
            read_timeout_seconds=11.0,
        )
    assert secret not in str(constructor_error.value)


def test_s3_factory_rejects_partial_explicit_credentials(monkeypatch):
    from app.core.integration import IntegrationConfigurationError
    from app.integrations.storage import factory, s3 as s3_module

    calls = 0

    def fake_client(**kwargs):
        nonlocal calls
        del kwargs
        calls += 1
        return object()

    monkeypatch.setattr(s3_module.boto3, "client", fake_client)
    monkeypatch.delenv("S3_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("S3_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)

    for access_key, secret_key in (("access-only", None), (None, "secret-only")):
        config = Settings(
            _env_file=None,
            object_storage_provider="s3",
            s3_access_key_id=access_key,
            s3_secret_access_key=secret_key,
        )
        with pytest.raises(
            IntegrationConfigurationError,
            match="credentials are incomplete",
        ):
            factory.create_object_storage_provider(config)

    assert calls == 0


def test_required_provider_ports_are_available():
    from app.core.events import EventPublisher, QueuePublisher
    from app.modules.analytics.ports import TextGenerationProvider
    from app.modules.assets.ports import AssetManagementProvider, GISProvider
    from app.modules.billing.ports import PaymentProvider
    from app.modules.identity.ports import IdentityProvider
    from app.modules.monitoring.ports import MaritimeProvider, WeatherProvider
    from app.modules.notifications.ports import NotificationProvider
    from app.modules.operations.ports import ConstructionProvider
    from app.modules.orders.ports import ERPProvider
    from app.modules.processing.ports import ProcessingProvider
    from app.modules.datasets.ports import SatelliteProvider

    assert all(
        port is not None
        for port in (
            AssetManagementProvider,
            ConstructionProvider,
            ERPProvider,
            EventPublisher,
            GISProvider,
            IdentityProvider,
            MaritimeProvider,
            NotificationProvider,
            PaymentProvider,
            ProcessingProvider,
            QueuePublisher,
            SatelliteProvider,
            TextGenerationProvider,
            WeatherProvider,
        )
    )


def test_domain_modules_do_not_load_environment_or_vendor_clients():
    forbidden_roots = {
        "app.integrations",
        "boto3",
        "botocore",
        "httpx",
        "os",
        "paho",
        "requests",
        "stripe",
    }
    for path in (APP_ROOT / "modules").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                targets = [node.module or ""]
            else:
                targets = []
            for target in targets:
                assert not any(
                    target == root or target.startswith(f"{root}.")
                    for root in forbidden_roots
                ), f"{path}: domain module imports {target}"
            if isinstance(node, ast.Attribute):
                owner = node.value
                if isinstance(owner, ast.Name) and owner.id == "os":
                    assert node.attr not in {"getenv", "environ"}, (
                        f"{path}: domain module reads process environment"
                    )


def test_admin_integration_credentials_are_encrypted_at_rest(db_session, monkeypatch):
    from app.core import config as config_module
    from app.core import encryption
    from app.routers.admin import IntegrationCreate, create_integration

    company = Company(
        name="Phase 2 encryption",
        email=f"phase2-{uuid.uuid4().hex}@example.test",
    )
    db_session.add(company)
    db_session.flush()
    api_key = "integration-api-key-sentinel"
    api_secret = "integration-api-secret-sentinel"
    monkeypatch.setattr(config_module.settings, "encryption_key", TEST_FERNET_KEY)
    monkeypatch.setattr(encryption, "_fernet", None)

    response = asyncio.run(
        create_integration(
            company.id,
            IntegrationCreate(
                connector_type="arcgis",
                name="Encrypted integration",
                api_key=api_key,
                api_secret=api_secret,
            ),
            db_session,
        )
    )
    row = db_session.get(Integration, response.id)

    assert row is not None
    assert row.api_key_encrypted != api_key
    assert row.api_secret_encrypted != api_secret
    assert api_key not in row.api_key_encrypted
    assert api_secret not in row.api_secret_encrypted
    assert encryption.decrypt(row.api_key_encrypted) == api_key
    assert encryption.decrypt(row.api_secret_encrypted) == api_secret


def test_deployed_credential_writes_never_fall_back_to_plaintext(monkeypatch):
    from app.core import config as config_module
    from app.core import encryption

    sentinel = "must-never-be-stored-plain"
    monkeypatch.setattr(
        config_module.settings,
        "env",
        RuntimeEnvironment.PRODUCTION,
    )
    monkeypatch.setattr(encryption, "_get_fernet", lambda: None)

    with pytest.raises(RuntimeError) as unavailable:
        encryption.encrypt(sentinel)

    assert sentinel not in str(unavailable.value)


def test_phase_34_openapi_contract_is_byte_stable(client):
    payload = json.dumps(
        client.app.openapi(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    assert hashlib.sha256(payload).hexdigest() == PHASE_34_OPENAPI_SHA256
