"""Normalized billing-provider facade over the compatibility gateway adapters."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Protocol

from app.core.integration import (
    IntegrationFailure,
    IntegrationResult,
    IntegrationStatus,
)
from app.modules.billing.ports import PaymentProvider as BillingPaymentProvider


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _Value:
    value: str


@dataclass(slots=True)
class _PaymentIntent:
    id: str
    company_id: str
    order_id: str
    amount: int
    currency: _Value
    provider: _Value
    description: str
    metadata: dict[str, Any] = field(default_factory=dict)
    idempotency_key: Optional[str] = None


class _PaymentAdapter(Protocol):
    provider_name: str

    async def create_payment(self, intent: _PaymentIntent) -> Any: ...

    async def check_status(self, provider_reference: str) -> Any: ...

    async def refund(
        self,
        provider_reference: str,
        amount: Optional[int] = None,
    ) -> Any: ...

    def verify_webhook(self, payload: bytes, signature: str) -> bool: ...


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _payment_value(result: Any) -> Mapping[str, Any]:
    raw_response = result.raw_response or {}
    return {
        "success": result.success,
        "payment_id": result.payment_id,
        "status": result.status.value,
        "provider_reference": result.provider_reference,
        "client_token": result.client_secret,
        "redirect_url": result.redirect_url,
        "qr_code": result.qr_code,
        "transfer_details": raw_response.get("transfer_details"),
        "instructions": raw_response.get("instructions"),
    }


def _refund_value(result: Any) -> Mapping[str, Any]:
    return {
        "success": result.success,
        "refund_id": result.refund_id,
        "amount": result.amount,
        "status": result.status,
    }


def _provider_unavailable(provider: str, operation: str) -> IntegrationResult[Any]:
    return IntegrationResult.failed(
        provider=provider,
        operation=operation,
        failure=IntegrationFailure(
            code="provider_unavailable",
            message="Payment provider is unavailable",
            retryable=True,
        ),
    )


class NormalizedPaymentProviderAdapter:
    """Expose a gateway through the billing module's normalized provider port."""

    def __init__(self, adapter: _PaymentAdapter):
        self.adapter = adapter
        self.provider_name = adapter.provider_name

    async def create_payment(
        self,
        request: Mapping[str, Any],
    ) -> IntegrationResult[Mapping[str, Any]]:
        intent = _PaymentIntent(
            id=str(request["id"]),
            company_id=str(request["company_id"]),
            order_id=str(request["order_id"]),
            amount=int(request["amount"]),
            currency=_Value(_enum_value(request["currency"])),
            provider=_Value(_enum_value(request.get("provider", self.provider_name))),
            description=str(request.get("description", "")),
            metadata=dict(request.get("metadata") or {}),
            idempotency_key=request.get("idempotency_key"),
        )
        try:
            result = await self.adapter.create_payment(intent)
        except Exception as error:
            logger.error(
                "Payment provider create failed (%s)",
                type(error).__name__,
            )
            return _provider_unavailable(self.provider_name, "create_payment")
        value = _payment_value(result)
        if not result.success:
            if result.error_code == "provider_unavailable":
                return _provider_unavailable(
                    self.provider_name,
                    "create_payment",
                )
            status = (
                IntegrationStatus.NOT_CONFIGURED
                if result.error_code == "provider_not_configured"
                else IntegrationStatus.FAILED
            )
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation="create_payment",
                status=status,
                failure=IntegrationFailure(
                    code=(
                        "provider_not_configured"
                        if result.error_code == "provider_not_configured"
                        else "payment_failed"
                    ),
                    message=(
                        "Payment provider is not configured"
                        if result.error_code == "provider_not_configured"
                        else "Payment provider rejected the request"
                    ),
                ),
            )
        if result.raw_response and result.raw_response.get("mock") is True:
            return IntegrationResult.simulated(
                provider=self.provider_name,
                operation="create_payment",
                value=value,
            )
        if _enum_value(result.status) == "completed":
            return IntegrationResult.succeeded(
                provider=self.provider_name,
                operation="create_payment",
                value=value,
            )
        return IntegrationResult.accepted(
            provider=self.provider_name,
            operation="create_payment",
            value=value,
        )

    async def check_status(
        self,
        external_reference: str,
    ) -> IntegrationResult[Mapping[str, Any]]:
        try:
            status = await self.adapter.check_status(external_reference)
        except Exception as error:
            logger.error(
                "Payment provider status check failed (%s)",
                type(error).__name__,
            )
            return _provider_unavailable(self.provider_name, "check_status")
        status_value = _enum_value(status)
        value = {"status": status_value}
        if status_value in {"pending", "processing", "awaiting_confirmation"}:
            return IntegrationResult.pending(
                provider=self.provider_name,
                operation="check_status",
                value=value,
            )
        if status_value == "failed":
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation="check_status",
                failure=IntegrationFailure(
                    code="payment_failed",
                    message="payment provider reported a failed status",
                ),
            )
        return IntegrationResult.succeeded(
            provider=self.provider_name,
            operation="check_status",
            value=value,
        )

    async def refund(
        self,
        external_reference: str,
        amount: Optional[int] = None,
    ) -> IntegrationResult[Mapping[str, Any]]:
        try:
            result = await self.adapter.refund(external_reference, amount)
        except Exception as error:
            logger.error(
                "Payment provider refund failed (%s)",
                type(error).__name__,
            )
            return _provider_unavailable(self.provider_name, "refund")
        if result.success:
            return IntegrationResult.accepted(
                provider=self.provider_name,
                operation="refund",
                value=_refund_value(result),
            )
        return IntegrationResult.failed(
            provider=self.provider_name,
            operation="refund",
            failure=IntegrationFailure(
                code="refund_failed",
                message="Payment provider rejected the refund",
            ),
        )

    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        try:
            return self.adapter.verify_webhook(payload, signature)
        except Exception as error:
            logger.error(
                "Payment provider webhook verification failed (%s)",
                type(error).__name__,
            )
            return False


def as_billing_payment_provider(
    adapter: _PaymentAdapter,
) -> BillingPaymentProvider:
    """Type-narrowed constructor for consumers of the billing module port."""

    return NormalizedPaymentProviderAdapter(adapter)


__all__ = ["NormalizedPaymentProviderAdapter", "as_billing_payment_provider"]
