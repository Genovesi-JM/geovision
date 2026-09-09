"""Concrete payment gateways behind GeoVision's billing adapter contract."""

from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from typing import Optional

import httpx

from app.core.config import Settings, settings
from app.services.payments import (
    PaymentAdapter,
    PaymentIntent,
    PaymentResult,
    PaymentStatus,
    RefundResult,
)


logger = logging.getLogger(__name__)


def _http_timeout(config: Settings) -> httpx.Timeout:
    """Apply the shared integration timeout convention to every gateway call."""

    return httpx.Timeout(
        config.integration_read_timeout_seconds,
        connect=config.integration_connect_timeout_seconds,
    )


def _not_configured_payment(
    intent: PaymentIntent,
    provider_name: str,
) -> PaymentResult:
    return PaymentResult(
        success=False,
        payment_id=intent.id,
        status=PaymentStatus.FAILED,
        error_code="provider_not_configured",
        error_message=f"{provider_name} payment provider is not configured",
    )


class MulticaixaExpressAdapter(PaymentAdapter):
    provider_name = "multicaixa_express"

    def __init__(self, config: Optional[Settings] = None):
        self.config = config or settings
        self.api_url = self.config.multicaixa_api_url
        self.merchant_id = self.config.multicaixa_merchant_id
        self.api_key = self.config.multicaixa_api_key
        self.webhook_secret = self.config.multicaixa_webhook_secret

    async def create_payment(self, intent: PaymentIntent) -> PaymentResult:
        if not self.merchant_id or not self.api_key:
            if self.config.is_deployed:
                logger.error("Multicaixa is not configured in a deployed environment")
                return _not_configured_payment(intent, "Multicaixa")
            logger.warning("Multicaixa not configured - returning mock response")
            return PaymentResult(
                success=True,
                payment_id=intent.id,
                status=PaymentStatus.PENDING,
                provider_reference=f"MCX-{uuid.uuid4().hex[:12].upper()}",
                qr_code=(
                    "00020101021126330014mcx.co.ao0112"
                    f"{intent.id}520400005303AOA5406{intent.amount}5802AO5925GEOVISION"
                ),
                raw_response={"mock": True},
            )
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.api_url}/payments",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "X-Merchant-ID": self.merchant_id,
                        "X-Idempotency-Key": intent.idempotency_key or intent.id,
                    },
                    json={
                        "amount": intent.amount,
                        "currency": intent.currency.value,
                        "reference": intent.order_id,
                        "description": intent.description,
                        "callback_url": self.config.multicaixa_callback_url,
                        "expires_in_minutes": 30,
                    },
                    timeout=_http_timeout(self.config),
                )
                if response.status_code == 200:
                    data = response.json()
                    return PaymentResult(
                        success=True,
                        payment_id=intent.id,
                        status=PaymentStatus.PENDING,
                        provider_reference=data.get("payment_id"),
                        qr_code=data.get("qr_code"),
                        raw_response=data,
                    )
                return PaymentResult(
                    success=False,
                    payment_id=intent.id,
                    status=PaymentStatus.FAILED,
                    error_code=str(response.status_code),
                    error_message="Multicaixa rejected the payment request",
                )
            except Exception as error:
                logger.error(
                    "Multicaixa payment request failed (%s)",
                    type(error).__name__,
                )
                return PaymentResult(
                    success=False,
                    payment_id=intent.id,
                    status=PaymentStatus.FAILED,
                    error_code="provider_unavailable",
                    error_message="Multicaixa payment provider is unavailable",
                )

    async def check_status(self, provider_reference: str) -> PaymentStatus:
        if not self.api_key:
            return PaymentStatus.FAILED if self.config.is_deployed else PaymentStatus.COMPLETED
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_url}/payments/{provider_reference}",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=_http_timeout(self.config),
            )
            if response.status_code == 200:
                data = response.json()
                mapping = {
                    "pending": PaymentStatus.PENDING,
                    "processing": PaymentStatus.PROCESSING,
                    "completed": PaymentStatus.COMPLETED,
                    "failed": PaymentStatus.FAILED,
                    "expired": PaymentStatus.CANCELLED,
                }
                return mapping.get(data.get("status"), PaymentStatus.PENDING)
        return PaymentStatus.PENDING

    async def refund(
        self,
        provider_reference: str,
        amount: Optional[int] = None,
    ) -> RefundResult:
        if not self.api_key:
            if self.config.is_deployed:
                return RefundResult(
                    success=False,
                    refund_id="",
                    amount=0,
                    status="failed",
                    error_message="Multicaixa payment provider is not configured",
                )
            return RefundResult(
                success=True,
                refund_id=f"REF-{uuid.uuid4().hex[:8]}",
                amount=amount or 0,
                status="completed",
            )
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_url}/payments/{provider_reference}/refund",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"amount": amount} if amount else {},
                timeout=_http_timeout(self.config),
            )
            if response.status_code == 200:
                data = response.json()
                return RefundResult(
                    success=True,
                    refund_id=data.get("refund_id"),
                    amount=data.get("amount", amount or 0),
                    status=data.get("status", "completed"),
                )
            return RefundResult(
                success=False,
                refund_id="",
                amount=0,
                status="failed",
                error_message="Multicaixa rejected the refund request",
            )

    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        if not self.webhook_secret:
            return not self.config.is_deployed
        if not signature:
            return False
        expected = hmac.new(
            self.webhook_secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)


