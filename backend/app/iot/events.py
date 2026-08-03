from __future__ import annotations

import asyncio
from collections import defaultdict


class DeviceEventHub:
    """In-process fan-out for SSE/WebSocket clients.

    Durable truth remains in PostgreSQL. This small fan-out layer makes a
    single development instance live without adding infrastructure; Redis can
    replace it behind the same API when multiple backend replicas are used.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, device_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers[device_id].add(queue)
        return queue

    def unsubscribe(self, device_id: str, queue: asyncio.Queue) -> None:
        self._subscribers[device_id].discard(queue)

    def publish(self, device_id: str, event: dict) -> None:
        for queue in tuple(self._subscribers.get(device_id, ())):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass


event_hub = DeviceEventHub()
