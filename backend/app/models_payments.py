# app/models_payments.py
"""
Payment System Models for GeoVision Platform

Supports:
- Multiple payment providers (Multicaixa, Visa/MC, IBAN)
- Payment intents and transactions
- Webhook event logging
- Bank transfer reconciliation
- Refunds
- Idempotent and auditable operations
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional
from enum import Enum

from sqlalchemy import (
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
    Integer,
    Index,
    JSON,
    Enum as SQLEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _uuid():
    return str(uuid.uuid4())


# ============ ENUMS ============

class PaymentProviderType(str, Enum):
    MULTICAIXA_EXPRESS = "multicaixa_express"
    VISA_MASTERCARD = "visa_mastercard"
    IBAN_AO = "iban_ao"
    IBAN_INTERNATIONAL = "iban_international"
    MANUAL = "manual"


class PaymentIntentStatus(str, Enum):
    CREATED = "created"
    PENDING = "pending"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"
    EXPIRED = "expired"


class TransactionType(str, Enum):
    CHARGE = "charge"
    CAPTURE = "capture"
    REFUND = "refund"
    VOID = "void"
    TRANSFER = "transfer"
    FEE = "fee"
    ADJUSTMENT = "adjustment"


class TransactionStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RefundReason(str, Enum):
    CUSTOMER_REQUEST = "customer_request"
    DUPLICATE = "duplicate"
    FRAUDULENT = "fraudulent"
    SERVICE_NOT_DELIVERED = "service_not_delivered"
    PRODUCT_DEFECTIVE = "product_defective"
    OTHER = "other"


# ============ PAYMENT PROVIDERS ============

class PaymentProvider(Base):
    """
    Configuration for payment providers.
    System-level config, not per-company.
    """
    __tablename__ = "payment_providers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    
    # Provider Info
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(50), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Configuration (encrypted in production)
    api_key_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    api_secret_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    merchant_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    terminal_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Endpoints
    api_base_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    webhook_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    webhook_secret: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # IBAN config (for bank transfers)
    bank_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    iban: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    swift_bic: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    account_holder: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # Fees
    fee_percentage: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0)
    fee_fixed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # In smallest unit
    
    # Currencies
    supported_currencies: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    default_currency: Mapped[str] = mapped_column(String(3), nullable=False, default="AOA")
    
    # Limits
    min_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    max_amount: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_test_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    
    # Settings
    settings: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_payment_providers_type", "provider_type"),
        Index("idx_payment_providers_active", "is_active"),
    )


# ============ PAYMENT INTENTS ============

class PaymentIntent(Base):
    """
    A payment intention for an order.
    Tracks the full payment lifecycle.
    """
    __tablename__ = "payment_intents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    
    # Idempotency
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    
    # Links
    order_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    company_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Provider
    provider_id: Mapped[str] = mapped_column(String(36), ForeignKey("payment_providers.id"), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Amount
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # In smallest currency unit
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="AOA")
    
    # Fees
    provider_fee: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    platform_fee: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    net_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    # Status
    status: Mapped[str] = mapped_column(String(30), nullable=False, default=PaymentIntentStatus.CREATED.value)
    
    # Provider References
    provider_intent_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    provider_reference: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # IBAN specific
    bank_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)  # Payment reference
    
    # Multicaixa specific
    entity_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    payment_reference: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Card specific
    last_four: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    card_brand: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # Timing
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    failed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Error handling
    failure_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    failure_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Metadata
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    metadata: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    
    # Refund tracking
    refunded_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    provider = relationship("PaymentProvider")
    user = relationship("User")
    transactions = relationship("PaymentTransaction", back_populates="payment_intent", cascade="all, delete-orphan")
    refunds = relationship("PaymentRefund", back_populates="payment_intent", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_payment_intents_order", "order_id"),
        Index("idx_payment_intents_status", "status"),
        Index("idx_payment_intents_provider", "provider_id"),
        Index("idx_payment_intents_created", "created_at"),
    )


# ============ PAYMENT TRANSACTIONS ============

class PaymentTransaction(Base):
    """
    Individual transaction records.
    Each payment intent can have multiple transactions.
    """
    __tablename__ = "payment_transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    
    payment_intent_id: Mapped[str] = mapped_column(String(36), ForeignKey("payment_intents.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Transaction Type
    transaction_type: Mapped[str] = mapped_column(String(30), nullable=False)
    
    # Amount
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="AOA")
    
    # Status
    status: Mapped[str] = mapped_column(String(30), nullable=False, default=TransactionStatus.PENDING.value)
    
    # Provider Data
    provider_transaction_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    provider_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    
    # Result
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Request/Response tracking (for debugging)
    request_payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    response_payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    
    # Timing
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    payment_intent = relationship("PaymentIntent", back_populates="transactions")

    __table_args__ = (
        Index("idx_payment_transactions_intent", "payment_intent_id"),
        Index("idx_payment_transactions_type", "transaction_type"),
        Index("idx_payment_transactions_status", "status"),
    )


# ============ WEBHOOK EVENTS ============

class PaymentWebhookEvent(Base):
    """
    Log of all webhook events received from payment providers.
    Ensures idempotent processing.
    """
    __tablename__ = "payment_webhook_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    
    # Provider Info
    provider_type: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    
    # Event Data
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # JSON - raw webhook body
    
    # Processing
    processed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    process_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Linked entities
    payment_intent_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    order_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    
    # Request Info
    ip_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    signature_valid: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        Index("idx_webhook_events_provider", "provider_type"),
        Index("idx_webhook_events_processed", "processed"),
        Index("idx_webhook_events_type", "event_type"),
    )


# ============ BANK TRANSFER RECONCILIATION ============

class BankTransferReconciliation(Base):
    """
    Reconciliation of bank transfer payments.
    Links bank statements to payment intents.
    """
    __tablename__ = "bank_transfer_reconciliations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    
    payment_intent_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("payment_intents.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Bank Statement Info
    bank_name: Mapped[str] = mapped_column(String(200), nullable=False)
    statement_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    statement_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Transaction Details
    sender_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    sender_iban: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    payment_reference: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    
    # Amount
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="AOA")
    
    # Matching
    matched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    matched_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    matched_by_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    match_confidence: Mapped[Optional[float]] = mapped_column(Numeric(3, 2), nullable=True)  # 0.00 to 1.00
    
    # Status
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    # pending, matched, unmatched, disputed
    
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    payment_intent = relationship("PaymentIntent")

    __table_args__ = (
        Index("idx_reconciliation_reference", "payment_reference"),
        Index("idx_reconciliation_matched", "matched"),
        Index("idx_reconciliation_status", "status"),
    )


# ============ REFUNDS ============

class PaymentRefund(Base):
    """
    Refund records for payments.
    """
    __tablename__ = "payment_refunds"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    
    payment_intent_id: Mapped[str] = mapped_column(String(36), ForeignKey("payment_intents.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Idempotency
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    
    # Amount
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="AOA")
    
    # Reason
    reason: Mapped[str] = mapped_column(String(50), nullable=False, default=RefundReason.CUSTOMER_REQUEST.value)
    reason_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Status
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    # pending, processing, succeeded, failed
    
    # Provider
    provider_refund_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # Processing
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    failed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Actor
    requested_by_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    # Metadata
    metadata: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    payment_intent = relationship("PaymentIntent", back_populates="refunds")
    requested_by = relationship("User", foreign_keys=[requested_by_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])

    __table_args__ = (
        Index("idx_refunds_intent", "payment_intent_id"),
        Index("idx_refunds_status", "status"),
    )


# ============ PAYOUT (for future marketplace) ============

class Payout(Base):
    """
    Payouts to vendors/partners (future marketplace feature).
    """
    __tablename__ = "payouts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    
    # Recipient
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    
    # Amount
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="AOA")
    
    # Bank Details
    bank_name: Mapped[str] = mapped_column(String(200), nullable=False)
    iban: Mapped[str] = mapped_column(String(50), nullable=False)
    swift_bic: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    account_holder: Mapped[str] = mapped_column(String(200), nullable=False)
    
    # Status
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    # pending, processing, sent, completed, failed
    
    # Reference
    payout_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Timing
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Actor
    approved_by_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    
    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_payouts_company", "company_id"),
        Index("idx_payouts_status", "status"),
    )
