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
import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from importlib import import_module
from typing import Optional, Dict, Any, Mapping
from enum import Enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.integration import IntegrationStatus

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


_PAYMENT_TRANSITIONS = {
    PaymentStatus.PENDING: {
        PaymentStatus.PROCESSING,
        PaymentStatus.AWAITING_CONFIRMATION,
        PaymentStatus.COMPLETED,
        PaymentStatus.FAILED,
        PaymentStatus.CANCELLED,
    },
    PaymentStatus.PROCESSING: {
        PaymentStatus.COMPLETED,
        PaymentStatus.FAILED,
        PaymentStatus.CANCELLED,
    },
    PaymentStatus.AWAITING_CONFIRMATION: {
        PaymentStatus.COMPLETED,
        PaymentStatus.FAILED,
        PaymentStatus.CANCELLED,
    },
    PaymentStatus.COMPLETED: {
        PaymentStatus.PARTIALLY_REFUNDED,
        PaymentStatus.REFUNDED,
    },
    PaymentStatus.PARTIALLY_REFUNDED: {
        PaymentStatus.PARTIALLY_REFUNDED,
        PaymentStatus.REFUNDED,
    },
    PaymentStatus.FAILED: set(),
    PaymentStatus.CANCELLED: set(),
    PaymentStatus.REFUNDED: set(),
}


