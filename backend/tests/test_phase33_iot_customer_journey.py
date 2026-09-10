from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

from app.core.config import settings
from app.core.event_names import EventNames
from app.core.events import DomainEvent
from app.models import (
    Action,
    IotAlert,
    IotAlertRule,
    IotDevice,
    KpiDefinition,
    KpiValue,
    Notification,
    NotificationDelivery,
    Observation,
    Site,
    TelemetryReceipt,
    User,
)
from app.services.event_consumers import default_event_consumers
from app.services.event_outbox import dispatch_pending_events
from app.iot.watchdog import mark_offline_devices
from app.modules.notifications.materializer import materialize_notification_event
from app.utils import hash_password


PASSWORD = "long-password-123"


def _owner(client, db_session, prefix: str) -> tuple[User, dict[str, str], str, str]:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        email=f"{prefix}-{suffix}@example.com",
        password_hash=hash_password(PASSWORD),
        role="cliente",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    login = client.post("/auth/login", json={"email": user.email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    bearer = {"Authorization": f"Bearer {login.json()['access_token']}"}
    created = client.post(
        "/organizations",
        headers=bearer,
        json={
            "name": f"Phase 33 IoT {suffix}",
            "country": "Spain",
            "timezone": "Europe/Madrid",
            "workspace": {
                "name": "Connected operations",
                "customer_type": "business",
                "sector_focus": "agriculture",
                "modules_enabled": [
                    "projects",
                    "monitoring",
                    "iot",
                    "kpi",
                    "actions",
                    "alerts",
                    "map",
                ],
            },
        },
    )
    assert created.status_code == 201, created.text
    organization_id = created.json()["id"]
    workspace_id = created.json()["workspaces"][0]["id"]
    return (
        user,
        {**bearer, "X-Workspace-ID": workspace_id},
        organization_id,
        workspace_id,
    )


def _drain_events(db_session) -> None:
    registry = default_event_consumers(settings)
    while True:
        stats = dispatch_pending_events(
            db_session,
            worker_id=f"phase33-{uuid.uuid4().hex[:8]}",
            registry=registry,
            config=settings,
            limit=500,
        )
        if stats["claimed"] == 0:
            return


def test_simulated_iot_alert_reaches_customer_intelligence_and_inbox(
    client, db_session, monkeypatch
):
    owner, headers, organization_id, workspace_id = _owner(
        client, db_session, "phase33-iot"
    )
    site = Site(
        company_id=organization_id,
        name="Synthetic connected field",
        country="Spain",
        sector="agriculture",
        latitude=40.4168,
        longitude=-3.7038,
    )
    db_session.add(site)
    db_session.commit()

    legacy_asset_response = client.post(
        "/iot/assets",
        headers=headers,
        json={
            "name": "Synthetic irrigation block",
            "site_id": site.id,
            "asset_type": "field",
        },
    )
    assert legacy_asset_response.status_code == 201, legacy_asset_response.text
    legacy_asset = legacy_asset_response.json()
    device_response = client.post(
        "/iot/devices",
        headers=headers,
        json={
            "name": "Synthetic soil station",
            "site_id": site.id,
            "asset_id": legacy_asset["id"],
            "device_type": "multi_sensor",
            "transport": "rest",
            "channels": [
                {
                    "key": "soil_moisture",
                    "label": "Soil moisture",
                    "measurement_type": "soil_moisture",
                    "unit": "%",
                },
                {
                    "key": "battery",
                    "label": "Battery",
                    "measurement_type": "battery",
                    "unit": "%",
                },
            ],
        },
    )
    assert device_response.status_code == 201, device_response.text
    device = device_response.json()
    exchange = client.post(
        "/iot/provision/exchange",
        json={
            "device_uid": device["device_uid"],
            "provisioning_token": device["provisioning"]["token"],
            "firmware_version": "synthetic-1.0.0",
        },
    )
    assert exchange.status_code == 200, exchange.text
    device_headers = {
        "Authorization": f"Device {exchange.json()['device_secret']}",
        "X-Device-ID": device["device_uid"],
    }
    rule = client.post(
        "/iot/alert-rules",
        headers=headers,
        json={
            "name": "Synthetic dry-soil threshold",
            "device_id": device["id"],
            "channel": "soil_moisture",
            "operator": "lt",
            "threshold": 20,
            "severity": "critical",
        },
    )
    assert rule.status_code == 201, rule.text
    sustained_rule = client.post(
        "/iot/alert-rules",
        headers=headers,
        json={
            "name": "Synthetic sustained low-battery threshold",
            "device_id": device["id"],
            "channel": "battery",
            "operator": "lt",
            "threshold": 90,
            "severity": "warning",
            "sustained_seconds": 3600,
        },
    )
    assert sustained_rule.status_code == 201, sustained_rule.text

    measured_at = datetime.now(timezone.utc)
    payload = {
        "protocol_version": "geovision.telemetry.v1",
        "device_id": device["device_uid"],
        "message_id": "phase33-critical-1",
        "timestamp": measured_at.isoformat(),
        "stream_id": "phase33-boot-a",
        "sequence": 2,
        "measurements": {
            "soil_moisture": {
                "value": 12.5,
                "unit": "%",
                "quality": "good",
            },
            "battery": {"value": 81, "unit": "%", "quality": "good"},
        },
    }
    accepted = client.post("/iot/ingest", headers=device_headers, json=payload)
    assert accepted.status_code == 200, accepted.text
    intelligence = accepted.json()["intelligence"]
    assert intelligence["materialized"] is True
    assert len(intelligence["kpi_value_ids"]) == 2
    assert len(intelligence["observation_ids"]) == 1
    assert len(intelligence["action_ids"]) == 1

    action_id = intelligence["action_ids"][0]
    assert db_session.get(Action, action_id).priority == "CRITICAL"
    assert db_session.get(Observation, intelligence["observation_ids"][0]).severity == (
        "CRITICAL"
    )
    initial_values = [
        db_session.get(KpiValue, value_id) for value_id in intelligence["kpi_value_ids"]
    ]
    battery_value = next(
        value
        for value in initial_values
        if db_session.get(KpiDefinition, value.kpi_definition_id).name == "Battery"
    )
    assert battery_value.status == "GOOD"
    assert (
        db_session.query(IotAlert)
        .filter_by(rule_id=sustained_rule.json()["id"], status="pending")
        .count()
        == 1
    )
    initial_kpis = (
        db_session.query(KpiValue)
        .filter_by(
            workspace_id=workspace_id,
            asset_id=legacy_asset["core_asset_id"],
        )
        .count()
    )

    duplicate = client.post("/iot/ingest", headers=device_headers, json=payload)
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["duplicate"] is True
    assert (
        db_session.query(KpiValue)
        .filter_by(
            workspace_id=workspace_id,
            asset_id=legacy_asset["core_asset_id"],
        )
        .count()
        == initial_kpis
    )
    assert (
        db_session.query(Action)
        .filter_by(
            organization_id=organization_id, asset_id=legacy_asset["core_asset_id"]
        )
        .count()
        == 1
    )

    # The same channel name with a different valid measurement unit must not
    # overwrite the first device's KPI definition or collapse its value.
    metric_device_response = client.post(
        "/iot/devices",
        headers=headers,
        json={
            "name": "Synthetic volumetric soil station",
            "site_id": site.id,
            "asset_id": legacy_asset["id"],
            "device_type": "soil_sensor",
            "transport": "rest",
            "channels": [
                {
                    "key": "soil_moisture",
                    "label": "Volumetric soil moisture",
                    "measurement_type": "soil_moisture",
                    "unit": "m3/m3",
                },
                {
                    "key": "battery",
                    "label": "Battery",
                    "measurement_type": "battery",
                    "unit": "%",
                },
            ],
        },
    )
    assert metric_device_response.status_code == 201, metric_device_response.text
    metric_device = metric_device_response.json()
    metric_exchange = client.post(
        "/iot/provision/exchange",
        json={
            "device_uid": metric_device["device_uid"],
            "provisioning_token": metric_device["provisioning"]["token"],
            "firmware_version": "synthetic-1.0.0",
        },
    )
    assert metric_exchange.status_code == 200, metric_exchange.text
    metric_accepted = client.post(
        "/iot/ingest",
        headers={
            "Authorization": f"Device {metric_exchange.json()['device_secret']}",
            "X-Device-ID": metric_device["device_uid"],
        },
        json={
            **payload,
            "device_id": metric_device["device_uid"],
            "message_id": "phase33-metric-unit-1",
            "stream_id": "phase33-boot-b",
            "measurements": {
                "soil_moisture": {
                    "value": 0.31,
                    "unit": "m3/m3",
                    "quality": "good",
                },
                "battery": {"value": 92, "unit": "%", "quality": "good"},
            },
        },
    )
    assert metric_accepted.status_code == 200, metric_accepted.text
    first_definitions = {
        db_session.get(
            KpiDefinition, db_session.get(KpiValue, value_id).kpi_definition_id
        )
        for value_id in intelligence["kpi_value_ids"]
    }
    metric_definitions = {
        db_session.get(
            KpiDefinition, db_session.get(KpiValue, value_id).kpi_definition_id
        )
        for value_id in metric_accepted.json()["intelligence"]["kpi_value_ids"]
    }
    percent_soil = next(
        row
        for row in first_definitions
        if row.unit == "%" and "soil" in row.name.lower()
    )
    volumetric_soil = next(row for row in metric_definitions if row.unit == "m3/m3")
    assert percent_soil.id != volumetric_soil.id
    assert percent_soil.key != volumetric_soil.key

    # Once an alert is open, later bad readings remain critical even though the
    # notification edge is emitted only once.
    persistent = {
        **payload,
        "message_id": "phase33-critical-2",
        "sequence": 3,
        "timestamp": (measured_at + timedelta(seconds=1)).isoformat(),
        "measurements": {
            "soil_moisture": {"value": 11.8, "unit": "%", "quality": "good"},
            "battery": {"value": 80, "unit": "%", "quality": "good"},
        },
    }
    persistent_result = client.post(
        "/iot/ingest", headers=device_headers, json=persistent
    )
    assert persistent_result.status_code == 200, persistent_result.text
    assert persistent_result.json()["intelligence"]["observation_ids"] == []
    current_soil_value = (
        db_session.query(KpiValue)
        .filter(
            KpiValue.workspace_id == workspace_id,
            KpiValue.asset_id == legacy_asset["core_asset_id"],
            KpiValue.kpi_definition_id == percent_soil.id,
        )
        .order_by(KpiValue.measured_at.desc())
        .first()
    )
    assert current_soil_value.status == "CRITICAL"
    projected_kpis = (
        db_session.query(KpiValue)
        .filter_by(
            workspace_id=workspace_id,
            asset_id=legacy_asset["core_asset_id"],
        )
        .count()
    )
    assert projected_kpis == initial_kpis + 4

    queued_at = measured_at - timedelta(minutes=30)
    replay = {
        **payload,
        "message_id": "phase33-offline-replay-1",
        "sequence": 1,
        "timestamp": (measured_at - timedelta(hours=1)).isoformat(),
        "queued_at": queued_at.isoformat(),
        "replayed_from_edge": True,
        "measurements": {
            "soil_moisture": {"value": 9, "unit": "%", "quality": "good"},
            "battery": {"value": 70, "unit": "%", "quality": "good"},
        },
    }
    replayed = client.post("/iot/ingest", headers=device_headers, json=replay)
    assert replayed.status_code == 200, replayed.text
    assert replayed.json()["out_of_order"] is True
    assert replayed.json()["intelligence"]["reason"] == "out_of_order"
    assert (
        db_session.query(KpiValue)
        .filter_by(
            workspace_id=workspace_id,
            asset_id=legacy_asset["core_asset_id"],
        )
        .count()
        == projected_kpis
    )

    summary = client.get(
        "/portal/assets/summary",
        headers=headers,
        params={"asset_id": legacy_asset["core_asset_id"]},
    )
    assert summary.status_code == 200, summary.text
    item = summary.json()["items"][0]
    assert item["technical_metric_count"] == 4
    assert item["open_action_count"] == 1
    assert item["unvalidated_observation_count"] == 1
    assert item["decision_status"] == "CRITICAL"

    # Derived-intelligence failures are isolated: the raw receipt and readings
    # remain accepted and queryable for a repair/replay worker.
    receipt_count = db_session.query(TelemetryReceipt).count()

    def fail_projection(*args, **kwargs):
        raise RuntimeError("synthetic projection failure")

    from app.iot.intelligence import materialize_iot_intelligence as original_projection

    monkeypatch.setattr("app.iot.service.materialize_iot_intelligence", fail_projection)
    failed_projection_payload = {
        **persistent,
        "message_id": "phase33-projection-failure-1",
        "sequence": 4,
        "timestamp": (measured_at + timedelta(seconds=2)).isoformat(),
    }
    raw_only = client.post(
        "/iot/ingest", headers=device_headers, json=failed_projection_payload
    )
    assert raw_only.status_code == 200, raw_only.text
    assert raw_only.json()["stored"] == 2
    assert raw_only.json()["intelligence"] == {
        "materialized": False,
        "kpi_value_ids": [],
        "observation_ids": [],
        "action_ids": [],
        "reason": "projection_failed",
    }
    db_session.expire_all()
    assert db_session.query(TelemetryReceipt).count() == receipt_count + 1
    assert db_session.get(TelemetryReceipt, raw_only.json()["receipt_id"]) is not None
    assert (
        db_session.query(KpiValue)
        .filter_by(
            workspace_id=workspace_id,
            asset_id=legacy_asset["core_asset_id"],
        )
        .count()
        == projected_kpis
    )
    monkeypatch.setattr(
        "app.iot.service.materialize_iot_intelligence", original_projection
    )
    _drain_events(db_session)
    assert (
        db_session.query(KpiValue)
        .filter_by(
            workspace_id=workspace_id,
            asset_id=legacy_asset["core_asset_id"],
        )
        .count()
        == projected_kpis + 2
    )

    stored_device = db_session.get(IotDevice, device["id"])
    stored_device.last_seen_at = datetime.now(timezone.utc).replace(tzinfo=None) - (
        timedelta(seconds=settings.iot_offline_after_seconds + 5)
    )
    stored_device.status = "online"
    stored_device.connectivity_status = "online"
    db_session.commit()
    assert device["id"] in mark_offline_devices()
    _drain_events(db_session)

    inbox = client.get(
        "/notifications",
        headers=headers,
        params={"workspace_id": workspace_id},
    )
    assert inbox.status_code == 200, inbox.text
    notifications = inbox.json()["items"]
    assert {item["notification_type"] for item in notifications} >= {
        "action.review_requested",
        "device.alert_triggered",
        "device.offline",
    }
    alert_notification = next(
        item
        for item in notifications
        if item["notification_type"] == "device.alert_triggered"
    )
    stored_alert_notification = db_session.get(Notification, alert_notification["id"])
    assert stored_alert_notification is not None
    # The rule uses the schema's default ["log"] policy. It creates an inbox
    # item, but must not queue any configured external channel.
    alert_deliveries = (
        db_session.query(NotificationDelivery)
        .filter(NotificationDelivery.notification_id == alert_notification["id"])
        .all()
    )
    assert alert_deliveries
    assert {row.status for row in alert_deliveries} == {"SUPPRESSED"}
    action_notification = next(
        item
        for item in notifications
        if item["notification_type"] == "action.review_requested"
    )
    target = client.get(
        f"/notifications/{action_notification['id']}/target", headers=headers
    )
    assert target.status_code == 200, target.text
    assert target.json()["target_type"] == "ACTION"
    assert target.json()["target_id"] == action_id
    assert target.json()["app_path"] == f"/actions/{action_id}"

    offline_summary = client.get(
        "/portal/assets/summary",
        headers=headers,
        params={"asset_id": legacy_asset["core_asset_id"]},
    )
    assert offline_summary.status_code == 200, offline_summary.text
    assert offline_summary.json()["totals"]["offline_devices"] == 1

    _, outsider_headers, _, outsider_workspace_id = _owner(
        client, db_session, "phase33-outsider"
    )
    outsider_inbox = client.get(
        "/notifications",
        headers=outsider_headers,
        params={"workspace_id": outsider_workspace_id},
    )
    assert outsider_inbox.status_code == 200, outsider_inbox.text
    assert outsider_inbox.json()["items"] == []
    assert (
        client.get(
            f"/notifications/{action_notification['id']}/target",
            headers=outsider_headers,
        ).status_code
        == 404
    )

    second_workspace = client.post(
        f"/organizations/{organization_id}/workspaces",
        headers=headers,
        json={
            "name": "Separate connected workspace",
            "customer_type": "business",
            "sector_focus": "agriculture",
            "modules_enabled": ["monitoring", "iot", "kpi", "actions", "alerts"],
        },
    )
    assert second_workspace.status_code == 201, second_workspace.text
    second_headers = {
        "Authorization": headers["Authorization"],
        "X-Workspace-ID": second_workspace.json()["id"],
    }
    second_summary = client.get("/portal/assets/summary", headers=second_headers)
    assert second_summary.status_code == 200, second_summary.text
    assert second_summary.json()["items"] == []
    second_inbox = client.get(
        "/notifications",
        headers=second_headers,
        params={"workspace_id": second_workspace.json()["id"]},
    )
    assert second_inbox.status_code == 200, second_inbox.text
    assert second_inbox.json()["items"] == []

    second_asset = client.post(
        "/assets",
        headers=second_headers,
        json={
            "sector": "AGRICULTURE",
            "asset_type": "FIELD",
            "name": "Separate workspace field",
        },
    )
    assert second_asset.status_code == 201, second_asset.text
    reassigned = client.post(
        f"/iot/devices/{device['id']}/assignments",
        headers=second_headers,
        json={
            "asset_id": second_asset.json()["id"],
            "reason": "Verify immutable event workspace routing",
        },
    )
    assert reassigned.status_code == 201, reassigned.text
    triggered_alert = (
        db_session.query(IotAlert).filter_by(rule_id=rule.json()["id"]).one()
    )
    historical_event = DomainEvent(
        name=EventNames.DEVICE_ALERT_TRIGGERED,
        aggregate_type="iot_alert",
        aggregate_id=triggered_alert.id,
        idempotency_key=f"phase33-historical-alert-{uuid.uuid4().hex}",
        payload={
            "alert_id": triggered_alert.id,
            "device_id": device["id"],
            "organization_id": organization_id,
            "workspace_id": workspace_id,
            "asset_id": legacy_asset["core_asset_id"],
            "severity": "critical",
        },
    )
    materialize_notification_event(db_session, historical_event)
    db_session.commit()
    second_inbox = client.get(
        "/notifications",
        headers=second_headers,
        params={"workspace_id": second_workspace.json()["id"]},
    )
    assert second_inbox.status_code == 200, second_inbox.text
    assert second_inbox.json()["items"] == []

    # A fresh alert after reassignment belongs to workspace B. It must create
    # a new B notification instead of aggregating into the recent A inbox row.
    original_alert_occurrences = stored_alert_notification.occurrence_count
    triggered_alert.status = "resolved"
    triggered_alert.resolved_at = datetime.now(timezone.utc).replace(tzinfo=None)
    stored_rule = db_session.get(IotAlertRule, rule.json()["id"])
    assert stored_rule is not None
    stored_rule.cooldown_seconds = 0
    db_session.commit()
    post_reassignment = client.post(
        "/iot/ingest",
        headers=device_headers,
        json={
            **persistent,
            "message_id": "phase33-post-reassignment-alert",
            "sequence": 5,
            "timestamp": (measured_at + timedelta(seconds=3)).isoformat(),
        },
    )
    assert post_reassignment.status_code == 200, post_reassignment.text
    _drain_events(db_session)
    reassigned_inbox = client.get(
        "/notifications",
        headers=second_headers,
        params={"workspace_id": second_workspace.json()["id"]},
    )
    assert reassigned_inbox.status_code == 200, reassigned_inbox.text
    reassigned_alert = next(
        item
        for item in reassigned_inbox.json()["items"]
        if item["notification_type"] == "device.alert_triggered"
    )
    assert reassigned_alert["id"] != alert_notification["id"]
    assert reassigned_alert["workspace_id"] == second_workspace.json()["id"]
    assert reassigned_alert["target_id"] == second_asset.json()["id"]
    db_session.refresh(stored_alert_notification)
    assert stored_alert_notification.occurrence_count == original_alert_occurrences
