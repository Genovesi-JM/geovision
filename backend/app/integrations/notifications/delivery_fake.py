"""Deterministic in-memory adapter for notification delivery tests."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.integration import IntegrationResult
from app.modules.notifications.delivery_ports import (
    DeliveryAcknowledgement,
    ExternalDeliveryMessage,
)


@dataclass(slots=True)
class FakeDeliveryProvider:
    """Simulate a provider while retaining only non-secret delivery identities."""

    provider_name: str = "fake"
    delivered_ids: list[str] = field(default_factory=list)
    _idempotency_keys: set[str] = field(default_factory=set, repr=False)

    def deliver(
        self,
        message: ExternalDeliveryMessage,
    ) -> IntegrationResult[DeliveryAcknowledgement]:
        if message.idempotency_key not in self._idempotency_keys:
            self._idempotency_keys.add(message.idempotency_key)
            self.delivered_ids.append(message.delivery_id)
        return IntegrationResult.simulated(
            provider=self.provider_name,
            operation="deliver",
            value=DeliveryAcknowledgement(
                provider_message_id=f"fake:{message.delivery_id}"
            ),
        )


__all__ = ["FakeDeliveryProvider"]
