from __future__ import annotations

import asyncio
import csv
import io
import json
import secrets
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import StreamingResponse, Response
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.database import get_db
from app.deps import get_current_user
from app.iot.events import event_hub
from app.iot.registry import valid_unit
from app.iot.schemas import (
    AlertRuleCreate,
    AlertAssignment,
    CalibrationCreate,
    CommandCreate,
    CommandResult,
    CommissioningCreate,
    DeviceCreate,
    ProvisionExchange,
    TelemetryEnvelope,
)
from app.iot.security import hash_secret, new_secret, protect_secret, secret_matches, sign_mqtt_payload
from app.iot.service import authenticate_device, device_for_company, ingest_telemetry, json_value, latest_readings
from app.models import (
    AuditLog,
    CalibrationRecord,
    CommissioningRecord,
    CompanyUser,
    DeviceCredential,
    DeviceProvisioningToken,
    IotAlert,
    IotAlertRule,
    IotAsset,
    IotCommand,
    IotDevice,
    IotGateway,
    SensorChannel,
    Site,
    TelemetryAggregate,
    TelemetryReading,
    User,
    Company,
)
from app.oauth2 import verify_access_token
from app.routers.me import _get_user_company_id

router = APIRouter(prefix="/iot", tags=["iot"])
mobile_router = APIRouter(prefix="/mobile", tags=["mobile", "iot"])

OUTPUT_COMMANDS = {
    "beacon_on", "beacon_off", "buzzer_on", "buzzer_off",
    "demo_fan_on", "demo_fan_off", "low_voltage_valve_open",
    "low_voltage_valve_close", "relay_on", "relay_off",
}


class DeviceStatusUpdate(BaseModel):
    status: str = Field(pattern="^(active|disabled|quarantined)$")
    reason: str = Field(min_length=4, max_length=500)


class AssetCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    site_id: str
    asset_type: str = Field(min_length=2, max_length=80)
    external_reference: str | None = Field(default=None, max_length=120)
    latitude: float | None = None
    longitude: float | None = None
    metadata: dict = Field(default_factory=dict)


class GatewayCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    site_id: str
    gateway_type: str = Field(min_length=2, max_length=40)
    device_id: str | None = None
    configuration: dict = Field(default_factory=dict)


def _company_id(user: User, db: Session) -> str:
    value = _get_user_company_id(user, db)
    if not value:
        raise HTTPException(status_code=409, detail="Create or link a customer organisation before provisioning hardware")
    return value


def _audit(db: Session, user: User, action: str, resource_type: str, resource_id: str, details: dict | None = None) -> None:
    db.add(AuditLog(
        user_id=user.id, user_email=user.email, action=action,
        resource_type=resource_type, resource_id=resource_id,
        details=json.dumps(details or {}, default=str),
    ))


def _topics(device: IotDevice) -> dict:
    base = f"geovision/v1/{device.company_id}/{device.site_id}/{device.public_id}"
    return {name: f"{base}/{name}" for name in (
        "telemetry", "state", "events", "commands", "command-results", "configuration"
    )}


def _device_payload(db: Session, device: IotDevice) -> dict:
    site = db.get(Site, device.site_id)
    readings = latest_readings(db, device)
    battery = next((r["value"] for r in readings if r["channel"] == "battery"), 0)
    signal = next((r["value"] for r in readings if r["channel"] == "signal"), 0)
    last = max((datetime.fromisoformat(r["at"].replace("Z", "+00:00")) for r in readings), default=None)
    label = ", ".join(f"{r['channel']} {r['value']}{r['unit'] or ''}" for r in readings[:3]) or None
    return {
        "id": device.id, "device_uid": device.public_id, "name": device.name,
        "type": device.device_type, "site_id": device.site_id,
        "site_name": site.name if site else "", "asset_id": device.asset_id,
        "status": device.status, "battery_percent": int(float(battery or 0)),
        "signal_percent": int(float(signal or 0)),
        "last_reading_at": last.isoformat() if last else None,
        "last_reading_label": label, "provider_id": "geovision-backend",
        "transport": device.transport, "capabilities": json_value(device.capabilities_json, []),
        "allow_remote_control": device.allow_remote_control,
        "last_seen_at": device.last_seen_at.isoformat() + "Z" if device.last_seen_at else None,
        "topics": _topics(device), "readings": readings,
    }


