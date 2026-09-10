from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from app.core.event_names import EventNames
from app.models import (
    CatalogItem,
    Company,
    EventOutbox,
    IntegrationOutbox,
    Inventory,
    Order,
    Product,
    User,
)
from app.modules.orders.schemas import DraftOrderCreate
from app.modules.orders.services import create_draft_order
from app.services.orders import OrderService, PaymentMethod


def _login_headers(client, email: str) -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": "123456"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _add_cart_item(client, cart_id: str) -> dict:
    item = client.get("/catalog/items").json()[0]
    response = client.post(
        f"/shop/cart/{cart_id}/items",
        json={"product_id": item["id"], "quantity": 1, "currency": "AOA"},
    )
    assert response.status_code == 200, response.text
    return item


def _assert_committed_erp_handoff(db_session, order_id: str) -> IntegrationOutbox:
    db_session.expire_all()
    order = db_session.get(Order, order_id)
    assert order is not None

    outbox = (
        db_session.query(IntegrationOutbox)
        .filter(
            IntegrationOutbox.aggregate_type == "order",
            IntegrationOutbox.aggregate_id == order_id,
            IntegrationOutbox.event_type == EventNames.ORDER_CREATED,
        )
        .one()
    )
    assert outbox.idempotency_key == (
        f"order:{order_id}:{EventNames.ORDER_CREATED}:created.v1"
    )
    payload = json.loads(outbox.payload_json)
    assert payload["order_number"] == order.order_number
    assert payload["currency"] == order.currency
    assert payload["total_cents"] == int(order.total)
    assert payload["customer"]["geovision_id"] == (
        order.organization_id or order.company_id or order.user_id
    )
    assert payload["items"]
    assert all(item["item_code"] and item["qty"] > 0 for item in payload["items"])

    wake_event = (
        db_session.query(EventOutbox)
        .filter(
            EventOutbox.aggregate_type == "integration_outbox",
            EventOutbox.aggregate_id == outbox.id,
            EventOutbox.event_type == EventNames.ERP_SYNC_REQUESTED,
        )
        .one()
    )
    assert wake_event.idempotency_key == f"erp-outbox:{outbox.id}"
    return outbox


@pytest.mark.parametrize(
    "path_template",
    ("/orders/checkout/{cart_id}", "/shop/checkout/{cart_id}"),
)
def test_checkout_routes_commit_one_erp_handoff(
    client,
    db_session,
    path_template: str,
):
    cart_id = f"erp-checkout-{uuid.uuid4().hex}"
    _add_cart_item(client, cart_id)
    headers = _login_headers(client, "teste@clientes.com")
    headers["Idempotency-Key"] = f"erp-checkout-{uuid.uuid4().hex}"
    payload = {
        "payment_method": "iban_angola",
        "currency": "AOA",
        "billing_info": {
            "name": "ERP atomicity customer",
            "email": "erp-atomicity@example.com",
            "country": "AO",
        },
    }
    path = path_template.format(cart_id=cart_id)

    first = client.post(path, headers=headers, json=payload)
    repeated = client.post(path, headers=headers, json=payload)

    assert first.status_code == 200, first.text
    assert repeated.status_code == 200, repeated.text
    order_id = first.json()["order_id"]
    assert repeated.json()["order_id"] == order_id
    _assert_committed_erp_handoff(db_session, order_id)
    assert (
        db_session.query(IntegrationOutbox)
        .filter(
            IntegrationOutbox.aggregate_type == "order",
            IntegrationOutbox.aggregate_id == order_id,
        )
        .count()
        == 1
    )


def test_internal_order_route_commits_erp_handoff(client, db_session):
    organization = Company(
        name=f"ERP internal {uuid.uuid4().hex[:8]}",
        email=f"erp-internal-{uuid.uuid4().hex}@example.com",
        status="active",
    )
    db_session.add(organization)
    db_session.commit()
    item = (
        db_session.query(CatalogItem)
        .filter(CatalogItem.status == "PUBLISHED")
        .first()
    )
    assert item is not None

    response = client.post(
        "/orders/internal",
        headers=_login_headers(client, "teste@admin.com"),
        json={
            "organization_id": organization.id,
            "currency": "AOA",
            "items": [{"catalog_item_id": item.id, "quantity": 2}],
        },
    )

    assert response.status_code == 201, response.text
    outbox = _assert_committed_erp_handoff(db_session, response.json()["id"])
    assert outbox.company_id == organization.id


def test_legacy_direct_order_route_commits_erp_handoff(client, db_session):
    product = Product(
        sku=f"ERP-{uuid.uuid4().hex[:12]}",
        name="ERP atomicity legacy product",
        price=12500,
        currency="AOA",
        is_active=True,
    )
    db_session.add(product)
    db_session.flush()
    db_session.add(Inventory(product_id=product.id, qty_on_hand=20, qty_reserved=0))
    db_session.commit()

    response = client.post(
        "/orders/orders",
        headers=_login_headers(client, "teste@clientes.com"),
        json={
            "items": [{"product_id": product.id, "qty": 2}],
            "shipping_address": {"country": "AO"},
        },
    )

    assert response.status_code == 200, response.text
    outbox = _assert_committed_erp_handoff(db_session, response.json()["order_id"])
    payload = json.loads(outbox.payload_json)
    assert payload["items"] == [
        {
            "item_code": product.sku,
            "item_name": product.name,
            "qty": 2,
            "rate": 125.0,
        }
    ]


