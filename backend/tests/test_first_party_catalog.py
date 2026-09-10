from __future__ import annotations

import uuid

from app.core.tokens import create_user_access_token
from app.models import CatalogItem, InternalRoleAssignment, User


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


def _item_payload(item_type: str, suffix: str, **overrides):
    payload = {
        "code": f"PHASE7_{item_type}_{suffix}",
        "slug": f"phase7-{item_type.lower().replace('_', '-')}-{suffix}",
        "name": f"Phase 7 {item_type} {suffix}",
        "summary": "A GeoVision-managed offer",
        "description": "Sold and fulfilled by GeoVision, with no seller storefront.",
        "item_type": item_type,
        "category": "phase7",
        "sectors": ["agriculture", "environmental"],
        "asset_types": ["farm", "site"],
        "customer_content": {"included": ["GeoVision support"]},
        "deliverables": ["Documented result"],
        "price_model": "FIXED",
        "currency": "AOA",
        "unit_amount": 125000,
        "pricing": {"AOA": 125000, "USD": 15000},
        "availability_status": "AVAILABLE",
        "status": "PUBLISHED",
        "recommendation_triggers": [
            {"kpi": "soil_moisture", "operator": "lt", "threshold": 20}
        ],
        "requires_site": item_type != "PHYSICAL_PRODUCT",
        "requires_scheduling": item_type in {"INSTALLATION", "INSPECTION", "SERVICE"},
    }
    payload.update(overrides)
    return payload


def test_public_catalogue_is_canonical_and_published_only(client, db_session):
    response = client.get("/catalog/items")
    assert response.status_code == 200, response.text
    items = response.json()
    assert items
    assert all(item["item_type"] in {
        "PHYSICAL_PRODUCT",
        "SERVICE",
        "MONITORING_PLAN",
        "INSTALLATION",
        "INSPECTION",
        "ANALYSIS",
    } for item in items)
    assert all("metadata" not in item and "supplier_id" not in item for item in items)
    assert all(
        set(item["sectors"]).issubset(
            {"AGRICULTURE", "INFRASTRUCTURE", "ENVIRONMENTAL", "MINING", "PORTS_INDUSTRIAL"}
        )
        for item in items
    )

    shop_ids = {item["id"] for item in client.get("/shop/products").json()}
    assert {item["id"] for item in items} == shop_ids

    archived = (
        db_session.query(CatalogItem)
        .filter(CatalogItem.status == "ARCHIVED")
        .first()
    )
    assert archived is not None
    assert client.get(f"/catalog/items/{archived.id}").status_code == 404


def test_infrastructure_catalogue_exposes_the_six_supported_actions(client):
    response = client.get("/catalog/items", params={"sector": "infrastructure"})
    assert response.status_code == 200, response.text
    items = {item["id"]: item for item in response.json()}

    expected = {
        "prod_infra_progress_survey": "SERVICE",
        "prod_infra_technical_inspection": "INSPECTION",
        "prod_infra_thermal_inspection": "INSPECTION",
        "prod_infra_3d_mapping": "SERVICE",
        "prod_infra_specialist_review": "SERVICE",
        "prod_infra_monitoring_plan": "MONITORING_PLAN",
    }
    assert expected.keys() <= items.keys()
    for item_id, item_type in expected.items():
        item = items[item_id]
        assert item["item_type"] == item_type
        assert item["sectors"] == ["INFRASTRUCTURE"]
        assert {"BUILDING", "BRIDGE", "ROAD", "SITE"} <= set(
            item["asset_types"]
        )
        assert item["deliverables"]
        assert "supplier_id" not in item
        assert "metadata" not in item
        assert set(item["translations"]) == {"pt", "en", "es", "fr"}
        assert all(
            translation["name"] and translation["description"]
            for translation in item["translations"].values()
        )

    assert "not an engineering diagnosis" in items[
        "prod_infra_technical_inspection"
    ]["description"]
    assert "not labelled as faults" in items[
        "prod_infra_thermal_inspection"
    ]["description"]

    road_response = client.get(
        "/catalog/items",
        params={"sector": "infrastructure", "asset_type": "road"},
    )
    assert road_response.status_code == 200, road_response.text
    assert expected.keys() <= {item["id"] for item in road_response.json()}


