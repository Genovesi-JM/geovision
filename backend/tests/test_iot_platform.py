from datetime import datetime, timezone
import uuid

from app.models import Company, CompanyUser, Site, User
from app.utils import hash_password
from app.iot.security import sign_mqtt_payload


def _auth(client, email="teste@admin.com", password="123456"):
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _tenant(db_session, email="teste@admin.com"):
    suffix = uuid.uuid4().hex[:8]
    company = Company(name=f"IoT Test {suffix}", email=f"iot-{suffix}@example.test")
    db_session.add(company); db_session.flush()
    db_session.add(CompanyUser(company_id=company.id, email=email, name="IoT Admin", role="owner", is_active=True))
    site = Site(company_id=company.id, name="Test Pump Room", country="Angola", sector="infrastructure")
    db_session.add(site); db_session.commit()
    return company, site


def _provision(client, headers, site_id):
    created = client.post("/iot/devices", headers=headers, json={
        "name": "Pump room multi-sensor", "site_id": site_id,
        "device_type": "multi_sensor", "transport": "mqtt",
        "allow_remote_control": True,
        "capabilities": ["command:relay_on", "command:relay_off", "command:request_diagnostics"],
        "channels": [
            {"key": "temperature", "label": "Temperature", "measurement_type": "temperature", "unit": "Cel"},
            {"key": "water_leak", "label": "Leak", "measurement_type": "water_leak", "data_type": "boolean"},
            {"key": "safety_ok", "label": "Local safety", "measurement_type": "generic", "data_type": "boolean"},
            {"key": "battery", "label": "Battery", "measurement_type": "battery", "unit": "%"},
            {"key": "signal", "label": "Signal", "measurement_type": "signal", "unit": "%"},
        ],
    })
    assert created.status_code == 201, created.text
    body = created.json()
    exchanged = client.post("/iot/provision/exchange", json={
        "device_uid": body["device_uid"],
        "provisioning_token": body["provisioning"]["token"],
        "firmware_version": "test-1.0.0",
    })
    assert exchanged.status_code == 200, exchanged.text
    return body, exchanged.json()["device_secret"]


def _ingest(client, uid, secret, message_id, temperature, safety=True):
    return client.post("/iot/ingest", headers={"Authorization": f"Device {secret}", "X-Device-ID": uid}, json={
        "message_id": message_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "measurements": {"temperature": temperature, "water_leak": False, "safety_ok": safety, "battery": 87, "signal": 73},
    })


def test_provision_rest_ingest_duplicate_alert_resolution_and_safe_command(client, db_session):
    owner_email = f"iot-owner-{uuid.uuid4().hex[:8]}@example.com"
    owner = User(email=owner_email, password_hash=hash_password("long-password-123"), role="cliente", is_active=True)
    db_session.add(owner); db_session.commit()
    _, site = _tenant(db_session, owner_email)
    headers = _auth(client, owner_email, "long-password-123")
    asset = client.post("/iot/assets", headers=headers, json={"name": "Water tank A", "site_id": site.id, "asset_type": "tank"})
    assert asset.status_code == 201 and client.get("/iot/assets", headers=headers).json()[0]["name"] == "Water tank A"
    gateway = client.post("/iot/gateways", headers=headers, json={"name": "Plant gateway", "site_id": site.id, "gateway_type": "edge"})
    assert gateway.status_code == 201 and client.get("/iot/gateways", headers=headers).json()[0]["name"] == "Plant gateway"
    device, secret = _provision(client, headers, site.id)
    uid, device_id = device["device_uid"], device["id"]

    normal = _ingest(client, uid, secret, "msg-normal", 24.5)
    assert normal.status_code == 200, normal.text
    assert normal.json()["stored"] == 5

    duplicate = _ingest(client, uid, secret, "msg-normal", 99)
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True

    rule = client.post("/iot/alert-rules", headers=headers, json={
        "name": "High temperature", "device_id": device_id, "channel": "temperature",
        "operator": "gt", "threshold": 30, "severity": "critical",
    })
    assert rule.status_code == 201, rule.text

    critical = _ingest(client, uid, secret, "msg-critical", 38.2)
    assert critical.status_code == 200, critical.text
    alerts = client.get("/iot/alerts", headers=headers).json()
    assert alerts[0]["status"] == "notified"
    assert alerts[0]["severity"] == "critical"

    ack = client.post(f"/iot/alerts/{alerts[0]['id']}/acknowledge", headers=headers)
    assert ack.status_code == 200
    assigned = client.post(f"/iot/alerts/{alerts[0]['id']}/assign", headers=headers, json={"assignee_id": owner.id})
    assert assigned.status_code == 200 and assigned.json()["status"] == "assigned"
    recovered = _ingest(client, uid, secret, "msg-recovered", 26.0)
    assert recovered.status_code == 200
    assert client.get("/iot/alerts", headers=headers).json()[0]["status"] == "resolved"
    closed = client.post(f"/iot/alerts/{alerts[0]['id']}/close", headers=headers)
    assert closed.status_code == 200 and closed.json()["status"] == "closed"
    csv_report = client.get(f"/iot/devices/{device_id}/telemetry.csv", headers=headers)
    assert csv_report.status_code == 200 and "temperature" in csv_report.text
    aggregates = client.get(f"/iot/devices/{device_id}/aggregates", headers=headers)
    assert aggregates.status_code == 200
    pdf_report = client.get(f"/iot/devices/{device_id}/report.pdf", headers=headers)
    assert pdf_report.status_code == 200 and pdf_report.content.startswith(b"%PDF")

    command = client.post(f"/iot/devices/{device_id}/commands", headers=headers, json={
        "name": "relay_on", "confirmed": True,
        "reason": "Supervised low-voltage test relay", "fail_safe_state": "off",
    })
    assert command.status_code == 202, command.text
    pending = client.get("/iot/device/commands", headers={"Authorization": f"Device {secret}", "X-Device-ID": uid})
    assert pending.status_code == 200
    assert pending.json()["items"][0]["name"] == "relay_on"
    command_id = pending.json()["items"][0]["id"]
    result = client.post("/iot/device/command-results", headers={"Authorization": f"Device {secret}", "X-Device-ID": uid}, json={
        "command_id": command_id, "status": "completed", "actual_state": {"relay": True},
    })
    assert result.status_code == 200