def test_legacy_direct_order_enqueue_failure_rolls_back_everything(
    client,
    db_session,
    monkeypatch,
):
    product = Product(
        sku=f"ERP-ROLLBACK-{uuid.uuid4().hex[:8]}",
        name="ERP rollback legacy product",
        price=8400,
        currency="AOA",
        is_active=True,
    )
    db_session.add(product)
    db_session.flush()
    db_session.add(Inventory(product_id=product.id, qty_on_hand=10, qty_reserved=0))
    db_session.commit()

    from app.modules.orders.services import enqueue_order_created_erp

    staged_ids: dict[str, str] = {}

    def stage_handoff_then_fail(db, *, order):
        enqueue_order_created_erp(db, order=order)
        db.flush()
        outbox = (
            db.query(IntegrationOutbox)
            .filter(IntegrationOutbox.aggregate_id == order.id)
            .one()
        )
        wake_event = (
            db.query(EventOutbox)
            .filter(
                EventOutbox.aggregate_type == "integration_outbox",
                EventOutbox.aggregate_id == outbox.id,
            )
            .one()
        )
        staged_ids.update(
            order=order.id,
            outbox=outbox.id,
            wake_event=wake_event.id,
        )
        raise RuntimeError("forced ERP enqueue boundary failure")

    monkeypatch.setattr(
        "app.routers.orders.enqueue_order_created_erp",
        stage_handoff_then_fail,
    )

    with pytest.raises(RuntimeError, match="forced ERP enqueue boundary failure"):
        client.post(
            "/orders/orders",
            headers=_login_headers(client, "teste@clientes.com"),
            json={"items": [{"product_id": product.id, "qty": 3}]},
        )

    assert set(staged_ids) == {"order", "outbox", "wake_event"}
    db_session.expire_all()
    assert db_session.get(Order, staged_ids["order"]) is None
    assert db_session.get(IntegrationOutbox, staged_ids["outbox"]) is None
    assert db_session.get(EventOutbox, staged_ids["wake_event"]) is None
    inventory = db_session.get(Inventory, product.id)
    assert inventory is not None
    assert inventory.qty_reserved == 0


def test_checkout_failure_rolls_back_order_and_erp_handoff(
    client,
    db_session,
    monkeypatch,
):
    cart_id = f"erp-rollback-{uuid.uuid4().hex}"
    _add_cart_item(client, cart_id)
    checkout_key = f"erp-rollback-{uuid.uuid4().hex}"
    service = OrderService(db_session)

    async def fail_after_enqueue(*_args, **_kwargs):
        raise RuntimeError("forced payment boundary failure")

    monkeypatch.setattr(service, "_initiate_payment", fail_after_enqueue)

    with pytest.raises(RuntimeError, match="forced payment boundary failure"):
        asyncio.run(
            service.checkout(
                cart_id=cart_id,
                user_id=None,
                payment_method=PaymentMethod.IBAN_ANGOLA,
                currency="AOA",
                idempotency_key=checkout_key,
            )
        )

    staged_order = (
        db_session.query(Order)
        .filter(Order.checkout_idempotency_key == checkout_key)
        .one()
    )
    staged_outbox = (
        db_session.query(IntegrationOutbox)
        .filter(IntegrationOutbox.aggregate_id == staged_order.id)
        .one()
    )
    staged_wake_event = (
        db_session.query(EventOutbox)
        .filter(
            EventOutbox.aggregate_type == "integration_outbox",
            EventOutbox.aggregate_id == staged_outbox.id,
        )
        .one()
    )
    order_id = staged_order.id
    outbox_id = staged_outbox.id
    wake_event_id = staged_wake_event.id

    db_session.rollback()

    assert db_session.get(Order, order_id) is None
    assert db_session.get(IntegrationOutbox, outbox_id) is None
    assert db_session.get(EventOutbox, wake_event_id) is None


def test_uncommitted_internal_draft_rolls_back_with_erp_handoff(db_session):
    organization = Company(
        name=f"ERP draft rollback {uuid.uuid4().hex[:8]}",
        email=f"erp-draft-rollback-{uuid.uuid4().hex}@example.com",
        status="active",
    )
    db_session.add(organization)
    db_session.commit()
    actor = db_session.query(User).filter(User.email == "teste@admin.com").one()
    item = (
        db_session.query(CatalogItem)
        .filter(CatalogItem.status == "PUBLISHED")
        .first()
    )
    assert item is not None

    order = create_draft_order(
        db_session,
        actor=actor,
        data=DraftOrderCreate(
            organization_id=organization.id,
            currency="AOA",
            items=[{"catalog_item_id": item.id, "quantity": 1}],
        ),
    )
    db_session.flush()
    staged_outbox = (
        db_session.query(IntegrationOutbox)
        .filter(IntegrationOutbox.aggregate_id == order.id)
        .one()
    )
    staged_wake_event = (
        db_session.query(EventOutbox)
        .filter(
            EventOutbox.aggregate_type == "integration_outbox",
            EventOutbox.aggregate_id == staged_outbox.id,
        )
        .one()
    )
    order_id = order.id
    outbox_id = staged_outbox.id
    wake_event_id = staged_wake_event.id

    db_session.rollback()

    assert db_session.get(Order, order_id) is None
    assert db_session.get(IntegrationOutbox, outbox_id) is None
    assert db_session.get(EventOutbox, wake_event_id) is None
