from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import uuid

from app.core.config import Settings, settings
from app.core.event_names import EventNames
from app.integrations.iot.azure_iot_hub import AzureIotHubEventGridAdapter
from app.models import (
    Company,
    CompanyUser,
    DeviceAssignment,
    EventOutbox,
    IotDevice,
    Site,
    TelemetryReading,
    TelemetryReceipt,
    User,
)
from app.modules.monitoring.iot_ports import CloudTelemetryProvider
from app.utils import hash_password


def _auth(client, email: str, password: str = "long-password-123") -> dict[str, str]:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _tenant(db, *, prefix: str = "edge"):
    suffix = uuid.uuid4().hex[:8]
    email = f"{prefix}-{suffix}@example.com"
    user = User(
        email=email,
        password_hash=hash_password("long-password-123"),
        role="cliente",
        is_active=True,
    )
    db.add(user)
    db.flush()
    company = Company(name=f"Edge {suffix}", email=email, status="active")
    db.add(company)
    db.flush()
    db.add(
        CompanyUser(
            company_id=company.id,
            user_id=user.id,
            email=email,
            name="Edge owner",
            role="owner",
            is_active=True,
        )
    )
    site = Site(
        company_id=company.id,
        name="Connected field",
        country="Spain",
        sector="agriculture",
        latitude=40.4168,
        longitude=-3.7038,
    )
    db.add(site)
    db.commit()
    return email, company, site


