from __future__ import annotations

import asyncio
import json
import uuid

from app.core.tokens import create_user_access_token
from app.models import (
    CatalogItem,
    Company,
    Order,
    OrderEvent,
    Payment,
    PaymentWebhookEvent,
    User,
)
from app.services.payments import (
    Currency,
    PaymentIdempotencyConflict,
    PaymentOrchestrator,
    PaymentProvider,
    PaymentResult,
    PaymentStatus,
    RefundResult,
)


def _login_headers(client, email: str, password: str = "123456") -> dict[str, str]:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _headers(user: User) -> dict[str, str]:
    token = create_user_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        auth_generation=user.auth_generation,
    )
    return {"Authorization": f"Bearer {token}"}


def _add_cart_item(client, cart_id: str) -> dict:
    product = client.get("/catalog/items").json()[0]
    response = client.post(
        f"/shop/cart/{cart_id}/items",
        json={"product_id": product["id"], "quantity": 1, "currency": "AOA"},
    )
    assert response.status_code == 200, response.text
    return product


def _remove_order_fixture(db_session, order: Order) -> None:
    """Keep session-scoped acceptance data from affecting older aggregate tests."""
    db_session.query(PaymentWebhookEvent).filter(
        PaymentWebhookEvent.order_id == order.id
    ).delete(synchronize_session=False)
    db_session.query(Payment).filter(Payment.order_id == order.id).delete(
        synchronize_session=False
    )
    db_session.query(OrderEvent).filter(OrderEvent.order_id == order.id).delete(
        synchronize_session=False
    )
    db_session.delete(order)
    db_session.commit()


