from app.database import SessionLocal
from app.models import CompanyUser, Site


def _login_headers(client):
    response = client.post(
        "/auth/login",
        json={"email": "teste@clientes.com", "password": "123456"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_customer_site():
    db = SessionLocal()
    try:
        membership = (
            db.query(CompanyUser)
            .filter(CompanyUser.email == "teste@clientes.com")
            .first()
        )
        assert membership is not None
        site = Site(
            company_id=membership.company_id,
            name="Mobile Test Farm",
            country="Angola",
            province="Malanje",
            latitude=-9.54,
            longitude=16.34,
            area_hectares=142,
            sector="agriculture",
        )
        db.add(site)
        db.commit()
        return site.id
    finally:
        db.close()


def test_mobile_sites_and_service_request_contract(client):
    headers = _login_headers(client)
    site_id = _create_customer_site()

    sites = client.get("/mobile/sites", headers=headers)
    assert sites.status_code == 200, sites.text
    payload = sites.json()
    assert payload[0]["id"] == site_id
    assert payload[0]["center"] == {"lat": -9.54, "lng": 16.34}
    assert payload[0]["total_hectares"] == 142

    created = client.post(
        "/mobile/service-requests",
        headers=headers,
        json={
            "site_id": site_id,
            "site_name": "ignored client snapshot",
            "type": "inspection",
            "urgency": "high",
            "description": "Inspect the irrigation anomaly.",
            "attachments": [],
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["site_name"] == "Mobile Test Farm"
    assert created.json()["status"] == "submitted"

    listed = client.get("/mobile/service-requests", headers=headers)
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["id"] == created.json()["id"]


def test_mobile_routes_require_authentication(client):
    assert client.get("/mobile/sites").status_code == 403
    assert client.get("/mobile/service-requests").status_code == 403
