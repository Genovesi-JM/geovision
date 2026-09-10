"""Deterministic queue test doubles."""

from __future__ import annotations

from app.core.events import QueueMessage
from app.core.integration import (
    IntegrationFailure,
    IntegrationResult,
    IntegrationStatus,
)


class InMemoryQueuePublisher:
    provider_name = "in_memory"

    def __init__(self) -> None:
        self.messages: list[QueueMessage] = []

    def publish(self, message: QueueMessage) -> IntegrationResult[None]:
        self.messages.append(message)
        return IntegrationResult.succeeded(
            provider=self.provider_name,
            operation="publish",
        )


class UnavailableQueuePublisher:
    provider_name = "null"

    def publish(self, message: QueueMessage) -> IntegrationResult[None]:
        del message
        return IntegrationResult.failed(
            provider=self.provider_name,
            operation="publish",
            failure=IntegrationFailure(
                code="queue_not_configured",
                message="Durable queue delivery is not configured",
                retryable=False,
            ),
            status=IntegrationStatus.NOT_CONFIGURED,
        )


__all__ = ["InMemoryQueuePublisher", "UnavailableQueuePublisher"]
