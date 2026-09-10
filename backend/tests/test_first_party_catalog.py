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
    assert all(
        item["item_type"]
        in {
            "PHYSICAL_PRODUCT",
            "SERVICE",
            "MONITORING_PLAN",
            "INSTALLATION",
            "INSPECTION",
            "ANALYSIS",
        }
        for item in items
    )
    assert all("metadata" not in item and "supplier_id" not in item for item in items)
    assert all(
        set(item["sectors"]).issubset(
            {
                "agriculture",
                "construction_infrastructure",
                "environment",
                "mining",
                "industry_energy_utilities",
                "ports_logistics",
            }
        )
        for item in items
    )

    shop_ids = {item["id"] for item in client.get("/shop/products").json()}
    assert {item["id"] for item in items} == shop_ids

    archived = (
        db_session.query(CatalogItem).filter(CatalogItem.status == "ARCHIVED").first()
    )
    assert archived is not None
    assert client.get(f"/catalog/items/{archived.id}").status_code == 404

    published = db_session.get(CatalogItem, items[0]["id"])
    original_sectors = published.sectors_json
    published.sectors_json = '["FUTURE_SPECIAL"]'
    db_session.commit()
    public_detail = client.get(f"/catalog/items/{published.id}")
    assert public_detail.status_code == 200, public_detail.text
    assert public_detail.json()["sectors"] == []
    shop_detail = client.get(f"/shop/products/{published.id}")
    assert shop_detail.status_code == 200, shop_detail.text
    assert shop_detail.json()["sectors"] == []
    assert client.get("/catalog/items", params={"sector": "future"}).status_code == 422
    assert client.get("/shop/products", params={"sector": "future"}).status_code == 422
    published.sectors_json = original_sectors
    db_session.commit()


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
        assert item["sectors"] == ["construction_infrastructure"]
        assert {"BUILDING", "BRIDGE", "ROAD", "SITE"} <= set(item["asset_types"])
        assert item["deliverables"]
        assert "supplier_id" not in item
        assert "metadata" not in item
        assert set(item["translations"]) == {"pt", "en", "es", "fr"}
        assert all(
            translation["name"] and translation["description"]
            for translation in item["translations"].values()
        )

    assert (
        "not an engineering diagnosis"
        in items["prod_infra_technical_inspection"]["description"]
    )
    assert (
        "not labelled as faults"
        in items["prod_infra_thermal_inspection"]["description"]
    )

    road_response = client.get(
        "/catalog/items",
        params={"sector": "infrastructure", "asset_type": "road"},
    )
    assert road_response.status_code == 200, road_response.text
    assert expected.keys() <= {item["id"] for item in road_response.json()}


def test_environmental_catalogue_exposes_the_six_supported_actions(client):
    response = client.get("/catalog/items", params={"sector": "environmental"})
    assert response.status_code == 200, response.text
    items = {item["id"]: item for item in response.json()}

    expected = {
        "prod_env_environmental_survey": "SERVICE",
        "prod_env_reforestation_monitoring": "MONITORING_PLAN",
        "prod_env_targeted_drone_verification": "SERVICE",
        "prod_env_sensor_installation": "INSTALLATION",
        "prod_env_monitoring_plan": "MONITORING_PLAN",
        "prod_env_specialist_review": "SERVICE",
    }
    asset_types = {
        "COASTAL_AREA",
        "ENVIRONMENTAL_SITE",
        "FOREST",
        "HABITAT",
        "LAND_PARCEL",
        "PROTECTED_AREA",
        "RESTORATION_SITE",
        "SITE",
        "WATER_BODY",
        "WETLAND",
    }
    assert expected.keys() <= items.keys()
    for item_id, item_type in expected.items():
        item = items[item_id]
        assert item["item_type"] == item_type
        assert item["sectors"] == ["environment"]
        assert set(item["asset_types"]) == asset_types
        assert item["deliverables"]
        assert "supplier_id" not in item
        assert "metadata" not in item
        assert set(item["translations"]) == {"pt", "en", "es", "fr"}
        assert all(
            translation["name"] and translation["description"]
            for translation in item["translations"].values()
        )

    assert "without assigning" in items["prod_env_environmental_survey"]["description"]
    assert (
        "do not diagnose" in items["prod_env_reforestation_monitoring"]["description"]
    )
    assert (
        "does not confirm a cause automatically"
        in items["prod_env_targeted_drone_verification"]["description"]
    )

    forest_response = client.get(
        "/catalog/items",
        params={"sector": "environmental", "asset_type": "forest"},
    )
    assert forest_response.status_code == 200, forest_response.text
    assert expected.keys() <= {item["id"] for item in forest_response.json()}


