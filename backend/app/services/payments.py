"""
Payment Orchestrator Service — DB-backed

Multi-provider payment processing for Angola + International:
- Multicaixa Express (Angola mobile payments/ATM)
- Visa/Mastercard (via Stripe or local acquirer)
- IBAN Bank Transfer (manual confirmation)

Features:
- Idempotency for payment intents (DB-persisted)
- Webhook signature verification
- Status polling for async payments
- Refund handling
"""
import os
import hmac
import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from enum import Enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

def _utcnow():
    return datetime.now(timezone.utc)


# ============ ENUMS ============

class PaymentProvider(str, Enum):
    MULTICAIXA_EXPRESS = "multicaixa_express"
    VISA_MASTERCARD = "visa_mastercard"
    IBAN_TRANSFER = "iban_transfer"
    PAYPAL = "paypal"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


class Currency(str, Enum):
    AOA = "AOA"
    USD = "USD"
    EUR = "EUR"


# ============ DATA CLASSES ============

@dataclass
class PaymentIntent:
    """Payment intent before processing."""
    id: str
    company_id: str
    order_id: str
    amount: int
    currency: Currency
    provider: PaymentProvider
    description: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    idempotency_key: Optional[str] = None
    status: PaymentStatus = PaymentStatus.PENDING
    provider_reference: Optional[str] = None
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    expires_at: Optional[datetime] = None


@dataclass
class PaymentResult:
    """Result from payment processing."""
    success: bool
    payment_id: str
    status: PaymentStatus
    provider_reference: Optional[str] = None
    client_secret: Optional[str] = None
    redirect_url: Optional[str] = None
    qr_code: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None


@dataclass
class RefundResult:
    """Result from refund processing."""
    success: bool
    refund_id: str
    amount: int
    status: str
    error_message: Optional[str] = None


# ============ PROVIDER ADAPTERS (unchanged — no state) ============

class PaymentAdapter(ABC):
    @abstractmethod
    async def create_payment(self, intent: PaymentIntent) -> PaymentResult: ...
    @abstractmethod
    async def check_status(self, provider_reference: str) -> PaymentStatus: ...
    @abstractmethod
    async def refund(self, provider_reference: str, amount: Optional[int] = None) -> RefundResult: ...
    @abstractmethod
    def verify_webhook(self, payload: bytes, signature: str) -> bool: ...


