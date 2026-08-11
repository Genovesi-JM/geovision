from app.database import SessionLocal
from app.models import CompanyUser, Site


def _login_headers(client):
    response = client.post(
        "/auth/login",
        json={"email": "teste@clientes.com", "password": "123456"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_customer_site(*, sector="agriculture", name="Mobile Test Farm"):
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
            name=name,
            country="Angola",
            province="Malanje",
            latitude=-9.54,
            longitude=16.34,
            area_hectares=142,
            sector=sector,
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
    assert {item["id"] for item in payload[0]["kpis"]} == {
        "ndvi_avg",
        "water_stress",
        "hectares_monitored",
        "yield_estimate",
    }

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


def test_mobile_home_site_returns_home_kpis(client):
    headers = _login_headers(client)
    site_id = _create_customer_site(sector="home", name="Mobile Test Home")
    response = client.get("/mobile/sites", headers=headers)
    assert response.status_code == 200, response.text
    home = next(item for item in response.json() if item["id"] == site_id)
    assert {item["id"] for item in home["kpis"]} == {
        "comfort_index",
        "air_quality",
        "tank_level",
        "leak_events",
    }


def test_mobile_routes_require_authentication(client):
    assert client.get("/mobile/sites").status_code == 403
    assert client.post("/mobile/sites", json={"name": "Forbidden"}).status_code == 403
    assert client.get("/mobile/service-requests").status_code == 403


def test_customer_can_add_site_only_to_own_organisation(client):
    headers = _login_headers(client)
    created = client.post(
        "/mobile/sites",
        headers=headers,
        json={
            "name": "Fazenda Nova Esperança",
            "sector": "agriculture",
            "country": "Angola",
            "province": "Huambo",
            "municipality": "Caála",
            "latitude": -12.852,
            "longitude": 15.561,
            "area_hectares": 380.5,
        },
    )
    assert created.status_code == 201, created.text
    payload = created.json()
    assert payload["name"] == "Fazenda Nova Esperança"
    assert payload["location"] == "Caála, Huambo, Angola"
    assert payload["center"] == {"lat": -12.852, "lng": 15.561}

    listed = client.get("/mobile/sites", headers=headers)
    assert any(site["id"] == payload["id"] for site in listed.json())

    incomplete_geography = client.post(
        "/mobile/sites",
        headers=headers,
        json={
            "name": "Invalid geography",
            "country": "Portugal",
            "province": "Huambo",
        },
    )
    assert incomplete_geography.status_code == 422


def test_drone_registry_separates_neo_import_from_automated_missions(client):
    headers = _login_headers(client)
    site_id = _create_customer_site()
    neo = client.post(
        "/mobile/drones",
        headers=headers,
        json={"name": "Meu Neo", "model": "DJI Neo", "site_id": site_id},
    )
    assert neo.status_code == 201, neo.text
    assert neo.json()["sdk_supported"] is False
    assert neo.json()["connection_mode"] == "media_import"

    rejected = client.post(
        "/mobile/drone-missions",
        headers=headers,
        json={
            "site_id": site_id,
            "aircraft_id": neo.json()["id"],
            "name": "Neo must not fly this grid",
            "boundary": [
                {"lat": -9.54, "lng": 16.34},
                {"lat": -9.55, "lng": 16.34},
                {"lat": -9.55, "lng": 16.35},
            ],
        },
    )
    assert rejected.status_code == 409

    enterprise = client.post(
        "/mobile/drones",
        headers=headers,
        json={
            "name": "Mapping aircraft",
            "model": "DJI Mavic 3 Enterprise",
            "site_id": site_id,
        },
    )
    assert enterprise.status_code == 201, enterprise.text
    assert enterprise.json()["sdk_supported"] is True

    mission = client.post(
        "/mobile/drone-missions",
        headers=headers,
        json={
            "site_id": site_id,
            "aircraft_id": enterprise.json()["id"],
            "name": "Block A mapping",
            "altitude_m": 80,
            "boundary": [
                {"lat": -9.54, "lng": 16.34},
                {"lat": -9.55, "lng": 16.34},
                {"lat": -9.55, "lng": 16.35},
            ],
        },
    )
    assert mission.status_code == 201, mission.text
    assert mission.json()["status"] == "draft"

    incomplete = client.post(
        f"/mobile/drone-missions/{mission.json()['id']}/approve",
        headers=headers,
        json={
            "pilot_confirmed": True,
            "airspace_checked": True,
            "weather_checked": False,
            "people_clear": True,
            "aircraft_checked": True,
        },
    )
    assert incomplete.status_code == 409

    approved = client.post(
        f"/mobile/drone-missions/{mission.json()['id']}/approve",
        headers=headers,
        json={
            "pilot_confirmed": True,
            "airspace_checked": True,
            "weather_checked": True,
            "people_clear": True,
            "aircraft_checked": True,
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["execution"] == "provider_handoff_required"