def test_checkout_is_idempotent_and_uses_canonical_catalog_snapshots(client, db_session):
    headers = _login_headers(client, "teste@clientes.com")
    cart_id = f"phase8-{uuid.uuid4().hex}"
    product = _add_cart_item(client, cart_id)
    headers["Idempotency-Key"] = f"checkout-{uuid.uuid4().hex}"
    payload = {
        "payment_method": "iban_angola",
        "currency": "AOA",
        "billing_info": {"name": "GeoVision customer", "email": "customer@example.com"},
    }

    first = client.post(f"/orders/checkout/{cart_id}", headers=headers, json=payload)
    second = client.post(f"/orders/checkout/{cart_id}", headers=headers, json=payload)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["order_id"] == second.json()["order_id"]

    order = db_session.get(Order, first.json()["order_id"])
    assert order is not None
    assert order.id != order.payment_reference
    assert order.fulfilment_status == "CONFIRMED"
    assert order.payment_status == "PENDING"
    assert len(order.items) == 1
    item = order.items[0]
    assert item.catalog_item_id == product["id"]
    assert item.catalog_item_type == product["item_type"]
    assert json.loads(item.pricing_snapshot_json)["unit_amount"] == product["unit_amount"]
    assert item.product_id is None or len(item.product_id) <= 36

    detail = client.get(f"/orders/{order.id}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["payment_status"] == "PENDING"
    assert "payment_reference" not in detail.json()
    _remove_order_fixture(db_session, order)


def test_payment_api_uses_order_truth_and_enforces_customer_ownership(client, db_session):
    owner_headers = _login_headers(client, "teste@clientes.com")
    cart_id = f"phase8-payment-{uuid.uuid4().hex}"
    _add_cart_item(client, cart_id)
    checkout = client.post(
        f"/orders/checkout/{cart_id}",
        headers={**owner_headers, "Idempotency-Key": f"checkout-{uuid.uuid4().hex}"},
        json={
            "payment_method": "iban_angola",
            "currency": "AOA",
            "billing_info": {"name": "Owner", "email": "owner@example.com"},
        },
    )
    assert checkout.status_code == 200, checkout.text
    order = db_session.get(Order, checkout.json()["order_id"])
    assert order is not None
    payment = db_session.get(Payment, order.payment_intent_id)
    assert payment is not None

    tampered = client.post(
        "/payments/",
        headers=owner_headers,
        json={
            "company_id": payment.company_id,
            "order_id": order.id,
            "amount": int(order.total) - 1,
            "currency": order.currency,
            "provider": "iban_transfer",
            "description": "client-controlled text",
        },
    )
    assert tampered.status_code == 422

    outsider = User(
        email=f"phase8-outsider-{uuid.uuid4().hex}@example.com",
        role="cliente",
        is_active=True,
    )
    db_session.add(outsider)
    db_session.commit()
    assert client.get(f"/payments/{payment.id}", headers=_headers(outsider)).status_code == 404
    assert client.get(f"/orders/{order.id}", headers=_headers(outsider)).status_code == 404
    _remove_order_fixture(db_session, order)


def test_payment_provider_catalog_is_not_shadowed_by_payment_id_route(client):
    response = client.get("/payments/providers")
    assert response.status_code == 200, response.text
    assert {row["provider"] for row in response.json()} >= {
        "multicaixa_express",
        "visa_mastercard",
        "iban_transfer",
    }


class _WebhookAdapter:
    provider_name = "phase8_fake"

    async def create_payment(self, intent):
        return PaymentResult(
            success=True,
            payment_id=intent.id,
            status=PaymentStatus.PENDING,
            provider_reference="pi_phase8",
        )

    async def check_status(self, provider_reference: str):
        del provider_reference
        return PaymentStatus.PENDING

    async def refund(self, provider_reference: str, amount: int | None = None):
        del provider_reference
        return RefundResult(True, "refund-phase8", amount or 0, "accepted")

    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        del payload
        return signature == "valid"


def test_webhook_ledger_makes_settlement_and_order_effects_idempotent(db_session):
    company = Company(
        name=f"Phase 8 {uuid.uuid4().hex[:8]}",
        email=f"phase8-{uuid.uuid4().hex}@example.com",
        status="active",
    )
    customer = User(
        email=f"phase8-customer-{uuid.uuid4().hex}@example.com",
        role="cliente",
        is_active=True,
    )
    db_session.add_all([company, customer])
    db_session.flush()
    order = Order(
        user_id=customer.id,
        company_id=company.id,
        organization_id=company.id,
        order_number=f"GV-2026-{uuid.uuid4().hex[:8].upper()}",
        order_type="SERVICE",
        status="awaiting_payment",
        fulfilment_status="CONFIRMED",
        payment_status="PENDING",
        currency="EUR",
        subtotal=4200,
        total=4200,
    )
    db_session.add(order)
    db_session.flush()
    payment = Payment(
        company_id=company.id,
        organization_id=company.id,
        order_id=order.id,
        amount=4200,
        currency="EUR",
        provider=PaymentProvider.VISA_MASTERCARD.value,
        status=PaymentStatus.PENDING.value,
        provider_reference="pi_phase8",
    )
    db_session.add(payment)
    db_session.commit()

    orchestrator = PaymentOrchestrator(
        db_session,
        adapters={PaymentProvider.VISA_MASTERCARD: _WebhookAdapter()},
    )
    payload = json.dumps(
        {
            "id": "evt_phase8_once",
            "type": "payment_intent.succeeded",
            "data": {"object": {"id": "pi_phase8"}},
        }
    ).encode()
    first = asyncio.run(
        orchestrator.handle_webhook(
            PaymentProvider.VISA_MASTERCARD, payload, "valid"
        )
    )
    second = asyncio.run(
        orchestrator.handle_webhook(
            PaymentProvider.VISA_MASTERCARD, payload, "valid"
        )
    )

    db_session.refresh(order)
    db_session.refresh(payment)
    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert payment.status == "completed"
    assert order.payment_status == "PAID"
    assert order.fulfilment_status == "PAID"
    assert (
        db_session.query(PaymentWebhookEvent)
        .filter(PaymentWebhookEvent.event_id == "evt_phase8_once")
        .count()
        == 1
    )
    assert (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order.id, OrderEvent.event_type == "payment_paid")
        .count()
        == 1
    )