def test_device_auth_validation_and_tenant_isolation(client, db_session):
    owner_email = f"owner-{uuid.uuid4().hex[:8]}@example.com"
    owner = User(email=owner_email, password_hash=hash_password("long-password-123"), role="cliente", is_active=True)
    db_session.add(owner); db_session.commit()
    _, site = _tenant(db_session, owner_email)
    headers = _auth(client, owner_email, "long-password-123")
    device, secret = _provision(client, headers, site.id)
    rejected = _ingest(client, device["device_uid"], "wrong-secret-value-that-is-long-enough", "bad-auth", 20)
    assert rejected.status_code == 401

    suffix = uuid.uuid4().hex[:8]
    email = f"other-{suffix}@example.com"
    user = User(email=email, password_hash=hash_password("long-password-123"), role="cliente", is_active=True)
    db_session.add(user); db_session.flush()
    other_company = Company(name="Other tenant", email=email)
    db_session.add(other_company); db_session.flush()
    db_session.add(CompanyUser(company_id=other_company.id, email=email, name="Other", role="owner", is_active=True))
    db_session.commit()
    other_headers = _auth(client, email, "long-password-123")
    hidden = client.get(f"/iot/devices/{device['id']}", headers=other_headers)
    assert hidden.status_code == 404


def test_signed_mqtt_ingestion_path(client, db_session):
    owner_email = f"mqtt-owner-{uuid.uuid4().hex[:8]}@example.com"
    db_session.add(User(email=owner_email, password_hash=hash_password("long-password-123"), role="cliente", is_active=True)); db_session.commit()
    company, site = _tenant(db_session, owner_email); headers = _auth(client, owner_email, "long-password-123")
    device, secret = _provision(client, headers, site.id)
    payload = {
        "device_uid": device["device_uid"], "message_id": f"mqtt-{uuid.uuid4().hex}",
        "nonce": uuid.uuid4().hex, "timestamp": datetime.now(timezone.utc).isoformat(),
        "measurements": {"temperature": 22.2, "water_leak": False, "safety_ok": True, "battery": 90, "signal": 80},
        "metadata": {"test": "mqtt"},
    }
    payload["signature"] = sign_mqtt_payload(payload, secret)
    from app.iot.mqtt import mqtt_bridge
    mqtt_bridge._process(company.id, site.id, device["device_uid"], "telemetry", payload)
    latest = client.get(f"/iot/devices/{device['id']}/latest", headers=headers)
    assert latest.status_code == 200
    assert any(row["channel"] == "temperature" and row["value"] == 22.2 for row in latest.json()["readings"])
