"""Executable MQTT network smoke test for the local broker and ingestion bridge."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
import uuid
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import paho.mqtt.client as mqtt

from app.config import settings
import app.database as database
from app.iot.mqtt import mqtt_bridge
from app.iot.security import hash_secret, protect_secret, sign_mqtt_payload
from app.models import Company, DeviceCredential, IotDevice, SensorChannel, Site, TelemetryReading


async def main():
    fd, db_path = tempfile.mkstemp(prefix="geovision-mqtt-smoke-", suffix=".db"); os.close(fd)
    try:
        database.init_db_engine(f"sqlite:///{db_path}"); database.Base.metadata.create_all(bind=database.engine)
        db = database.SessionLocal(); secret = "ephemeral-smoke-secret-" + uuid.uuid4().hex
        company = Company(name="MQTT Smoke", email=f"mqtt-{uuid.uuid4().hex[:8]}@example.com"); db.add(company); db.flush()
        site = Site(company_id=company.id, name="MQTT Lab", country="Angola"); db.add(site); db.flush()
        device = IotDevice(public_id="gv-smoke-" + uuid.uuid4().hex[:8], company_id=company.id, site_id=site.id, name="MQTT Smoke Sensor", device_type="multi_sensor", transport="mqtt", token_hash=hash_secret(secret), secret_encrypted=protect_secret(secret))
        db.add(device); db.flush(); db.add(DeviceCredential(device_id=device.id, token_hash=hash_secret(secret), secret_encrypted=protect_secret(secret)))
        db.add(SensorChannel(device_id=device.id, key="temperature", label="Temperature", measurement_type="temperature", unit="Cel", data_type="number")); db.commit()

        settings.mqtt_enabled = True; settings.mqtt_host = os.getenv("GV_MQTT_HOST", "127.0.0.1"); settings.mqtt_port = int(os.getenv("GV_MQTT_PORT", "1884")); settings.mqtt_tls = False
        mqtt_bridge.start(asyncio.get_running_loop())
        deadline = time.time() + 5
        while (not mqtt_bridge.client or not mqtt_bridge.client.is_connected()) and time.time() < deadline: await asyncio.sleep(.1)
        assert mqtt_bridge.client and mqtt_bridge.client.is_connected(), "bridge did not connect to broker"

        payload = {"device_uid": device.public_id, "message_id": "smoke-" + uuid.uuid4().hex, "nonce": uuid.uuid4().hex, "timestamp": datetime.now(timezone.utc).isoformat(), "measurements": {"temperature": 27.4}, "metadata": {"smoke_test": True}}
        payload["signature"] = sign_mqtt_payload(payload, secret)
        publisher = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="geovision-smoke-publisher"); publisher.connect(settings.mqtt_host, settings.mqtt_port, 30); publisher.loop_start()
        topic = f"geovision/v1/{company.id}/{site.id}/{device.public_id}/telemetry"; publisher.publish(topic, json.dumps(payload), qos=1).wait_for_publish(5)
        deadline = time.time() + 8; stored = None
        while time.time() < deadline:
            db.expire_all(); stored = db.query(TelemetryReading).filter(TelemetryReading.device_id == device.id, TelemetryReading.message_id == payload["message_id"]).first()
            if stored: break
            await asyncio.sleep(.2)
        assert stored and stored.numeric_value == 27.4, "broker message was not stored"
        print(json.dumps({"mqtt_network": "pass", "topic_pattern": "geovision/v1/{tenant}/{site}/{device}/telemetry", "stored_channel": stored.channel, "stored_value": stored.numeric_value, "device_status": db.get(IotDevice, device.id).status}))
        publisher.disconnect(); publisher.loop_stop(); db.close(); mqtt_bridge.stop()
    finally:
        Path(db_path).unlink(missing_ok=True)


if __name__ == "__main__": asyncio.run(main())
