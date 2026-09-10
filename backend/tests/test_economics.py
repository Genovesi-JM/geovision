from __future__ import annotations

import json
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest

from app.core.time import utc_now
from app.core.tokens import create_user_access_token
from app.models import (
    Account,
    AccountMember,
    Asset,
    AuditLog,
    CatalogItem,
    Company,
    CompanyUser,
    InternalCost,
    InternalRoleAssignment,
    Order,
    OrderItem,
    ProviderUsage,
    User,
)
from app.modules.economics.domain import EconomicsError
from app.modules.economics.schemas import ProviderUsageCreate
from app.modules.economics.services import record_provider_usage


def _headers(user: User) -> dict[str, str]:
    token = create_user_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        auth_generation=user.auth_generation,
    )
    return {"Authorization": f"Bearer {token}"}


def _user(db_session, *, role: str | None = None, label: str = "user") -> User:
    user = User(
        email=f"phase25-{label}-{uuid.uuid4().hex}@example.test",
        role="client",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    if role:
        db_session.add(InternalRoleAssignment(user_id=user.id, role=role))
    db_session.commit()
    return user


def _fixture(db_session):
    suffix = uuid.uuid4().hex[:10]
    customer = _user(db_session, label="customer")
    organization = Company(
        name=f"Phase 25 organization {suffix}",
        email=f"phase25-org-{suffix}@example.test",
        status="active",
    )
    other_organization = Company(
        name=f"Phase 25 other organization {suffix}",
        email=f"phase25-other-org-{suffix}@example.test",
        status="active",
    )
    db_session.add_all([organization, other_organization])
    db_session.flush()
    workspace = Account(
        organization_id=organization.id,
        name=f"Economics workspace {suffix}",
        sector_focus="agriculture",
        entity_type="organization",
        customer_type="farm",
        dashboard_profile="farm",
        modules_enabled='["assets","services"]',
        status="active",
    )
    other_workspace = Account(
        organization_id=other_organization.id,
        name=f"Other economics workspace {suffix}",
        sector_focus="construction",
        entity_type="organization",
        customer_type="enterprise",
        dashboard_profile="construction",
        modules_enabled='["assets","services"]',
        status="active",
    )
    item = CatalogItem(
        code=f"PHASE25-{suffix.upper()}",
        slug=f"phase25-{suffix}",
        item_type="SERVICE",
        name="Crop intelligence review",
        price_model="FIXED",
        currency="AOA",
        unit_amount=1000,
        status="PUBLISHED",
    )
    other_item = CatalogItem(
        code=f"PHASE25-OTHER-{suffix.upper()}",
        slug=f"phase25-other-{suffix}",
        item_type="SERVICE",
        name="Unrelated review",
        price_model="FIXED",
        currency="AOA",
        unit_amount=700,
        status="PUBLISHED",
    )
    db_session.add_all([workspace, other_workspace, item, other_item])
    db_session.flush()
    db_session.add_all(
        [
            CompanyUser(
                company_id=organization.id,
                user_id=customer.id,
                email=customer.email,
                role="member",
                is_active=True,
                status="active",
            ),
            AccountMember(
                account_id=workspace.id,
                user_id=customer.id,
                role="member",
                status="active",
            ),
        ]
    )
    asset = Asset(
        organization_id=organization.id,
        workspace_id=workspace.id,
        sector="AGRICULTURE",
        asset_type="FARM",
        name="Economics field",
        status="active",
    )
    other_asset = Asset(
        organization_id=other_organization.id,
        workspace_id=other_workspace.id,
        sector="CONSTRUCTION",
        asset_type="SITE",
        name="Unrelated site",
        status="active",
    )
    order = Order(
        user_id=customer.id,
        company_id=organization.id,
        organization_id=organization.id,
        workspace_id=workspace.id,
        order_number=f"GV-P25-{suffix.upper()}",
        order_type="SERVICE",
        status="paid",
        fulfilment_status="PAID",
        payment_status="PAID",
        currency="AOA",
        subtotal=1000,
        total=1000,
    )
    other_order = Order(
        user_id=customer.id,
        company_id=other_organization.id,
        organization_id=other_organization.id,
        workspace_id=other_workspace.id,
        order_number=f"GV-P25-OTHER-{suffix.upper()}",
        order_type="SERVICE",
        status="paid",
        fulfilment_status="PAID",
        payment_status="PAID",
        currency="AOA",
        subtotal=700,
        total=700,
    )
    db_session.add_all([asset, other_asset, order, other_order])
    db_session.flush()
    order_item = OrderItem(
        order_id=order.id,
        catalog_item_id=item.id,
        name=item.name,
        product_type="service",
        catalog_item_type="SERVICE",
        currency="AOA",
        unit_price=1000,
        qty=1,
        line_total=1000,
    )
    other_order_item = OrderItem(
        order_id=other_order.id,
        catalog_item_id=other_item.id,
        name=other_item.name,
        product_type="service",
        catalog_item_type="SERVICE",
        currency="AOA",
        unit_price=700,
        qty=1,
        line_total=700,
    )
    db_session.add_all([order_item, other_order_item])
    db_session.commit()
    return {
        "customer": customer,
        "organization": organization,
        "other_organization": other_organization,
        "workspace": workspace,
        "other_workspace": other_workspace,
        "item": item,
        "other_item": other_item,
        "asset": asset,
        "other_asset": other_asset,
        "order": order,
        "other_order": other_order,
        "order_item": order_item,
        "other_order_item": other_order_item,
    }


def _cost_payload(data, *, key: str = "cost-key-001", amount: str = "250"):
    return {
        "order_id": data["order"].id,
        "order_item_id": data["order_item"].id,
        "asset_id": data["asset"].id,
        "cost_type": "SPECIALIST_REVIEW",
        "description": "Specialist QA review",
        "amount": amount,
        "currency": "aoa",
        "incurred_at": utc_now().isoformat(),
        "reference": "review-shift-42",
        "idempotency_key": key,
        "metadata": {"region": "Bengo", "batch": 4},
    }


def _usage_payload(data, *, key: str = "usage-key-001", reference: str = "scene-42"):
    return {
        "organization_id": data["organization"].id,
        "order_item_id": data["order_item"].id,
        "asset_id": data["asset"].id,
        "provider": "Azure Maps",
        "service": "Satellite Tiles",
        "usage_type": "tile_request",
        "quantity": "4",
        "unit": "request",
        "currency": "aoa",
        "unit_cost": "2.5",
        "occurred_at": (utc_now() - timedelta(minutes=3)).isoformat(),
        "provider_reference": reference,
        "idempotency_key": key,
        "metadata": {"zoom": 16},
    }


@pytest.mark.security_regression
def test_cost_usage_idempotency_and_private_unit_economics(client, db_session):
    data = _fixture(db_session)
    finance = _user(db_session, role="GV_FINANCE", label="finance")
    operations = _user(db_session, role="GV_OPERATIONS", label="operations")

    cost_payload = _cost_payload(data)
    cost = client.post(
        "/internal/economics/costs",
        headers=_headers(operations),
        json=cost_payload,
    )
    assert cost.status_code == 201, cost.text
    assert Decimal(cost.json()["amount"]) == Decimal("250")
    assert cost.json()["organization_id"] == data["organization"].id
    assert cost.json()["workspace_id"] == data["workspace"].id
    assert cost.json()["catalog_item_id"] == data["item"].id

    replay = client.post(
        "/internal/economics/costs",
        headers=_headers(operations),
        json=cost_payload,
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == cost.json()["id"]

    usage_payload = _usage_payload(data)
    usage = client.post(
        "/internal/economics/provider-usage",
        headers=_headers(operations),
        json=usage_payload,
    )
    assert usage.status_code == 201, usage.text
    assert Decimal(usage.json()["total_cost"]) == Decimal("10")
    assert usage.json()["order_id"] == data["order"].id
    assert usage.json()["workspace_id"] == data["workspace"].id
    assert usage.json()["catalog_item_id"] == data["item"].id

    replay = client.post(
        "/internal/economics/provider-usage",
        headers=_headers(operations),
        json=usage_payload,
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == usage.json()["id"]

    assert db_session.query(InternalCost).filter(
        InternalCost.idempotency_key == "cost-key-001"
    ).count() == 1
    assert db_session.query(ProviderUsage).filter(
        ProviderUsage.idempotency_key == "usage-key-001"
    ).count() == 1
    audited_ids = {
        row.resource_id
        for row in db_session.query(AuditLog)
        .filter(
            AuditLog.resource_id.in_([cost.json()["id"], usage.json()["id"]])
        )
        .all()
    }
    assert audited_ids == {cost.json()["id"], usage.json()["id"]}

    for path in (
        f"/internal/economics/orders/{data['order'].id}",
        f"/internal/economics/catalog-items/{data['item'].id}",
        f"/internal/economics/organizations/{data['organization'].id}",
    ):
        response = client.get(path, headers=_headers(finance))
        assert response.status_code == 200, response.text
        currency = response.json()["currencies"]
        assert len(currency) == 1
        assert currency[0]["currency"] == "AOA"
        assert Decimal(currency[0]["revenue"]) == Decimal("1000")
        assert Decimal(currency[0]["internal_cost"]) == Decimal("250")
        assert Decimal(currency[0]["provider_cost"]) == Decimal("10")
        assert Decimal(currency[0]["direct_cost"]) == Decimal("260")
        assert Decimal(currency[0]["gross_contribution"]) == Decimal("740")
        assert Decimal(currency[0]["gross_margin_percent"]) == Decimal("74")

    customer_headers = {
        **_headers(data["customer"]),
        "X-Workspace-ID": data["workspace"].id,
    }
    customer_paths = (
        "/orders",
        f"/orders/{data['order'].id}",
        f"/orders/{data['order'].id}/progress",
        "/mobile/home",
        "/portal/experience",
        "/portal/assets/summary",
    )
    forbidden_customer_fields = (
        "agreed_cost_amount",
        "cost_reference",
        "direct_cost",
        "gross_contribution",
        "gross_margin",
        "internal_cost",
        "provider_cost",
        "provider_usage",
    )
    for path in customer_paths:
        customer_response = client.get(path, headers=customer_headers)
        assert customer_response.status_code == 200, customer_response.text
        serialized = json.dumps(customer_response.json()).lower()
        for forbidden in forbidden_customer_fields:
            assert forbidden not in serialized, f"{path} exposed {forbidden}"


def test_finance_read_boundary_and_customer_non_discovery(client, db_session):
    data = _fixture(db_session)
    finance = _user(db_session, role="GV_FINANCE", label="finance-read")
    admin = _user(db_session, role="GV_SUPER_ADMIN", label="admin-read")
    operations = _user(db_session, role="GV_OPERATIONS", label="operations-read")
    analyst = _user(db_session, role="GV_ANALYST", label="analyst-read")

    create = client.post(
        "/internal/economics/costs",
        headers=_headers(finance),
        json=_cost_payload(data, key="cost-read-001"),
    )
    assert create.status_code == 201

    path = f"/internal/economics/costs?organization_id={data['organization'].id}"
    for actor in (finance, admin):
        response = client.get(path, headers=_headers(actor))
        assert response.status_code == 200
        assert response.json()["total"] == 1

    for actor in (operations, analyst, data["customer"]):
        response = client.get(path, headers=_headers(actor))
        assert response.status_code == 403
        response = client.get(
            f"/internal/economics/orders/{data['order'].id}",
            headers=_headers(actor),
        )
        assert response.status_code == 403

    denied_write = client.post(
        "/internal/economics/provider-usage",
        headers=_headers(data["customer"]),
        json=_usage_payload(data, key="usage-denied-001"),
    )
    assert denied_write.status_code == 403


def test_scope_currency_metadata_and_idempotency_fail_closed(client, db_session):
    data = _fixture(db_session)
    finance = _user(db_session, role="GV_FINANCE", label="finance-invalid")
    headers = _headers(finance)

    cross_scope = _usage_payload(data, key="usage-cross-001")
    cross_scope["asset_id"] = data["other_asset"].id
    response = client.post(
        "/internal/economics/provider-usage", headers=headers, json=cross_scope
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "scope_reference_invalid"

    wrong_currency = _cost_payload(data, key="cost-currency-001")
    wrong_currency["currency"] = "USD"
    response = client.post(
        "/internal/economics/costs", headers=headers, json=wrong_currency
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "currency_mismatch"

    wrong_item = _cost_payload(data, key="cost-item-001")
    wrong_item["order_item_id"] = data["other_order_item"].id
    response = client.post(
        "/internal/economics/costs", headers=headers, json=wrong_item
    )
    assert response.status_code == 404

    secret = _usage_payload(data, key="usage-secret-001")
    secret["metadata"] = {"nested": {"api_key": "never-store-this"}}
    response = client.post(
        "/internal/economics/provider-usage", headers=headers, json=secret
    )
    assert response.status_code == 422
    assert "never-store-this" not in response.text

    overflow = _usage_payload(data, key="usage-overflow-001")
    overflow["quantity"] = "99999999999999.999999"
    overflow["unit_cost"] = "99999999999999.999999"
    response = client.post(
        "/internal/economics/provider-usage", headers=headers, json=overflow
    )
    assert response.status_code == 422
    assert response.status_code < 500

    accepted = _cost_payload(data, key="cost-conflict-001")
    response = client.post("/internal/economics/costs", headers=headers, json=accepted)
    assert response.status_code == 201
    drifted = dict(accepted)
    drifted["amount"] = "251"
    response = client.post("/internal/economics/costs", headers=headers, json=drifted)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "idempotency_conflict"
    assert db_session.query(InternalCost).filter(
        InternalCost.idempotency_key == "cost-conflict-001"
    ).count() == 1


def test_provider_usage_system_actor_org_scoped_keys_and_repeat_reference(db_session):
    data = _fixture(db_session)
    occurred_at = utc_now()
    base = dict(
        provider="sentinel_hub",
        service="imagery_search",
        usage_type="scene_query",
        quantity=Decimal("1"),
        unit="request",
        occurred_at=occurred_at,
        provider_reference="provider-batch-42",
        metadata={"prompt_tokens": 12, "completion_tokens": 4},
    )
    first_payload = ProviderUsageCreate(
        organization_id=data["organization"].id,
        idempotency_key="worker-shared-key",
        **base,
    )
    first, created = record_provider_usage(db_session, payload=first_payload)
    assert created is True
    second_payload = ProviderUsageCreate(
        organization_id=data["other_organization"].id,
        idempotency_key="worker-shared-key",
        **base,
    )
    second, created = record_provider_usage(db_session, payload=second_payload)
    assert created is True
    repeated_reference = ProviderUsageCreate(
        organization_id=data["organization"].id,
        idempotency_key="worker-second-event",
        **base,
    )
    third, created = record_provider_usage(db_session, payload=repeated_reference)
    assert created is True
    db_session.commit()

    assert first.id != second.id != third.id
    assert first.created_by_user_id is None
    assert db_session.query(ProviderUsage).filter(
        ProviderUsage.provider_reference == "provider-batch-42"
    ).count() == 3
    system_audits = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.action == "economics.provider_usage.recorded",
            AuditLog.resource_id.in_([first.id, second.id, third.id]),
        )
        .all()
    )
    assert len(system_audits) == 3
    assert all(row.user_id is None for row in system_audits)

    with pytest.raises(EconomicsError) as conflict:
        record_provider_usage(
            db_session,
            payload=ProviderUsageCreate(
                organization_id=data["organization"].id,
                idempotency_key="worker-shared-key",
                provider="sentinel_hub",
                service="imagery_search",
                usage_type="scene_query",
                quantity=Decimal("2"),
                unit="request",
                occurred_at=occurred_at,
                provider_reference="provider-batch-42",
            ),
        )
    assert conflict.value.code == "idempotency_conflict"
