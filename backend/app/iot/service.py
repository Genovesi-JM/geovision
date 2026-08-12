from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.iot.notifications import notification_adapters
from app.iot.registry import valid_unit
from app.iot.schemas import MeasurementValue, TelemetryEnvelope
from app.iot.security import secret_matches, timestamp_is_fresh
from app.config import settings
from app.models import (
    DeviceCredential,
    IotAlert,
    IotAlertRule,
    IotCommand,
    IotDevice,
    SensorChannel,
    Site,
    TelemetryReading,
)
from app.time_utils import utc_now

# On-device firmware also enforces these locally; the backend rule is the
# "decide" layer of detect → decide → act → confirm.
IRRIGATION_TRIGGER_PCT = 25.0
IRRIGATION_TARGET_PCT = 40.0


def json_value(value: str | None, fallback):
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return fallback


def device_for_company(db: Session, device_id: str, company_id: str) -> IotDevice:
    device = db.get(IotDevice, device_id)
    if not device or device.company_id != company_id:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


def active_credential(db: Session, device: IotDevice) -> DeviceCredential | None:
    now = utc_now()
    return (
        db.query(DeviceCredential)
        .filter(
            DeviceCredential.device_id == device.id,
            DeviceCredential.status == "active",
            (DeviceCredential.expires_at.is_(None) | (DeviceCredential.expires_at > now)),
        )
        .order_by(DeviceCredential.issued_at.desc())
        .first()
    )


def authenticate_device(db: Session, device_uid: str, token: str) -> IotDevice:
    device = db.query(IotDevice).filter(IotDevice.public_id == device_uid).first()
    if not device or device.status in {"disabled", "quarantined"}:
        raise HTTPException(status_code=401, detail="Invalid or disabled device")
    credential = active_credential(db, device)
    expected = credential.token_hash if credential else device.token_hash
    if not secret_matches(token, expected):
        raise HTTPException(status_code=401, detail="Invalid device credential")
    return device


def _normalize_value(raw):
    if isinstance(raw, MeasurementValue):
        return raw.value, raw.unit, raw.quality, raw.metadata
    return raw, None, "good", {}


def _comparison(operator: str, value: float, threshold: float, previous: float | None) -> bool:
    if operator == "gt": return value > threshold
    if operator == "gte": return value >= threshold
    if operator == "lt": return value < threshold
    if operator == "lte": return value <= threshold
    if operator == "eq": return value == threshold
    if operator == "ne": return value != threshold
    if operator == "rapid_rise": return previous is not None and value - previous >= threshold
    if operator == "rapid_fall": return previous is not None and previous - value >= threshold
    return False


def _evaluate_alerts(db: Session, device: IotDevice, reading: TelemetryReading, previous: float | None) -> list[dict]:
    if reading.numeric_value is None:
        return []
    rules = (
        db.query(IotAlertRule)
        .filter(
            IotAlertRule.company_id == device.company_id,
            IotAlertRule.enabled.is_(True),
            IotAlertRule.channel == reading.channel,
            (IotAlertRule.device_id.is_(None) | (IotAlertRule.device_id == device.id)),
            (IotAlertRule.site_id.is_(None) | (IotAlertRule.site_id == device.site_id)),
        )
        .all()
    )
    events: list[dict] = []
    for rule in rules:
        now = utc_now()
        triggered = _comparison(rule.operator, reading.numeric_value, rule.threshold, previous)
        open_alert = (
            db.query(IotAlert)
            .filter(IotAlert.rule_id == rule.id, IotAlert.device_id == device.id, IotAlert.status.in_(["pending", "triggered", "notified", "acknowledged", "assigned"]))
            .order_by(IotAlert.opened_at.desc())
            .first()
        )
        if triggered and not open_alert:
            recent = (
                db.query(IotAlert)
                .filter(IotAlert.rule_id == rule.id, IotAlert.device_id == device.id)
                .order_by(IotAlert.opened_at.desc())
                .first()
            )
            if recent and (now - recent.opened_at).total_seconds() < rule.cooldown_seconds:
                continue
            alert = IotAlert(
                company_id=device.company_id, device_id=device.id, rule_id=rule.id,
                channel=reading.channel, value=reading.numeric_value,
                severity=rule.severity,
                message=f"{rule.name}: {reading.channel}={reading.numeric_value:g} {reading.unit or ''}".strip(),
                status="pending" if rule.sustained_seconds else "triggered",
            )
            db.add(alert)
            db.flush()
            open_alert = alert
        if triggered and open_alert and open_alert.status == "pending" and (now - open_alert.opened_at).total_seconds() >= rule.sustained_seconds:
            open_alert.status = "triggered"
        if triggered and open_alert and open_alert.status == "triggered":
            open_alert.value = reading.numeric_value
            event = {"type": "alert.triggered", "id": open_alert.id, "severity": open_alert.severity, "message": open_alert.message}
            for channel in json_value(rule.notification_channels_json, ["log"]):
                adapter = notification_adapters.get(channel)
                try:
                    if adapter: adapter.send(event)
                except RuntimeError:
                    continue
            open_alert.status = "notified"
            events.append(event)
        elif not triggered and open_alert:
            open_alert.status = "resolved"
            open_alert.resolved_at = now
            events.append({"type": "alert.resolved", "id": open_alert.id, "severity": open_alert.severity, "message": open_alert.message})
    return events


