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
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from importlib import import_module
from typing import Optional, Dict, Any, Mapping
from enum import Enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

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
    client_secret: Optional[str] = field(default=None, repr=False)
    redirect_url: Optional[str] = None
    qr_code: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = field(default=None, repr=False)


@dataclass
class RefundResult:
    """Result from refund processing."""
    success: bool
    refund_id: str
    amount: int
    status: str
    error_message: Optional[str] = None


# ============ PROVIDER PORT ============

class PaymentAdapter(ABC):
    """Legacy-compatible adapter contract implemented by payment integrations."""

    provider_name: str

    @abstractmethod
    async def create_payment(self, intent: PaymentIntent) -> PaymentResult: ...
    @abstractmethod
    async def check_status(self, provider_reference: str) -> PaymentStatus: ...
    @abstractmethod
    async def refund(self, provider_reference: str, amount: Optional[int] = None) -> RefundResult: ...
    @abstractmethod
    def verify_webhook(self, payload: bytes, signature: str) -> bool: ...

# ============ PAYMENT ORCHESTRATOR — DB-backed ============

def _create_default_adapters() -> Dict[PaymentProvider, PaymentAdapter]:
    """Resolve concrete gateways only for the default runtime path."""

    from app.integrations.payments.factory import create_payment_adapters

    return create_payment_adapters()


class PaymentOrchestrator:
    """Main payment orchestration service. Persists data in Payment table."""

    def __init__(
        self,
        db: Session,
        adapters: Optional[Mapping[PaymentProvider, PaymentAdapter]] = None,
    ):
        self.db = db
        self.adapters = dict(adapters) if adapters is not None else _create_default_adapters()

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
        try:
            result = await adapter.create_payment(intent)
        except Exception as error:
            logger.error(
                "Payment provider create failed (%s)",
                type(error).__name__,
            )
            result = PaymentResult(
                success=False,
                payment_id=payment_id,
                status=PaymentStatus.FAILED,
                error_code="provider_unavailable",
                error_message="Payment provider is unavailable",
            )

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
            try:
                new_status = await adapter.check_status(row.provider_reference)
            except Exception as error:
                logger.error(
                    "Payment provider status check failed (%s)",
                    type(error).__name__,
                )
                return status
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
        try:
            result = await adapter.refund(row.provider_reference or "", amount)
        except Exception as error:
            logger.error(
                "Payment provider refund failed (%s)",
                type(error).__name__,
            )
            return RefundResult(
                success=False,
                refund_id="",
                amount=amount or 0,
                status="failed",
                error_message="Payment provider is unavailable",
            )
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
        try:
            verified = adapter.verify_webhook(payload, signature)
        except Exception as error:
            logger.error(
                "Payment provider webhook verification failed (%s)",
                type(error).__name__,
            )
            verified = False
        if not verified:
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


def get_payment_orchestrator(
    db: Session,
    adapters: Optional[Mapping[PaymentProvider, PaymentAdapter]] = None,
) -> PaymentOrchestrator:
    """Get payment orchestrator instance (requires db session)."""
    return PaymentOrchestrator(db, adapters=adapters)


_ADAPTER_EXPORTS = {
    "MulticaixaExpressAdapter",
    "VisaMastercardAdapter",
    "IBANTransferAdapter",
    "PayPalAdapter",
}


def __getattr__(name: str):
    """Keep legacy adapter imports without eagerly loading provider libraries."""

    if name not in _ADAPTER_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module("app.integrations.payments.adapters")
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | _ADAPTER_EXPORTS)


__all__ = [
    "Currency",
    "IBANTransferAdapter",
    "MulticaixaExpressAdapter",
    "PayPalAdapter",
    "PaymentAdapter",
    "PaymentIntent",
    "PaymentOrchestrator",
    "PaymentProvider",
    "PaymentResult",
    "PaymentStatus",
    "RefundResult",
    "VisaMastercardAdapter",
    "get_payment_orchestrator",
]
