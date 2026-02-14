"""
Payment Orchestrator Service

Multi-provider payment processing for Angola + International:
- Multicaixa Express (Angola mobile payments/ATM)
- Visa/Mastercard (via Stripe or local acquirer)
- IBAN Bank Transfer (manual confirmation)

Features:
- Idempotency for payment intents
- Webhook signature verification
- Status polling for async payments
- Refund handling
"""
import os
import hmac
import hashlib
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from enum import Enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ============ ENUMS ============

class PaymentProvider(str, Enum):
    MULTICAIXA_EXPRESS = "multicaixa_express"
    VISA_MASTERCARD = "visa_mastercard"
    IBAN_TRANSFER = "iban_transfer"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    AWAITING_CONFIRMATION = "awaiting_confirmation"  # For IBAN
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


class Currency(str, Enum):
    AOA = "AOA"  # Angolan Kwanza
    USD = "USD"
    EUR = "EUR"


# ============ DATA CLASSES ============

@dataclass
class PaymentIntent:
    """Payment intent before processing."""
    id: str
    company_id: str
    order_id: str
    amount: int  # In smallest currency unit (centavos/cents)
    currency: Currency
    provider: PaymentProvider
    description: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    idempotency_key: Optional[str] = None
    status: PaymentStatus = PaymentStatus.PENDING
    provider_reference: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None


@dataclass
class PaymentResult:
    """Result from payment processing."""
    success: bool
    payment_id: str
    status: PaymentStatus
    provider_reference: Optional[str] = None
    redirect_url: Optional[str] = None  # For 3D Secure / Multicaixa
    qr_code: Optional[str] = None  # For Multicaixa Express
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


# ============ PROVIDER ADAPTERS ============

class PaymentAdapter(ABC):
    """Base class for payment provider adapters."""
    
    @abstractmethod
    async def create_payment(self, intent: PaymentIntent) -> PaymentResult:
        """Create payment with provider."""
        pass
    
    @abstractmethod
    async def check_status(self, provider_reference: str) -> PaymentStatus:
        """Check payment status."""
        pass
    
    @abstractmethod
    async def refund(self, provider_reference: str, amount: Optional[int] = None) -> RefundResult:
        """Process refund."""
        pass
    
    @abstractmethod
    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        """Verify webhook signature."""
        pass


