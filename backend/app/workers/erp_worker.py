"""Independent process for durable ERP synchronization."""

from __future__ import annotations

import argparse
import os
import signal
import socket
import threading
import uuid

from app.core.config import Settings, settings


def default_worker_id() -> str:
    return f"erp:{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def run_erp_worker_cycle(
    *, worker_id: str, config: Settings = settings
) -> dict[str, int]:
    from app.core import database
    from app.integrations.erp import get_erp_adapter
    from app.workers.erp_worker_repository import SqlAlchemyErpRepository
    from app.workers.erp_worker_runner import run_erp_cycle

    repository = SqlAlchemyErpRepository(database.SessionLocal)
    return run_erp_cycle(
        repository,
        worker_id=worker_id,
        provider_resolver=lambda provider_name: get_erp_adapter(
            config, provider_name=provider_name
        ),
        batch_size=config.erp_worker_batch_size,
        lease_seconds=config.erp_worker_claim_timeout_seconds,
        retry_initial_seconds=config.integration_retry_initial_seconds,
        retry_max_seconds=config.integration_retry_max_seconds,
    )


def run_forever(
    *,
    worker_id: str | None = None,
    config: Settings = settings,
    stop: threading.Event | None = None,
) -> None:
    identifier = worker_id or default_worker_id()
    stop_event = stop or threading.Event()
    while not stop_event.is_set():
        run_erp_worker_cycle(worker_id=identifier, config=config)
        stop_event.wait(config.erp_worker_poll_seconds)


def requeue_outbox(outbox_id: str) -> bool:
    from app.core import database
    from app.core.time import utc_now
    from app.workers.erp_worker_repository import SqlAlchemyErpRepository

    return SqlAlchemyErpRepository(database.SessionLocal).requeue_dead_letter(
        outbox_id, now=utc_now()
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run GeoVision ERP synchronization")
    parser.add_argument("--once", action="store_true", help="process one due batch")
    parser.add_argument("--requeue", metavar="OUTBOX_ID", help="requeue one dead letter")
    args = parser.parse_args()
    if args.requeue:
        if not requeue_outbox(args.requeue):
            raise SystemExit("ERP item was not found or is not dead-lettered")
        return
    if args.once:
        run_erp_worker_cycle(worker_id=default_worker_id())
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
    "requeue_outbox",
    "run_erp_worker_cycle",
    "run_forever",
]
