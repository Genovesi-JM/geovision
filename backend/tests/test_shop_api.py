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
    assert all(set(product["translations"]) == {"pt", "en", "es", "fr"} for product in products)
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
    }.intersection(product_ids)
    kit_products = [p for p in products if p["id"].startswith("prod_kit_")]
    assert kit_products, "DIY kits should be seeded into the marketplace"
    water = next((p for p in kit_products if p["id"] == "prod_kit_water_tank_starter"), None)
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

    # "home" is no longer a GeoVision sector — no product may carry it.
    assert all("home" not in product["sectors"] for product in products)
    environment_products = client.get(
        "/shop/products", params={"sector": "ambiental"}
    ).json()
    assert environment_products
    assert all("environment" in product["sectors"] for product in environment_products)
    # The former Home kits remain in the catalogue under their professional
    # sectors (infrastructure / environment), just not recommended for "home".
    energy = next((p for p in products if p["id"] == "prod_kit_energy_meter_starter"), None)
    assert energy is not None and "infrastructure" in energy["sectors"]


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

    converted = client.patch(
        f"/shop/cart/{cart_id}/currency", json={"currency": "USD"}
    )
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

    assert client.get(f"/shop/orders/{result['order_id']}").status_code == 403
    owned = client.get(f"/shop/orders/{result['order_id']}", headers=headers)
    assert owned.status_code == 200, owned.text
    assert owned.json()["order_number"] == result["order_number"]

    history = client.get("/shop/orders", headers=headers)
    assert history.status_code == 200, history.text
    assert any(order["id"] == result["order_id"] for order in history.json())


def test_payment_methods_only_advertise_real_settlement(client):
    """Without gateway credentials, only IBAN/bank transfer should be enabled."""
    data = client.get("/shop/payment-methods").json()
    by_method = {m["method"]: m for m in data["methods"]}
    # IBAN always settles (manual confirmation, no gateway).
    assert by_method["iban_angola"]["enabled"] is True and by_method["iban_angola"]["settles"] is True
    assert by_method["iban_international"]["enabled"] is True
    # Gateways are disabled until their credentials are configured (else they mock).
    assert by_method["visa_mastercard"]["enabled"] is False
    assert by_method["multicaixa_express"]["enabled"] is False
    assert by_method["paypal"]["enabled"] is False
    assert data["any_gateway_live"] is False