class MulticaixaExpressAdapter(PaymentAdapter):
    """
    Multicaixa Express adapter for Angola mobile/ATM payments.
    
    Docs: https://developer.multicaixa.co.ao (hypothetical)
    """
    
    def __init__(self):
        self.api_url = os.getenv("MULTICAIXA_API_URL", "https://api.multicaixa.co.ao/v1")
        self.merchant_id = os.getenv("MULTICAIXA_MERCHANT_ID")
        self.api_key = os.getenv("MULTICAIXA_API_KEY")
        self.webhook_secret = os.getenv("MULTICAIXA_WEBHOOK_SECRET")
    
    async def create_payment(self, intent: PaymentIntent) -> PaymentResult:
        """Create Multicaixa Express payment."""
        
        if not self.merchant_id or not self.api_key:
            logger.warning("Multicaixa not configured - returning mock response")
            return PaymentResult(
                success=True,
                payment_id=intent.id,
                status=PaymentStatus.PENDING,
                provider_reference=f"MCX-{uuid.uuid4().hex[:12].upper()}",
                qr_code=f"00020101021126330014mcx.co.ao0112{intent.id}520400005303AOA5406{intent.amount}5802AO5925GEOVISION",
                raw_response={"mock": True}
            )
        
        # Real implementation
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
                        "callback_url": os.getenv("MULTICAIXA_CALLBACK_URL"),
                        "expires_in_minutes": 30,
                    },
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return PaymentResult(
                        success=True,
                        payment_id=intent.id,
                        status=PaymentStatus.PENDING,
                        provider_reference=data.get("payment_id"),
                        qr_code=data.get("qr_code"),
                        raw_response=data
                    )
                else:
                    return PaymentResult(
                        success=False,
                        payment_id=intent.id,
                        status=PaymentStatus.FAILED,
                        error_code=str(response.status_code),
                        error_message=response.text,
                    )
            except Exception as e:
                logger.error(f"Multicaixa API error: {e}")
                return PaymentResult(
                    success=False,
                    payment_id=intent.id,
                    status=PaymentStatus.FAILED,
                    error_message=str(e),
                )
    
    async def check_status(self, provider_reference: str) -> PaymentStatus:
        """Check Multicaixa payment status."""
        
        if not self.api_key:
            # Mock response
            return PaymentStatus.COMPLETED
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_url}/payments/{provider_reference}",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10.0
            )
            
            if response.status_code == 200:
                data = response.json()
                status_map = {
                    "pending": PaymentStatus.PENDING,
                    "processing": PaymentStatus.PROCESSING,
                    "completed": PaymentStatus.COMPLETED,
                    "failed": PaymentStatus.FAILED,
                    "expired": PaymentStatus.CANCELLED,
                }
                return status_map.get(data.get("status"), PaymentStatus.PENDING)
        
        return PaymentStatus.PENDING
    
    async def refund(self, provider_reference: str, amount: Optional[int] = None) -> RefundResult:
        """Process Multicaixa refund."""
        
        if not self.api_key:
            return RefundResult(
                success=True,
                refund_id=f"REF-{uuid.uuid4().hex[:8]}",
                amount=amount or 0,
                status="completed"
            )
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_url}/payments/{provider_reference}/refund",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"amount": amount} if amount else {},
                timeout=30.0
            )
            
            if response.status_code == 200:
                data = response.json()
                return RefundResult(
                    success=True,
                    refund_id=data.get("refund_id"),
                    amount=data.get("amount", amount or 0),
                    status=data.get("status", "completed")
                )
            else:
                return RefundResult(
                    success=False,
                    refund_id="",
                    amount=0,
                    status="failed",
                    error_message=response.text
                )
    
    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        """Verify Multicaixa webhook signature."""
        
        if not self.webhook_secret:
            logger.warning("Multicaixa webhook secret not configured")
            return True  # Allow in dev mode
        
        expected = hmac.new(
            self.webhook_secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected, signature)