def test_authorized_staff_manage_one_catalogue_for_every_offer_type(client):
    headers = _login_headers(client, "teste@admin.com")
    suffix = uuid.uuid4().hex[:8]
    supplier = client.post(
        "/catalog/internal/suppliers",
        headers=headers,
        json={
            "code": f"PROC_{suffix}",
            "legal_name": "Qualified Equipment Source",
            "contact_email": "procurement@example.com",
            "metadata": {"qualification": "pending review"},
        },
    )
    assert supplier.status_code == 201, supplier.text
    supplier_id = supplier.json()["id"]

    created = []
    for item_type in (
        "PHYSICAL_PRODUCT",
        "SERVICE",
        "MONITORING_PLAN",
        "INSTALLATION",
        "INSPECTION",
        "ANALYSIS",
    ):
        response = client.post(
            "/catalog/internal/items",
            headers=headers,
            json=_item_payload(item_type, suffix, supplier_id=supplier_id),
        )
        assert response.status_code == 201, response.text
        assert response.json()["supplier_id"] == supplier_id
        created.append(response.json())

    assert {item["item_type"] for item in created} == {
        "PHYSICAL_PRODUCT",
        "SERVICE",
        "MONITORING_PLAN",
        "INSTALLATION",
        "INSPECTION",
        "ANALYSIS",
    }
    filtered = client.get(
        "/catalog/items",
        params={"item_type": "INSPECTION", "sector": "agro", "asset_type": "farm"},
    )
    assert filtered.status_code == 200, filtered.text
    assert any(item["id"] == next(row["id"] for row in created if row["item_type"] == "INSPECTION") for item in filtered.json())
    assert all("supplier_id" not in item for item in filtered.json())


def test_customer_cannot_manage_catalog_but_inventory_staff_can(client, db_session):
    customer_headers = _login_headers(client, "teste@clientes.com")
    assert client.get("/catalog/internal/items", headers=customer_headers).status_code == 403
    denied = client.post(
        "/catalog/internal/items",
        headers=customer_headers,
        json=_item_payload("SERVICE", uuid.uuid4().hex[:8]),
    )
    assert denied.status_code == 403

    user = User(
        email=f"inventory-{uuid.uuid4().hex}@example.com",
        password_hash=None,
        role="cliente",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(
        InternalRoleAssignment(
            user_id=user.id,
            role="GV_INVENTORY",
            is_active=True,
        )
    )
    db_session.commit()
    db_session.refresh(user)

    allowed = client.post(
        "/catalog/internal/items",
        headers=_headers(user),
        json=_item_payload("PHYSICAL_PRODUCT", uuid.uuid4().hex[:8]),
    )
    assert allowed.status_code == 201, allowed.text


def test_catalogue_rejects_secret_metadata_and_unpriced_publication(client):
    headers = _login_headers(client, "teste@admin.com")
    suffix = uuid.uuid4().hex[:8]
    secret = client.post(
        "/catalog/internal/items",
        headers=headers,
        json=_item_payload("SERVICE", suffix, metadata={"api_key": "must-not-store"}),
    )
    assert secret.status_code == 422

    unpriced = client.post(
        "/catalog/internal/items",
        headers=headers,
        json=_item_payload(
            "SERVICE",
            uuid.uuid4().hex[:8],
            unit_amount=None,
            pricing={},
        ),
    )
    assert unpriced.status_code == 422

    quote = client.post(
        "/catalog/internal/items",
        headers=headers,
        json=_item_payload(
            "ANALYSIS",
            uuid.uuid4().hex[:8],
            price_model="QUOTE",
            unit_amount=None,
            pricing={},
        ),
    )
    assert quote.status_code == 201, quote.text


def test_legacy_admin_delete_archives_without_losing_catalog_history(client):
    headers = _login_headers(client, "teste@admin.com")
    created = client.post(
        "/catalog/internal/items",
        headers=headers,
        json=_item_payload("INSTALLATION", uuid.uuid4().hex[:8]),
    )
    assert created.status_code == 201, created.text
    item_id = created.json()["id"]
    archived = client.delete(f"/admin/products/{item_id}", headers=headers)
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "ARCHIVED"
    internal = client.get(f"/catalog/internal/items/{item_id}", headers=headers)
    assert internal.status_code == 200
    assert internal.json()["status"] == "ARCHIVED"
    assert client.get(f"/catalog/items/{item_id}").status_code == 404
    assert client.get(f"/shop/products/{item_id}").status_code == 404


def test_no_public_seller_provider_or_bidding_surface(client):
    route_paths = {route.path.lower() for route in client.app.routes}
    forbidden_fragments = ("/sellers", "/vendors", "/provider-bids", "/contractor-storefront")
    assert all(not any(fragment in path for fragment in forbidden_fragments) for path in route_paths)
