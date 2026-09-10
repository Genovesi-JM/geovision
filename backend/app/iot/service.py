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
from app.core.config import settings
from app.core.event_names import EventNames
from app.models import (
    DeviceCredential,
    IotAlert,
    IotAlertRule,
    IotCommand,
    IotDevice,
    SensorChannel,
    Site,
    TelemetryReceipt,
    TelemetryReading,
)
from app.core.time import utc_now
from app.services.event_outbox import enqueue_domain_event

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


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _recorded_at(envelope: TelemetryEnvelope, now: datetime) -> tuple[datetime, datetime | None]:
    recorded_at = _naive_utc(envelope.timestamp)
    queued_at = _naive_utc(envelope.queued_at) if envelope.queued_at else None
    if envelope.replayed_from_edge:
        if queued_at is None:
            raise HTTPException(status_code=422, detail="Store-and-forward queued_at is required")
        if queued_at < recorded_at - timedelta(seconds=5):
            raise HTTPException(status_code=422, detail="queued_at cannot precede the measurement")
        if queued_at > now + timedelta(minutes=5) or recorded_at > now + timedelta(minutes=5):
            raise HTTPException(status_code=422, detail="Telemetry timestamp is in the future")
        if recorded_at < now - timedelta(days=settings.iot_store_forward_max_age_days):
            raise HTTPException(status_code=422, detail="Store-and-forward telemetry exceeds retention")
    elif not timestamp_is_fresh(recorded_at):
        raise HTTPException(status_code=422, detail="Telemetry timestamp is outside the accepted window")
    return recorded_at, queued_at


def _device_identity_matches(device: IotDevice, envelope: TelemetryEnvelope) -> bool:
    if envelope.device_id is None:
        return True
    allowed = {device.id, device.public_id}
    if device.provider_device_id:
        allowed.add(device.provider_device_id)
    return envelope.device_id in allowed


def _mark_contact(db: Session, device: IotDevice, *, remote_ip: str | None) -> None:
    device.last_seen_at = utc_now()
    device.last_ip = remote_ip
    device.status = "online"
    device.connectivity_status = "online"
    db.commit()