def _evaluate_irrigation(db: Session, device: IotDevice) -> list[dict]:
    """Closed-loop irrigation automation (the platform decides and acts).

    When a valve-capable device reports dry soil, enqueue a valve-open command;
    when soil recovers, enqueue valve-close. Same safety gates as a manual
    command (safety interlock confirmed, tank not empty); the device firmware
    also enforces its own local interlocks so this never has sole control.
    """
    caps = set(json_value(device.capabilities_json, []))
    if not device.allow_remote_control or "command:low_voltage_valve_open" not in caps:
        return []
    latest = {r["channel"]: r["value"] for r in latest_readings(db, device)}
    soil = latest.get("soil_moisture")
    if not isinstance(soil, (int, float)) or isinstance(soil, bool):
        return []
    valve_open = latest.get("valve_open") is True
    safety_ok = latest.get("safety_ok", True) is True
    tank = latest.get("tank_level")
    tank_ok = not isinstance(tank, (int, float)) or tank > 5
    # Don't stack commands: wait for the current one to be delivered/acted.
    if db.query(IotCommand.id).filter(IotCommand.device_id == device.id, IotCommand.status.in_(["queued", "delivered"])).first():
        return []

    def enqueue(name: str, reason: str) -> dict:
        db.add(IotCommand(
            company_id=device.company_id, device_id=device.id, requested_by="system-auto-irrig",
            correlation_id=str(uuid.uuid4()), name=name, arguments_json="{}", reason=reason,
            fail_safe_state="off", expires_at=utc_now() + timedelta(seconds=300),
        ))
        db.flush()
        return {"type": "automation.irrigation", "action": name, "device_id": device.id, "reason": reason, "soil_moisture": soil}

    if soil < IRRIGATION_TRIGGER_PCT and not valve_open and safety_ok and tank_ok:
        return [enqueue("low_voltage_valve_open", f"Auto-irrigation: soil {soil:g}% below {IRRIGATION_TRIGGER_PCT:g}%")]
    if valve_open and soil >= IRRIGATION_TARGET_PCT:
        return [enqueue("low_voltage_valve_close", f"Auto-irrigation: soil {soil:g}% recovered to target")]
    return []


