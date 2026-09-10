"""Azure Service Bus topic adapter isolated from GeoVision domain modules."""

from __future__ import annotations

import json
from typing import Any, Callable

from app.core.config import Settings
from app.core.events import QueueMessage
from app.core.integration import (
    IntegrationFailure,
    IntegrationResult,
    IntegrationStatus,
    sanitize_integration_message,
)


def _client(config: Settings):
    try:
        from azure.servicebus import ServiceBusClient
    except ImportError as exc:
        raise RuntimeError("azure-servicebus package is not installed") from exc
    if config.service_bus_connection_string:
        return ServiceBusClient.from_connection_string(
            conn_str=config.service_bus_connection_string
        )
    from azure.identity import DefaultAzureCredential

    credential = DefaultAzureCredential(
        managed_identity_client_id=config.azure_managed_identity_client_id
    )
    return ServiceBusClient(
        fully_qualified_namespace=config.service_bus_fully_qualified_namespace,
        credential=credential,
    )


class AzureServiceBusPublisher:
    provider_name = "azure_service_bus"

    def __init__(self, config: Settings) -> None:
        self._config = config

    def publish(self, message: QueueMessage) -> IntegrationResult[None]:
        try:
            from azure.servicebus import ServiceBusMessage

            body = json.dumps(
                dict(message.payload),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
                default=str,
            )
            outbound = ServiceBusMessage(
                body,
                message_id=message.message_id,
                correlation_id=message.correlation_id,
                subject=message.subject,
                content_type="application/json",
                application_properties={
                    "geovision_event": message.subject or "domain.event",
                    "idempotency_key": message.idempotency_key or message.message_id,
                },
            )
            with _client(self._config) as client:
                with client.get_topic_sender(
                    topic_name=self._config.service_bus_topic
                ) as sender:
                    sender.send_messages(outbound)
            return IntegrationResult.succeeded(
                provider=self.provider_name,
                operation="publish",
            )
        except Exception as exc:
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation="publish",
                failure=IntegrationFailure(
                    code="service_bus_publish_failed",
                    message=sanitize_integration_message(
                        exc,
                        secret_values=(self._config.service_bus_connection_string or "",),
                    ),
                    retryable=True,
                ),
                status=IntegrationStatus.RETRYING,
            )


class AzureServiceBusConsumer:
    """Peek-lock receiver that settles only after the application callback."""

    provider_name = "azure_service_bus"

    def __init__(self, config: Settings) -> None:
        self._config = config

    @staticmethod
    def _body(message: Any) -> dict[str, Any]:
        raw = b"".join(bytes(part) for part in message.body).decode("utf-8")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("queue event envelope must be a JSON object")
        return value

    def consume_batch(
        self,
        callback: Callable[[dict[str, Any]], None],
        *,
        max_messages: int,
        max_wait_seconds: float = 1.0,
    ) -> dict[str, int]:
        stats = {"received": 0, "completed": 0, "abandoned": 0, "dead_lettered": 0}
        with _client(self._config) as client:
            with client.get_subscription_receiver(
                topic_name=self._config.service_bus_topic,
                subscription_name=self._config.service_bus_subscription,
                max_wait_time=max_wait_seconds,
            ) as receiver:
                messages = receiver.receive_messages(
                    max_message_count=max_messages,
                    max_wait_time=max_wait_seconds,
                )
                stats["received"] = len(messages)
                for message in messages:
                    try:
                        callback(self._body(message))
                        receiver.complete_message(message)
                        stats["completed"] += 1
                    except Exception as exc:
                        if getattr(message, "delivery_count", 1) >= self._config.event_worker_max_attempts:
                            receiver.dead_letter_message(
                                message,
                                reason="GeoVisionConsumerFailure",
                                error_description=sanitize_integration_message(exc),
                            )
                            stats["dead_lettered"] += 1
                        else:
                            receiver.abandon_message(message)
                            stats["abandoned"] += 1
        return stats


__all__ = ["AzureServiceBusConsumer", "AzureServiceBusPublisher"]