class MulticaixaExpressAdapter(PaymentAdapter):
    def __init__(self):
        self.api_url = os.getenv("MULTICAIXA_API_URL", "https://api.multicaixa.co.ao/v1")
        self.merchant_id = os.getenv("MULTICAIXA_MERCHANT_ID")
        self.api_key = os.getenv("MULTICAIXA_API_KEY")
        self.webhook_secret = os.getenv("MULTICAIXA_WEBHOOK_SECRET")

    async def create_payment(self, intent: PaymentIntent) -> PaymentResult:
        if not self.merchant_id or not self.api_key:
            logger.warning("Multicaixa not configured - returning mock response")
            return PaymentResult(
                success=True, payment_id=intent.id, status=PaymentStatus.PENDING,
                provider_reference=f"MCX-{uuid.uuid4().hex[:12].upper()}",
                qr_code=f"00020101021126330014mcx.co.ao0112{intent.id}520400005303AOA5406{intent.amount}5802AO5925GEOVISION",
                raw_response={"mock": True})
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(f"{self.api_url}/payments", headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "X-Merchant-ID": self.merchant_id,
                    "X-Idempotency-Key": intent.idempotency_key or intent.id,
                }, json={"amount": intent.amount, "currency": intent.currency.value,
                         "reference": intent.order_id, "description": intent.description,
                         "callback_url": os.getenv("MULTICAIXA_CALLBACK_URL"), "expires_in_minutes": 30},
                    timeout=30.0)
                if response.status_code == 200:
                    data = response.json()
                    return PaymentResult(success=True, payment_id=intent.id, status=PaymentStatus.PENDING,
                                        provider_reference=data.get("payment_id"), qr_code=data.get("qr_code"), raw_response=data)
                return PaymentResult(success=False, payment_id=intent.id, status=PaymentStatus.FAILED,
                                    error_code=str(response.status_code), error_message=response.text)
            except Exception as e:
                logger.error(f"Multicaixa API error: {e}")
                return PaymentResult(success=False, payment_id=intent.id, status=PaymentStatus.FAILED, error_message=str(e))

    async def check_status(self, provider_reference: str) -> PaymentStatus:
        if not self.api_key:
            return PaymentStatus.COMPLETED
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.api_url}/payments/{provider_reference}",
                                        headers={"Authorization": f"Bearer {self.api_key}"}, timeout=10.0)
            if response.status_code == 200:
                data = response.json()
                m = {"pending": PaymentStatus.PENDING, "processing": PaymentStatus.PROCESSING,
                     "completed": PaymentStatus.COMPLETED, "failed": PaymentStatus.FAILED, "expired": PaymentStatus.CANCELLED}
                return m.get(data.get("status"), PaymentStatus.PENDING)
        return PaymentStatus.PENDING

    async def refund(self, provider_reference: str, amount: Optional[int] = None) -> RefundResult:
        if not self.api_key:
            return RefundResult(success=True, refund_id=f"REF-{uuid.uuid4().hex[:8]}", amount=amount or 0, status="completed")
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{self.api_url}/payments/{provider_reference}/refund",
                                         headers={"Authorization": f"Bearer {self.api_key}"},
                                         json={"amount": amount} if amount else {}, timeout=30.0)
            if response.status_code == 200:
                data = response.json()
                return RefundResult(success=True, refund_id=data.get("refund_id"), amount=data.get("amount", amount or 0), status=data.get("status", "completed"))
            return RefundResult(success=False, refund_id="", amount=0, status="failed", error_message=response.text)

    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        if not self.webhook_secret:
            return True
        expected = hmac.new(self.webhook_secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


class VisaMastercardAdapter(PaymentAdapter):
    def __init__(self):
        self.api_key = os.getenv("STRIPE_SECRET_KEY")
        self.webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
        self.api_url = "https://api.stripe.com/v1"

    async def create_payment(self, intent: PaymentIntent) -> PaymentResult:
        if not self.api_key:
            logger.warning("Stripe not configured - returning mock response")
            return PaymentResult(success=True, payment_id=intent.id, status=PaymentStatus.PENDING,
                                provider_reference=f"pi_{uuid.uuid4().hex[:24]}", raw_response={"mock": True})
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(f"{self.api_url}/payment_intents", auth=(self.api_key, ""),
                    headers={"Idempotency-Key": intent.idempotency_key or intent.id},
                    data={"amount": intent.amount, "currency": intent.currency.value.lower(),
                          "description": intent.description, "metadata[order_id]": intent.order_id,
                          "metadata[company_id]": intent.company_id, "automatic_payment_methods[enabled]": "true"},
                    timeout=30.0)
                if response.status_code == 200:
                    data = response.json()
                    return PaymentResult(success=True, payment_id=intent.id, status=PaymentStatus.PENDING,
                                        provider_reference=data.get("id"),
                                        client_secret=data.get("client_secret"),
                                        raw_response=data)
                data = response.json()
                return PaymentResult(success=False, payment_id=intent.id, status=PaymentStatus.FAILED,
                                    error_code=data.get("error", {}).get("code"),
                                    error_message=data.get("error", {}).get("message"))
            except Exception as e:
                logger.error(f"Stripe API error: {e}")
                return PaymentResult(success=False, payment_id=intent.id, status=PaymentStatus.FAILED, error_message=str(e))

    async def check_status(self, provider_reference: str) -> PaymentStatus:
        if not self.api_key:
            return PaymentStatus.COMPLETED
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.api_url}/payment_intents/{provider_reference}",
                                        auth=(self.api_key, ""), timeout=10.0)
            if response.status_code == 200:
                data = response.json()
                m = {"requires_payment_method": PaymentStatus.PENDING, "requires_confirmation": PaymentStatus.PENDING,
                     "requires_action": PaymentStatus.PROCESSING, "processing": PaymentStatus.PROCESSING,
                     "succeeded": PaymentStatus.COMPLETED, "canceled": PaymentStatus.CANCELLED}
                return m.get(data.get("status"), PaymentStatus.PENDING)
        return PaymentStatus.PENDING

    async def refund(self, provider_reference: str, amount: Optional[int] = None) -> RefundResult:
        if not self.api_key:
            return RefundResult(success=True, refund_id=f"re_{uuid.uuid4().hex[:24]}", amount=amount or 0, status="succeeded")
        async with httpx.AsyncClient() as client:
            data = {"payment_intent": provider_reference}
            if amount:
                data["amount"] = str(amount)
            response = await client.post(f"{self.api_url}/refunds", auth=(self.api_key, ""), data=data, timeout=30.0)
            if response.status_code == 200:
                result = response.json()
                return RefundResult(success=True, refund_id=result.get("id"), amount=result.get("amount", amount or 0), status=result.get("status", "succeeded"))
            return RefundResult(success=False, refund_id="", amount=0, status="failed", error_message=response.text)

    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        if not self.webhook_secret:
            return True
        try:
            parts = dict(p.split("=", 1) for p in signature.split(","))
            timestamp = parts.get("t"); sig = parts.get("v1")
            if not timestamp or not sig: return False
            signed_payload = f"{timestamp}.{payload.decode()}"
            expected = hmac.new(self.webhook_secret.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()
            return hmac.compare_digest(expected, sig)
        except Exception as e:
            logger.error(f"Webhook verification error: {e}")
            return False


class IBANTransferAdapter(PaymentAdapter):
    """Handles both Angolan (AOA) and international (USD/EUR) bank transfers."""

    # Angolan account (AOA)
    BANK_AOA = {
        "iban": os.getenv("COMPANY_IBAN", "AO06004400005506300102101"),
        "bic": os.getenv("COMPANY_BIC", "BFAOAOAO"),
        "bank_name": os.getenv("COMPANY_BANK_NAME", "Banco de Fomento Angola"),
        "beneficiary": "GeoVision Lda",
    }
    # International account (USD / EUR)
    BANK_INTL = {
        "iban": os.getenv("COMPANY_IBAN_INTL", "PT50003600559910003085730"),
        "bic": os.getenv("COMPANY_BIC_INTL", "MPIOPTPL"),
        "bank_name": os.getenv("COMPANY_BANK_INTL", "Banco Millennium BCP"),
        "beneficiary": "GeoVision Lda",
    }

    async def create_payment(self, intent: PaymentIntent) -> PaymentResult:
        reference = f"GV-{intent.order_id[-8:].upper()}"
        is_international = intent.currency.value in ("USD", "EUR")
        bank = self.BANK_INTL if is_international else self.BANK_AOA
        return PaymentResult(success=True, payment_id=intent.id,
            status=PaymentStatus.AWAITING_CONFIRMATION, provider_reference=reference,
            raw_response={"transfer_details": {
                **bank, "reference": reference,
                "amount": intent.amount / 100, "currency": intent.currency.value},
                "instructions": "Please include the reference in your transfer description. "
                                "Payment will be confirmed within 1-2 business days after receipt."})

    async def check_status(self, provider_reference: str) -> PaymentStatus:
        return PaymentStatus.AWAITING_CONFIRMATION

    async def refund(self, provider_reference: str, amount: Optional[int] = None) -> RefundResult:
        return RefundResult(success=True, refund_id=f"BANK-REF-{uuid.uuid4().hex[:8]}",
                           amount=amount or 0, status="pending_manual_transfer",
                           error_message="Refund will be processed manually via bank transfer")

    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        return True


class PayPalAdapter(PaymentAdapter):
    """PayPal payments — placeholder for full SDK integration.
    Uses PayPal REST API (v2). Set PAYPAL_CLIENT_ID and PAYPAL_SECRET env vars.
    Defaults to sandbox mode (PAYPAL_MODE=sandbox|live)."""

    def __init__(self):
        self.client_id = os.getenv("PAYPAL_CLIENT_ID", "")
        self.secret = os.getenv("PAYPAL_SECRET", "")
        mode = os.getenv("PAYPAL_MODE", "sandbox")
        self.api_url = "https://api-m.paypal.com" if mode == "live" else "https://api-m.sandbox.paypal.com"

    async def _get_token(self) -> Optional[str]:
        if not self.client_id or not self.secret:
            return None
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{self.api_url}/v1/oauth2/token",
                auth=(self.client_id, self.secret),
                data={"grant_type": "client_credentials"}, timeout=15.0)
            if r.status_code == 200:
                return r.json().get("access_token")
        return None

    async def create_payment(self, intent: PaymentIntent) -> PaymentResult:
        token = await self._get_token()
        if not token:
            # Mock mode — no PayPal credentials configured
            logger.warning("PayPal: no credentials, returning mock payment")
            mock_id = f"PAYPAL-MOCK-{uuid.uuid4().hex[:12].upper()}"
            return PaymentResult(success=True, payment_id=intent.id,
                status=PaymentStatus.PENDING, provider_reference=mock_id,
                redirect_url=f"https://www.sandbox.paypal.com/checkoutnow?token={mock_id}",
                raw_response={"mock": True})

        currency = intent.currency.value  # USD or EUR
        amount_str = f"{intent.amount / 100:.2f}"
        body = {
            "intent": "CAPTURE",
            "purchase_units": [{
                "reference_id": intent.order_id,
                "description": intent.description,
                "amount": {"currency_code": currency, "value": amount_str},
            }],
            "application_context": {
                "return_url": os.getenv("PAYPAL_RETURN_URL", "https://geovisionops.com/loja.html?paypal=success"),
                "cancel_url": os.getenv("PAYPAL_CANCEL_URL", "https://geovisionops.com/loja.html?paypal=cancel"),
                "brand_name": "GeoVision",
            },
        }
        async with httpx.AsyncClient() as client:
            try:
                r = await client.post(f"{self.api_url}/v2/checkout/orders",
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                             "PayPal-Request-Id": intent.idempotency_key or intent.id},
                    json=body, timeout=30.0)
                if r.status_code in (200, 201):
                    data = r.json()
                    approve_link = next((l["href"] for l in data.get("links", []) if l.get("rel") == "approve"), None)
                    return PaymentResult(success=True, payment_id=intent.id,
                        status=PaymentStatus.PENDING, provider_reference=data.get("id"),
                        redirect_url=approve_link, raw_response=data)
                return PaymentResult(success=False, payment_id=intent.id,
                    status=PaymentStatus.FAILED, error_message=r.text)
            except Exception as e:
                logger.error(f"PayPal API error: {e}")
                return PaymentResult(success=False, payment_id=intent.id,
                    status=PaymentStatus.FAILED, error_message=str(e))

    async def check_status(self, provider_reference: str) -> PaymentStatus:
        token = await self._get_token()
        if not token:
            return PaymentStatus.COMPLETED
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{self.api_url}/v2/checkout/orders/{provider_reference}",
                headers={"Authorization": f"Bearer {token}"}, timeout=10.0)
            if r.status_code == 200:
                st = r.json().get("status", "")
                m = {"CREATED": PaymentStatus.PENDING, "APPROVED": PaymentStatus.PROCESSING,
                     "COMPLETED": PaymentStatus.COMPLETED, "VOIDED": PaymentStatus.CANCELLED}
                return m.get(st, PaymentStatus.PENDING)
        return PaymentStatus.PENDING

    async def refund(self, provider_reference: str, amount: Optional[int] = None) -> RefundResult:
        return RefundResult(success=False, refund_id="", amount=amount or 0,
            status="pending", error_message="PayPal refunds — use PayPal dashboard")

    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        # PayPal webhook verification requires Webhook ID — implement when webhooks are set up
        return True