def test_signed_stripe_webhook_with_malformed_nested_data_is_safely_ignored(db_session):
    orchestrator = PaymentOrchestrator(
        db_session,
        adapters={PaymentProvider.VISA_MASTERCARD: _WebhookAdapter()},
    )
    payload = json.dumps(
        {
            "id": f"evt_malformed_{uuid.uuid4().hex}",
            "type": "payment_intent.succeeded",
            "data": [],
        }
    ).encode()

    result = asyncio.run(
        orchestrator.handle_webhook(
            PaymentProvider.VISA_MASTERCARD, payload, "valid"
        )
    )

    assert result["status"] == "ok"
    assert result["duplicate"] is False
    receipt = (
        db_session.query(PaymentWebhookEvent)
        .filter(PaymentWebhookEvent.event_id == json.loads(payload)["id"])
        .one()
    )
    assert receipt.outcome == "IGNORED"
    assert receipt.provider_reference is None


def test_internal_order_lifecycle_supports_mixed_catalog_and_blocks_shortcuts(
    client, db_session
):
    organization = Company(
        name=f"Mixed lifecycle {uuid.uuid4().hex[:8]}",
        email=f"mixed-{uuid.uuid4().hex}@example.com",
        status="active",
    )
    db_session.add(organization)
    db_session.commit()
    items = db_session.query(CatalogItem).filter(CatalogItem.status == "PUBLISHED").all()
    physical = next(item for item in items if item.item_type == "PHYSICAL_PRODUCT")
    service = next(item for item in items if item.item_type != "PHYSICAL_PRODUCT")
    admin_headers = _login_headers(client, "teste@admin.com")

    created = client.post(
        "/orders/internal",
        headers=admin_headers,
        json={
            "organization_id": organization.id,
            "currency": "AOA",
            "items": [
                {"catalog_item_id": physical.id, "quantity": 1},
                {"catalog_item_id": service.id, "quantity": 1},
            ],
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["order_type"] == "MIXED"
    assert body["fulfilment_status"] == "DRAFT"
    assert {item["catalog_item_type"] for item in body["items"]} == {
        physical.item_type,
        service.item_type,
    }

    shortcut = client.patch(
        f"/orders/internal/{body['id']}/fulfilment",
        headers=admin_headers,
        json={"status": "PROCESSING", "expected_version": body["lifecycle_version"]},
    )
    assert shortcut.status_code == 409

    quoted = client.patch(
        f"/orders/internal/{body['id']}/fulfilment",
        headers=admin_headers,
        json={"status": "QUOTED", "expected_version": body["lifecycle_version"]},
    )
    assert quoted.status_code == 200, quoted.text
    confirmed = client.patch(
        f"/orders/internal/{body['id']}/fulfilment",
        headers=admin_headers,
        json={
            "status": "CONFIRMED",
            "expected_version": quoted.json()["lifecycle_version"],
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    unpaid = client.patch(
        f"/orders/internal/{body['id']}/fulfilment",
        headers=admin_headers,
        json={
            "status": "SCHEDULING",
            "expected_version": confirmed.json()["lifecycle_version"],
        },
    )
    assert unpaid.status_code == 422

    customer_headers = _login_headers(client, "teste@clientes.com")
    assert client.get("/orders/internal", headers=customer_headers).status_code == 403


def test_payment_idempotency_rejects_cross_order_reuse(db_session):
    adapter = _WebhookAdapter()
    orchestrator = PaymentOrchestrator(
        db_session,
        adapters={PaymentProvider.VISA_MASTERCARD: adapter},
    )
    key = f"phase8-payment-{uuid.uuid4().hex}"
    common = dict(
        company_id=str(uuid.uuid4()),
        amount=7500,
        currency=Currency.EUR,
        provider=PaymentProvider.VISA_MASTERCARD,
        description="Phase 8 payment",
        idempotency_key=key,
    )
    asyncio.run(orchestrator.create_payment(order_id=str(uuid.uuid4()), **common))
    try:
        asyncio.run(orchestrator.create_payment(order_id=str(uuid.uuid4()), **common))
    except PaymentIdempotencyConflict:
        pass
    else:
        raise AssertionError("cross-order idempotency-key reuse must fail")
