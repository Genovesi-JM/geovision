from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from app.config import settings
from app.iot.events import event_hub
from app.models import IotDevice


async def device_watchdog(stop: asyncio.Event) -> None:
    cycles = 0
    while not stop.is_set():
        device_ids = await asyncio.to_thread(_mark_offline)
        for device_id in device_ids:
            event_hub.publish(device_id, {"type": "device.state", "status": "offline", "reason": "heartbeat_timeout"})
        cycles += 1
        if cycles == 1 or cycles % 10 == 0:
            await asyncio.to_thread(_maintain_telemetry)
        try:
            await asyncio.wait_for(stop.wait(), timeout=30)
        except asyncio.TimeoutError:
            pass


def _mark_offline() -> list[str]:
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(seconds=settings.iot_offline_after_seconds)
        rows = db.query(IotDevice).filter(IotDevice.last_seen_at.is_not(None), IotDevice.last_seen_at < cutoff, IotDevice.status == "online").all()
        for device in rows:
            device.status = "offline"
        db.commit()
        return [device.id for device in rows]
    finally:
        db.close()


def _maintain_telemetry() -> None:
    from app.database import SessionLocal
    from app.iot.maintenance import aggregate_and_retain
    db = SessionLocal()
    try:
        aggregate_and_retain(db)
    finally:
        db.close()