# ============ PAYMENT ORCHESTRATOR — DB-backed ============

class PaymentOrchestrator:
    """Main payment orchestration service. Persists data in Payment table."""

    def __init__(self, db: Session):
        self.db = db
        self.adapters: Dict[PaymentProvider, PaymentAdapter] = {
            PaymentProvider.MULTICAIXA_EXPRESS: MulticaixaExpressAdapter(),
            PaymentProvider.VISA_MASTERCARD: VisaMastercardAdapter(),
            PaymentProvider.IBAN_TRANSFER: IBANTransferAdapter(),
            PaymentProvider.PAYPAL: PayPalAdapter(),
        }

    def _model(self):
        from app.models import Payment
        return Payment

    def _get_adapter(self, provider: PaymentProvider) -> PaymentAdapter:
        adapter = self.adapters.get(provider)
        if not adapter:
            raise ValueError(f"Unknown provider: {provider}")
        return adapter

    async def create_payment(self, company_id: str, order_id: str, amount: int,
                             currency: Currency, provider: PaymentProvider,
                             description: str, metadata: Optional[Dict[str, Any]] = None,
                             idempotency_key: Optional[str] = None) -> PaymentResult:
        PM = self._model()

        # Idempotency check
        if idempotency_key:
            existing = self.db.query(PM).filter(PM.idempotency_key == idempotency_key).first()
            if existing:
                return PaymentResult(success=True, payment_id=existing.id,
                    status=PaymentStatus(existing.status), provider_reference=existing.provider_reference)

        payment_id = str(uuid.uuid4())
        intent = PaymentIntent(
            id=payment_id, company_id=company_id, order_id=order_id,
            amount=amount, currency=currency, provider=provider,
            description=description, metadata=metadata or {},
            idempotency_key=idempotency_key,
            expires_at=_utcnow() + timedelta(hours=1),
        )

        adapter = self._get_adapter(provider)
        result = await adapter.create_payment(intent)

        # Persist to DB
        row = PM(
            id=payment_id, company_id=company_id, order_id=order_id,
            amount=amount, currency=currency.value, provider=provider.value,
            status=result.status.value, idempotency_key=idempotency_key,
            provider_reference=result.provider_reference,
            metadata_json=json.dumps(metadata or {}),
        )
        self.db.add(row)
        self.db.commit()

        logger.info(f"Created payment {payment_id} via {provider.value}: {result.status.value}")
        return result

    async def check_status(self, payment_id: str) -> Optional[PaymentStatus]:
        PM = self._model()
        row = self.db.get(PM, payment_id)
        if not row:
            return None
        status = PaymentStatus(row.status)
        if status in [PaymentStatus.COMPLETED, PaymentStatus.FAILED,
                      PaymentStatus.CANCELLED, PaymentStatus.REFUNDED]:
            return status
        # Poll provider
        adapter = self._get_adapter(PaymentProvider(row.provider))
        if row.provider_reference:
            new_status = await adapter.check_status(row.provider_reference)
            row.status = new_status.value
            row.updated_at = _utcnow()
            self.db.commit()
            return new_status
        return status

    async def confirm_iban_transfer(self, payment_id: str, confirmed_by: str,
                                    bank_reference: Optional[str] = None) -> bool:
        PM = self._model()
        row = self.db.get(PM, payment_id)
        if not row or row.provider != PaymentProvider.IBAN_TRANSFER.value:
            return False
        row.status = PaymentStatus.COMPLETED.value
        row.updated_at = _utcnow()
        meta = json.loads(row.metadata_json or "{}")
        meta["confirmed_by"] = confirmed_by
        meta["confirmed_at"] = _utcnow().isoformat()
        if bank_reference:
            meta["bank_reference"] = bank_reference
        row.metadata_json = json.dumps(meta)
        self.db.commit()
        logger.info(f"IBAN transfer {payment_id} confirmed by {confirmed_by}")
        return True

    async def refund(self, payment_id: str, amount: Optional[int] = None,
                     reason: Optional[str] = None) -> RefundResult:
        PM = self._model()
        row = self.db.get(PM, payment_id)
        if not row:
            return RefundResult(success=False, refund_id="", amount=0, status="failed", error_message="Payment not found")
        status = PaymentStatus(row.status)
        if status not in [PaymentStatus.COMPLETED, PaymentStatus.PARTIALLY_REFUNDED]:
            return RefundResult(success=False, refund_id="", amount=0, status="failed",
                               error_message=f"Cannot refund payment with status: {status.value}")
        adapter = self._get_adapter(PaymentProvider(row.provider))
        result = await adapter.refund(row.provider_reference or "", amount)
        if result.success:
            if amount and amount < row.amount:
                row.status = PaymentStatus.PARTIALLY_REFUNDED.value
            else:
                row.status = PaymentStatus.REFUNDED.value
            row.updated_at = _utcnow()
            meta = json.loads(row.metadata_json or "{}")
            meta["refund_reason"] = reason
            row.metadata_json = json.dumps(meta)
            self.db.commit()
            logger.info(f"Refunded payment {payment_id}: {result.amount}")
        return result

    async def handle_webhook(self, provider: PaymentProvider,
                             payload: bytes, signature: str) -> Dict[str, Any]:
        PM = self._model()
        adapter = self._get_adapter(provider)
        if not adapter.verify_webhook(payload, signature):
            logger.warning(f"Invalid webhook signature for {provider.value}")
            return {"status": "error", "message": "Invalid signature"}

        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return {"status": "error", "message": "Invalid JSON"}

        provider_ref = None
        new_status = None
        if provider == PaymentProvider.MULTICAIXA_EXPRESS:
            provider_ref = data.get("payment_id")
            m = {"completed": PaymentStatus.COMPLETED, "failed": PaymentStatus.FAILED, "expired": PaymentStatus.CANCELLED}
            new_status = m.get(data.get("status"))
        elif provider == PaymentProvider.VISA_MASTERCARD:
            event_type = data.get("type")
            if event_type == "payment_intent.succeeded":
                provider_ref = data.get("data", {}).get("object", {}).get("id")
                new_status = PaymentStatus.COMPLETED
            elif event_type == "payment_intent.payment_failed":
                provider_ref = data.get("data", {}).get("object", {}).get("id")
                new_status = PaymentStatus.FAILED

        if provider_ref and new_status:
            row = self.db.query(PM).filter(PM.provider_reference == provider_ref).first()
            if row:
                old_status = row.status
                row.status = new_status.value
                row.updated_at = _utcnow()
                self.db.commit()
                logger.info(f"Webhook updated payment {row.id}: {old_status} -> {new_status.value}")
                return {"status": "ok", "payment_id": row.id, "new_status": new_status.value}

        return {"status": "ok", "message": "No matching payment found"}

    def get_payment(self, payment_id: str) -> Optional[PaymentIntent]:
        PM = self._model()
        row = self.db.get(PM, payment_id)
        if not row:
            return None
        return PaymentIntent(
            id=row.id, company_id=row.company_id, order_id=row.order_id,
            amount=row.amount, currency=Currency(row.currency),
            provider=PaymentProvider(row.provider), description="",
            metadata=json.loads(row.metadata_json or "{}"),
            idempotency_key=row.idempotency_key,
            status=PaymentStatus(row.status),
            provider_reference=row.provider_reference,
            created_at=row.created_at, updated_at=row.updated_at)

    def list_payments(self, company_id=None, status=None, provider=None, limit=50):
        PM = self._model()
        q = self.db.query(PM)
        if company_id:
            q = q.filter(PM.company_id == company_id)
        if status:
            q = q.filter(PM.status == status.value if isinstance(status, PaymentStatus) else status)
        if provider:
            q = q.filter(PM.provider == provider.value if isinstance(provider, PaymentProvider) else provider)
        q = q.order_by(PM.created_at.desc()).limit(limit)
        rows = q.all()
        return [PaymentIntent(
            id=r.id, company_id=r.company_id, order_id=r.order_id,
            amount=r.amount, currency=Currency(r.currency),
            provider=PaymentProvider(r.provider), description="",
            metadata=json.loads(r.metadata_json or "{}"),
            idempotency_key=r.idempotency_key,
            status=PaymentStatus(r.status), provider_reference=r.provider_reference,
            created_at=r.created_at, updated_at=r.updated_at) for r in rows]


def get_payment_orchestrator(db: Session) -> PaymentOrchestrator:
    """Get payment orchestrator instance (requires db session)."""
    return PaymentOrchestrator(db)