class PaymentIdempotencyConflict(ValueError):
    """An idempotency key was reused for a materially different payment."""


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
        # The billing module owns the provider interface. Legacy gateway
        # adapters are normalized once at this boundary, then every live
        # payment operation goes through the module-owned port.
        from app.integrations.payments.normalized import as_billing_payment_provider

        self.providers = {
            provider: as_billing_payment_provider(adapter)
            for provider, adapter in self.adapters.items()
        }

    def _model(self):
        from app.models import Payment
        return Payment

    def _get_adapter(self, provider: PaymentProvider) -> PaymentAdapter:
        adapter = self.adapters.get(provider)
        if not adapter:
            raise ValueError(f"Unknown provider: {provider}")
        return adapter

    def _get_provider(self, provider: PaymentProvider):
        normalized = self.providers.get(provider)
        if not normalized:
            raise ValueError(f"Unknown provider: {provider}")
        return normalized

    async def create_payment(self, company_id: str, order_id: str, amount: int,
                             currency: Currency, provider: PaymentProvider,
                             description: str, metadata: Optional[Dict[str, Any]] = None,
                             idempotency_key: Optional[str] = None) -> PaymentResult:
        PM = self._model()

        if amount <= 0:
            raise ValueError("Payment amount must be positive")

        # Idempotency protects one immutable commercial request. Returning a
        # previous payment for a different order/amount would cross tenants.
        if idempotency_key:
            existing = self.db.query(PM).filter(PM.idempotency_key == idempotency_key).first()
            if existing:
                expected = (
                    company_id,
                    order_id,
                    amount,
                    currency.value,
                    provider.value,
                )
                actual = (
                    existing.company_id,
                    existing.order_id,
                    existing.amount,
                    existing.currency,
                    existing.provider,
                )
                if actual != expected:
                    raise PaymentIdempotencyConflict(
                        "Idempotency key is already bound to another payment request"
                    )
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

        normalized = await self._get_provider(provider).create_payment(
            {
                "id": intent.id,
                "company_id": intent.company_id,
                "order_id": intent.order_id,
                "amount": intent.amount,
                "currency": intent.currency,
                "provider": intent.provider,
                "description": intent.description,
                "metadata": intent.metadata,
                "idempotency_key": intent.idempotency_key,
            }
        )
        value = dict(normalized.value or {})
        result_status = value.get("status", PaymentStatus.FAILED.value)
        try:
            parsed_status = PaymentStatus(result_status)
        except ValueError:
            parsed_status = PaymentStatus.FAILED
        result = PaymentResult(
            success=normalized.ok,
            payment_id=payment_id,
            status=parsed_status if normalized.ok else PaymentStatus.FAILED,
            provider_reference=value.get("provider_reference"),
            client_secret=value.get("client_token"),
            redirect_url=value.get("redirect_url"),
            qr_code=value.get("qr_code"),
            error_code=normalized.failure.code if normalized.failure else None,
            error_message=normalized.failure.message if normalized.failure else None,
            raw_response={
                key: value.get(key)
                for key in ("transfer_details", "instructions")
                if value.get(key) is not None
            },
        )

        # Persist to DB
        from app.models import Company

        row = PM(
            id=payment_id, company_id=company_id, order_id=order_id,
            organization_id=company_id if self.db.get(Company, company_id) else None,
            amount=amount, currency=currency.value, provider=provider.value,
            status=result.status.value, idempotency_key=idempotency_key,
            provider_reference=result.provider_reference,
            metadata_json=json.dumps(metadata or {}),
        )
        self.db.add(row)
        self.db.flush()
        from app.modules.orders.services import apply_payment_state

        apply_payment_state(
            self.db,
            payment=row,
            provider_status=result.status.value,
            actor_name="Payment provider",
        )
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
        # Poll through the provider-neutral billing port.
        provider = self._get_provider(PaymentProvider(row.provider))
        if row.provider_reference:
            result = await provider.check_status(row.provider_reference)
            if result.status in {
                IntegrationStatus.FAILED,
                IntegrationStatus.NOT_CONFIGURED,
                IntegrationStatus.RETRYING,
            } and (not result.failure or result.failure.code != "payment_failed"):
                return status
            value = dict(result.value or {})
            reported = value.get("status")
            if not reported and result.failure and result.failure.code == "payment_failed":
                reported = PaymentStatus.FAILED.value
            try:
                new_status = PaymentStatus(reported)
            except (TypeError, ValueError):
                return status
            if new_status != status and new_status not in _PAYMENT_TRANSITIONS[status]:
                logger.warning(
                    "Ignoring stale payment transition %s -> %s",
                    status.value,
                    new_status.value,
                )
                return status
            row.status = new_status.value
            row.updated_at = _utcnow()
            from app.modules.orders.services import apply_payment_state

            apply_payment_state(
                self.db,
                payment=row,
                provider_status=new_status.value,
                actor_name="Payment provider status check",
            )
            self.db.commit()
            return new_status
        return status

    async def confirm_iban_transfer(self, payment_id: str, confirmed_by: str,
                                    bank_reference: Optional[str] = None) -> bool:
        PM = self._model()
        row = self.db.get(PM, payment_id)
        if not row or row.provider != PaymentProvider.IBAN_TRANSFER.value:
            return False
        current = PaymentStatus(row.status)
        if current == PaymentStatus.COMPLETED:
            return True
        if PaymentStatus.COMPLETED not in _PAYMENT_TRANSITIONS[current]:
            return False
        row.status = PaymentStatus.COMPLETED.value
        now = _utcnow()
        row.updated_at = now
        row.completed_at = now
        meta = json.loads(row.metadata_json or "{}")
        meta["confirmed_by"] = confirmed_by
        meta["confirmed_at"] = _utcnow().isoformat()
        if bank_reference:
            meta["bank_reference"] = bank_reference
        row.metadata_json = json.dumps(meta)
        from app.modules.orders.services import apply_payment_state

        apply_payment_state(
            self.db,
            payment=row,
            provider_status=PaymentStatus.COMPLETED.value,
            actor_name=confirmed_by,
        )
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
        remaining = max(0, row.amount - int(row.refunded_amount or 0))
        requested_amount = amount if amount is not None else remaining
        if requested_amount <= 0 or requested_amount > remaining:
            return RefundResult(
                success=False,
                refund_id="",
                amount=0,
                status="failed",
                error_message="Refund amount exceeds the unsettled payment balance",
            )
        normalized = await self._get_provider(PaymentProvider(row.provider)).refund(
            row.provider_reference or "", requested_amount
        )
        value = dict(normalized.value or {})
        result = RefundResult(
            success=normalized.ok,
            refund_id=str(value.get("refund_id") or ""),
            amount=int(value.get("amount") or requested_amount) if normalized.ok else 0,
            status=str(value.get("status") or ("accepted" if normalized.ok else "failed")),
            error_message=normalized.failure.message if normalized.failure else None,
        )
        if result.success:
            row.refunded_amount = min(row.amount, int(row.refunded_amount or 0) + requested_amount)
            if row.refunded_amount < row.amount:
                row.status = PaymentStatus.PARTIALLY_REFUNDED.value
            else:
                row.status = PaymentStatus.REFUNDED.value
            row.updated_at = _utcnow()
            meta = json.loads(row.metadata_json or "{}")
            meta["refund_reason"] = reason
            row.metadata_json = json.dumps(meta)
            from app.modules.orders.services import apply_payment_state

            apply_payment_state(
                self.db,
                payment=row,
                provider_status=row.status,
                actor_name="GeoVision finance",
            )
            self.db.commit()
            logger.info(f"Refunded payment {payment_id}: {result.amount}")
        return result

    async def handle_webhook(self, provider: PaymentProvider,
                             payload: bytes, signature: str) -> Dict[str, Any]:
        PM = self._model()
        from app.models import PaymentWebhookEvent

        verified = self._get_provider(provider).verify_webhook(payload, signature)
        if not verified:
            logger.warning(f"Invalid webhook signature for {provider.value}")
            return {"status": "error", "message": "Invalid signature"}

        try:
            data = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {"status": "error", "message": "Invalid JSON"}
        if not isinstance(data, dict):
            return {"status": "error", "message": "Invalid JSON"}

        provider_ref = None
        new_status = None
        provider_status = None
        if provider == PaymentProvider.MULTICAIXA_EXPRESS:
            provider_ref = data.get("payment_id")
            provider_status = str(data.get("status") or "") or None
            m = {"completed": PaymentStatus.COMPLETED, "failed": PaymentStatus.FAILED, "expired": PaymentStatus.CANCELLED}
            new_status = m.get(data.get("status"))
        elif provider == PaymentProvider.VISA_MASTERCARD:
            event_type = data.get("type")
            provider_status = str(event_type or "") or None
            event_data = data.get("data")
            event_object = (
                event_data.get("object") if isinstance(event_data, dict) else None
            )
            event_object = event_object if isinstance(event_object, dict) else {}
            if event_type == "payment_intent.succeeded":
                provider_ref = event_object.get("id")
                new_status = PaymentStatus.COMPLETED
            elif event_type == "payment_intent.payment_failed":
                provider_ref = event_object.get("id")
                new_status = PaymentStatus.FAILED

        # Signed input is still untrusted input. Only scalar provider IDs can
        # be used in a database predicate, and bounded status text prevents a
        # validly signed but malformed event from overflowing ledger columns.
        if provider_ref is not None and not isinstance(provider_ref, (str, int)):
            provider_ref = None
            new_status = None
        if provider_ref is not None:
            provider_ref = str(provider_ref)[:200]
        if provider_status is not None:
            provider_status = provider_status[:50]

        digest = hashlib.sha256(payload).hexdigest()
        supplied_event_id = data.get("id") or data.get("event_id")
        event_id = str(supplied_event_id or f"sha256:{digest}")[:200]
        existing = (
            self.db.query(PaymentWebhookEvent)
            .filter(
                PaymentWebhookEvent.provider == provider.value,
                PaymentWebhookEvent.event_id == event_id,
            )
            .first()
        )
        if existing:
            return {
                "status": "ok",
                "duplicate": True,
                "event_id": event_id,
                "payment_id": existing.payment_id,
            }

        receipt = PaymentWebhookEvent(
            provider=provider.value,
            event_id=event_id,
            payload_sha256=digest,
            signature_verified=True,
            provider_reference=provider_ref if provider_ref else None,
            provider_status=provider_status,
            outcome="RECEIVED",
        )
        self.db.add(receipt)
        try:
            self.db.flush()
        except IntegrityError:
            # Another worker won the unique provider/event race.
            self.db.rollback()
            existing = (
                self.db.query(PaymentWebhookEvent)
                .filter(
                    PaymentWebhookEvent.provider == provider.value,
                    PaymentWebhookEvent.event_id == event_id,
                )
                .first()
            )
            return {
                "status": "ok",
                "duplicate": True,
                "event_id": event_id,
                "payment_id": existing.payment_id if existing else None,
            }

        if provider_ref and new_status:
            row = self.db.query(PM).filter(PM.provider_reference == provider_ref).first()
            if row:
                receipt.payment_id = row.id
                receipt.order_id = row.order_id
                try:
                    old_status = PaymentStatus(row.status)
                except ValueError:
                    old_status = PaymentStatus.PENDING
                if new_status != old_status and new_status not in _PAYMENT_TRANSITIONS[old_status]:
                    receipt.outcome = "IGNORED"
                    receipt.error_code = "stale_transition"
                    receipt.processed_at = _utcnow()
                    self.db.commit()
                    return {
                        "status": "ok",
                        "duplicate": False,
                        "event_id": event_id,
                        "payment_id": row.id,
                        "message": "Stale payment transition ignored",
                    }
                if new_status != old_status:
                    now = _utcnow()
                    row.status = new_status.value
                    row.updated_at = now
                    if new_status == PaymentStatus.COMPLETED:
                        row.completed_at = row.completed_at or now
                    elif new_status == PaymentStatus.FAILED:
                        row.failed_at = row.failed_at or now
                    from app.modules.orders.services import apply_payment_state

                    apply_payment_state(
                        self.db,
                        payment=row,
                        provider_status=new_status.value,
                        source_event_id=event_id,
                    )
                receipt.outcome = "PROCESSED"
                receipt.processed_at = _utcnow()
                self.db.commit()
                logger.info(
                    "Webhook processed payment %s: %s -> %s",
                    row.id,
                    old_status.value,
                    new_status.value,
                )
                return {
                    "status": "ok",
                    "duplicate": False,
                    "event_id": event_id,
                    "payment_id": row.id,
                    "new_status": new_status.value,
                }

        receipt.outcome = "IGNORED"
        receipt.error_code = "no_matching_payment"
        receipt.processed_at = _utcnow()
        self.db.commit()
        return {
            "status": "ok",
            "duplicate": False,
            "event_id": event_id,
            "message": "No matching payment found",
        }

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
    "IBANTransferAdapter",  # noqa: F822 - provided lazily by module __getattr__
    "MulticaixaExpressAdapter",  # noqa: F822 - provided lazily by module __getattr__
    "PayPalAdapter",  # noqa: F822 - provided lazily by module __getattr__
    "PaymentAdapter",
    "PaymentIntent",
    "PaymentIdempotencyConflict",
    "PaymentOrchestrator",
    "PaymentProvider",
    "PaymentResult",
    "PaymentStatus",
    "RefundResult",
    "VisaMastercardAdapter",  # noqa: F822 - provided lazily by module __getattr__
    "get_payment_orchestrator",
]
