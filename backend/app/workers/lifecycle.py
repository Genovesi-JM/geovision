"""Compatibility lifecycle for workers currently hosted by the API process."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from collections.abc import AsyncIterator

from fastapi import FastAPI

from app.core.config import settings


async def _in_process_event_worker(stop: asyncio.Event) -> None:
    """Local single-process convenience; deployed replicas use a worker service."""

    from app.workers.event_worker import default_worker_id, run_event_cycle

    worker_id = default_worker_id()
    while not stop.is_set():
        await asyncio.to_thread(run_event_cycle, worker_id=worker_id)
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.event_worker_poll_seconds)
        except asyncio.TimeoutError:
            pass


async def _in_process_processing_worker(stop: asyncio.Event) -> None:
    """Local convenience runner; deployment uses the independent worker CLI."""

    from app.workers.processing_worker import (
        default_worker_id,
        run_processing_worker_cycle,
    )

    worker_id = default_worker_id()
    while not stop.is_set():
        await asyncio.to_thread(run_processing_worker_cycle, worker_id=worker_id)
        try:
            await asyncio.wait_for(
                stop.wait(), timeout=settings.processing_worker_poll_seconds
            )
        except asyncio.TimeoutError:
            pass


async def _in_process_intelligence_worker(stop: asyncio.Event) -> None:
    """Local convenience runner; deployment uses the independent worker CLI."""

    from app.workers.intelligence_worker import (
        default_worker_id,
        run_intelligence_worker_cycle,
    )

    worker_id = default_worker_id()
    while not stop.is_set():
        await asyncio.to_thread(run_intelligence_worker_cycle, worker_id=worker_id)
        try:
            await asyncio.wait_for(
                stop.wait(), timeout=settings.intelligence_worker_poll_seconds
            )
        except asyncio.TimeoutError:
            pass


@asynccontextmanager
async def application_workers(application: FastAPI) -> AsyncIterator[None]:
    """Run the existing MQTT bridge and IoT watchdog for one API instance.

    This preserves Phase 0 behavior while giving later phases one boundary from
    which to move durable work into separately deployed worker processes.
    """

    from app.iot.mqtt import mqtt_bridge
    from app.iot.watchdog import device_watchdog

    stop_event = asyncio.Event()
    watchdog_task = (
        asyncio.create_task(device_watchdog(stop_event))
        if settings.iot_watchdog_in_process
        else None
    )
    event_worker_task = (
        asyncio.create_task(_in_process_event_worker(stop_event))
        if settings.event_worker_in_process
        else None
    )
    processing_worker_task = (
        asyncio.create_task(_in_process_processing_worker(stop_event))
        if settings.processing_worker_in_process
        else None
    )
    intelligence_worker_task = (
        asyncio.create_task(_in_process_intelligence_worker(stop_event))
        if settings.intelligence_worker_in_process
        else None
    )
    application.state.iot_watchdog_stop = stop_event
    application.state.iot_watchdog_task = watchdog_task
    mqtt_bridge.start(asyncio.get_running_loop())

    try:
        yield
    finally:
        stop_event.set()
        mqtt_bridge.stop()
        if watchdog_task is not None:
            try:
                await asyncio.wait_for(watchdog_task, timeout=2)
            except TimeoutError:
                watchdog_task.cancel()
                with suppress(asyncio.CancelledError):
                    await watchdog_task
        if event_worker_task is not None:
            try:
                await asyncio.wait_for(event_worker_task, timeout=2)
            except TimeoutError:
                event_worker_task.cancel()
                with suppress(asyncio.CancelledError):
                    await event_worker_task
        if processing_worker_task is not None:
            try:
                await asyncio.wait_for(processing_worker_task, timeout=2)
            except TimeoutError:
                processing_worker_task.cancel()
                with suppress(asyncio.CancelledError):
                    await processing_worker_task
        if intelligence_worker_task is not None:
            try:
                await asyncio.wait_for(intelligence_worker_task, timeout=2)
            except TimeoutError:
                intelligence_worker_task.cancel()
                with suppress(asyncio.CancelledError):
                    await intelligence_worker_task
