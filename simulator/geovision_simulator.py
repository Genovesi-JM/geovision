#!/usr/bin/env python3
"""GeoVision field-device simulator using the production MQTT/REST envelopes."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import random
import ssl
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests


def load_config(path: str) -> dict:
    candidate = Path(path)
    if not candidate.exists():
        raise SystemExit(f"Simulator config not found: {candidate}. Run the IoT seed/provisioning step first.")
    return json.loads(candidate.read_text())


def canonical(payload: dict) -> bytes:
    return json.dumps({k: v for k, v in payload.items() if k != "signature"}, sort_keys=True, separators=(",", ":")).encode()


def signed(payload: dict, secret: str) -> dict:
    payload["signature"] = hmac.new(secret.encode(), canonical(payload), hashlib.sha256).hexdigest()
    return payload


class Simulator:
    def __init__(self, config: dict, transport: str):
        self.config = config; self.transport = transport
        self.sequence = 0; self.buffer_path = Path(os.getenv("GV_SIM_BUFFER", "/tmp/geovision-simulator-buffer.jsonl"))
        self.values = {"temperature": 24.0, "humidity": 58.0, "water_leak": False, "tank_level": 72.0, "door_open": False, "power": 420.0, "battery": 92.0, "signal": 84.0, "safety_ok": True}
        self.client = None
        # Irrigation demo physics: soil dries out, wets when the valve is open.
        self.valve_open = False; self.soil = 38.0; self.irr_tank = 88.0

    def connect(self):
        if self.transport != "mqtt": return
        import paho.mqtt.client as mqtt
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.config["device_uid"])
        host = os.getenv("GV_MQTT_HOST", "localhost"); port = int(os.getenv("GV_MQTT_PORT", "8883"))
        if os.getenv("GV_MQTT_TLS", "true").lower() == "true":
            ca = os.getenv("GV_MQTT_CA", str(Path(__file__).resolve().parents[1] / ".iot/certs/ca.crt"))
            self.client.tls_set(ca_certs=ca, cert_reqs=ssl.CERT_REQUIRED)
        self.client.will_set(self.config["topics"]["state"], json.dumps(self.envelope({"safety_ok": True}, extra={"state": "offline"})), qos=1, retain=True)
        self.client.connect(host, port, 60); self.client.loop_start()
        self.client.publish(self.config["topics"]["state"], json.dumps(self.envelope({"safety_ok": True}, extra={"state": "online"})), qos=1, retain=True)

    def envelope(self, measurements: dict, *, timestamp=None, message_id=None, nonce=None, extra=None):
        self.sequence += 1
        payload = {"device_uid": self.config["device_uid"], "message_id": message_id or f"sim-{self.sequence}-{uuid.uuid4().hex[:8]}", "nonce": nonce or uuid.uuid4().hex, "timestamp": timestamp or datetime.now(timezone.utc).isoformat(), "measurements": measurements, "metadata": {"simulator": True, "sequence": self.sequence}}
        payload.update(extra or {})
        return signed(payload, self.config["device_secret"])

    def publish(self, measurements: dict, **kwargs):
        payload = self.envelope(measurements, **kwargs)
        try:
            if self.transport == "mqtt":
                info = self.client.publish(self.config["topics"]["telemetry"], json.dumps(payload), qos=1); info.wait_for_publish(5)
            else:
                rest_payload = {k: payload[k] for k in ("message_id", "timestamp", "measurements", "metadata")}
                response = requests.post(self.config.get("rest_url", "http://127.0.0.1:8010/iot/ingest"), headers={"Authorization": f"Device {self.config['device_secret']}", "X-Device-ID": self.config["device_uid"]}, json=rest_payload, timeout=10)
                response.raise_for_status()
            print(json.dumps({"sent": payload["message_id"], "values": measurements}, default=str), flush=True)
        except Exception as exc:
            with self.buffer_path.open("a") as handle: handle.write(json.dumps(payload) + "\n")
            print(f"offline-buffered: {exc}", file=sys.stderr, flush=True)
        return payload

    def poll_commands(self):
        """REST command poll: apply valve open/close and confirm the result —
        this is what lets the backend automation actually act on the device."""
        if self.transport != "rest":
            return
        base = self.config.get("rest_url", "").replace("/iot/ingest", "")
        headers = {"Authorization": f"Device {self.config['device_secret']}", "X-Device-ID": self.config["device_uid"]}
        try:
            response = requests.get(base + "/iot/device/commands", headers=headers, timeout=10)
            response.raise_for_status()
            items = response.json().get("items", [])
        except Exception as exc:
            print(f"command-poll failed: {exc}", file=sys.stderr, flush=True)
            return
        for cmd in items:
            name = cmd.get("name")
            if name == "low_voltage_valve_open":
                self.valve_open = True
            elif name == "low_voltage_valve_close":
                self.valve_open = False
            try:
                requests.post(base + "/iot/device/command-results", headers=headers,
                              json={"command_id": cmd["id"], "status": "completed", "actual_state": {"valve_open": self.valve_open}, "message": "simulator applied"}, timeout=10)
            except Exception:
                pass
            print(json.dumps({"command": name, "valve_open": self.valve_open}), flush=True)

    def irrigation_step(self):
        """One frame of the detect→decide→act→confirm loop: poll for a valve
        command from the backend, then model the soil responding."""
        self.poll_commands()
        if self.valve_open:
            self.soil = min(100.0, self.soil + 6.0); self.irr_tank = max(0.0, self.irr_tank - 2.0); flow = 12.0
        else:
            self.soil = max(0.0, self.soil - 4.0); flow = 0.0
        values = {"battery": 96.0, "flow": flow, "safety_ok": True, "signal": 82.0,
                  "soil_moisture": round(self.soil, 1), "soil_temperature": 22.0,
                  "tank_level": round(self.irr_tank, 1), "valve_open": self.valve_open}
        return self.publish(values)

    def scenario(self, name: str):
        values = dict(self.values)
        if name == "normal": pass
        elif name == "warning": values.update(temperature=31.5, battery=24)
        elif name == "critical": values.update(temperature=42.0, water_leak=True, tank_level=8, power=3900)
        elif name == "leak": values["water_leak"] = True
        elif name == "low_tank": values["tank_level"] = 7
        elif name == "door_open": values["door_open"] = True
        elif name == "high_load": values["power"] = 4500
        elif name == "low_battery": values["battery"] = 8
        elif name == "weak_signal": values["signal"] = 9
        elif name == "sensor_failure": values["temperature"] = {"value": 0, "unit": "Cel", "quality": "sensor_error"}
        elif name == "gradual": values["temperature"] += self.sequence * 0.8
        elif name == "delayed": return self.publish(values, timestamp=(datetime.now(timezone.utc) - timedelta(hours=2)).isoformat())
        elif name == "duplicate":
            message_id = f"duplicate-{uuid.uuid4().hex[:8]}"; self.publish(values, message_id=message_id); return self.publish(values, message_id=message_id)
        values["temperature"] = values["temperature"] if isinstance(values["temperature"], dict) else round(float(values["temperature"]) + random.uniform(-0.15, .15), 2)
        return self.publish(values)

    def interactive(self):
        print("Commands: normal warning critical leak low_tank door_open high_load low_battery weak_signal sensor_failure duplicate delayed set KEY VALUE quit")
        while True:
            try: command = input("geovision-sim> ").strip()
            except EOFError: return
            if command in {"quit", "exit"}: return
            if command.startswith("set "):
                _, key, raw = command.split(maxsplit=2); self.values[key] = raw.lower() == "true" if raw.lower() in {"true", "false"} else float(raw); self.publish(dict(self.values))
            elif command: self.scenario(command)


def main():
    parser = argparse.ArgumentParser(); sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run"); run.add_argument("--config", default=os.getenv("GV_SIM_CONFIG", ".iot/simulator.json")); run.add_argument("--transport", choices=["mqtt", "rest"], default=os.getenv("GV_SIM_TRANSPORT", "mqtt")); run.add_argument("--scenario", default="demo"); run.add_argument("--interval", type=float, default=5); run.add_argument("--count", type=int, default=0); run.add_argument("--interactive", action="store_true")
    args = parser.parse_args(); sim = Simulator(load_config(args.config), args.transport); sim.connect()
    if args.interactive: sim.interactive(); return
    if args.scenario == "irrigation":
        count = 0
        while args.count == 0 or count < args.count:
            sim.irrigation_step(); count += 1; time.sleep(args.interval)
        return
    scenarios = ["normal", "normal", "warning", "critical", "normal"] if args.scenario == "demo" else [args.scenario]
    count = 0
    while args.count == 0 or count < args.count:
        sim.scenario(scenarios[count % len(scenarios)]); count += 1; time.sleep(args.interval)


if __name__ == "__main__": main()