@router.post("/assets", status_code=status.HTTP_201_CREATED)
def create_asset(payload: AssetCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company_id = _company_id(user, db); site = db.get(Site, payload.site_id)
    if not site or site.company_id != company_id: raise HTTPException(status_code=404, detail="Site not found")
    row = IotAsset(company_id=company_id, site_id=site.id, name=payload.name.strip(), asset_type=payload.asset_type, external_reference=payload.external_reference, latitude=payload.latitude, longitude=payload.longitude, metadata_json=json.dumps(payload.metadata))
    db.add(row); db.flush(); _audit(db, user, "iot.asset_created", "iot_asset", row.id); db.commit()
    return {"id": row.id, **payload.model_dump()}


@router.get("/assets")
def list_assets(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company_id = _company_id(user, db)
    rows = db.query(IotAsset).filter(IotAsset.company_id == company_id).order_by(IotAsset.name).all()
    return [{"id": row.id, "name": row.name, "site_id": row.site_id, "asset_type": row.asset_type, "external_reference": row.external_reference, "latitude": row.latitude, "longitude": row.longitude, "metadata": json_value(row.metadata_json, {})} for row in rows]


@router.post("/gateways", status_code=status.HTTP_201_CREATED)
def create_gateway(payload: GatewayCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company_id = _company_id(user, db); site = db.get(Site, payload.site_id)
    if not site or site.company_id != company_id: raise HTTPException(status_code=404, detail="Site not found")
    if payload.device_id: device_for_company(db, payload.device_id, company_id)
    row = IotGateway(company_id=company_id, site_id=site.id, device_id=payload.device_id, name=payload.name.strip(), gateway_type=payload.gateway_type, configuration_json=json.dumps(payload.configuration))
    db.add(row); db.flush(); _audit(db, user, "iot.gateway_created", "iot_gateway", row.id); db.commit()
    return {"id": row.id, **payload.model_dump()}


@router.get("/gateways")
def list_gateways(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company_id = _company_id(user, db)
    rows = db.query(IotGateway).filter(IotGateway.company_id == company_id).order_by(IotGateway.name).all()
    return [{"id": row.id, "name": row.name, "site_id": row.site_id, "device_id": row.device_id, "gateway_type": row.gateway_type, "status": row.status, "configuration": json_value(row.configuration_json, {})} for row in rows]


@router.post("/devices", status_code=status.HTTP_201_CREATED)
def create_device(payload: DeviceCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company_id = _company_id(user, db)
    site = db.get(Site, payload.site_id)
    if not site or site.company_id != company_id:
        raise HTTPException(status_code=404, detail="Site not found")
    if payload.asset_id:
        asset = db.get(IotAsset, payload.asset_id)
        if not asset or asset.company_id != company_id or asset.site_id != site.id: raise HTTPException(status_code=404, detail="Asset not found at this site")
    if payload.gateway_id:
        gateway = db.get(IotGateway, payload.gateway_id)
        if not gateway or gateway.company_id != company_id or gateway.site_id != site.id: raise HTTPException(status_code=404, detail="Gateway not found at this site")
    for channel in payload.channels:
        if not valid_unit(channel.measurement_type, channel.unit):
            raise HTTPException(status_code=422, detail=f"Unsupported unit for {channel.key}: {channel.unit}")
    placeholder = new_secret()
    public_id = f"gv-{secrets.token_hex(6)}"
    device = IotDevice(
        public_id=public_id, company_id=company_id, site_id=site.id,
        asset_id=payload.asset_id, gateway_id=payload.gateway_id,
        name=payload.name.strip(), device_type=payload.device_type,
        transport=payload.transport, hardware_model=payload.hardware_model,
        capabilities_json=json.dumps(sorted(set(payload.capabilities))),
        token_hash=hash_secret(placeholder), secret_encrypted=protect_secret(placeholder),
        allow_remote_control=payload.allow_remote_control, created_by=user.id,
    )
    db.add(device)
    db.flush()
    for channel in payload.channels:
        db.add(SensorChannel(device_id=device.id, asset_id=payload.asset_id, **channel.model_dump()))
    one_time = new_secret()
    token_row = DeviceProvisioningToken(
        device_id=device.id, token_hash=hash_secret(one_time),
        expires_at=datetime.utcnow() + timedelta(minutes=30), created_by=user.id,
    )
    db.add(token_row)
    _audit(db, user, "iot.device_created", "iot_device", device.id, {"site_id": site.id, "transport": device.transport})
    db.commit()
    return {
        **_device_payload(db, device),
        "provisioning": {
            "token": one_time, "expires_at": token_row.expires_at.isoformat() + "Z",
            "exchange_url": "/iot/provision/exchange",
            "qr_payload": json.dumps({"device_uid": public_id, "token": one_time}),
        },
        "important": "The provisioning token is shown once and expires in 30 minutes.",
    }


@router.post("/provision/exchange")
def exchange_provisioning_token(payload: ProvisionExchange, db: Session = Depends(get_db)):
    device = db.query(IotDevice).filter(IotDevice.public_id == payload.device_uid).first()
    if not device or device.status in {"disabled", "quarantined"}:
        raise HTTPException(status_code=401, detail="Invalid device")
    row = (
        db.query(DeviceProvisioningToken)
        .filter(DeviceProvisioningToken.device_id == device.id, DeviceProvisioningToken.used_at.is_(None))
        .order_by(DeviceProvisioningToken.created_at.desc()).first()
    )
    if not row or row.expires_at <= datetime.utcnow() or not secret_matches(payload.provisioning_token, row.token_hash):
        raise HTTPException(status_code=401, detail="Invalid or expired provisioning token")
    permanent = new_secret()
    db.query(DeviceCredential).filter(DeviceCredential.device_id == device.id, DeviceCredential.status == "active").update({"status": "revoked", "revoked_at": datetime.utcnow()})
    credential = DeviceCredential(device_id=device.id, token_hash=hash_secret(permanent), secret_encrypted=protect_secret(permanent))
    db.add(credential)
    device.token_hash = credential.token_hash
    device.secret_encrypted = credential.secret_encrypted
    device.firmware_version = payload.firmware_version
    device.status = "pairing"
    row.used_at = datetime.utcnow()
    db.commit()
    return {
        "device_uid": device.public_id, "device_secret": permanent,
        "topics": _topics(device), "mqtt_client_id": device.public_id,
        "rest_ingest_url": "/iot/ingest",
        "important": "Store this credential in secure device storage; it cannot be shown again.",
    }


def _device_auth_headers(db: Session, authorization: str | None, device_uid: str | None) -> IotDevice:
    if not authorization or not authorization.startswith("Device ") or not device_uid:
        raise HTTPException(status_code=401, detail="Device authentication required")
    return authenticate_device(db, device_uid, authorization[7:])


@router.post("/ingest")
def rest_ingest(
    payload: TelemetryEnvelope, request: Request,
    authorization: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    device = _device_auth_headers(db, authorization, x_device_id)
    return ingest_telemetry(
        db, device, payload, source="rest", remote_ip=request.client.host if request.client else None,
        publish=event_hub.publish,
    )


@router.get("/devices")
def list_devices(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company_id = _company_id(user, db)
    return [_device_payload(db, row) for row in db.query(IotDevice).filter(IotDevice.company_id == company_id).order_by(IotDevice.name).all()]


@mobile_router.get("/devices")
def mobile_devices(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company_id = _company_id(user, db)
    return {"items": [_device_payload(db, row) for row in db.query(IotDevice).filter(IotDevice.company_id == company_id).order_by(IotDevice.name).all()]}


@router.get("/devices/{device_id}")
def get_device(device_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _device_payload(db, device_for_company(db, device_id, _company_id(user, db)))


@router.post("/devices/{device_id}/provision")
def renew_provisioning(device_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    device = device_for_company(db, device_id, _company_id(user, db)); one_time = new_secret()
    row = DeviceProvisioningToken(device_id=device.id, token_hash=hash_secret(one_time), expires_at=datetime.utcnow() + timedelta(minutes=30), created_by=user.id)
    db.add(row); _audit(db, user, "iot.provisioning_token_created", "iot_device", device.id); db.commit()
    return {"outcome": "success", "message": "One-time provisioning token created", "data": {"device_uid": device.public_id, "token": one_time, "expires_at": row.expires_at.isoformat() + "Z", "topics": _topics(device)}}


@router.post("/devices/{device_id}/status")
def update_device_status(device_id: str, payload: DeviceStatusUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    device = device_for_company(db, device_id, _company_id(user, db)); device.status = payload.status
    if payload.status in {"disabled", "quarantined"}:
        db.query(DeviceCredential).filter(DeviceCredential.device_id == device.id, DeviceCredential.status == "active").update({"status": "revoked", "revoked_at": datetime.utcnow()}, synchronize_session=False)
    _audit(db, user, f"iot.device_{payload.status}", "iot_device", device.id, {"reason": payload.reason}); db.commit()
    return {"id": device.id, "status": device.status}


@router.post("/devices/{device_id}/diagnose")
def diagnose_device(device_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    device = device_for_company(db, device_id, _company_id(user, db)); readings = latest_readings(db, device)
    stale = not device.last_seen_at or (datetime.utcnow() - device.last_seen_at).total_seconds() > 120
    return {"outcome": "offline" if stale else "success", "message": "No recent heartbeat" if stale else "Telemetry route and storage are operational", "retryable": stale, "data": {"last_seen_at": device.last_seen_at.isoformat() + "Z" if device.last_seen_at else None, "channels_reporting": len(readings), "status": device.status}}


@router.get("/devices/{device_id}/latest")
def get_latest(device_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    device = device_for_company(db, device_id, _company_id(user, db))
    readings = latest_readings(db, device)
    return {"device_id": device.id, "status": device.status, "at": max((r["at"] for r in readings), default=None), "readings": readings, "label": ", ".join(f"{r['channel']}={r['value']}" for r in readings)}


@router.get("/devices/{device_id}/telemetry")
def telemetry_history(device_id: str, channel: str | None = None, limit: int = 500, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    device = device_for_company(db, device_id, _company_id(user, db))
    q = db.query(TelemetryReading).filter(TelemetryReading.device_id == device.id)
    if channel: q = q.filter(TelemetryReading.channel == channel)
    rows = q.order_by(TelemetryReading.recorded_at.desc()).limit(min(max(limit, 1), 5000)).all()
    return [{"channel": r.channel, "value": r.boolean_value if r.boolean_value is not None else r.numeric_value if r.numeric_value is not None else r.text_value, "unit": r.unit, "quality": r.quality, "at": r.recorded_at.isoformat() + "Z"} for r in reversed(rows)]


@router.get("/devices/{device_id}/telemetry.csv")
def telemetry_csv(device_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    device = device_for_company(db, device_id, _company_id(user, db))
    rows = db.query(TelemetryReading).filter(TelemetryReading.device_id == device.id).order_by(TelemetryReading.recorded_at).limit(100000).all()
    stream = io.StringIO(); writer = csv.writer(stream)
    writer.writerow(["device_uid", "channel", "value", "unit", "quality", "recorded_at", "received_at"])
    for r in rows:
        value = r.boolean_value if r.boolean_value is not None else r.numeric_value if r.numeric_value is not None else r.text_value
        writer.writerow([device.public_id, r.channel, value, r.unit or "", r.quality, r.recorded_at.isoformat() + "Z", r.received_at.isoformat() + "Z"])
    return StreamingResponse(iter([stream.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{device.public_id}-telemetry.csv"'})


@router.get("/devices/{device_id}/aggregates")
def telemetry_aggregates(device_id: str, channel: str | None = None, limit: int = 2000, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    device_for_company(db, device_id, _company_id(user, db))
    query = db.query(TelemetryAggregate).filter(TelemetryAggregate.device_id == device_id)
    if channel: query = query.filter(TelemetryAggregate.channel == channel)
    rows = query.order_by(TelemetryAggregate.bucket_start.desc()).limit(min(max(limit, 1), 5000)).all()
    return [{"channel": row.channel, "bucket_start": row.bucket_start.isoformat() + "Z", "bucket_seconds": row.bucket_seconds, "sample_count": row.sample_count, "min": row.minimum, "max": row.maximum, "avg": row.average, "unit": row.unit} for row in reversed(rows)]


@router.get("/devices/{device_id}/report.pdf")
def device_report_pdf(device_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company_id = _company_id(user, db); device = device_for_company(db, device_id, company_id)
    end = datetime.utcnow(); start = end - timedelta(days=30)
    readings = db.query(TelemetryReading).filter(TelemetryReading.device_id == device.id, TelemetryReading.recorded_at >= start, TelemetryReading.recorded_at <= end).order_by(TelemetryReading.recorded_at).all()
    alerts = db.query(IotAlert).filter(IotAlert.device_id == device.id, IotAlert.opened_at >= start, IotAlert.opened_at <= end).order_by(IotAlert.opened_at).all()
    from app.iot.reports import build_device_pdf
    content = build_device_pdf(device, db.get(Site, device.site_id), db.get(Company, company_id), readings, alerts, start, end)
    return Response(content=content, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{device.public_id}-report.pdf"'})


@router.post("/alert-rules", status_code=201)
def create_alert_rule(payload: AlertRuleCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company_id = _company_id(user, db)
    if payload.device_id: device_for_company(db, payload.device_id, company_id)
    if payload.site_id:
        site = db.get(Site, payload.site_id)
        if not site or site.company_id != company_id: raise HTTPException(status_code=404, detail="Site not found")
    row = IotAlertRule(company_id=company_id, name=payload.name, device_id=payload.device_id, site_id=payload.site_id, channel=payload.channel, operator=payload.operator, threshold=payload.threshold, severity=payload.severity, cooldown_seconds=payload.cooldown_seconds, sustained_seconds=payload.sustained_seconds, notification_channels_json=json.dumps(payload.notification_channels))
    db.add(row); _audit(db, user, "iot.alert_rule_created", "iot_alert_rule", row.id); db.commit(); db.refresh(row)
    return {"id": row.id, **payload.model_dump()}


@router.get("/alerts")
def list_alerts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company_id = _company_id(user, db)
    rows = db.query(IotAlert).filter(IotAlert.company_id == company_id).order_by(IotAlert.opened_at.desc()).limit(500).all()
    return [{"id": r.id, "device_id": r.device_id, "channel": r.channel, "value": r.value, "severity": r.severity, "message": r.message, "status": r.status, "opened_at": r.opened_at.isoformat() + "Z", "acknowledged_at": r.acknowledged_at.isoformat() + "Z" if r.acknowledged_at else None, "assigned_to": r.assigned_to, "resolved_at": r.resolved_at.isoformat() + "Z" if r.resolved_at else None, "closed_at": r.closed_at.isoformat() + "Z" if r.closed_at else None} for r in rows]


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company_id = _company_id(user, db); row = db.get(IotAlert, alert_id)
    if not row or row.company_id != company_id: raise HTTPException(status_code=404, detail="Alert not found")
    if row.status not in {"triggered", "notified"}: raise HTTPException(status_code=409, detail="Alert cannot be acknowledged in its current state")
    row.status = "acknowledged"; row.acknowledged_at = datetime.utcnow(); row.acknowledged_by = user.id
    _audit(db, user, "iot.alert_acknowledged", "iot_alert", row.id); db.commit()
    return {"id": row.id, "status": row.status}


@router.post("/alerts/{alert_id}/assign")
def assign_alert(alert_id: str, payload: AlertAssignment, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company_id = _company_id(user, db); row = db.get(IotAlert, alert_id)
    if not row or row.company_id != company_id: raise HTTPException(status_code=404, detail="Alert not found")
    if row.status not in {"acknowledged", "assigned"}: raise HTTPException(status_code=409, detail="Acknowledge the alert before assignment")
    row.status = "assigned"; row.assigned_at = datetime.utcnow(); row.assigned_to = payload.assignee_id
    _audit(db, user, "iot.alert_assigned", "iot_alert", row.id, {"assigned_to": payload.assignee_id}); db.commit()
    return {"id": row.id, "status": row.status, "assigned_to": row.assigned_to}


@router.post("/alerts/{alert_id}/close")
def close_alert(alert_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company_id = _company_id(user, db); row = db.get(IotAlert, alert_id)
    if not row or row.company_id != company_id: raise HTTPException(status_code=404, detail="Alert not found")
    if row.status not in {"resolved", "acknowledged", "assigned"}: raise HTTPException(status_code=409, detail="Alert cannot be closed in its current state")
    row.status = "closed"; row.closed_at = datetime.utcnow()
    _audit(db, user, "iot.alert_closed", "iot_alert", row.id); db.commit()
    return {"id": row.id, "status": row.status}


def _can_command(db: Session, user: User, company_id: str) -> bool:
    if user.role == "admin": return True
    membership = db.query(CompanyUser).filter(CompanyUser.company_id == company_id, CompanyUser.email == user.email, CompanyUser.is_active.is_(True)).first()
    return bool(membership and membership.role in {"owner", "admin", "manager", "operator"})


@router.post("/devices/{device_id}/commands", status_code=202)
def create_command(device_id: str, payload: CommandCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company_id = _company_id(user, db); device = device_for_company(db, device_id, company_id)
    if not _can_command(db, user, company_id): raise HTTPException(status_code=403, detail="Operator permission required")
    if not payload.confirmed: raise HTTPException(status_code=409, detail="Explicit confirmation is required")
    capabilities = set(json_value(device.capabilities_json, []))
    if f"command:{payload.name}" not in capabilities: raise HTTPException(status_code=409, detail="Command is not enabled for this device")
    if payload.name in OUTPUT_COMMANDS:
        if not device.allow_remote_control: raise HTTPException(status_code=409, detail="Remote output control is disabled")
        latest = {r["channel"]: r["value"] for r in latest_readings(db, device)}
        if latest.get("safety_ok") is not True: raise HTTPException(status_code=409, detail="Local safety interlock is not confirmed")
    command = IotCommand(company_id=company_id, device_id=device.id, requested_by=user.id, correlation_id=str(uuid.uuid4()), name=payload.name, arguments_json=json.dumps(payload.arguments), reason=payload.reason, fail_safe_state=payload.fail_safe_state, expires_at=datetime.utcnow() + timedelta(seconds=300))
    db.add(command); _audit(db, user, "iot.command_queued", "iot_command", command.id, {"name": command.name, "reason": command.reason}); db.commit(); db.refresh(command)
    from app.iot.mqtt import mqtt_bridge
    from app.iot.service import active_credential
    from app.iot.security import reveal_secret
    credential = active_credential(db, device)
    command_payload = {
        "arguments": payload.arguments, "correlation_id": command.correlation_id,
        "expires_at": command.expires_at.isoformat() + "Z", "id": command.id,
        "name": command.name, "nonce": uuid.uuid4().hex, "reason": command.reason,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    signature = sign_mqtt_payload(command_payload, reveal_secret(credential.secret_encrypted if credential else device.secret_encrypted))
    mqtt_bridge.publish_command(_topics(device)["commands"], {"payload": command_payload, "signature": signature})
    event_hub.publish(device.id, {"type": "command.queued", "command_id": command.id, "name": command.name})
    return {"outcome": "pending", "message": "Command queued for device acknowledgement", "data": {"command_id": command.id, "correlation_id": command.correlation_id, "expires_at": command.expires_at.isoformat() + "Z"}}


@router.get("/devices/{device_id}/commands")
def command_history(device_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    device = device_for_company(db, device_id, _company_id(user, db)); rows = db.query(IotCommand).filter(IotCommand.device_id == device.id).order_by(IotCommand.created_at.desc()).limit(200).all()
    return [{"id": row.id, "correlation_id": row.correlation_id, "name": row.name, "status": row.status, "reason": row.reason, "fail_safe_state": row.fail_safe_state, "created_at": row.created_at.isoformat() + "Z", "acknowledged_at": row.acknowledged_at.isoformat() + "Z" if row.acknowledged_at else None, "result": json_value(row.result_json, {})} for row in rows]


@router.get("/device/commands")
def poll_device_commands(authorization: str | None = Header(default=None), x_device_id: str | None = Header(default=None), db: Session = Depends(get_db)):
    device = _device_auth_headers(db, authorization, x_device_id); now = datetime.utcnow()
    db.query(IotCommand).filter(IotCommand.device_id == device.id, IotCommand.status.in_(["queued", "delivered"]), IotCommand.expires_at <= now).update({"status": "timed_out"}, synchronize_session=False)
    rows = db.query(IotCommand).filter(IotCommand.device_id == device.id, IotCommand.status == "queued", IotCommand.expires_at > now).order_by(IotCommand.created_at).limit(20).all()
    result = []
    for row in rows:
        row.status = "delivered"; row.delivered_at = now
        result.append({"id": row.id, "correlation_id": row.correlation_id, "name": row.name, "arguments": json_value(row.arguments_json, {}), "reason": row.reason, "fail_safe_state": row.fail_safe_state, "expires_at": row.expires_at.isoformat() + "Z"})
    db.commit(); return {"items": result}


@router.post("/device/command-results")
def device_command_result(payload: CommandResult, authorization: str | None = Header(default=None), x_device_id: str | None = Header(default=None), db: Session = Depends(get_db)):
    device = _device_auth_headers(db, authorization, x_device_id); command = db.get(IotCommand, payload.command_id)
    if not command or command.device_id != device.id: raise HTTPException(status_code=404, detail="Command not found")
    command.status = payload.status; command.acknowledged_at = datetime.utcnow(); command.result_json = json.dumps({"actual_state": payload.actual_state, "message": payload.message})
    db.commit(); event_hub.publish(device.id, {"type": "command.result", "command_id": command.id, "status": command.status, "actual_state": payload.actual_state})
    return {"accepted": True}


@router.post("/devices/{device_id}/commissioning", status_code=201)
def commission_device(device_id: str, payload: CommissioningCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company_id = _company_id(user, db); device = device_for_company(db, device_id, company_id)
    if payload.result == "passed" and (not payload.checklist or not all(payload.checklist.values())): raise HTTPException(status_code=422, detail="Every commissioning check must pass")
    row = CommissioningRecord(company_id=company_id, device_id=device.id, technician_id=user.id, checklist_json=json.dumps(payload.checklist), result=payload.result, notes=payload.notes)
    db.add(row); device.status = "online" if payload.result == "passed" and device.last_seen_at else "commissioned"; _audit(db, user, "iot.device_commissioned", "iot_device", device.id, {"result": payload.result}); db.commit(); db.refresh(row)
    return {"id": row.id, "result": row.result, "commissioned_at": row.commissioned_at.isoformat() + "Z"}


@router.post("/channels/{channel_id}/calibrations", status_code=201)
def calibrate(channel_id: str, payload: CalibrationCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company_id = _company_id(user, db); channel = db.get(SensorChannel, channel_id)
    if not channel: raise HTTPException(status_code=404, detail="Channel not found")
    device_for_company(db, channel.device_id, company_id)
    row = CalibrationRecord(company_id=company_id, channel_id=channel.id, calibrated_by=user.id, **payload.model_dump())
    db.add(row); _audit(db, user, "iot.channel_calibrated", "sensor_channel", channel.id); db.commit(); db.refresh(row)
    return {"id": row.id, "calibrated_at": row.calibrated_at.isoformat() + "Z"}


@router.get("/devices/{device_id}/events")
async def device_events(device_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    device_for_company(db, device_id, _company_id(user, db)); queue = event_hub.subscribe(device_id)
    async def stream():
        try:
            yield "event: ready\ndata: {}\n\n"
            while True:
                try: event = await asyncio.wait_for(queue.get(), timeout=20)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"; continue
                yield f"event: {event.get('type', 'message')}\ndata: {json.dumps(event, default=str)}\n\n"
        finally: event_hub.unsubscribe(device_id, queue)
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.websocket("/ws")
async def websocket_events(websocket: WebSocket):
    await websocket.accept(); queue = None; device_id = None
    try:
        auth = await asyncio.wait_for(websocket.receive_json(), timeout=10)
        claims = verify_access_token(str(auth.get("token") or "")); user_id = claims.get("uid"); device_id = str(auth.get("device_id") or "")
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            user = db.get(User, user_id); company_id = _company_id(user, db) if user else None
            device_for_company(db, device_id, company_id)
        finally: db.close()
        queue = event_hub.subscribe(device_id); await websocket.send_json({"type": "ready", "device_id": device_id})
        while True:
            try: event = await asyncio.wait_for(queue.get(), timeout=20); await websocket.send_json(event)
            except asyncio.TimeoutError: await websocket.send_json({"type": "keepalive"})
    except (WebSocketDisconnect, asyncio.TimeoutError): pass
    except Exception: await websocket.close(code=4401)
    finally:
        if queue is not None and device_id: event_hub.unsubscribe(device_id, queue)