def test_mining_catalogue_exposes_quality_gated_services(client):
    response = client.get("/catalog/items", params={"sector": "mining"})
    assert response.status_code == 200, response.text
    items = {item["id"]: item for item in response.json()}

    expected = {
        "prod_mining_volumetry_survey": "SERVICE",
        "prod_mining_site_progress_survey": "SERVICE",
        "prod_mining_lidar_specialist_survey": "SERVICE",
        "prod_mining_environmental_monitoring": "MONITORING_PLAN",
        "prod_mining_repeat_monitoring_plan": "MONITORING_PLAN",
    }
    asset_types = {
        "ENVIRONMENTAL_MONITORING_ZONE",
        "HAUL_ROAD",
        "MINE_SITE",
        "PIT",
        "QUARRY",
        "SLOPE",
        "STOCKPILE_ZONE",
        "TALUS",
    }
    assert expected.keys() <= items.keys()
    for item_id, item_type in expected.items():
        item = items[item_id]
        assert item["item_type"] == item_type
        assert item["sectors"] == ["mining"]
        assert set(item["asset_types"]) == asset_types
        assert item["deliverables"]
        assert "supplier_id" not in item
        assert "metadata" not in item
        assert set(item["translations"]) == {"pt", "en", "es", "fr"}
        assert all(
            translation["name"] and translation["description"]
            for translation in item["translations"].values()
        )

    volumetry = items["prod_mining_volumetry_survey"]["description"]
    assert "project tolerances" in volumetry
    assert "LiDAR is not required" in volumetry
    progress = items["prod_mining_site_progress_survey"]["description"]
    assert "not an ore, reserve, or geotechnical conclusion" in progress
    environmental = items["prod_mining_environmental_monitoring"]["description"]
    assert "does not automatically determine" in environmental

    stockpile_response = client.get(
        "/catalog/items",
        params={"sector": "mining", "asset_type": "stockpile_zone"},
    )
    assert stockpile_response.status_code == 200, stockpile_response.text
    assert expected.keys() <= {item["id"] for item in stockpile_response.json()}


def test_ports_catalogue_exposes_asset_centric_inspection_services(client):
    response = client.get("/catalog/items", params={"sector": "ports_logistics"})
    assert response.status_code == 200, response.text
    items = {item["id"]: item for item in response.json()}

    expected = {
        "prod_ports_visual_inspection": "INSPECTION",
        "prod_ports_thermal_inspection": "INSPECTION",
        "prod_ports_3d_mapping": "SERVICE",
        "prod_ports_sensor_installation": "INSTALLATION",
        "prod_ports_monitoring_plan": "MONITORING_PLAN",
        "prod_ports_specialist_review": "SERVICE",
    }
    asset_types = {
        "BERTH",
        "CRANE",
        "EQUIPMENT",
        "GANTRY",
        "INSPECTION_ZONE",
        "LOADING_AREA",
        "PORT",
        "QUAY",
        "ROOF",
        "STRUCTURE",
        "TANK",
        "TERMINAL",
        "WAREHOUSE",
    }
    assert expected.keys() <= items.keys()
    for item_id, item_type in expected.items():
        item = items[item_id]
        assert item["item_type"] == item_type
        assert item["sectors"] == [
            "industry_energy_utilities",
            "ports_logistics",
        ]
        assert set(item["asset_types"]) == asset_types
        assert item["deliverables"]
        assert "supplier_id" not in item
        assert "metadata" not in item
        assert set(item["translations"]) == {"pt", "en", "es", "fr"}
        assert all(
            translation["name"] and translation["description"]
            for translation in item["translations"].values()
        )

    visual = items["prod_ports_visual_inspection"]["description"]
    assert "review candidates" in visual
    assert "do not automatically establish" in visual
    thermal = items["prod_ports_thermal_inspection"]["description"]
    assert "not automatically classified as faults" in thermal
    monitoring = items["prod_ports_monitoring_plan"]["description"]
    assert "Missing evidence remains explicitly unknown" in monitoring
    specialist = items["prod_ports_specialist_review"]["description"]
    assert "does not create an automatic" in specialist

    gantry_response = client.get(
        "/catalog/items",
        params={"sector": "industry", "asset_type": "gantry"},
    )
    assert gantry_response.status_code == 200, gantry_response.text
    assert expected.keys() <= {item["id"] for item in gantry_response.json()}


