#!/usr/bin/env python3
"""Reference Raspberry Pi FieldBox queue for GeoVision telemetry v1.

This intentionally uses only Python's standard library. It can sit between
ESP32 sensor nodes and either the GeoVision REST boundary or an IoT Hub-facing
forwarder. Measurements and fail-safe local actions keep working while the WAN
is unavailable; forwarding resumes in sequence order after reconnection.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Callable, Mapping
from urllib import request
import uuid


PROTOCOL_VERSION = "geovision.telemetry.v1"
SAFE_COMMANDS = frozenset(
    {
        "beacon_off",
        "buzzer_off",
        "demo_fan_off",
        "low_voltage_valve_close",
        "relay_off",
        "request_diagnostics",
        "set_reporting_interval",
    }
)


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class DurableQueue:
    """Bounded SQLite queue with persistent stream and sequence state."""

    def __init__(self, path: Path, *, max_items: int = 50_000):
        self.path = path
        self.max_items = max_items
        self.connection = sqlite3.connect(path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS telemetry_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT NOT NULL UNIQUE,
                queued_at TEXT NOT NULL,
                envelope_json TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self.connection.commit()

    def _state(self, key: str, fallback: str) -> str:
        row = self.connection.execute(
            "SELECT value FROM state WHERE key = ?", (key,)
        ).fetchone()
        if row:
            return str(row[0])
        self.connection.execute(
            "INSERT INTO state (key, value) VALUES (?, ?)", (key, fallback)
        )
        self.connection.commit()
        return fallback

    @property
    def stream_id(self) -> str:
        return self._state("stream_id", f"fieldbox-{uuid.uuid4().hex[:16]}")

    def next_sequence(self) -> int:
        with self.connection:
            current = int(self._state("sequence", "-1")) + 1
            self.connection.execute(
                "UPDATE state SET value = ? WHERE key = 'sequence'", (str(current),)
            )
        return current

    def enqueue(self, envelope: Mapping[str, object]) -> None:
        queued_at = utc_iso()
        stored = dict(envelope)
        stored["replayed_from_edge"] = True
        stored["queued_at"] = queued_at
        with self.connection:
            self.connection.execute(
                """
                INSERT OR IGNORE INTO telemetry_queue
                    (message_id, queued_at, envelope_json)
                VALUES (?, ?, ?)
                """,
                (
                    str(stored["message_id"]),
                    queued_at,
                    json.dumps(stored, separators=(",", ":"), sort_keys=True),
                ),
            )
            excess = self.connection.execute(
                """
                SELECT CASE WHEN COUNT(*) > ? THEN COUNT(*) - ? ELSE 0 END
                  FROM telemetry_queue
                """,
                (self.max_items, self.max_items),
            ).fetchone()[0]
            if excess:
                self.connection.execute(
                    """
                    DELETE FROM telemetry_queue
                     WHERE id IN (
                         SELECT id FROM telemetry_queue ORDER BY id LIMIT ?
                     )
                    """,
                    (int(excess),),
                )

    def pending(self, limit: int = 100) -> list[tuple[int, dict[str, object]]]:
        rows = self.connection.execute(
            "SELECT id, envelope_json FROM telemetry_queue ORDER BY id LIMIT ?",
            (limit,),
        ).fetchall()
        return [(int(row[0]), json.loads(row[1])) for row in rows]

    def delivered(self, row_id: int) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM telemetry_queue WHERE id = ?", (row_id,))

    def failed(self, row_id: int) -> None:
        with self.connection:
            self.connection.execute(
                "UPDATE telemetry_queue SET attempts = attempts + 1 WHERE id = ?",
                (row_id,),
            )

    def count(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM telemetry_queue").fetchone()[0])


@dataclass(frozen=True)
class LocalAction:
    name: str
    reason: str


class SafeLocalRules:
    """Fail-safe rules may de-energize outputs; they never open/energize one."""

    def evaluate(self, measurements: Mapping[str, object]) -> tuple[LocalAction, ...]:
        actions: list[LocalAction] = []
        if measurements.get("water_leak") is True:
            actions.append(LocalAction("low_voltage_valve_close", "local leak interlock"))
        tank = measurements.get("tank_level")
        if isinstance(tank, (int, float)) and not isinstance(tank, bool) and tank < 3:
            actions.append(LocalAction("low_voltage_valve_close", "local empty-tank interlock"))
        return tuple(actions)

    def command_result(self, command: Mapping[str, object]) -> dict[str, object]:
        name = str(command.get("name") or "")
        accepted = name in SAFE_COMMANDS
        return {
            "command_id": str(command.get("id") or ""),
            "status": "acknowledged" if accepted else "rejected",
            "actual_state": {},
            "message": "safe command accepted" if accepted else "unsafe command disabled by default",
        }


class FieldBox:
    def __init__(
        self,
        queue: DurableQueue,
        *,
        firmware_version: str,
        local_action: Callable[[LocalAction], None] | None = None,
    ):
        self.queue = queue
        self.firmware_version = firmware_version
        self.local_action = local_action or (lambda _: None)
        self.rules = SafeLocalRules()

    def capture(
        self,
        *,
        device_id: str,
        measurements: Mapping[str, object],
        location: Mapping[str, float] | None = None,
        context: Mapping[str, object] | None = None,
        timestamp: str | None = None,
    ) -> dict[str, object]:
        sequence = self.queue.next_sequence()
        envelope: dict[str, object] = {
            "protocol_version": PROTOCOL_VERSION,
            "device_id": device_id,
            "message_id": f"{self.queue.stream_id}:{sequence}",
            "timestamp": timestamp or utc_iso(),
            "stream_id": self.queue.stream_id,
            "sequence": sequence,
            "firmware_version": self.firmware_version,
            "replayed_from_edge": False,
            "measurements": dict(measurements),
            "context": {"gateway": "raspberry_pi_fieldbox", **dict(context or {})},
            "metadata": {},
        }
        if location:
            envelope["location"] = dict(location)
        for action in self.rules.evaluate(measurements):
            self.local_action(action)
        self.queue.enqueue(envelope)
        return envelope

    def flush(self, send: Callable[[Mapping[str, object]], bool], *, limit: int = 100) -> int:
        delivered = 0
        for row_id, envelope in self.queue.pending(limit):
            if not send(envelope):
                self.queue.failed(row_id)
                break
            self.queue.delivered(row_id)
            delivered += 1
        return delivered


def rest_sender(api_base: str, device_id: str, device_secret: str):
    """Build a sender without storing either credential in the queue."""

    endpoint = api_base.rstrip("/") + "/iot/ingest"

    def send(envelope: Mapping[str, object]) -> bool:
        body = json.dumps(envelope, separators=(",", ":")).encode()
        call = request.Request(
            endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Device {device_secret}",
                "Content-Type": "application/json",
                "X-Device-ID": device_id,
            },
        )
        try:
            with request.urlopen(call, timeout=15) as response:
                return 200 <= response.status < 300
        except OSError:
            return False

    return send


__all__ = [
    "DurableQueue",
    "FieldBox",
    "LocalAction",
    "PROTOCOL_VERSION",
    "SAFE_COMMANDS",
    "SafeLocalRules",
    "rest_sender",
]
