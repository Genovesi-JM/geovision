"""Independent durable event publisher and consumer process."""

from __future__ import annotations

import argparse
import os
import signal
import socket
import threading
import uuid
from typing import Any

from app.core.config import Settings, settings
from app.services.event_consumers import default_event_consumers
from app.services.event_outbox import (
    deliver_to_local_consumers,
    deserialize_event,
    dispatch_pending_events,
)


def default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def _consume_remote_payload(payload: dict[str, Any]) -> None:
    from app.core import database

    db = database.SessionLocal()
    try:
        event = deserialize_event(payload)
        deliver_to_local_consumers(db, event, default_event_consumers())
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def run_event_cycle(
    *,
    worker_id: str,
    config: Settings = settings,
) -> dict[str, int]:
    from app.core import database

    db = database.SessionLocal()
    try:
        stats = dispatch_pending_events(
            db,
            worker_id=worker_id,
            registry=default_event_consumers(),
            config=config,
        )
    finally:
        db.close()
    if config.queue_provider == "azure_service_bus":
        from app.integrations.events.azure_service_bus import AzureServiceBusConsumer

        received = AzureServiceBusConsumer(config).consume_batch(
            _consume_remote_payload,
            max_messages=config.event_worker_batch_size,
            max_wait_seconds=min(config.event_worker_poll_seconds, 5.0),
        )
        stats.update({f"consumer_{key}": value for key, value in received.items()})
    return stats


def run_forever(
    *,
    worker_id: str | None = None,
    config: Settings = settings,
    stop: threading.Event | None = None,
) -> None:
    identifier = worker_id or default_worker_id()
    stop_event = stop or threading.Event()
    while not stop_event.is_set():
        run_event_cycle(worker_id=identifier, config=config)
        stop_event.wait(config.event_worker_poll_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the GeoVision durable event worker")
    parser.add_argument("--once", action="store_true", help="process one available batch")
    args = parser.parse_args()
    stop = threading.Event()

    def request_stop(*_: object) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    worker_id = default_worker_id()
    if args.once:
        run_event_cycle(worker_id=worker_id)
        return
    run_forever(worker_id=worker_id, stop=stop)


if __name__ == "__main__":
    main()


__all__ = ["default_worker_id", "main", "run_event_cycle", "run_forever"]