def _health_snapshot(readings: list[dict], current_battery: float | None) -> tuple[float | None, str]:
    battery = current_battery
    for reading in readings:
        if reading["channel"] == "battery" and isinstance(reading["value"], (int, float)):
            battery = max(0.0, min(100.0, float(reading["value"])))
    qualities = {str(reading["quality"]) for reading in readings}
    if "sensor_error" in qualities or "bad" in qualities or (battery is not None and battery < 10):
        return battery, "critical"
    if "uncertain" in qualities or (battery is not None and battery < 25):
        return battery, "degraded"
    return battery, "healthy"


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
    provider_message_id: str | None = None,
    remote_ip: str | None = None,
    publish: Callable[[str, dict], None] | None = None,
) -> dict:
    now = utc_now()
    if not _device_identity_matches(device, envelope):
        raise HTTPException(status_code=422, detail="Telemetry device_id does not match the authenticated device")

    existing_receipt = (
        db.query(TelemetryReceipt)
        .filter(
            TelemetryReceipt.device_id == device.id,
            TelemetryReceipt.message_id == envelope.message_id,
        )
        .first()
    )
    if provider_message_id and existing_receipt is None:
        existing_receipt = (
            db.query(TelemetryReceipt)
            .filter(
                TelemetryReceipt.provider_code == device.provider_code,
                TelemetryReceipt.provider_message_id == provider_message_id,
            )
            .first()
        )
        if existing_receipt is not None and existing_receipt.device_id != device.id:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "provider_message_conflict",
                    "message": "The provider event identity is already bound to another device",
                },
            )
    legacy_duplicate = None
    if existing_receipt is None:
        legacy_duplicate = (
            db.query(TelemetryReading.id)
            .filter(
                TelemetryReading.device_id == device.id,
                TelemetryReading.message_id == envelope.message_id,
            )
            .first()
        )
    if existing_receipt or legacy_duplicate:
        _mark_contact(db, device, remote_ip=remote_ip)
        return {
            "accepted": True,
            "duplicate": True,
            "stored": 0,
            "message_id": existing_receipt.message_id if existing_receipt else envelope.message_id,
            "receipt_id": existing_receipt.id if existing_receipt else None,
            "out_of_order": existing_receipt.out_of_order if existing_receipt else False,
            "replayed_from_edge": (
                existing_receipt.replayed_from_edge if existing_receipt else envelope.replayed_from_edge
            ),
        }

    recorded_at, queued_at = _recorded_at(envelope, now)

    if envelope.stream_id is not None and envelope.sequence is not None:
        sequence_row = (
            db.query(TelemetryReceipt)
            .filter(
                TelemetryReceipt.device_id == device.id,
                TelemetryReceipt.stream_id == envelope.stream_id,
                TelemetryReceipt.sequence == envelope.sequence,
            )
            .first()
        )
        if sequence_row:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "telemetry_sequence_conflict",
                    "message": "The stream sequence is already bound to another message",
                },
            )

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

    latest_receipt = (
        db.query(TelemetryReceipt)
        .filter(TelemetryReceipt.device_id == device.id)
        .order_by(TelemetryReceipt.recorded_at.desc(), TelemetryReceipt.received_at.desc())
        .first()
    )
    out_of_order = bool(latest_receipt and recorded_at < latest_receipt.recorded_at)
    if (
        envelope.stream_id is not None
        and envelope.sequence is not None
        and device.last_stream_id == envelope.stream_id
        and device.last_sequence is not None
        and envelope.sequence < device.last_sequence
    ):
        out_of_order = True

    receipt = TelemetryReceipt(
        device_id=device.id,
        company_id=device.company_id,
        site_id=device.site_id,
        core_asset_id=device.core_asset_id,
        message_id=envelope.message_id,
        provider_code=device.provider_code,
        provider_message_id=provider_message_id,
        protocol_version=envelope.protocol_version,
        firmware_version=envelope.firmware_version,
        stream_id=envelope.stream_id,
        sequence=envelope.sequence,
        recorded_at=recorded_at,
        received_at=now,
        out_of_order=out_of_order,
        replayed_from_edge=envelope.replayed_from_edge,
        queued_at=queued_at,
        measurement_count=len(envelope.measurements),
        context_json=json.dumps(
            {"context": envelope.context, "source": source},
            separators=(",", ":"),
            sort_keys=True,
        ),
    )
    db.add(receipt)
    db.flush()

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
            receipt_id=receipt.id, device_id=device.id, company_id=device.company_id,
            site_id=device.site_id, core_asset_id=device.core_asset_id,
            message_id=envelope.message_id, channel=key, numeric_value=numeric,
            text_value=text, boolean_value=boolean, unit=unit, quality=quality,
            sequence=envelope.sequence, protocol_version=envelope.protocol_version,
            source=source, recorded_at=recorded_at,
            metadata_json=json.dumps(
                {
                    **envelope.metadata,
                    **metadata,
                    "context": envelope.context,
                    "replayed_from_edge": envelope.replayed_from_edge,
                    "source": source,
                },
                default=str,
            ),
        )
        db.add(row)
        db.flush()
        if not out_of_order:
            alert_events.extend(
                _evaluate_alerts(
                    db,
                    device,
                    row,
                    previous_row.numeric_value if previous_row else None,
                )
            )
        reading_payloads.append({"channel": key, "value": value, "unit": unit, "quality": quality})

    automation_events = [] if out_of_order else _evaluate_irrigation(db, device)

    device.last_seen_at = now
    device.last_ip = remote_ip
    device.status = "online"
    device.connectivity_status = "online"
    if not out_of_order:
        device.protocol_version = envelope.protocol_version
        if envelope.firmware_version:
            device.firmware_version = envelope.firmware_version
        if envelope.stream_id is not None and envelope.sequence is not None:
            device.last_stream_id = envelope.stream_id
            device.last_sequence = envelope.sequence
        device.battery_percent, device.health_status = _health_snapshot(
            reading_payloads,
            device.battery_percent,
        )
        latitude = envelope.location.latitude if envelope.location else next(
            (
                float(row["value"])
                for row in reading_payloads
                if row["channel"] == "latitude" and isinstance(row["value"], (int, float))
            ),
            None,
        )
        longitude = envelope.location.longitude if envelope.location else next(
            (
                float(row["value"])
                for row in reading_payloads
                if row["channel"] == "longitude" and isinstance(row["value"], (int, float))
            ),
            None,
        )
        if latitude is not None and longitude is not None:
            device.last_latitude = latitude
            device.last_longitude = longitude
    enqueue_domain_event(
        db,
        name=EventNames.DEVICE_TELEMETRY_RECEIVED,
        aggregate_type="iot_device",
        aggregate_id=device.id,
        idempotency_key=f"device:{device.id}:telemetry:{envelope.message_id}",
        correlation_id=envelope.message_id,
        occurred_at=recorded_at,
        payload={
            "device_id": device.id,
            "device_uid": device.public_id,
            "organization_id": device.company_id,
            "site_id": device.site_id,
            "asset_id": device.core_asset_id,
            "message_id": envelope.message_id,
            "receipt_id": receipt.id,
            "protocol_version": envelope.protocol_version,
            "stream_id": envelope.stream_id,
            "sequence": envelope.sequence,
            "out_of_order": out_of_order,
            "replayed_from_edge": envelope.replayed_from_edge,
            "source": source,
            "channels": [reading["channel"] for reading in reading_payloads],
            "alert_ids": [event["id"] for event in alert_events],
        },
    )
    for alert_event in alert_events:
        if alert_event.get("type") != "alert.triggered":
            continue
        alert_id = str(alert_event.get("id") or "")
        if not alert_id:
            continue
        enqueue_domain_event(
            db,
            name=EventNames.DEVICE_ALERT_TRIGGERED,
            aggregate_type="iot_alert",
            aggregate_id=alert_id,
            idempotency_key=f"iot-alert:{alert_id}:triggered",
            correlation_id=envelope.message_id,
            causation_id=str(receipt.id),
            occurred_at=recorded_at,
            payload={
                "alert_id": alert_id,
                "device_id": device.id,
                "organization_id": device.company_id,
                "asset_id": device.core_asset_id,
                "severity": alert_event.get("severity"),
            },
        )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"accepted": True, "duplicate": True, "stored": 0, "message_id": envelope.message_id}

    event = {
        "type": "telemetry", "device_id": device.id, "device_uid": device.public_id,
        "message_id": envelope.message_id, "at": recorded_at.isoformat() + "Z",
        "receipt_id": receipt.id, "asset_id": device.core_asset_id,
        "out_of_order": out_of_order, "replayed_from_edge": envelope.replayed_from_edge,
        "readings": reading_payloads, "alerts": alert_events, "automation": automation_events,
    }
    if publish:
        publish(device.id, event)
        for alert in alert_events:
            publish(device.id, alert)
        for act in automation_events:
            publish(device.id, act)
    return {
        "accepted": True,
        "duplicate": False,
        "stored": len(reading_payloads),
        "message_id": envelope.message_id,
        "receipt_id": receipt.id,
        "asset_id": device.core_asset_id,
        "out_of_order": out_of_order,
        "replayed_from_edge": envelope.replayed_from_edge,
        "automation": automation_events,
    }


def latest_readings(db: Session, device: IotDevice) -> list[dict]:
    result = []
    channel_keys = [row[0] for row in db.query(SensorChannel.key).filter(SensorChannel.device_id == device.id).all()]
    for key in channel_keys:
        row = db.query(TelemetryReading).filter(TelemetryReading.device_id == device.id, TelemetryReading.channel == key).order_by(TelemetryReading.recorded_at.desc()).first()
        if row:
            value = row.boolean_value if row.boolean_value is not None else row.numeric_value if row.numeric_value is not None else row.text_value
            result.append({"channel": key, "value": value, "unit": row.unit, "quality": row.quality, "at": row.recorded_at.isoformat() + "Z"})
    return result
