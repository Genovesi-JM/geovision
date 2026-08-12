from __future__ import annotations

import asyncio
import json
import logging
import ssl
from datetime import datetime

from app.config import settings
from app.iot.events import event_hub
from app.iot.schemas import MqttEnvelope, TelemetryEnvelope
from app.iot.security import parse_utc, reveal_secret, timestamp_is_fresh, verify_mqtt_signature
from app.iot.service import active_credential, ingest_telemetry
from app.models import IotCommand, IotDevice, IotMessageNonce
from app.time_utils import utc_now

logger = logging.getLogger(__name__)


class MqttBridge:
    def __init__(self) -> None:
        self.client = None
        self.loop: asyncio.AbstractEventLoop | None = None

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        if not settings.mqtt_enabled or self.client is not None:
            return
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            logger.error("MQTT_ENABLED=true but paho-mqtt is not installed")
            return
        self.loop = loop
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=settings.mqtt_client_id, clean_session=True)
        if settings.mqtt_username:
            self.client.username_pw_set(settings.mqtt_username, settings.mqtt_password)
        if settings.mqtt_tls:
            self.client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        self.client.connect_async(settings.mqtt_host, settings.mqtt_port, keepalive=60)
        self.client.loop_start()

    def stop(self) -> None:
        if self.client:
            try:
                self.client.disconnect(); self.client.loop_stop()
            finally:
                self.client = None

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code == 0:
            client.subscribe(f"{settings.mqtt_topic_prefix}/v1/+/+/+/telemetry", qos=1)
            client.subscribe(f"{settings.mqtt_topic_prefix}/v1/+/+/+/state", qos=1)
            client.subscribe(f"{settings.mqtt_topic_prefix}/v1/+/+/+/command-results", qos=1)
            logger.info("MQTT bridge connected and subscribed")
        else:
            logger.error("MQTT connection rejected: %s", reason_code)

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties) -> None:
        if reason_code:
            logger.warning("MQTT bridge disconnected: %s", reason_code)

    def _on_message(self, client, userdata, message) -> None:
        try:
            parts = message.topic.split("/")
            if len(parts) != 6 or parts[0] != settings.mqtt_topic_prefix or parts[1] != "v1":
                logger.warning("Rejected malformed MQTT topic: %s", message.topic); return
            _, _, tenant_id, site_id, device_uid, kind = parts
            payload = json.loads(message.payload.decode("utf-8"))
            self._process(tenant_id, site_id, device_uid, kind, payload)
        except Exception as exc:
            logger.warning("Rejected MQTT message on %s: %s", message.topic, exc)

    def _process(self, tenant_id: str, site_id: str, device_uid: str, kind: str, payload: dict) -> None:
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            device = db.query(IotDevice).filter(IotDevice.public_id == device_uid).first()
            if not device or device.company_id != tenant_id or device.site_id != site_id or device.status in {"disabled", "quarantined"}:
                raise ValueError("unknown or mismatched device")
            credential = active_credential(db, device)
            protected = credential.secret_encrypted if credential else device.secret_encrypted
            if not verify_mqtt_signature(payload, reveal_secret(protected)):
                raise ValueError("invalid signature")
            nonce = str(payload.get("nonce") or "")
            if len(nonce) < 8 or db.query(IotMessageNonce).filter(IotMessageNonce.device_id == device.id, IotMessageNonce.nonce == nonce).first():
                raise ValueError("invalid or replayed nonce")
            timestamp = parse_utc(str(payload.get("timestamp") or ""))
            if not timestamp_is_fresh(timestamp) and kind != "state": raise ValueError("stale message")
            db.add(IotMessageNonce(device_id=device.id, nonce=nonce))
            if kind == "telemetry":
                signed = MqttEnvelope.model_validate({**payload, "device_uid": payload.get("device_uid", device_uid)})
                envelope = TelemetryEnvelope(message_id=signed.message_id, timestamp=signed.timestamp, measurements=signed.measurements, metadata=signed.metadata)
                publish = (lambda device_id, event: self.loop.call_soon_threadsafe(event_hub.publish, device_id, event)) if self.loop else None
                ingest_telemetry(db, device, envelope, source="mqtt", publish=publish)
            elif kind == "state":
                state = str(payload.get("state") or "")
                if state not in {"online", "offline", "maintenance"}: raise ValueError("invalid state")
                device.status = state; device.last_seen_at = utc_now(); db.commit()
                if self.loop: self.loop.call_soon_threadsafe(event_hub.publish, device.id, {"type": "device.state", "status": state})
            elif kind == "command-results":
                command = db.get(IotCommand, str(payload.get("command_id") or ""))
                result_status = str(payload.get("status") or "")
                if not command or command.device_id != device.id or result_status not in {"acknowledged", "completed", "failed", "rejected", "timed_out"}:
                    raise ValueError("invalid command result")
                command.status = result_status; command.acknowledged_at = utc_now()
                command.result_json = json.dumps({"actual_state": payload.get("actual_state") or {}, "message": payload.get("message")})
                db.commit()
                if self.loop: self.loop.call_soon_threadsafe(event_hub.publish, device.id, {"type": "command.result", "command_id": command.id, "status": command.status, "actual_state": payload.get("actual_state") or {}})
        finally:
            db.close()

    def publish_command(self, topic: str, payload: dict) -> None:
        if self.client:
            self.client.publish(topic, json.dumps(payload, separators=(",", ":")), qos=1, retain=False)


mqtt_bridge = MqttBridge()