def _create_device(client, headers, site_id: str, **extra):
    payload = {
        "name": "Field sensor",
        "site_id": site_id,
        "device_type": "multi_sensor",
        "transport": "rest",
        "channels": [
            {
                "key": "temperature",
                "label": "Temperature",
                "measurement_type": "temperature",
                "unit": "Cel",
            },
            {
                "key": "battery",
                "label": "Battery",
                "measurement_type": "battery",
                "unit": "%",
            },
        ],
        **extra,
    }
    response = client.post("/iot/devices", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _exchange(client, device: dict) -> str:
    response = client.post(
        "/iot/provision/exchange",
        json={
            "device_uid": device["device_uid"],
            "provisioning_token": device["provisioning"]["token"],
            "firmware_version": "edge-test-1.0.0",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["device_secret"]


def _envelope(device_uid: str, *, message_id: str, sequence: int, **changes):
    payload = {
        "protocol_version": "geovision.telemetry.v1",
        "device_id": device_uid,
        "message_id": message_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stream_id": "fieldbox-boot-a",
        "sequence": sequence,
        "firmware_version": "fieldbox-1.2.3",
        "measurements": {
            "temperature": {"value": 23.5, "unit": "Cel", "quality": "good"},
            "battery": {"value": 88, "unit": "%", "quality": "good"},
        },
        "location": {"latitude": 40.42, "longitude": -3.71, "accuracy_meters": 8},
        "context": {"gateway": "raspberry_pi_fieldbox"},
    }
    payload.update(changes)
    return payload


def test_versioned_receipts_asset_health_duplicates_and_out_of_order(
    client, db_session
):
    email, _, site = _tenant(db_session)
    headers = _auth(client, email)
    asset_response = client.post(
        "/iot/assets",
        headers=headers,
        json={"name": "Irrigation sector A", "site_id": site.id, "asset_type": "field"},
    )
    assert asset_response.status_code == 201, asset_response.text
    asset = asset_response.json()
    device = _create_device(client, headers, site.id, asset_id=asset["id"])
    assert device["core_asset_id"] == asset["core_asset_id"]
    assert device["allow_remote_control"] is False
    secret = _exchange(client, device)
    auth = {
        "Authorization": f"Device {secret}",
        "X-Device-ID": device["device_uid"],
    }

    first_payload = _envelope(device["device_uid"], message_id="edge-10", sequence=10)
    first = client.post("/iot/ingest", headers=auth, json=first_payload)
    assert first.status_code == 200, first.text
    assert first.json()["asset_id"] == asset["core_asset_id"]
    assert first.json()["out_of_order"] is False

    duplicate = client.post("/iot/ingest", headers=auth, json=first_payload)
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True
    assert duplicate.json()["stored"] == 0

    queued_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    replay = _envelope(
        device["device_uid"],
        message_id="edge-08",
        sequence=8,
        timestamp=(queued_at - timedelta(minutes=30)).isoformat(),
        queued_at=queued_at.isoformat(),
        replayed_from_edge=True,
        measurements={
            "temperature": {"value": 99, "unit": "Cel", "quality": "bad"},
            "battery": {"value": 2, "unit": "%", "quality": "good"},
        },
        location={"latitude": 1, "longitude": 2},
    )
    replayed = client.post("/iot/ingest", headers=auth, json=replay)
    assert replayed.status_code == 200, replayed.text
    assert replayed.json()["replayed_from_edge"] is True
    assert replayed.json()["out_of_order"] is True

    collision = dict(replay)
    collision["message_id"] = "edge-08-conflict"
    conflict = client.post("/iot/ingest", headers=auth, json=collision)
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "telemetry_sequence_conflict"

    db_session.expire_all()
    stored_device = db_session.get(IotDevice, device["id"])
    assert stored_device.core_asset_id == asset["core_asset_id"]
    assert stored_device.last_seen_at is not None
    assert stored_device.connectivity_status == "online"
    assert stored_device.health_status == "healthy"
    assert stored_device.battery_percent == 88
    assert stored_device.last_latitude == 40.42
    assert stored_device.last_sequence == 10
    assert db_session.query(TelemetryReceipt).filter_by(device_id=device["id"]).count() == 2
    assert db_session.query(TelemetryReading).filter_by(device_id=device["id"]).count() == 4
    assert (
        db_session.query(EventOutbox)
        .filter(
            EventOutbox.aggregate_id == device["id"],
            EventOutbox.event_type == EventNames.DEVICE_TELEMETRY_RECEIVED,
        )
        .count()
        == 2
    )
    receipts = client.get(f"/iot/devices/{device['id']}/receipts", headers=headers)
    assert receipts.status_code == 200
    assert {row["message_id"] for row in receipts.json()} == {"edge-10", "edge-08"}


def test_assignment_history_is_canonical_and_tenant_safe(client, db_session):
    email, _, site = _tenant(db_session, prefix="assignment")
    headers = _auth(client, email)
    first = client.post(
        "/iot/assets",
        headers=headers,
        json={"name": "Pump A", "site_id": site.id, "asset_type": "pump"},
    ).json()
    second = client.post(
        "/iot/assets",
        headers=headers,
        json={"name": "Pump B", "site_id": site.id, "asset_type": "pump"},
    ).json()
    device = _create_device(client, headers, site.id, asset_id=first["id"])

    moved = client.post(
        f"/iot/devices/{device['id']}/assignments",
        headers=headers,
        json={"asset_id": second["core_asset_id"], "reason": "Sensor moved to Pump B"},
    )
    assert moved.status_code == 201, moved.text
    history = client.get(
        f"/iot/devices/{device['id']}/assignments", headers=headers
    ).json()
    assert len(history) == 2
    assert sum(row["status"] == "active" for row in history) == 1
    assert history[0]["asset_id"] == second["core_asset_id"]
    db_session.expire_all()
    assert (
        db_session.query(DeviceAssignment)
        .filter_by(device_id=device["id"], status="active")
        .one()
        .asset_id
        == second["core_asset_id"]
    )

    other_email, _, _ = _tenant(db_session, prefix="assignment-other")
    other_headers = _auth(client, other_email)
    assert (
        client.get(f"/iot/devices/{device['id']}/assignments", headers=other_headers).status_code
        == 404
    )


def _azure_event(hub: str, provider_id: str, envelope: dict, event_id: str):
    return [
        {
            "id": event_id,
            "topic": f"/subscriptions/test/resourceGroups/test/providers/Microsoft.Devices/IotHubs/{hub}",
            "subject": f"devices/{provider_id}",
            "eventType": "Microsoft.Devices.DeviceTelemetry",
            "eventTime": datetime.now(timezone.utc).isoformat(),
            "data": {
                "body": envelope,
                "properties": {},
                "systemProperties": {
                    "iothub-content-type": "application/json",
                    "iothub-content-encoding": "utf-8",
                    "iothub-connection-device-id": provider_id,
                },
            },
        }
    ]


def test_azure_iot_hub_event_grid_uses_the_same_ingestion_boundary(
    client, db_session, monkeypatch
):
    hub = "geovision-test-hub"
    secret = "iot-hub-test-secret-value-with-32-characters"
    monkeypatch.setattr(settings, "iot_cloud_provider", "azure_iot_hub")
    monkeypatch.setattr(settings, "azure_iot_hub_enabled", True)
    monkeypatch.setattr(settings, "azure_iot_hub_webhook_secret", secret)
    monkeypatch.setattr(settings, "azure_iot_hub_name", hub)

    email, _, site = _tenant(db_session, prefix="azure")
    headers = _auth(client, email)
    provider_id = f"iot-device-{uuid.uuid4().hex[:10]}"
    device = _create_device(
        client,
        headers,
        site.id,
        transport="azure_iot_hub",
        provider_code="azure_iot_hub",
        provider_device_id=provider_id,
    )
    envelope = _envelope(
        device["device_uid"],
        message_id="azure-message-1",
        sequence=1,
    )
    event = _azure_event(hub, provider_id, envelope, "azure-event-1")
    delivery_headers = {"X-GeoVision-IoT-Hub-Secret": secret}

    delivered = client.post(
        "/iot/providers/azure-iot-hub/events",
        headers=delivery_headers,
        json=event,
    )
    assert delivered.status_code == 200, delivered.text
    assert delivered.json()["stored"] == 2
    repeated = client.post(
        "/iot/providers/azure-iot-hub/events",
        headers=delivery_headers,
        json=event,
    )
    assert repeated.status_code == 200
    assert repeated.json()["duplicates"] == 1
    assert repeated.json()["stored"] == 0

    validation = client.post(
        "/iot/providers/azure-iot-hub/events",
        headers=delivery_headers,
        json=[
            {
                "id": "validation-1",
                "topic": f"/subscriptions/test/providers/Microsoft.Devices/IotHubs/{hub}",
                "eventType": "Microsoft.EventGrid.SubscriptionValidationEvent",
                "eventTime": datetime.now(timezone.utc).isoformat(),
                "data": {"validationCode": "proof-code"},
            }
        ],
    )
    assert validation.status_code == 200
    assert validation.json() == {"validationResponse": "proof-code"}
    assert client.post(
        "/iot/providers/azure-iot-hub/events",
        headers={"X-GeoVision-IoT-Hub-Secret": "wrong"},
        json=event,
    ).status_code == 400

    db_session.expire_all()
    receipt = db_session.query(TelemetryReceipt).filter_by(message_id="azure-message-1").one()
    assert receipt.provider_code == "azure_iot_hub"
    assert receipt.provider_message_id == "azure-event-1"
    assert receipt.core_asset_id == device["core_asset_id"]


def test_azure_adapter_decodes_base64_without_leaking_into_domain_contract():
    config = Settings(
        _env_file=None,
        iot_cloud_provider="azure_iot_hub",
        azure_iot_hub_enabled=True,
        azure_iot_hub_webhook_secret="x" * 40,
        azure_iot_hub_name="test-hub",
    )
    adapter = AzureIotHubEventGridAdapter(config)
    assert isinstance(adapter, CloudTelemetryProvider)
    assert config.model_dump()["azure_iot_hub_webhook_secret"] == "[REDACTED]"
    assert config.safe_summary()["configured"]["azure_iot_hub"] is True
    envelope = _envelope("gv-test", message_id="encoded-1", sequence=1)
    event = _azure_event("test-hub", "external-device", envelope, "event-encoded")
    event[0]["data"]["body"] = base64.b64encode(json.dumps(envelope).encode()).decode()
    event[0]["data"]["systemProperties"]["iothub-content-type"] = (
        "application/octet-stream"
    )
    batch = adapter.parse_delivery(
        event,
        headers={"X-GeoVision-IoT-Hub-Secret": "x" * 40},
    )
    assert batch.events[0].provider_device_id == "external-device"
    assert batch.events[0].envelope["protocol_version"] == "geovision.telemetry.v1"


def test_fieldbox_queue_and_safe_local_rules_work_without_network(tmp_path):
    fieldbox_dir = Path(__file__).resolve().parents[2] / "edge" / "fieldbox"
    sys.path.insert(0, str(fieldbox_dir))
    try:
        from geovision_fieldbox import DurableQueue, FieldBox, SafeLocalRules
    finally:
        sys.path.remove(str(fieldbox_dir))

    actions = []
    queue = DurableQueue(tmp_path / "fieldbox.sqlite", max_items=2)
    fieldbox = FieldBox(queue, firmware_version="fieldbox-test", local_action=actions.append)
    for value in (20, 21, 22):
        fieldbox.capture(
            device_id="gv-fieldbox-test",
            measurements={"temperature": value, "water_leak": value == 22},
        )
    assert queue.count() == 2
    pending = queue.pending()
    assert [item[1]["sequence"] for item in pending] == [1, 2]
    assert all(item[1]["replayed_from_edge"] is True for item in pending)
    assert actions[-1].name == "low_voltage_valve_close"

    assert fieldbox.flush(lambda _: False) == 0
    assert queue.count() == 2
    assert fieldbox.flush(lambda _: True) == 2
    assert queue.count() == 0
    assert SafeLocalRules().command_result({"id": "c1", "name": "relay_on"})[
        "status"
    ] == "rejected"
    assert SafeLocalRules().command_result(
        {"id": "c2", "name": "low_voltage_valve_close"}
    )["status"] == "acknowledged"
