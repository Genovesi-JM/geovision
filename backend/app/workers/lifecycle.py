"""Compatibility lifecycle for workers currently hosted by the API process."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from collections.abc import AsyncIterator

from fastapi import FastAPI


@asynccontextmanager
async def application_workers(application: FastAPI) -> AsyncIterator[None]:
    """Run the existing MQTT bridge and IoT watchdog for one API instance.

    This preserves Phase 0 behavior while giving later phases one boundary from
    which to move durable work into separately deployed worker processes.
    """

    from app.iot.mqtt import mqtt_bridge
    from app.iot.watchdog import device_watchdog

    stop_event = asyncio.Event()
    watchdog_task = asyncio.create_task(device_watchdog(stop_event))
    application.state.iot_watchdog_stop = stop_event
    application.state.iot_watchdog_task = watchdog_task
    mqtt_bridge.start(asyncio.get_running_loop())

    try:
        yield
    finally:
        stop_event.set()
        mqtt_bridge.stop()
        try:
            await asyncio.wait_for(watchdog_task, timeout=2)
        except TimeoutError:
            watchdog_task.cancel()
            with suppress(asyncio.CancelledError):
                await watchdog_task
