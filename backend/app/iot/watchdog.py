from __future__ import annotations

import asyncio
from datetime import timedelta

from app.core.config import settings
from app.core.event_names import EventNames
from app.iot.events import event_hub
from app.models import Asset, IotDevice
from app.core.time import utc_now
from app.services.event_outbox import enqueue_domain_event


async def device_watchdog(stop: asyncio.Event) -> None:
    cycles = 0
    while not stop.is_set():
        device_ids = await asyncio.to_thread(mark_offline_devices)
        for device_id in device_ids:
            event_hub.publish(
                device_id,
                {
                    "type": "device.state",
                    "status": "offline",
                    "reason": "heartbeat_timeout",
                },
            )
        cycles += 1
        if cycles == 1 or cycles % 10 == 0:
            await asyncio.to_thread(maintain_telemetry)
        try:
            await asyncio.wait_for(
                stop.wait(), timeout=settings.iot_watchdog_interval_seconds
            )
        except asyncio.TimeoutError:
            pass


def mark_offline_devices() -> list[str]:
    from app.core import database

    db = database.SessionLocal()
    try:
        cutoff = utc_now() - timedelta(seconds=settings.iot_offline_after_seconds)
        rows = (
            db.query(IotDevice)
            .filter(
                IotDevice.last_seen_at.is_not(None),
                IotDevice.last_seen_at < cutoff,
                IotDevice.status == "online",
            )
            .all()
        )
        for device in rows:
            asset = (
                db.get(Asset, device.core_asset_id) if device.core_asset_id else None
            )
            workspace_id = (
                asset.workspace_id
                if asset is not None and asset.organization_id == device.company_id
                else None
            )
            device.status = "offline"
            device.connectivity_status = "offline"
            if device.health_status == "healthy":
                device.health_status = "degraded"
            enqueue_domain_event(
                db,
                name=EventNames.DEVICE_OFFLINE_DETECTED,
                aggregate_type="iot_device",
                aggregate_id=device.id,
                idempotency_key=(
                    f"device:{device.id}:offline:{int(cutoff.timestamp())}"
                ),
                correlation_id=device.id,
                payload={
                    "device_id": device.id,
                    "organization_id": device.company_id,
                    "workspace_id": workspace_id,
                    "site_id": device.site_id,
                    "asset_id": device.core_asset_id,
                    "reason": "heartbeat_timeout",
                    "last_seen_at": device.last_seen_at,
                },
            )
        db.commit()
        return [device.id for device in rows]
    finally:
        db.close()


def maintain_telemetry() -> None:
    from app.core import database
    from app.iot.maintenance import aggregate_and_retain

    db = database.SessionLocal()
    try:
        aggregate_and_retain(db)
    finally:
        db.close()


# Compatibility aliases for existing callers during the worker migration.
_mark_offline = mark_offline_devices
_maintain_telemetry = maintain_telemetry


__all__ = ["device_watchdog", "maintain_telemetry", "mark_offline_devices"]