class VisaMastercardAdapter(PaymentAdapter):
    provider_name = "visa_mastercard"

    def __init__(self, config: Optional[Settings] = None):
        self.config = config or settings
        self.api_key = self.config.stripe_secret_key
        self.webhook_secret = self.config.stripe_webhook_secret
        self.api_url = "https://api.stripe.com/v1"

    async def create_payment(self, intent: PaymentIntent) -> PaymentResult:
        if not self.api_key:
            if self.config.is_deployed:
                logger.error("Stripe is not configured in a deployed environment")
                return _not_configured_payment(intent, "Stripe")
            logger.warning("Stripe not configured - returning mock response")
            return PaymentResult(
                success=True,
                payment_id=intent.id,
                status=PaymentStatus.PENDING,
                provider_reference=f"pi_{uuid.uuid4().hex[:24]}",
                raw_response={"mock": True},
            )
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.api_url}/payment_intents",
                    auth=(self.api_key, ""),
                    headers={"Idempotency-Key": intent.idempotency_key or intent.id},
                    data={
                        "amount": intent.amount,
                        "currency": intent.currency.value.lower(),
                        "description": intent.description,
                        "metadata[order_id]": intent.order_id,
                        "metadata[company_id]": intent.company_id,
                        "automatic_payment_methods[enabled]": "true",
                    },
                    timeout=_http_timeout(self.config),
                )
                if response.status_code == 200:
                    data = response.json()
                    return PaymentResult(
                        success=True,
                        payment_id=intent.id,
                        status=PaymentStatus.PENDING,
                        provider_reference=data.get("id"),
                        client_secret=data.get("client_secret"),
                        raw_response=data,
                    )
                data = response.json()
                return PaymentResult(
                    success=False,
                    payment_id=intent.id,
                    status=PaymentStatus.FAILED,
                    error_code=data.get("error", {}).get("code"),
                    error_message="Stripe rejected the payment request",
                )
            except Exception as error:
                logger.error(
                    "Stripe payment request failed (%s)",
                    type(error).__name__,
                )
                return PaymentResult(
                    success=False,
                    payment_id=intent.id,
                    status=PaymentStatus.FAILED,
                    error_code="provider_unavailable",
                    error_message="Stripe payment provider is unavailable",
                )

    async def check_status(self, provider_reference: str) -> PaymentStatus:
        if not self.api_key:
            return PaymentStatus.FAILED if self.config.is_deployed else PaymentStatus.COMPLETED
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_url}/payment_intents/{provider_reference}",
                auth=(self.api_key, ""),
                timeout=_http_timeout(self.config),
            )
            if response.status_code == 200:
                data = response.json()
                mapping = {
                    "requires_payment_method": PaymentStatus.PENDING,
                    "requires_confirmation": PaymentStatus.PENDING,
                    "requires_action": PaymentStatus.PROCESSING,
                    "processing": PaymentStatus.PROCESSING,
                    "succeeded": PaymentStatus.COMPLETED,
                    "canceled": PaymentStatus.CANCELLED,
                }
                return mapping.get(data.get("status"), PaymentStatus.PENDING)
        return PaymentStatus.PENDING

    async def refund(
        self,
        provider_reference: str,
        amount: Optional[int] = None,
    ) -> RefundResult:
        if not self.api_key:
            if self.config.is_deployed:
                return RefundResult(
                    success=False,
                    refund_id="",
                    amount=0,
                    status="failed",
                    error_message="Stripe payment provider is not configured",
                )
            return RefundResult(
                success=True,
                refund_id=f"re_{uuid.uuid4().hex[:24]}",
                amount=amount or 0,
                status="succeeded",
            )
        async with httpx.AsyncClient() as client:
            data = {"payment_intent": provider_reference}
            if amount:
                data["amount"] = str(amount)
            response = await client.post(
                f"{self.api_url}/refunds",
                auth=(self.api_key, ""),
                data=data,
                timeout=_http_timeout(self.config),
            )
            if response.status_code == 200:
                result = response.json()
                return RefundResult(
                    success=True,
                    refund_id=result.get("id"),
                    amount=result.get("amount", amount or 0),
                    status=result.get("status", "succeeded"),
                )
            return RefundResult(
                success=False,
                refund_id="",
                amount=0,
                status="failed",
                error_message="Stripe rejected the refund request",
            )

    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        if not self.webhook_secret:
            return not self.config.is_deployed
        if not signature:
            return False
        try:
            parts = dict(part.split("=", 1) for part in signature.split(","))
            timestamp = parts.get("t")
            signature_value = parts.get("v1")
            if not timestamp or not signature_value:
                return False
            signed_payload = f"{timestamp}.{payload.decode()}"
            expected = hmac.new(
                self.webhook_secret.encode(),
                signed_payload.encode(),
                hashlib.sha256,
            ).hexdigest()
            return hmac.compare_digest(expected, signature_value)
        except Exception as error:
            logger.error("Webhook verification failed (%s)", type(error).__name__)
            return False


