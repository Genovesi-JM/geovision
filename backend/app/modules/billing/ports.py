"""Provider port owned by the billing domain."""

from typing import Any, Mapping, Optional, Protocol, runtime_checkable

from app.core.integration import IntegrationResult


@runtime_checkable
class PaymentProvider(Protocol):
    provider_name: str

    async def create_payment(
        self,
        request: Mapping[str, Any],
    ) -> IntegrationResult[Mapping[str, Any]]: ...

    async def check_status(
        self,
        external_reference: str,
    ) -> IntegrationResult[Mapping[str, Any]]: ...

    async def refund(
        self,
        external_reference: str,
        amount: Optional[int] = None,
    ) -> IntegrationResult[Mapping[str, Any]]: ...

    def verify_webhook(self, payload: bytes, signature: str) -> bool: ...


__all__ = ["PaymentProvider"]
