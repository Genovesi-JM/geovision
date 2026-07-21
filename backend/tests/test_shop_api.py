def _customer_headers(client):
    response = client.post(
        "/auth/login",
        json={"email": "teste@clientes.com", "password": "123456"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


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
