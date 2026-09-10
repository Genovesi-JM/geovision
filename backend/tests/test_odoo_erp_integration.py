from __future__ import annotations

import hashlib
import hmac
import json
import time
from types import SimpleNamespace

import pytest

from app.core.events import DomainEvent
from app.core.config import Settings
from app.core.integration import (
    IntegrationFailure,
    IntegrationResult,
    IntegrationUnavailableError,
)
from app.core.time import utc_now
from app.database import SessionLocal
from app.integrations.erp.odoo import OdooAdapter
from app.integrations.erp.factory import get_erp_adapter
from app.models import ErpCallbackReceipt, ErpExternalReference, IntegrationOutbox, Order
from app.modules.orders.ports import ERPWriteResult
from app.services.erp_callbacks import (
    ErpCallbackError,
    apply_odoo_status_callback,
    verify_callback_signature,
)
from app.services.erp_sync import enqueue_erp_event
from app.services.event_consumers import _consume_erp_sync
from app.workers.erp_worker_repository import SqlAlchemyErpRepository
from app.workers.erp_worker_runner import run_erp_cycle


class _Response:
    def __init__(self, payload: object) -> None:
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def _clear_erp(db_session) -> None:
    db_session.query(ErpCallbackReceipt).delete()
    db_session.query(ErpExternalReference).delete()
    db_session.query(IntegrationOutbox).delete()
    db_session.commit()


def test_odoo_adapter_uses_json2_bridge_and_canonical_resource(monkeypatch):
    from app.integrations.erp import odoo

    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data)
        captured["timeout"] = timeout
        return _Response(
            {
                "external_id": "SO-42",
                "external_model": "sale.order",
                "invoice_status": "posted",
                "stock_status": "ready",
            }
        )

    monkeypatch.setattr(odoo, "urlopen", fake_urlopen)
    adapter = OdooAdapter(
        "https://tenant.odoo.example",
        "tenant_database",
        "top-secret-api-key",
        timeout_seconds=7,
    )

    result = adapter.upsert(
        "order",
        {
            "geovision_id": "gv-order-42",
            "organization_id": "gv-org-9",
            "source_event": "order.created",
            "currency": "AOA",
        },
        "order:gv-order-42:created.v1",
    )

    assert result.ok is True
    assert result.value == ERPWriteResult(
        external_id="SO-42",
        external_model="sale.order",
        invoice_status="posted",
        stock_status="ready",
    )
    assert captured["url"].endswith(
        "/json/2/geovision.integration.bridge/sync_from_geovision"
    )
    assert captured["headers"]["Authorization"] == "bearer top-secret-api-key"
    assert captured["headers"]["X-odoo-database"] == "tenant_database"
    assert captured["body"] == {
        "context": {"tracking_disable": False},
        "resource_type": "order",
        "geovision_id": "gv-order-42",
        "organization_id": "gv-org-9",
        "source_event": "order.created",
        "idempotency_key": "order:gv-order-42:created.v1",
        "values": {"currency": "AOA"},
    }
    assert captured["timeout"] == 7


def test_odoo_factory_requires_complete_configuration_and_redacts_secrets(monkeypatch):
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    config = Settings(
        _env_file=None,
        env="test",
        erp_provider="odoo",
        odoo_base_url="https://tenant.odoo.example/",
        odoo_database="tenant_database",
        odoo_api_key="odoo-secret-key",
        odoo_webhook_secret="odoo-secret-callback",
    )

    adapter = get_erp_adapter(config)

    assert isinstance(adapter, OdooAdapter)
    assert adapter.base_url == "https://tenant.odoo.example"
    assert config.safe_summary()["configured"]["odoo"] is True
    dumped = config.model_dump()
    assert dumped["odoo_api_key"] == "[REDACTED]"
    assert dumped["odoo_webhook_secret"] == "[REDACTED]"
    assert "odoo-secret" not in config.model_dump_json()


def test_event_consumer_never_calls_provider_and_preserves_pending_work(db_session):
    _clear_erp(db_session)
    item = enqueue_erp_event(
        db_session,
        company_id=None,
        aggregate_type="order",
        aggregate_id="gv-order-event",
        event_type="order.created",
        payload={"total": 15},
        version="created.v1",
        provider="odoo",
    )
    db_session.commit()
    event = DomainEvent(
        name="erp.sync_requested",
        aggregate_type="integration_outbox",
        aggregate_id=item.id,
        payload={"integration_outbox_id": item.id, "provider": "odoo"},
    )

    _consume_erp_sync(db_session, event)
    db_session.commit()
    db_session.refresh(item)

    assert item.status == "pending"
    assert item.attempts == 0
    assert item.external_id is None


class _SuccessfulProvider:
    provider_name = "odoo"

    def __init__(self) -> None:
        self.calls = []

    def upsert(self, resource_type, payload, idempotency_key):
        self.calls.append((resource_type, payload, idempotency_key))
        return IntegrationResult.accepted(
            provider="odoo",
            operation="upsert",
            value=ERPWriteResult(
                external_id="SO-100",
                external_model="sale.order",
                invoice_status="draft",
                stock_status="waiting",
            ),
        )

    def health(self):
        return {"provider": "odoo", "configured": True}


