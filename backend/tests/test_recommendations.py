"""Recommendations = the decision layer between an alert and an action.

Covers the dossier's core loop: alert -> recommendation -> action/marketplace.
"""
import uuid

from app.models import Company, CompanyUser, IotAlert, Site

from tests.test_iot_platform import _provision


def _fresh_tenant(client, db_session):
    """A brand-new user/company/site so company resolution is unambiguous."""
    email = f"rec-{uuid.uuid4().hex[:8]}@example.com"
    reg = client.post("/auth/register", json={
        "email": email, "password": "rec-pass-123", "full_name": "Rec Tester",
        "customer_type": "farm", "sectors": ["agro"],
    })
    assert reg.status_code == 201, reg.text
    company = Company(name=f"Rec {email}", email=email)
    db_session.add(company); db_session.flush()
    db_session.add(CompanyUser(company_id=company.id, email=email, name="Rec", role="owner", is_active=True))
    site = Site(company_id=company.id, name="Rec Field", country="Angola", sector="agro")
    db_session.add(site); db_session.commit()
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    return headers, company, site


def _rule(client, headers, device_id, channel):
    r = client.post("/iot/alert-rules", headers=headers, json={
        "name": f"{channel} rule", "device_id": device_id, "channel": channel,
        "operator": "gt", "threshold": 1, "severity": "critical",
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_recommendations_generate_link_and_lifecycle(client, db_session):
    headers, company, site = _fresh_tenant(client, db_session)
    device, _secret = _provision(client, headers, site.id)
    device_id = device["id"]

    soil_rule = _rule(client, headers, device_id, "soil_moisture")
    batt_rule = _rule(client, headers, device_id, "battery")

    # Two open alerts a customer would want turned into advice.
    db_session.add(IotAlert(company_id=company.id, device_id=device_id, rule_id=soil_rule,
                            channel="soil_moisture", value=12.0, severity="high",
                            message="Soil moisture low", status="open"))
    db_session.add(IotAlert(company_id=company.id, device_id=device_id, rule_id=batt_rule,
                            channel="battery", value=8.0, severity="warning",
                            message="Battery low", status="open"))
    db_session.commit()

    # Generate turns alerts into recommendations.
    gen = client.post("/iot/recommendations/generate", headers=headers)
    assert gen.status_code == 200, gen.text
    assert gen.json()["generated"] == 2

    recs = client.get("/iot/recommendations", headers=headers).json()
    by_cat = {r["category"]: r for r in recs}
    assert "irrigation" in by_cat, by_cat          # soil_moisture -> irrigation
    assert "replacement" in by_cat, by_cat         # battery -> replacement

    soil = by_cat["irrigation"]
    assert soil["alert_id"] and soil["priority"] in {"high", "critical"}
    # Irrigation advice is marketplace-linked (the store seeds an irrigation/water product).
    assert soil["action_type"] == "marketplace" and soil["product_id"]

    # Idempotent: re-running does not duplicate.
    assert client.post("/iot/recommendations/generate", headers=headers).json()["generated"] == 0

    # Accept surfaces the linked product so the client can jump to the store.
    acc = client.post(f"/iot/recommendations/{soil['id']}/accept", headers=headers)
    assert acc.status_code == 200 and acc.json()["status"] == "accepted"
    assert acc.json()["product"] and acc.json()["product"]["id"] == soil["product_id"]

    # Dismiss resolves a recommendation.
    dis = client.post(f"/iot/recommendations/{by_cat['replacement']['id']}/dismiss", headers=headers)
    assert dis.status_code == 200 and dis.json()["status"] == "dismissed"

    # Status filter works.
    accepted = client.get("/iot/recommendations?status=accepted", headers=headers).json()
    assert any(r["id"] == soil["id"] for r in accepted)


def test_recommendations_require_auth(client):
    assert client.get("/iot/recommendations").status_code in (401, 403)
