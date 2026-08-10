"""Idempotently create the local IoT demonstration tenant and simulator."""
from __future__ import annotations

import json
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal, init_db_engine
from app.iot import kits as kit_catalog
from app.iot.security import hash_secret, new_secret, protect_secret, reveal_secret
from app.models import Company, CompanyEntitlement, CompanyUser, DeviceCredential, IotAlertRule, IotDevice, SensorChannel, Site, User
from app.utils import hash_password


def main():
    init_db_engine(); db = SessionLocal()
    try:
        email = "iot.demo@geovisionops.com"; password = secrets.token_urlsafe(14)
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(email=email, password_hash=hash_password(password), role="cliente", is_active=True); db.add(user); db.flush()
        else:
            user.password_hash = hash_password(password)
        company = db.query(Company).filter(Company.email == email).first()
        if not company:
            company = Company(name="GeoVision IoT Demonstration", email=email, status="active", subscription_plan="demo"); db.add(company); db.flush()
        member = db.query(CompanyUser).filter(CompanyUser.company_id == company.id, CompanyUser.email == email).first()
        if not member: db.add(CompanyUser(company_id=company.id, email=email, name="IoT Demo", role="owner", is_active=True))
        site = db.query(Site).filter(Site.company_id == company.id, Site.name == "Live Sensor Lab").first()
        if not site:
            site = Site(company_id=company.id, name="Live Sensor Lab", country="Angola", province="Luanda", municipality="Talatona", sector="infrastructure", latitude=-8.918, longitude=13.184); db.add(site); db.flush()
        device = db.query(IotDevice).filter(IotDevice.public_id == "gv-demo-001").first()
        if not device:
            secret = new_secret(); protected = protect_secret(secret)
            device = IotDevice(public_id="gv-demo-001", company_id=company.id, site_id=site.id, name="GeoVision Multi-Sensor Demonstrator", device_type="multi_sensor", transport="mqtt", status="online", token_hash=hash_secret(secret), secret_encrypted=protected, capabilities_json=json.dumps(["command:beacon_on", "command:beacon_off", "command:buzzer_on", "command:buzzer_off", "command:relay_on", "command:relay_off", "command:request_diagnostics"]), allow_remote_control=True, created_by=user.id)
            db.add(device); db.flush(); db.add(DeviceCredential(device_id=device.id, token_hash=hash_secret(secret), secret_encrypted=protected))
            definitions = [
                ("temperature", "Temperature", "temperature", "Cel", "number"), ("humidity", "Humidity", "humidity", "%RH", "number"),
                ("water_leak", "Water leak", "water_leak", None, "boolean"), ("tank_level", "Tank level", "tank_level", "%", "number"),
                ("door_open", "Door", "door_contact", None, "boolean"), ("power", "Power", "power", "W", "number"),
                ("battery", "Battery", "battery", "%", "number"), ("signal", "Signal", "signal", "%", "number"),
                ("safety_ok", "Local safety interlock", "generic", None, "boolean"),
            ]
            for key, label, kind, unit, dtype in definitions: db.add(SensorChannel(device_id=device.id, key=key, label=label, measurement_type=kind, unit=unit, data_type=dtype))
            db.add(IotAlertRule(company_id=company.id, device_id=device.id, name="Critical demo temperature", channel="temperature", operator="gt", threshold=35, severity="critical", notification_channels_json='["log"]'))
        else:
            credential = db.query(DeviceCredential).filter(DeviceCredential.device_id == device.id, DeviceCredential.status == "active").order_by(DeviceCredential.issued_at.desc()).first()
            secret = reveal_secret(credential.secret_encrypted if credential else device.secret_encrypted)
        entitlement = db.query(CompanyEntitlement).filter(CompanyEntitlement.company_id == company.id).first()
        if not entitlement:
            from datetime import datetime, timedelta
            db.add(CompanyEntitlement(company_id=company.id, tier="growth", kit="Multi-Sensor Monitor", sensor_allowance=25, valid_until=datetime.utcnow() + timedelta(days=180), notes="Prepaid demonstration window."))
        # SoilControl device for the cause-and-effect irrigation demo.
        soil = db.query(IotDevice).filter(IotDevice.public_id == "gv-demo-soil").first()
        if not soil:
            kit = kit_catalog.get_kit("soil_control")
            soil_secret = new_secret(); soil_protected = protect_secret(soil_secret)
            soil = IotDevice(public_id="gv-demo-soil", company_id=company.id, site_id=site.id, name="SoilControl Demo", device_type=kit["device_type"], transport="mqtt", status="online", token_hash=hash_secret(soil_secret), secret_encrypted=soil_protected, capabilities_json=json.dumps([f"command:{c}" for c in kit["capabilities"]]), allow_remote_control=kit["allow_remote_control"], created_by=user.id)
            db.add(soil); db.flush(); db.add(DeviceCredential(device_id=soil.id, token_hash=hash_secret(soil_secret), secret_encrypted=soil_protected))
            for ch in kit["channels"]:
                db.add(SensorChannel(device_id=soil.id, key=ch["key"], label=ch["label"], measurement_type=ch["measurement_type"], unit=ch.get("unit"), data_type=ch["data_type"], minimum=ch.get("minimum"), maximum=ch.get("maximum")))
            for rule in kit["alert_rules"]:
                db.add(IotAlertRule(company_id=company.id, device_id=soil.id, name=rule["name"], channel=rule["channel"], operator=rule["operator"], threshold=rule["threshold"], severity=rule["severity"], notification_channels_json='["log"]'))
        else:
            soil_cred = db.query(DeviceCredential).filter(DeviceCredential.device_id == soil.id, DeviceCredential.status == "active").order_by(DeviceCredential.issued_at.desc()).first()
            soil_secret = reveal_secret(soil_cred.secret_encrypted if soil_cred else soil.secret_encrypted)
        db.commit()
        base = f"geovision/v1/{company.id}/{site.id}/{device.public_id}"
        runtime = Path(os.getenv("GV_RUNTIME_DIR", "/runtime")); runtime.mkdir(parents=True, exist_ok=True)
        rest_url = os.getenv("GV_REST_URL", "http://backend:8010/iot/ingest")
        (runtime / "simulator.json").write_text(json.dumps({"device_uid": device.public_id, "device_secret": secret, "topics": {name: f"{base}/{name}" for name in ("telemetry", "state", "events", "commands", "command-results", "configuration")}, "rest_url": rest_url}, indent=2))
        soil_base = f"geovision/v1/{company.id}/{site.id}/{soil.public_id}"
        (runtime / "simulator-soil.json").write_text(json.dumps({"device_uid": soil.public_id, "device_secret": soil_secret, "topics": {name: f"{soil_base}/{name}" for name in ("telemetry", "state", "events", "commands", "command-results", "configuration")}, "rest_url": rest_url}, indent=2))
        (runtime / "demo-login.txt").write_text(f"URL=http://127.0.0.1:8001/login.html\nEMAIL={email}\nPASSWORD={password}\n")
        print(f"Demo ready: device={device.public_id}; login details saved to /runtime/demo-login.txt")
    finally: db.close()


if __name__ == "__main__": main()
