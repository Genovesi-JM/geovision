"""
Payments Router

Multi-provider payment processing endpoints:
- Multicaixa Express (Angola)
- Visa/Mastercard (Stripe)
- IBAN Bank Transfer

Admin endpoints for:
- Transfer confirmation
- Reconciliation
- Refund processing
"""
import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Header, Request
from pydantic import BaseModel, Field

from sqlalchemy.orm import Session
from app.database import get_db
from app.deps import get_current_user, require_admin
from app.models import User

from app.services.payments import (
    get_payment_orchestrator,
    PaymentProvider,
    PaymentStatus,
    Currency,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])


# ============ SCHEMAS ============

class PaymentCreateRequest(BaseModel):
    """Request to create a payment."""
    company_id: str
    order_id: str
    amount: int = Field(..., gt=0, description="Amount in smallest currency unit (centavos/cents)")
    currency: Currency = Currency.AOA
    provider: PaymentProvider
    description: str = Field(..., max_length=500)
    metadata: Optional[dict] = None
    idempotency_key: Optional[str] = Field(None, max_length=100)


class PaymentResponse(BaseModel):
    """Payment creation response."""
    success: bool
    payment_id: str
    status: str
    provider_reference: Optional[str] = None
    redirect_url: Optional[str] = None
    qr_code: Optional[str] = None
    transfer_details: Optional[dict] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class PaymentStatusResponse(BaseModel):
    """Payment status response."""
    payment_id: str
    status: str
    provider: str
    amount: int
    currency: str
    created_at: datetime
    updated_at: datetime


class RefundRequest(BaseModel):
    """Refund request."""
    amount: Optional[int] = Field(None, gt=0, description="Partial refund amount, or null for full refund")
    reason: Optional[str] = Field(None, max_length=500)


class RefundResponse(BaseModel):
    """Refund response."""
    success: bool
    refund_id: str
    amount: int
    status: str
    error_message: Optional[str] = None


class IBANConfirmRequest(BaseModel):
    """IBAN transfer confirmation request."""
    confirmed_by: str = Field(..., description="Admin user ID")
    bank_reference: Optional[str] = Field(None, description="Bank transfer reference")


class PaymentListResponse(BaseModel):
    """List of payments."""
    payments: List[PaymentStatusResponse]
    total: int


class ProviderConfigResponse(BaseModel):
    """Provider configuration status."""
    provider: str
    configured: bool
    test_mode: bool
    supported_currencies: List[str]


# ============ ENDPOINTS ============

