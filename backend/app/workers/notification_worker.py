"""Independent process for retryable email and push notification delivery."""

from __future__ import annotations

import argparse
import os
import signal
import socket
import threading
import uuid

from app.core.config import Settings, settings


def default_worker_id() -> str:
    return f"notification:{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def _integer(config: Settings, name: str, default: int) -> int:
    return int(getattr(config, name, default))


def _number(config: Settings, name: str, default: float) -> float:
    return float(getattr(config, name, default))


def run_notification_worker_cycle(
    *,
    worker_id: str,
    config: Settings = settings,
) -> dict[str, int]:
    from app.core import database
    from app.core.encryption import decrypt
    from app.integrations.notifications.delivery_factory import (
        create_external_delivery_provider,
    )
    from app.workers.notification_delivery_repository import (
        SqlAlchemyNotificationDeliveryRepository,
    )
    from app.workers.notification_delivery_runner import run_delivery_cycle

    repository = SqlAlchemyNotificationDeliveryRepository(
        database.SessionLocal,
        payload_decoder=decrypt,
    )
    return run_delivery_cycle(
        repository,
        worker_id=worker_id,
        provider_resolver=lambda provider_name, message: (
            create_external_delivery_provider(
                provider_name=provider_name,
                channel=message.channel,
                config=config,
            )
        ),
        batch_size=_integer(config, "notification_worker_batch_size", 50),
        lease_seconds=_integer(
            config, "notification_worker_claim_timeout_seconds", 300
        ),
        retry_base_seconds=_number(
            config, "notification_worker_retry_base_seconds", 30.0
        ),
        retry_max_seconds=_number(
            config, "notification_worker_retry_max_seconds", 3600.0
        ),
    )


def run_forever(
    *,
    worker_id: str | None = None,
    config: Settings = settings,
    stop: threading.Event | None = None,
) -> None:
    identifier = worker_id or default_worker_id()
    stop_event = stop or threading.Event()
    poll_seconds = _number(config, "notification_worker_poll_seconds", 5.0)
    while not stop_event.is_set():
        run_notification_worker_cycle(worker_id=identifier, config=config)
        stop_event.wait(poll_seconds)


def requeue_delivery(delivery_id: str) -> bool:
    from app.core import database
    from app.core.encryption import decrypt
    from app.core.time import utc_now
    from app.workers.notification_delivery_repository import (
        SqlAlchemyNotificationDeliveryRepository,
    )

    repository = SqlAlchemyNotificationDeliveryRepository(
        database.SessionLocal,
        payload_decoder=decrypt,
    )
    return repository.requeue_dead_letter(delivery_id, now=utc_now())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run GeoVision external notification deliveries"
    )
    parser.add_argument("--once", action="store_true", help="process one due batch")
    parser.add_argument(
        "--requeue",
        metavar="DELIVERY_ID",
        help="requeue one dead-lettered delivery",
    )
    args = parser.parse_args()
    if args.requeue:
        if not requeue_delivery(args.requeue):
            raise SystemExit("delivery was not found or is not dead-lettered")
        return
    if args.once:
        run_notification_worker_cycle(worker_id=default_worker_id())
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
    "requeue_delivery",
    "run_forever",
    "run_notification_worker_cycle",
]