class _UnavailableProvider(_SuccessfulProvider):
    def upsert(self, resource_type, payload, idempotency_key):
        del resource_type, payload, idempotency_key
        raise IntegrationUnavailableError(
            provider="odoo",
            operation="upsert",
            message="Odoo is temporarily unavailable; api_key=must-not-escape",
        )


class _RejectedProvider(_SuccessfulProvider):
    def upsert(self, resource_type, payload, idempotency_key):
        del resource_type, payload, idempotency_key
        return IntegrationResult.failed(
            provider="odoo",
            operation="upsert",
            failure=IntegrationFailure(
                code="invalid_order",
                message="Odoo rejected the canonical order",
                retryable=False,
            ),
        )


def test_worker_uses_pinned_provider_and_persists_external_mapping(db_session):
    _clear_erp(db_session)
    item = enqueue_erp_event(
        db_session,
        company_id=None,
        aggregate_type="order",
        aggregate_id="gv-order-100",
        event_type="order.created",
        payload={"currency": "AOA", "total": 1250},
        version="created.v1",
        provider="odoo",
    )
    db_session.commit()
    provider = _SuccessfulProvider()
    resolved = []

    result = run_erp_cycle(
        SqlAlchemyErpRepository(SessionLocal),
        worker_id="erp-test-worker",
        provider_resolver=lambda name: resolved.append(name) or provider,
        retry_initial_seconds=60,
        retry_max_seconds=60,
    )

    db_session.expire_all()
    stored = db_session.get(IntegrationOutbox, item.id)
    reference = db_session.query(ErpExternalReference).filter_by(
        provider="odoo", resource_type="order", internal_id="gv-order-100"
    ).one()
    assert result["completed"] == 1
    assert resolved == ["odoo"]
    assert stored.status == "completed"
    assert stored.external_id == "SO-100"
    assert reference.external_id == "SO-100"
    assert reference.internal_id == "gv-order-100"
    assert reference.invoice_status == "draft"
    assert provider.calls[0][0] == "order"
    assert provider.calls[0][1]["geovision_id"] == "gv-order-100"


def test_odoo_downtime_keeps_core_order_and_durable_retry(db_session):
    _clear_erp(db_session)
    order = Order(
        id="gv-order-downtime",
        currency="AOA",
        fulfilment_status="CONFIRMED",
        payment_status="PAID",
        status="confirmed",
    )
    db_session.add(order)
    item = enqueue_erp_event(
        db_session,
        company_id=None,
        aggregate_type="order",
        aggregate_id=order.id,
        event_type="order.created",
        payload={"total": 42},
        version="created.v1",
        provider="odoo",
    )
    db_session.commit()

    result = run_erp_cycle(
        SqlAlchemyErpRepository(SessionLocal),
        worker_id="erp-downtime-worker",
        provider_resolver=lambda _: _UnavailableProvider(),
        retry_initial_seconds=60,
        retry_max_seconds=60,
    )

    db_session.expire_all()
    assert result["retried"] == 1
    assert db_session.get(Order, order.id).fulfilment_status == "CONFIRMED"
    stored = db_session.get(IntegrationOutbox, item.id)
    assert stored.status == "failed"
    assert stored.attempts == 1
    assert stored.next_attempt_at is not None
    assert stored.last_error_code == "unavailable"
    assert "must-not-escape" not in (stored.last_error or "")


def test_non_retryable_failure_is_visible_and_requeueable(db_session):
    _clear_erp(db_session)
    item = enqueue_erp_event(
        db_session,
        company_id=None,
        aggregate_type="order",
        aggregate_id="gv-order-rejected",
        event_type="order.created",
        payload={"total": -1},
        version="created.v1",
        provider="odoo",
    )
    db_session.commit()
    repository = SqlAlchemyErpRepository(SessionLocal)

    result = run_erp_cycle(
        repository,
        worker_id="erp-rejected-worker",
        provider_resolver=lambda _: _RejectedProvider(),
    )

    db_session.expire_all()
    stored = db_session.get(IntegrationOutbox, item.id)
    assert result["dead_lettered"] == 1
    assert stored.status == "dead_letter"
    assert stored.dead_lettered_at is not None
    assert repository.requeue_dead_letter(item.id, now=utc_now()) is True
    db_session.expire_all()
    assert db_session.get(IntegrationOutbox, item.id).status == "pending"


