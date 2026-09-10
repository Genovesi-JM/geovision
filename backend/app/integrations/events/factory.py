"""Lazy queue adapter composition."""

from __future__ import annotations

from app.core.config import Settings, settings
from app.core.events import QueuePublisher


def create_queue_publisher(config: Settings = settings) -> QueuePublisher:
    if config.queue_provider == "in_memory":
        from .local import InMemoryQueuePublisher

        return InMemoryQueuePublisher()
    if config.queue_provider == "azure_service_bus":
        from .azure_service_bus import AzureServiceBusPublisher

        return AzureServiceBusPublisher(config)
    from .local import UnavailableQueuePublisher

    return UnavailableQueuePublisher()


__all__ = ["create_queue_publisher"]
