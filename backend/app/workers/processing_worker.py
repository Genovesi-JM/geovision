"""Independent photogrammetry submission, polling, and output worker."""

from __future__ import annotations

import argparse
import os
import signal
import socket
import threading
import uuid

from app.core.config import Settings, settings


def default_worker_id() -> str:
    return f"processing:{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def run_processing_worker_cycle(
    *,
    worker_id: str,
    config: Settings = settings,
) -> dict[str, int]:
    from app.core import database
    from app.integrations.processing import create_processing_provider
    from app.integrations.storage import create_object_storage_provider
    from app.modules.processing.services import run_processing_cycle
    from app.services.storage import StorageService

    providers = {}

    def resolve(name: str):
        if name not in providers:
            providers[name] = create_processing_provider(config, name)
        return providers[name]

    storage = StorageService(create_object_storage_provider(config))
    db = database.SessionLocal()
    try:
        return run_processing_cycle(
            db,
            worker_id=worker_id,
            provider_resolver=resolve,
            storage=storage,
            config=config,
        )
    finally:
        db.close()
        for provider in providers.values():
            client = getattr(provider, "client", None)
            close = getattr(client, "close", None)
            if callable(close):
                close()


def run_forever(
    *,
    worker_id: str | None = None,
    config: Settings = settings,
    stop: threading.Event | None = None,
) -> None:
    identifier = worker_id or default_worker_id()
    stop_event = stop or threading.Event()
    while not stop_event.is_set():
        run_processing_worker_cycle(worker_id=identifier, config=config)
        stop_event.wait(config.processing_worker_poll_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run GeoVision processing jobs")
    parser.add_argument("--once", action="store_true", help="process one due batch")
    args = parser.parse_args()
    if args.once:
        run_processing_worker_cycle(worker_id=default_worker_id())
        return
    stop = threading.Event()

    def request_stop(*_: object) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    run_forever(stop=stop)


if __name__ == "__main__":
    main()


__all__ = [
    "default_worker_id",
    "main",
    "run_forever",
    "run_processing_worker_cycle",
]
