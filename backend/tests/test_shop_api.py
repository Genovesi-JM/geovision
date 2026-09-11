import json
import uuid

import pytest

from app.services.cart import CartSectorValidationError, get_cart_service
from app.iot.kits import get_kit
from app.models import CatalogItem, ShopProduct
from app.services.cart import seed_kit_products, seed_shop_products


def _customer_headers(client):
    response = client.post(
        "/auth/login",
        json={"email": "teste@clientes.com", "password": "123456"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_diy_kits_appear_in_marketplace(client):
    products = client.get("/shop/products").json()
    product_ids = {p["id"] for p in products}
    assert all(
        set(product["translations"]) == {"pt", "en", "es", "fr"} for product in products
    )
    assert all("ambiental" not in product["sectors"] for product in products)
    assert {
        "prod_infra_progress",
        "prod_infra_inspection",
        "prod_aerial_basic_mapping",
        "prod_agro_visual_inspection",
        "prod_supply_soil_probe",
        "prod_supply_irrigation_parts",
        "prod_supply_monitoring_spares",
        "prod_supply_weather_pack",
    }.issubset(product_ids)
    assert not {
        "prod_mining_volumetric",
        "prod_infra_digital_twin",
        "prod_agro_spraying",
        "prod_demining_thermal",
        "prod_solar_panel_inspection",
        "prod_kit_cold_chain_starter",
        "prod_kit_energy_meter_starter",
        "prod_kit_spray_control",
        "prod_kit_seed_flow",
    }.intersection(product_ids)
    kit_products = [p for p in products if p["id"].startswith("prod_kit_")]
    assert kit_products, "DIY kits should be seeded into the marketplace"
    water = next(
        (p for p in kit_products if p["id"] == "prod_kit_water_tank_starter"), None
    )
    assert water is not None
    assert water["product_type"] == "hardware" and water["category"] == "sensor_kit"
    # Prices are stored in minor units (×100): Water kit is $130 -> 13000.
    assert water["price_usd"] == 13000
    assert water["price"] > water["price_usd"]  # AOA figure is larger than USD
    assert water["price_eur"] > 0
    assert water["deliverables"] and water["sectors"]
    assert set(water["translations"]) == {"pt", "en", "es", "fr"}
    assert water["translations"]["pt"]["name"].startswith("GV Level")
    assert water["translations"]["en"]["description"]

    tracker = next(
        product
        for product in kit_products
        if product["id"] == "prod_kit_gps_asset_tracker"
    )
    assert tracker["sectors"] == [
        "construction_infrastructure",
        "mining",
        "industry_energy_utilities",
        "ports_logistics",
    ]

    # "home" is no longer a GeoVision sector — no product may carry it.
    assert all("home" not in product["sectors"] for product in products)
    environment_products = client.get(
        "/shop/products", params={"sector": "ambiental"}
    ).json()
    assert environment_products
    assert all("environment" in product["sectors"] for product in environment_products)
    # Standby concepts remain unavailable until their provisioning path is
    # validated; declaring a public sector does not make a kit sellable.
    assert "prod_kit_energy_meter_starter" not in product_ids


def test_kit_seed_reconciles_existing_catalogue_sectors_and_standby_state(
    client, db_session
):
    product_id = "prod_kit_gps_asset_tracker"
    item = db_session.get(CatalogItem, product_id)
    product = db_session.get(ShopProduct, product_id)
    kit = get_kit("gps_asset_tracker")
    assert item is not None and product is not None and kit is not None

    item.sectors_json = '["INFRASTRUCTURE"]'
    db_session.commit()
    seed_kit_products(db_session)
    db_session.refresh(item)
    assert json.loads(item.sectors_json) == [
        "INFRASTRUCTURE",
        "MINING",
        "INDUSTRY_ENERGY_UTILITIES",
        "PORTS_LOGISTICS",
    ]

    original_availability = kit.get("availability")
    try:
        kit["availability"] = "standby"
        seed_kit_products(db_session)
        db_session.refresh(item)
        db_session.refresh(product)
        assert item.status == "ARCHIVED"
        assert item.availability_status == "UNAVAILABLE"
        assert product.is_active is False
        assert product_id not in {
            row["id"] for row in client.get("/shop/products").json()
        }
    finally:
        if original_availability is None:
            kit.pop("availability", None)
        else:
            kit["availability"] = original_availability
        seed_kit_products(db_session)

    db_session.refresh(item)
    assert item.status == "PUBLISHED"
    assert item.availability_status == "AVAILABLE"


def test_static_seed_reconciles_controlled_sectors_and_archives_standby_offers(
    client, db_session
):
    active_id = "prod_ports_visual_inspection"
    active_item = db_session.get(CatalogItem, active_id)
    standby_id = "prod_demining_thermal"
    standby_item = db_session.get(CatalogItem, standby_id)
    standby_product = db_session.get(ShopProduct, standby_id)
    assert active_item is not None
    assert standby_item is not None and standby_product is not None

    active_item.sectors_json = '["PORTS_LOGISTICS"]'
    standby_item.status = "PUBLISHED"
    standby_item.availability_status = "AVAILABLE"
    standby_product.is_active = True
    db_session.commit()

    seed_shop_products(db_session)
    db_session.refresh(active_item)
    db_session.refresh(standby_item)
    db_session.refresh(standby_product)
    assert json.loads(active_item.sectors_json) == [
        "INDUSTRY_ENERGY_UTILITIES",
        "PORTS_LOGISTICS",
    ]
    assert standby_item.status == "ARCHIVED"
    assert standby_item.availability_status == "UNAVAILABLE"
    assert standby_product.is_active is False
    assert standby_id not in {row["id"] for row in client.get("/shop/products").json()}


def test_catalogue_exposes_explicit_multi_currency_contract(client):
    response = client.get("/shop/products")
    assert response.status_code == 200, response.text
    products = response.json()
    assert products
    product = products[0]
    assert product["price"] > 0
    assert product["price_usd"] > 0
    assert product["price_eur"] > 0
    assert product["currency"] == "AOA"
    assert product["sectors"]
    assert product["deliverables"]
    assert set(product["translations"]) == {"pt", "en", "es", "fr"}


@pytest.mark.parametrize("account_sector", ["future_special", "agriculture,mining"])
def test_cart_warning_rejects_noncanonical_account_sector(
    client, db_session, account_sector
):
    product = client.get("/shop/products").json()[0]

    response = client.post(
        "/shop/check-sector-mismatch",
        json={"product_id": product["id"], "account_sector": account_sector},
    )
    assert response.status_code == 422
    assert "six GeoVision public sectors" in response.json()["detail"]

    cart_id = f"invalid-sector-{uuid.uuid4().hex[:8]}"
    added = client.post(
        f"/shop/cart/{cart_id}/items",
        json={"product_id": product["id"], "quantity": 1},
    )
    assert added.status_code == 200, added.text
    cart_response = client.get(
        f"/shop/cart/{cart_id}/with-warnings",
        params={"account_sector": account_sector},
    )
    assert cart_response.status_code == 422

    service = get_cart_service(db_session)
    with pytest.raises(CartSectorValidationError):
        service.check_sector_mismatch(product["id"], account_sector)


def test_cart_currency_checkout_and_owned_order_contract(client):
    headers = _customer_headers(client)
    product = client.get("/shop/products").json()[0]
    cart_id = "mobile_contract_cart"

    added = client.post(
        f"/shop/cart/{cart_id}/items",
        json={"product_id": product["id"], "quantity": 2, "currency": "AOA"},
    )
    assert added.status_code == 200, added.text
    assert added.json()["item_count"] == 1
    assert added.json()["items"][0]["quantity"] == 2
    assert added.json()["currency"] == "AOA"

    converted = client.patch(f"/shop/cart/{cart_id}/currency", json={"currency": "USD"})
    assert converted.status_code == 200, converted.text
    assert converted.json()["currency"] == "USD"
    assert converted.json()["total"] == product["price_usd"] * 2

    # Return to AOA so the local bank-transfer method is valid.
    client.patch(f"/shop/cart/{cart_id}/currency", json={"currency": "AOA"})
    checkout = client.post(
        f"/shop/checkout/{cart_id}",
        headers=headers,
        json={
            "currency": "AOA",
            "payment_method": "iban_angola",
            "billing_info": {
                "name": "Cliente GeoVision",
                "email": "teste@clientes.com",
                "country": "AO",
            },
        },
    )
    assert checkout.status_code == 200, checkout.text
    result = checkout.json()
    assert result["success"] is True
    assert result["order_id"]

    # No bearer credential is an authentication failure, not an authorization
    # denial for an authenticated principal.
    assert client.get(f"/shop/orders/{result['order_id']}").status_code == 401
    owned = client.get(f"/shop/orders/{result['order_id']}", headers=headers)
    assert owned.status_code == 200, owned.text
    assert owned.json()["order_number"] == result["order_number"]

    history = client.get("/shop/orders", headers=headers)
    assert history.status_code == 200, history.text
    assert any(order["id"] == result["order_id"] for order in history.json())


def test_new_cart_uses_spain_first_currency_and_tax(client):
    product = client.get("/shop/products").json()[0]
    cart_id = "spain_first_cart"

    empty_cart = client.get(f"/shop/cart/{cart_id}")
    assert empty_cart.status_code == 200
    assert empty_cart.json()["currency"] == "EUR"
    assert empty_cart.json()["tax_rate"] == pytest.approx(0.21)

    added = client.post(
        f"/shop/cart/{cart_id}/items",
        json={"product_id": product["id"], "quantity": 1},
    )
    assert added.status_code == 200, added.text
    assert added.json()["currency"] == "EUR"
    assert added.json()["items"][0]["tax_rate"] == pytest.approx(0.21)

    angola = client.patch(f"/shop/cart/{cart_id}/currency", json={"currency": "AOA"})
    assert angola.json()["items"][0]["tax_rate"] == pytest.approx(0.14)

    dollar = client.patch(f"/shop/cart/{cart_id}/currency", json={"currency": "USD"})
    assert dollar.json()["items"][0]["tax_rate"] == pytest.approx(0.0)
    assert dollar.json()["tax_amount"] == 0


def test_authenticated_checkout_never_downgrades_workspace_denial_to_guest(client):
    headers = _customer_headers(client)
    headers["X-Account-ID"] = str(uuid.uuid4())

    response = client.post(
        "/shop/checkout/nonexistent-cart",
        headers=headers,
        json={
            "currency": "AOA",
            "payment_method": "iban_angola",
            "billing_info": {
                "name": "Cliente GeoVision",
                "email": "teste@clientes.com",
                "country": "AO",
            },
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Workspace access denied"


def test_payment_methods_only_advertise_real_settlement(client):
    """Without gateway credentials, only IBAN/bank transfer should be enabled."""
    data = client.get("/shop/payment-methods").json()
    by_method = {m["method"]: m for m in data["methods"]}
    # IBAN always settles (manual confirmation, no gateway).
    assert (
        by_method["iban_angola"]["enabled"] is True
        and by_method["iban_angola"]["settles"] is True
    )
    assert by_method["iban_international"]["enabled"] is True
    # Gateways are disabled until their credentials are configured (else they mock).
    assert by_method["visa_mastercard"]["enabled"] is False
    assert by_method["multicaixa_express"]["enabled"] is False
    assert by_method["paypal"]["enabled"] is False
    assert data["any_gateway_live"] is False