class IBANTransferAdapter(PaymentAdapter):
    """Handle both Angolan (AOA) and international (USD/EUR) transfers."""

    provider_name = "iban_transfer"
    BANK_AOA = {
        "iban": settings.company_iban,
        "bic": settings.company_bic,
        "bank_name": settings.company_bank_name,
        "beneficiary": "GeoVision Lda",
    }
    BANK_INTL = {
        "iban": settings.company_iban_intl,
        "bic": settings.company_bic_intl,
        "bank_name": settings.company_bank_intl,
        "beneficiary": "GeoVision Lda",
    }

    def __init__(self, config: Optional[Settings] = None):
        self.config = config or settings
        self.BANK_AOA = {
            "iban": self.config.company_iban,
            "bic": self.config.company_bic,
            "bank_name": self.config.company_bank_name,
            "beneficiary": "GeoVision Lda",
        }
        self.BANK_INTL = {
            "iban": self.config.company_iban_intl,
            "bic": self.config.company_bic_intl,
            "bank_name": self.config.company_bank_intl,
            "beneficiary": "GeoVision Lda",
        }

    async def create_payment(self, intent: PaymentIntent) -> PaymentResult:
        reference = f"GV-{intent.order_id[-8:].upper()}"
        is_international = intent.currency.value in ("USD", "EUR")
        bank = self.BANK_INTL if is_international else self.BANK_AOA
        return PaymentResult(
            success=True,
            payment_id=intent.id,
            status=PaymentStatus.AWAITING_CONFIRMATION,
            provider_reference=reference,
            raw_response={
                "transfer_details": {
                    **bank,
                    "reference": reference,
                    "amount": intent.amount / 100,
                    "currency": intent.currency.value,
                },
                "instructions": (
                    "Please include the reference in your transfer description. "
                    "Payment will be confirmed within 1-2 business days after receipt."
                ),
            },
        )

    async def check_status(self, provider_reference: str) -> PaymentStatus:
        return PaymentStatus.AWAITING_CONFIRMATION

    async def refund(
        self,
        provider_reference: str,
        amount: Optional[int] = None,
    ) -> RefundResult:
        return RefundResult(
            success=True,
            refund_id=f"BANK-REF-{uuid.uuid4().hex[:8]}",
            amount=amount or 0,
            status="pending_manual_transfer",
            error_message="Refund will be processed manually via bank transfer",
        )

    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        return not self.config.is_deployed