def ingest_telemetry(
    db: Session,
    device: IotDevice,
    envelope: TelemetryEnvelope,
    *,
    source: str,
    remote_ip: str | None = None,
    publish: Callable[[str, dict], None] | None = None,
) -> dict:
    recorded_at = envelope.timestamp.astimezone(timezone.utc).replace(tzinfo=None) if envelope.timestamp.tzinfo else envelope.timestamp
    if not timestamp_is_fresh(recorded_at):
        raise HTTPException(status_code=422, detail="Telemetry timestamp is outside the accepted window")

    existing = (
        db.query(TelemetryReading.id)
        .filter(TelemetryReading.device_id == device.id, TelemetryReading.message_id == envelope.message_id)
        .first()
    )
    if existing:
        return {"accepted": True, "duplicate": True, "stored": 0, "message_id": envelope.message_id}

    recent_count = db.query(TelemetryReading.id).filter(
        TelemetryReading.device_id == device.id,
        TelemetryReading.received_at >= utc_now() - timedelta(minutes=1),
    ).count()
    if recent_count >= settings.iot_max_messages_per_minute * max(len(envelope.measurements), 1):
        raise HTTPException(status_code=429, detail="Device telemetry rate limit exceeded")

    channels = {row.key: row for row in db.query(SensorChannel).filter(SensorChannel.device_id == device.id, SensorChannel.enabled.is_(True)).all()}
    unknown = sorted(set(envelope.measurements) - set(channels))
    if unknown:
        raise HTTPException(status_code=422, detail={"unknown_channels": unknown})

    reading_payloads = []
    alert_events: list[dict] = []
    for key, raw in envelope.measurements.items():
        channel = channels[key]
        value, supplied_unit, quality, metadata = _normalize_value(raw)
        unit = supplied_unit if supplied_unit is not None else channel.unit
        if unit != channel.unit or not valid_unit(channel.measurement_type, unit):
            raise HTTPException(status_code=422, detail=f"Invalid unit for channel {key}")
        numeric = text = boolean = None
        if channel.data_type == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise HTTPException(status_code=422, detail=f"Channel {key} requires a number")
            numeric = float(value)
            if channel.minimum is not None and numeric < channel.minimum:
                quality = "bad"
            if channel.maximum is not None and numeric > channel.maximum:
                quality = "bad"
        elif channel.data_type == "boolean":
            if not isinstance(value, bool):
                raise HTTPException(status_code=422, detail=f"Channel {key} requires a boolean")
            boolean = value
            numeric = 1.0 if value else 0.0
        else:
            text = str(value)[:2000]

        previous_row = (
            db.query(TelemetryReading)
            .filter(TelemetryReading.device_id == device.id, TelemetryReading.channel == key)
            .order_by(TelemetryReading.recorded_at.desc())
            .first()
        )
        row = TelemetryReading(
            device_id=device.id, company_id=device.company_id, site_id=device.site_id,
            message_id=envelope.message_id, channel=key, numeric_value=numeric,
            text_value=text, boolean_value=boolean, unit=unit, quality=quality,
            recorded_at=recorded_at, metadata_json=json.dumps({**envelope.metadata, **metadata, "source": source}),
        )
        db.add(row)
        db.flush()
        alert_events.extend(_evaluate_alerts(db, device, row, previous_row.numeric_value if previous_row else None))
        reading_payloads.append({"channel": key, "value": value, "unit": unit, "quality": quality})

    automation_events = _evaluate_irrigation(db, device)

    device.last_seen_at = utc_now()
    device.last_ip = remote_ip
    device.status = "online"
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"accepted": True, "duplicate": True, "stored": 0, "message_id": envelope.message_id}

    event = {
        "type": "telemetry", "device_id": device.id, "device_uid": device.public_id,
        "message_id": envelope.message_id, "at": recorded_at.isoformat() + "Z",
        "readings": reading_payloads, "alerts": alert_events, "automation": automation_events,
    }
    if publish:
        publish(device.id, event)
        for alert in alert_events:
            publish(device.id, alert)
        for act in automation_events:
            publish(device.id, act)
    return {"accepted": True, "duplicate": False, "stored": len(reading_payloads), "message_id": envelope.message_id, "automation": automation_events}


def latest_readings(db: Session, device: IotDevice) -> list[dict]:
    result = []
    channel_keys = [row[0] for row in db.query(SensorChannel.key).filter(SensorChannel.device_id == device.id).all()]
    for key in channel_keys:
        row = db.query(TelemetryReading).filter(TelemetryReading.device_id == device.id, TelemetryReading.channel == key).order_by(TelemetryReading.recorded_at.desc()).first()
        if row:
            value = row.boolean_value if row.boolean_value is not None else row.numeric_value if row.numeric_value is not None else row.text_value
            result.append({"channel": key, "value": value, "unit": row.unit, "quality": row.quality, "at": row.recorded_at.isoformat() + "Z"})
    return result