def test_shop_sector_registry_exposes_the_ordered_cross_surface_contract(client):
    response = client.get("/shop/sectors")
    assert response.status_code == 200, response.text
    assert response.json() == [
        {
            "key": "agriculture",
            "label": "Agricultura & Pecuária",
            "slug": "agricultura-pecuaria",
            "asset_sector": "AGRICULTURE",
            "capability_sector": "agriculture",
            "maturity": "available",
        },
        {
            "key": "construction_infrastructure",
            "label": "Construção & Infraestruturas",
            "slug": "construcao-infraestruturas",
            "asset_sector": "INFRASTRUCTURE",
            "capability_sector": "infrastructure",
            "maturity": "custom_project",
        },
        {
            "key": "environment",
            "label": "Ambiente",
            "slug": "ambiente",
            "asset_sector": "ENVIRONMENTAL",
            "capability_sector": "environmental",
            "maturity": "custom_project",
        },
        {
            "key": "mining",
            "label": "Mineração",
            "slug": "mineracao",
            "asset_sector": "MINING",
            "capability_sector": "mining",
            "maturity": "specialized",
        },
        {
            "key": "industry_energy_utilities",
            "label": "Indústria, Energia & Utilities",
            "slug": "industria-energia-utilities",
            "asset_sector": "INDUSTRY_ENERGY_UTILITIES",
            "capability_sector": "industry_energy_utilities",
            "maturity": "expansion",
        },
        {
            "key": "ports_logistics",
            "label": "Portos & Logística",
            "slug": "portos-logistica",
            "asset_sector": "PORTS_LOGISTICS",
            "capability_sector": "ports_logistics",
            "maturity": "expansion",
        },
    ]


def test_authorized_staff_manage_one_catalogue_for_every_offer_type(client):
    headers = _login_headers(client, "teste@admin.com")
    suffix = uuid.uuid4().hex[:8]
    oversized = client.post(
        "/catalog/internal/items",
        headers=headers,
        json=_item_payload("SERVICE", suffix, sectors=["agro"] * 7),
    )
    assert oversized.status_code == 422

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
        assert response.json()["sectors"] == ["AGRICULTURE", "ENVIRONMENTAL"]
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
    assert any(
        item["id"]
        == next(row["id"] for row in created if row["item_type"] == "INSPECTION")
        for item in filtered.json()
    )
    assert all("supplier_id" not in item for item in filtered.json())


def test_customer_cannot_manage_catalog_but_inventory_staff_can(client, db_session):
    customer_headers = _login_headers(client, "teste@clientes.com")
    assert (
        client.get("/catalog/internal/items", headers=customer_headers).status_code
        == 403
    )
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

    unknown_sector = client.post(
        "/catalog/internal/items",
        headers=headers,
        json=_item_payload(
            "SERVICE",
            uuid.uuid4().hex[:8],
            sectors=["future"],
        ),
    )
    assert unknown_sector.status_code == 422

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
    forbidden_fragments = (
        "/sellers",
        "/vendors",
        "/provider-bids",
        "/contractor-storefront",
    )
    assert all(
        not any(fragment in path for fragment in forbidden_fragments)
        for path in route_paths
    )