@router.post("/", response_model=PaymentResponse)
async def create_payment(request: PaymentCreateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Create a new payment.
    
    **Providers:**
    
    - `multicaixa_express`: Returns QR code for mobile payment
    - `visa_mastercard`: Returns payment intent for Stripe.js
    - `iban_transfer`: Returns bank transfer details
    
    **Idempotency:**
    
    Use `idempotency_key` to safely retry failed requests.
    Same key returns the original result without creating duplicate payments.
    """
    orchestrator = get_payment_orchestrator(db)
    
    result = await orchestrator.create_payment(
        company_id=request.company_id,
        order_id=request.order_id,
        amount=request.amount,
        currency=request.currency,
        provider=request.provider,
        description=request.description,
        metadata=request.metadata,
        idempotency_key=request.idempotency_key,
    )
    
    response = PaymentResponse(
        success=result.success,
        payment_id=result.payment_id,
        status=result.status.value,
        provider_reference=result.provider_reference,
        redirect_url=result.redirect_url,
        qr_code=result.qr_code,
        error_code=result.error_code,
        error_message=result.error_message,
    )
    
    # Add transfer details for IBAN
    if request.provider == PaymentProvider.IBAN_TRANSFER and result.raw_response:
        response.transfer_details = result.raw_response.get("transfer_details")
    
    return response


@router.get("/{payment_id}", response_model=PaymentStatusResponse)
async def get_payment_status(payment_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get payment status."""
    
    orchestrator = get_payment_orchestrator(db)
    
    payment = orchestrator.get_payment(payment_id)
    
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    # Poll provider for latest status
    await orchestrator.check_status(payment_id)
    
    return PaymentStatusResponse(
        payment_id=payment.id,
        status=payment.status.value,
        provider=payment.provider.value,
        amount=payment.amount,
        currency=payment.currency.value,
        created_at=payment.created_at,
        updated_at=payment.updated_at,
    )


@router.get("/", response_model=PaymentListResponse)
async def list_payments(
    company_id: Optional[str] = Query(None),
    status: Optional[PaymentStatus] = Query(None),
    provider: Optional[PaymentProvider] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List payments with filters."""
    
    orchestrator = get_payment_orchestrator(db)
    
    payments = orchestrator.list_payments(
        company_id=company_id,
        status=status,
        provider=provider,
        limit=limit,
    )
    
    return PaymentListResponse(
        payments=[
            PaymentStatusResponse(
                payment_id=p.id,
                status=p.status.value,
                provider=p.provider.value,
                amount=p.amount,
                currency=p.currency.value,
                created_at=p.created_at,
                updated_at=p.updated_at,
            )
            for p in payments
        ],
        total=len(payments),
    )


@router.post("/{payment_id}/refund", response_model=RefundResponse)
async def refund_payment(payment_id: str, request: RefundRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """
    Refund a payment.
    
    - Full refund: Omit `amount`
    - Partial refund: Specify `amount` in smallest currency unit
    """
    
    orchestrator = get_payment_orchestrator(db)
    
    result = await orchestrator.refund(
        payment_id=payment_id,
        amount=request.amount,
        reason=request.reason,
    )
    
    if not result.success:
        raise HTTPException(
            status_code=400,
            detail=result.error_message or "Refund failed"
        )
    
    return RefundResponse(
        success=result.success,
        refund_id=result.refund_id,
        amount=result.amount,
        status=result.status,
        error_message=result.error_message,
    )


# ============ ADMIN ENDPOINTS ============

@router.post("/{payment_id}/confirm-transfer")
async def confirm_iban_transfer(payment_id: str, request: IBANConfirmRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """
    **Admin only**: Confirm IBAN bank transfer receipt.
    
    Use this after verifying the bank transfer was received.
    """
    
    orchestrator = get_payment_orchestrator(db)
    
    payment = orchestrator.get_payment(payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    if payment.provider != PaymentProvider.IBAN_TRANSFER:
        raise HTTPException(
            status_code=400,
            detail="Only IBAN transfers require manual confirmation"
        )
    
    success = await orchestrator.confirm_iban_transfer(
        payment_id=payment_id,
        confirmed_by=request.confirmed_by,
        bank_reference=request.bank_reference,
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to confirm transfer")
    
    return {
        "message": "Transfer confirmed",
        "payment_id": payment_id,
        "confirmed_by": request.confirmed_by,
        "confirmed_at": datetime.utcnow().isoformat(),
    }


@router.get("/admin/pending-transfers")
async def list_pending_transfers(
    company_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    **Admin only**: List IBAN transfers awaiting confirmation.
    """
    
    orchestrator = get_payment_orchestrator(db)
    
    payments = orchestrator.list_payments(
        company_id=company_id,
        status=PaymentStatus.AWAITING_CONFIRMATION,
        provider=PaymentProvider.IBAN_TRANSFER,
        limit=limit,
    )
    
    return {
        "pending_transfers": [
            {
                "payment_id": p.id,
                "company_id": p.company_id,
                "order_id": p.order_id,
                "amount": p.amount,
                "currency": p.currency.value,
                "reference": p.provider_reference,
                "created_at": p.created_at.isoformat(),
            }
            for p in payments
        ],
        "total": len(payments),
    }


@router.get("/admin/reconciliation")
async def get_reconciliation_report(
    company_id: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    **Admin only**: Get reconciliation report.
    
    Shows payment totals by status and provider.
    """
    
    orchestrator = get_payment_orchestrator(db)
    
    # Get all payments
    all_payments = orchestrator.list_payments(
        company_id=company_id,
        limit=10000,
    )
    
    # Filter by date if provided
    if start_date:
        all_payments = [p for p in all_payments if p.created_at >= start_date]
    if end_date:
        all_payments = [p for p in all_payments if p.created_at <= end_date]
    
    # Aggregate by status
    by_status = {}
    for p in all_payments:
        status = p.status.value
        if status not in by_status:
            by_status[status] = {"count": 0, "total_aoa": 0, "total_usd": 0, "total_eur": 0}
        by_status[status]["count"] += 1
        if p.currency == Currency.AOA:
            by_status[status]["total_aoa"] += p.amount
        elif p.currency == Currency.USD:
            by_status[status]["total_usd"] += p.amount
        elif p.currency == Currency.EUR:
            by_status[status]["total_eur"] += p.amount
    
    # Aggregate by provider
    by_provider = {}
    for p in all_payments:
        provider = p.provider.value
        if provider not in by_provider:
            by_provider[provider] = {"count": 0, "completed": 0, "total_amount": 0}
        by_provider[provider]["count"] += 1
        if p.status == PaymentStatus.COMPLETED:
            by_provider[provider]["completed"] += 1
            by_provider[provider]["total_amount"] += p.amount
    
    return {
        "period": {
            "start": start_date.isoformat() if start_date else None,
            "end": end_date.isoformat() if end_date else None,
        },
        "total_payments": len(all_payments),
        "by_status": by_status,
        "by_provider": by_provider,
    }


# ============ WEBHOOKS ============

@router.post("/webhooks/multicaixa")
async def multicaixa_webhook(
    request: Request,
    x_multicaixa_signature: str = Header(..., alias="X-Multicaixa-Signature"),
    db: Session = Depends(get_db),
):
    """Webhook endpoint for Multicaixa Express."""
    
    orchestrator = get_payment_orchestrator(db)
    payload = await request.body()
    
    result = await orchestrator.handle_webhook(
        provider=PaymentProvider.MULTICAIXA_EXPRESS,
        payload=payload,
        signature=x_multicaixa_signature,
    )
    
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message"))
    
    return result


@router.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(..., alias="Stripe-Signature"),
    db: Session = Depends(get_db),
):
    """Webhook endpoint for Stripe (Visa/Mastercard)."""
    
    orchestrator = get_payment_orchestrator(db)
    payload = await request.body()
    
    result = await orchestrator.handle_webhook(
        provider=PaymentProvider.VISA_MASTERCARD,
        payload=payload,
        signature=stripe_signature,
    )
    
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message"))
    
    return result


# ============ PROVIDER CONFIG ============

@router.get("/providers", response_model=List[ProviderConfigResponse])
async def list_providers():
    """
    List available payment providers and configuration status.
    """
    import os
    
    providers = [
        ProviderConfigResponse(
            provider="multicaixa_express",
            configured=bool(os.getenv("MULTICAIXA_API_KEY")),
            test_mode=not bool(os.getenv("MULTICAIXA_API_KEY")),
            supported_currencies=["AOA"],
        ),
        ProviderConfigResponse(
            provider="visa_mastercard",
            configured=bool(os.getenv("STRIPE_SECRET_KEY")),
            test_mode="test" in (os.getenv("STRIPE_SECRET_KEY") or "test"),
            supported_currencies=["USD", "EUR", "AOA"],
        ),
        ProviderConfigResponse(
            provider="iban_transfer",
            configured=bool(os.getenv("COMPANY_IBAN")),
            test_mode=False,  # Always production
            supported_currencies=["AOA", "USD", "EUR"],
        ),
    ]
    
    return providers