def test_callback_signature_replay_and_projection_never_overwrite_order(db_session):
    _clear_erp(db_session)
    secret = "callback-secret-that-is-long-enough-for-production"
    raw = b'{"event_id":"evt-1"}'
    timestamp = "1700000000"
    signature = hmac.new(
        secret.encode(), timestamp.encode() + b"." + raw, hashlib.sha256
    ).hexdigest()
    verify_callback_signature(
        raw,
        timestamp=timestamp,
        signature=f"sha256={signature}",
        secret=secret,
        replay_window_seconds=300,
        now_seconds=1700000000,
    )
    with pytest.raises(ErpCallbackError) as missing_scheme:
        verify_callback_signature(
            raw,
            timestamp=timestamp,
            signature=signature,
            secret=secret,
            replay_window_seconds=300,
            now_seconds=1700000000,
        )
    assert missing_scheme.value.code == "odoo_callback_signature_invalid"
    with pytest.raises(ErpCallbackError) as expired:
        verify_callback_signature(
            raw,
            timestamp=timestamp,
            signature=f"sha256={signature}",
            secret=secret,
            replay_window_seconds=300,
            now_seconds=1700000400,
        )
    assert expired.value.code == "odoo_callback_expired"

    order = Order(
        id="gv-order-callback",
        currency="AOA",
        fulfilment_status="IN_PROGRESS",
        payment_status="AUTHORIZED",
        status="processing",
    )
    reference = ErpExternalReference(
        provider="odoo",
        resource_type="order",
        internal_id=order.id,
        external_model="sale.order",
        external_id="SO-CALLBACK",
    )
    db_session.add_all([order, reference])
    db_session.commit()
    payload = {
        "event_id": "odoo-event-1",
        "event_type": "invoice.status",
        "resource_type": "order",
        "geovision_id": order.id,
        "external_id": "SO-CALLBACK",
        "external_model": "sale.order",
        "invoice_status": "posted",
        "stock_status": "partially_available",
        "purchase_status": None,
        "provider_updated_at": None,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    outcome, projected = apply_odoo_status_callback(
        db_session, payload=payload, payload_sha256=digest
    )
    db_session.commit()
    duplicate, _ = apply_odoo_status_callback(
        db_session, payload=payload, payload_sha256=digest
    )

    db_session.refresh(order)
    assert outcome == "processed"
    assert duplicate == "duplicate"
    assert projected.invoice_status == "posted"
    assert projected.stock_status == "partially_available"
    assert order.fulfilment_status == "IN_PROGRESS"
    assert order.payment_status == "AUTHORIZED"
    assert db_session.query(ErpCallbackReceipt).count() == 1


def test_reference_status_is_tenant_scoped(monkeypatch, db_session):
    from app.routers import integrations

    _clear_erp(db_session)
    db_session.add(
        ErpExternalReference(
            company_id="company-a",
            provider="odoo",
            resource_type="order",
            internal_id="gv-order-visible",
            external_id="SO-PRIVATE",
            invoice_status="posted",
        )
    )
    db_session.commit()
    monkeypatch.setattr(
        integrations, "_get_user_company_id", lambda user, db: "company-a"
    )

    visible = integrations.reference_status(
        "order",
        "gv-order-visible",
        user=SimpleNamespace(),
        db=db_session,
    )
    assert visible["geovision_id"] == "gv-order-visible"
    assert visible["invoice_status"] == "posted"
    assert "external_id" not in visible

    monkeypatch.setattr(
        integrations, "_get_user_company_id", lambda user, db: "company-b"
    )
    with pytest.raises(Exception) as hidden:
        integrations.reference_status(
            "order",
            "gv-order-visible",
            user=SimpleNamespace(),
            db=db_session,
        )
    assert hidden.value.status_code == 404


def test_signed_callback_http_contract(client, monkeypatch, db_session):
    from app.routers import integrations

    _clear_erp(db_session)
    internal_id = "gv-order-http-callback"
    db_session.add(
        ErpExternalReference(
            provider="odoo",
            resource_type="order",
            internal_id=internal_id,
            external_model="sale.order",
            external_id="SO-HTTP",
        )
    )
    db_session.commit()
    secret = "http-callback-secret-that-is-long-enough"
    monkeypatch.setattr(integrations.settings, "odoo_webhook_secret", secret)
    payload = {
        "event_id": "odoo-http-event-1",
        "event_type": "stock.status",
        "resource_type": "order",
        "geovision_id": internal_id,
        "external_id": "SO-HTTP",
        "external_model": "sale.order",
        "stock_status": "assigned",
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    digest = hmac.new(
        secret.encode(), timestamp.encode() + b"." + raw, hashlib.sha256
    ).hexdigest()

    rejected = client.post(
        "/integrations/erp/odoo/callback",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-GeoVision-Timestamp": timestamp,
            "X-GeoVision-Signature": f"sha256={'0' * 64}",
        },
    )
    accepted = client.post(
        "/integrations/erp/odoo/callback",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-GeoVision-Timestamp": timestamp,
            "X-GeoVision-Signature": f"sha256={digest}",
        },
    )
    repeated = client.post(
        "/integrations/erp/odoo/callback",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-GeoVision-Timestamp": timestamp,
            "X-GeoVision-Signature": f"sha256={digest}",
        },
    )

    assert rejected.status_code == 401
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "processed"
    assert repeated.status_code == 200
    assert repeated.json()["status"] == "duplicate"
    db_session.expire_all()
    reference = db_session.query(ErpExternalReference).filter_by(
        provider="odoo", resource_type="order", internal_id=internal_id
    ).one()
    assert reference.stock_status == "assigned"