class PayPalAdapter(PaymentAdapter):
    """PayPal REST API v2 adapter with development-only simulation fallback."""

    provider_name = "paypal"

    def __init__(self, config: Optional[Settings] = None):
        self.config = config or settings
        self.client_id = self.config.paypal_client_id or ""
        self.secret = self.config.paypal_secret or ""
        self.api_url = (
            "https://api-m.paypal.com"
            if self.config.paypal_mode == "live"
            else "https://api-m.sandbox.paypal.com"
        )

    async def _get_token(self) -> Optional[str]:
        if not self.client_id or not self.secret:
            return None
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/v1/oauth2/token",
                    auth=(self.client_id, self.secret),
                    data={"grant_type": "client_credentials"},
                    timeout=_http_timeout(self.config),
                )
                if response.status_code == 200:
                    return response.json().get("access_token")
        except Exception as error:
            logger.error(
                "PayPal token request failed (%s)",
                type(error).__name__,
            )
        return None

    async def create_payment(self, intent: PaymentIntent) -> PaymentResult:
        token = await self._get_token()
        if not token:
            if self.config.is_deployed:
                provider_name = "PayPal"
                if self.client_id and self.secret:
                    return PaymentResult(
                        success=False,
                        payment_id=intent.id,
                        status=PaymentStatus.FAILED,
                        error_code="provider_unavailable",
                        error_message=f"{provider_name} payment provider is unavailable",
                    )
                return _not_configured_payment(intent, provider_name)
            logger.warning("PayPal: no credentials, returning mock payment")
            mock_id = f"PAYPAL-MOCK-{uuid.uuid4().hex[:12].upper()}"
            return PaymentResult(
                success=True,
                payment_id=intent.id,
                status=PaymentStatus.PENDING,
                provider_reference=mock_id,
                redirect_url=(
                    "https://www.sandbox.paypal.com/checkoutnow?token="
                    f"{mock_id}"
                ),
                raw_response={"mock": True},
            )

        currency = intent.currency.value
        amount_str = f"{intent.amount / 100:.2f}"
        body = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": intent.order_id,
                    "description": intent.description,
                    "amount": {"currency_code": currency, "value": amount_str},
                }
            ],
            "application_context": {
                "return_url": self.config.paypal_return_url,
                "cancel_url": self.config.paypal_cancel_url,
                "brand_name": "GeoVision",
            },
        }
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.api_url}/v2/checkout/orders",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                        "PayPal-Request-Id": intent.idempotency_key or intent.id,
                    },
                    json=body,
                    timeout=_http_timeout(self.config),
                )
                if response.status_code in (200, 201):
                    data = response.json()
                    approve_link = next(
                        (
                            link["href"]
                            for link in data.get("links", [])
                            if link.get("rel") == "approve"
                        ),
                        None,
                    )
                    return PaymentResult(
                        success=True,
                        payment_id=intent.id,
                        status=PaymentStatus.PENDING,
                        provider_reference=data.get("id"),
                        redirect_url=approve_link,
                        raw_response=data,
                    )
                return PaymentResult(
                    success=False,
                    payment_id=intent.id,
                    status=PaymentStatus.FAILED,
                    error_message="PayPal rejected the payment request",
                )
            except Exception as error:
                logger.error(
                    "PayPal payment request failed (%s)",
                    type(error).__name__,
                )
                return PaymentResult(
                    success=False,
                    payment_id=intent.id,
                    status=PaymentStatus.FAILED,
                    error_code="provider_unavailable",
                    error_message="PayPal payment provider is unavailable",
                )

    async def check_status(self, provider_reference: str) -> PaymentStatus:
        token = await self._get_token()
        if not token:
            return PaymentStatus.FAILED if self.config.is_deployed else PaymentStatus.COMPLETED
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_url}/v2/checkout/orders/{provider_reference}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=_http_timeout(self.config),
            )
            if response.status_code == 200:
                status = response.json().get("status", "")
                mapping = {
                    "CREATED": PaymentStatus.PENDING,
                    "APPROVED": PaymentStatus.PROCESSING,
                    "COMPLETED": PaymentStatus.COMPLETED,
                    "VOIDED": PaymentStatus.CANCELLED,
                }
                return mapping.get(status, PaymentStatus.PENDING)
        return PaymentStatus.PENDING

    async def refund(
        self,
        provider_reference: str,
        amount: Optional[int] = None,
    ) -> RefundResult:
        return RefundResult(
            success=False,
            refund_id="",
            amount=amount or 0,
            status="pending",
            error_message="PayPal refunds — use PayPal dashboard",
        )

    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        # PayPal verification requires its Webhook ID/API round trip. Until that
        # is configured, accepting callbacks would be unsafe when deployed.
        return not self.config.is_deployed


__all__ = [
    "IBANTransferAdapter",
    "MulticaixaExpressAdapter",
    "PayPalAdapter",
    "VisaMastercardAdapter",
]