class VisaMastercardAdapter(PaymentAdapter):
    """
    Visa/Mastercard adapter via Stripe or local acquirer.
    
    Using Stripe as default integration.
    """
    
    def __init__(self):
        self.api_key = os.getenv("STRIPE_SECRET_KEY")
        self.webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
        self.api_url = "https://api.stripe.com/v1"
    
    async def create_payment(self, intent: PaymentIntent) -> PaymentResult:
        """Create Stripe PaymentIntent."""
        
        if not self.api_key:
            logger.warning("Stripe not configured - returning mock response")
            return PaymentResult(
                success=True,
                payment_id=intent.id,
                status=PaymentStatus.PENDING,
                provider_reference=f"pi_{uuid.uuid4().hex[:24]}",
                redirect_url=None,
                raw_response={"mock": True}
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
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return PaymentResult(
                        success=True,
                        payment_id=intent.id,
                        status=PaymentStatus.PENDING,
                        provider_reference=data.get("id"),
                        raw_response=data
                    )
                else:
                    data = response.json()
                    return PaymentResult(
                        success=False,
                        payment_id=intent.id,
                        status=PaymentStatus.FAILED,
                        error_code=data.get("error", {}).get("code"),
                        error_message=data.get("error", {}).get("message"),
                    )
            except Exception as e:
                logger.error(f"Stripe API error: {e}")
                return PaymentResult(
                    success=False,
                    payment_id=intent.id,
                    status=PaymentStatus.FAILED,
                    error_message=str(e),
                )
    
    async def check_status(self, provider_reference: str) -> PaymentStatus:
        """Check Stripe PaymentIntent status."""
        
        if not self.api_key:
            return PaymentStatus.COMPLETED
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_url}/payment_intents/{provider_reference}",
                auth=(self.api_key, ""),
                timeout=10.0
            )
            
            if response.status_code == 200:
                data = response.json()
                status_map = {
                    "requires_payment_method": PaymentStatus.PENDING,
                    "requires_confirmation": PaymentStatus.PENDING,
                    "requires_action": PaymentStatus.PROCESSING,
                    "processing": PaymentStatus.PROCESSING,
                    "succeeded": PaymentStatus.COMPLETED,
                    "canceled": PaymentStatus.CANCELLED,
                }
                return status_map.get(data.get("status"), PaymentStatus.PENDING)
        
        return PaymentStatus.PENDING
    
    async def refund(self, provider_reference: str, amount: Optional[int] = None) -> RefundResult:
        """Create Stripe refund."""
        
        if not self.api_key:
            return RefundResult(
                success=True,
                refund_id=f"re_{uuid.uuid4().hex[:24]}",
                amount=amount or 0,
                status="succeeded"
            )
        
        async with httpx.AsyncClient() as client:
            data = {"payment_intent": provider_reference}
            if amount:
                data["amount"] = str(amount)
            
            response = await client.post(
                f"{self.api_url}/refunds",
                auth=(self.api_key, ""),
                data=data,
                timeout=30.0
            )
            
            if response.status_code == 200:
                result = response.json()
                return RefundResult(
                    success=True,
                    refund_id=result.get("id"),
                    amount=result.get("amount", amount or 0),
                    status=result.get("status", "succeeded")
                )
            else:
                return RefundResult(
                    success=False,
                    refund_id="",
                    amount=0,
                    status="failed",
                    error_message=response.text
                )
    
    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        """Verify Stripe webhook signature."""
        
        if not self.webhook_secret:
            logger.warning("Stripe webhook secret not configured")
            return True
        
        try:
            # Parse Stripe signature header
            # Format: t=timestamp,v1=signature
            parts = dict(p.split("=", 1) for p in signature.split(","))
            timestamp = parts.get("t")
            sig = parts.get("v1")
            
            if not timestamp or not sig:
                return False
            
            # Construct signed payload
            signed_payload = f"{timestamp}.{payload.decode()}"
            
            expected = hmac.new(
                self.webhook_secret.encode(),
                signed_payload.encode(),
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(expected, sig)
        except Exception as e:
            logger.error(f"Webhook verification error: {e}")
            return False


class IBANTransferAdapter(PaymentAdapter):
    """
    IBAN bank transfer adapter.
    
    Requires manual confirmation by admin.
    """
    
    def __init__(self):
        self.company_iban = os.getenv("COMPANY_IBAN")
        self.company_bic = os.getenv("COMPANY_BIC")
        self.company_bank_name = os.getenv("COMPANY_BANK_NAME", "Banco de Fomento Angola")
    
    async def create_payment(self, intent: PaymentIntent) -> PaymentResult:
        """Create bank transfer request."""
        
        reference = f"GV-{intent.order_id[-8:].upper()}"
        
        return PaymentResult(
            success=True,
            payment_id=intent.id,
            status=PaymentStatus.AWAITING_CONFIRMATION,
            provider_reference=reference,
            raw_response={
                "transfer_details": {
                    "iban": self.company_iban or "AO06004400005506300102101",
                    "bic": self.company_bic or "BFAOAOAO",
                    "bank_name": self.company_bank_name,
                    "beneficiary": "GeoVision Lda",
                    "reference": reference,
                    "amount": intent.amount / 100,  # Convert to main unit
                    "currency": intent.currency.value,
                },
                "instructions": "Please include the reference in your transfer description. "
                               "Payment will be confirmed within 1-2 business days after receipt."
            }
        )
    
    async def check_status(self, provider_reference: str) -> PaymentStatus:
        """Check bank transfer status - always awaiting unless manually confirmed."""
        return PaymentStatus.AWAITING_CONFIRMATION
    
    async def refund(self, provider_reference: str, amount: Optional[int] = None) -> RefundResult:
        """Bank transfer refund - manual process."""
        return RefundResult(
            success=True,
            refund_id=f"BANK-REF-{uuid.uuid4().hex[:8]}",
            amount=amount or 0,
            status="pending_manual_transfer",
            error_message="Refund will be processed manually via bank transfer"
        )
    
    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        """No webhooks for bank transfers."""
        return True


# ============ PAYMENT ORCHESTRATOR ============

class PaymentOrchestrator:
    """
    Main payment orchestration service.
    
    Handles provider selection, idempotency, and status tracking.
    """
    
    def __init__(self):
        self.adapters: Dict[PaymentProvider, PaymentAdapter] = {
            PaymentProvider.MULTICAIXA_EXPRESS: MulticaixaExpressAdapter(),
            PaymentProvider.VISA_MASTERCARD: VisaMastercardAdapter(),
            PaymentProvider.IBAN_TRANSFER: IBANTransferAdapter(),
        }
        
        # In-memory payment storage (replace with DB)
        self._payments: Dict[str, PaymentIntent] = {}
        self._idempotency_cache: Dict[str, str] = {}  # key -> payment_id
    
    def _get_adapter(self, provider: PaymentProvider) -> PaymentAdapter:
        """Get adapter for provider."""
        adapter = self.adapters.get(provider)
        if not adapter:
            raise ValueError(f"Unknown provider: {provider}")
        return adapter
    
    async def create_payment(
        self,
        company_id: str,
        order_id: str,
        amount: int,
        currency: Currency,
        provider: PaymentProvider,
        description: str,
        metadata: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> PaymentResult:
        """
        Create a new payment.
        
        Args:
            company_id: Company ID
            order_id: Order ID
            amount: Amount in smallest unit (centavos/cents)
            currency: Currency code
            provider: Payment provider
            description: Payment description
            metadata: Additional metadata
            idempotency_key: Key for idempotent requests
        
        Returns:
            PaymentResult with status and provider details
        """
        
        # Check idempotency
        if idempotency_key:
            existing_id = self._idempotency_cache.get(idempotency_key)
            if existing_id and existing_id in self._payments:
                existing = self._payments[existing_id]
                return PaymentResult(
                    success=True,
                    payment_id=existing.id,
                    status=existing.status,
                    provider_reference=existing.provider_reference,
                )
        
        # Create intent
        payment_id = str(uuid.uuid4())
        intent = PaymentIntent(
            id=payment_id,
            company_id=company_id,
            order_id=order_id,
            amount=amount,
            currency=currency,
            provider=provider,
            description=description,
            metadata=metadata or {},
            idempotency_key=idempotency_key,
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        
        # Process with provider
        adapter = self._get_adapter(provider)
        result = await adapter.create_payment(intent)
        
        # Update intent with result
        intent.status = result.status
        intent.provider_reference = result.provider_reference
        intent.updated_at = datetime.utcnow()
        
        # Store
        self._payments[payment_id] = intent
        if idempotency_key:
            self._idempotency_cache[idempotency_key] = payment_id
        
        logger.info(f"Created payment {payment_id} via {provider.value}: {result.status.value}")
        
        return result
    
    async def check_status(self, payment_id: str) -> Optional[PaymentStatus]:
        """Check payment status."""
        
        intent = self._payments.get(payment_id)
        if not intent:
            return None
        
        # For completed/failed payments, return cached status
        if intent.status in [PaymentStatus.COMPLETED, PaymentStatus.FAILED, 
                             PaymentStatus.CANCELLED, PaymentStatus.REFUNDED]:
            return intent.status
        
        # Check with provider
        adapter = self._get_adapter(intent.provider)
        if intent.provider_reference:
            status = await adapter.check_status(intent.provider_reference)
            intent.status = status
            intent.updated_at = datetime.utcnow()
        
        return intent.status
    
    async def confirm_iban_transfer(
        self,
        payment_id: str,
        confirmed_by: str,
        bank_reference: Optional[str] = None
    ) -> bool:
        """Manually confirm IBAN transfer (admin action)."""
        
        intent = self._payments.get(payment_id)
        if not intent:
            return False
        
        if intent.provider != PaymentProvider.IBAN_TRANSFER:
            return False
        
        intent.status = PaymentStatus.COMPLETED
        intent.updated_at = datetime.utcnow()
        intent.metadata["confirmed_by"] = confirmed_by
        intent.metadata["confirmed_at"] = datetime.utcnow().isoformat()
        if bank_reference:
            intent.metadata["bank_reference"] = bank_reference
        
        logger.info(f"IBAN transfer {payment_id} confirmed by {confirmed_by}")
        
        return True
    
    async def refund(
        self,
        payment_id: str,
        amount: Optional[int] = None,
        reason: Optional[str] = None
    ) -> RefundResult:
        """Process refund."""
        
        intent = self._payments.get(payment_id)
        if not intent:
            return RefundResult(
                success=False,
                refund_id="",
                amount=0,
                status="failed",
                error_message="Payment not found"
            )
        
        if intent.status not in [PaymentStatus.COMPLETED, PaymentStatus.PARTIALLY_REFUNDED]:
            return RefundResult(
                success=False,
                refund_id="",
                amount=0,
                status="failed",
                error_message=f"Cannot refund payment with status: {intent.status.value}"
            )
        
        adapter = self._get_adapter(intent.provider)
        provider_ref = intent.provider_reference or ""
        result = await adapter.refund(provider_ref, amount)
        
        if result.success:
            if amount and amount < intent.amount:
                intent.status = PaymentStatus.PARTIALLY_REFUNDED
            else:
                intent.status = PaymentStatus.REFUNDED
            intent.updated_at = datetime.utcnow()
            intent.metadata["refund_reason"] = reason
            
            logger.info(f"Refunded payment {payment_id}: {result.amount}")
        
        return result
    
    async def handle_webhook(
        self,
        provider: PaymentProvider,
        payload: bytes,
        signature: str
    ) -> Dict[str, Any]:
        """Handle webhook from payment provider."""
        
        adapter = self._get_adapter(provider)
        
        # Verify signature
        if not adapter.verify_webhook(payload, signature):
            logger.warning(f"Invalid webhook signature for {provider.value}")
            return {"status": "error", "message": "Invalid signature"}
        
        # Parse payload (provider-specific)
        import json
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return {"status": "error", "message": "Invalid JSON"}
        
        # Find payment by provider reference
        provider_ref = None
        new_status = None
        
        if provider == PaymentProvider.MULTICAIXA_EXPRESS:
            provider_ref = data.get("payment_id")
            status_map = {
                "completed": PaymentStatus.COMPLETED,
                "failed": PaymentStatus.FAILED,
                "expired": PaymentStatus.CANCELLED,
            }
            new_status = status_map.get(data.get("status"))
        
        elif provider == PaymentProvider.VISA_MASTERCARD:
            # Stripe webhook format
            event_type = data.get("type")
            if event_type == "payment_intent.succeeded":
                provider_ref = data.get("data", {}).get("object", {}).get("id")
                new_status = PaymentStatus.COMPLETED
            elif event_type == "payment_intent.payment_failed":
                provider_ref = data.get("data", {}).get("object", {}).get("id")
                new_status = PaymentStatus.FAILED
        
        if provider_ref and new_status:
            # Find and update payment
            for intent in self._payments.values():
                if intent.provider_reference == provider_ref:
                    old_status = intent.status
                    intent.status = new_status
                    intent.updated_at = datetime.utcnow()
                    
                    logger.info(
                        f"Webhook updated payment {intent.id}: "
                        f"{old_status.value} -> {new_status.value}"
                    )
                    
                    return {
                        "status": "ok",
                        "payment_id": intent.id,
                        "new_status": new_status.value
                    }
        
        return {"status": "ok", "message": "No matching payment found"}
    
    def get_payment(self, payment_id: str) -> Optional[PaymentIntent]:
        """Get payment by ID."""
        return self._payments.get(payment_id)
    
    def list_payments(
        self,
        company_id: Optional[str] = None,
        status: Optional[PaymentStatus] = None,
        provider: Optional[PaymentProvider] = None,
        limit: int = 50
    ) -> List[PaymentIntent]:
        """List payments with filters."""
        
        payments = list(self._payments.values())
        
        if company_id:
            payments = [p for p in payments if p.company_id == company_id]
        if status:
            payments = [p for p in payments if p.status == status]
        if provider:
            payments = [p for p in payments if p.provider == provider]
        
        # Sort by created_at descending
        payments.sort(key=lambda p: p.created_at, reverse=True)
        
        return payments[:limit]


# Singleton instance
_payment_orchestrator: Optional[PaymentOrchestrator] = None


def get_payment_orchestrator() -> PaymentOrchestrator:
    """Get or create payment orchestrator instance."""
    global _payment_orchestrator
    if _payment_orchestrator is None:
        _payment_orchestrator = PaymentOrchestrator()
    return _payment_orchestrator
