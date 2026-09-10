"""Independent IoT offline-detection and telemetry-maintenance worker."""

from __future__ import annotations

import argparse
import signal
import threading

from app.core.config import Settings, settings
from app.iot.watchdog import maintain_telemetry, mark_offline_devices


def run_iot_cycle(*, maintain: bool = True) -> dict[str, int]:
    offline_ids = mark_offline_devices()
    if maintain:
        maintain_telemetry()
    return {"marked_offline": len(offline_ids), "maintenance_runs": int(maintain)}


def run_forever(
    *,
    config: Settings = settings,
    stop: threading.Event | None = None,
) -> None:
    stop_event = stop or threading.Event()
    cycles = 0
    while not stop_event.is_set():
        run_iot_cycle(maintain=(cycles == 0 or cycles % 10 == 0))
        cycles += 1
        stop_event.wait(config.iot_watchdog_interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run GeoVision IoT maintenance")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.once:
        run_iot_cycle()
        return
    stop = threading.Event()

    def request_stop(*_: object) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    run_forever(stop=stop)


if __name__ == "__main__":
    main()


__all__ = ["main", "run_forever", "run_iot_cycle"]
