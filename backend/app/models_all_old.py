# app/models_all.py
"""
Unified Models Import for GeoVision Platform

This module consolidates all models from the platform for:
- Easy import in routers and services
- Alembic migration generation
- Database initialization

Usage:
    from app.models_all import (
        User, Company, Site, Dataset, Document,
        PaymentIntent, PaymentTransaction,
        RiskScore, RiskAlert,
        Product, Order, Cart,
        ...
    )
"""

# ============ CORE MODELS ============
from .models import (
    User,
    UserProfile,
    UserAddress,
    Account,
    AccountMember,
    Category,
    Product,
    ProductImage,
    Inventory,
    Order,
    OrderItem,
    ResetToken,
    OAuthState,
    Profile,  # Alias for UserProfile
)

# ============ ENTERPRISE MODELS ============
from .models_enterprise import (
    # Enums
    CompanyStatus,
    SubscriptionPlan,
    UserRole,
    DocumentType,
    DocumentStatus,
    ConnectorType,
    SyncStatus,
    AlertSeverity,
    # Models
    Company,
    CompanyMember,
    Site,
    Dataset,
    Document,
    SoftwareConnector,
    Alert,
    Invoice,
    AuditLog,
    AdminContact,
    TwoFactorAuth,
)

# ============ SHOP MODELS ============
from .models_shop import (
    # Enums
    ProductType,
    ProductCategory,
    OrderStatus,
    PaymentMethod,
    DeliverableType,
    EventType,
    # Models - Using aliases to avoid conflicts
    Product as ShopProduct,
    ProductVariant,
    Cart,
    CartItem,
    Order as ShopOrder,
    OrderItem as ShopOrderItem,
    OrderEvent,
    Deliverable,
    Invoice as ShopInvoice,
    Coupon,
    TaxRate,
    DeliveryZone,
    PaymentProof,
)

# ============ PAYMENT MODELS ============
from .models_payments import (
    # Enums
    PaymentProviderType,
    PaymentIntentStatus,
    TransactionType,
    TransactionStatus,
    RefundReason,
    # Models
    PaymentProvider,
    PaymentIntent,
    PaymentTransaction,
    PaymentWebhookEvent,
    BankTransferReconciliation,
    PaymentRefund,
    Payout,
)

# ============ RISK & ANALYTICS MODELS ============
from .models_risk import (
    # Enums
    RiskLevel,
    RiskCategory,
    AlertStatus,
    AlertPriority,
    NotificationType,
    # Models
    RiskScore,
    RiskAlert,
    AlertEvent,
    AlertNotification,
    SiteMetrics,
    AlertRule,
    SectorThreshold,
)

# ============ ALL MODEL CLASSES (for Alembic) ============
ALL_MODELS = [
    # Core
    User,
    UserProfile,
    UserAddress,
    Account,
    AccountMember,
    Category,
    Product,
    ProductImage,
    Inventory,
    Order,
    OrderItem,
    ResetToken,
    OAuthState,
    # Enterprise
    Company,
    CompanyMember,
    Site,
    Dataset,
    Document,
    SoftwareConnector,
    Alert,
    Invoice,
    AuditLog,
    AdminContact,
    TwoFactorAuth,
    # Shop
    ShopProduct,
    ProductVariant,
    Cart,
    CartItem,
    ShopOrder,
    ShopOrderItem,
    OrderEvent,
    Deliverable,
    ShopInvoice,
    Coupon,
    TaxRate,
    DeliveryZone,
    PaymentProof,
    # Payments
    PaymentProvider,
    PaymentIntent,
    PaymentTransaction,
    PaymentWebhookEvent,
    BankTransferReconciliation,
    PaymentRefund,
    Payout,
    # Risk
    RiskScore,
    RiskAlert,
    AlertEvent,
    AlertNotification,
    SiteMetrics,
    AlertRule,
    SectorThreshold,
]


# ============ ENTITY-RELATIONSHIP SUMMARY ============
"""
DATABASE ARCHITECTURE OVERVIEW
==============================

┌─────────────────────────────────────────────────────────────────────────────┐
│                              IDENTITY & TENANCY                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────┐    ┌──────────────────┐    ┌─────────┐                        │
│  │  User   │───▶│ CompanyMember    │◀───│ Company │                        │
│  └────┬────┘    └──────────────────┘    └────┬────┘                        │
│       │                                       │                              │
│       ▼                                       ▼                              │
│  ┌─────────────┐                        ┌─────────┐                         │
│  │ UserProfile │                        │  Site   │                         │
│  │ UserAddress │                        └────┬────┘                         │
│  │ TwoFactorAuth│                            │                              │
│  └─────────────┘                             ▼                              │
│                                         ┌─────────┐                         │
│                                         │ Dataset │                         │
│                                         └─────────┘                         │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                              E-COMMERCE FLOW                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────────┐    ┌──────────┐    ┌──────────┐    ┌──────────────┐        │
│  │ShopProduct │───▶│ CartItem │◀───│   Cart   │───▶│  ShopOrder   │        │
│  │  Variant   │    └──────────┘    └──────────┘    └──────┬───────┘        │
│  └────────────┘                                           │                 │
│                                                           ▼                 │
│  ┌────────────┐                              ┌────────────────────┐        │
│  │   Coupon   │─────────────────────────────▶│  ShopOrderItem     │        │
│  │   TaxRate  │                              │  OrderEvent        │        │
│  │DeliveryZone│                              │  Deliverable       │        │
│  └────────────┘                              │  ShopInvoice       │        │
│                                              └────────────────────┘        │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                              PAYMENT SYSTEM                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────┐    ┌───────────────┐    ┌────────────────────┐        │
│  │ PaymentProvider │───▶│ PaymentIntent │───▶│PaymentTransaction  │        │
│  └─────────────────┘    └───────┬───────┘    └────────────────────┘        │
│                                 │                                           │
│                                 ├────────────▶┌────────────────────┐        │
│                                 │             │  PaymentRefund     │        │
│                                 │             └────────────────────┘        │
│                                 │                                           │
│  ┌─────────────────────────┐   │             ┌────────────────────┐        │
│  │PaymentWebhookEvent      │◀──┴────────────▶│BankTransferRecon.  │        │
│  └─────────────────────────┘                 └────────────────────┘        │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                              RISK & ALERTS                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────┐    ┌───────────┐    ┌───────────┐                               │
│  │  Site  │───▶│ RiskScore │───▶│ RiskAlert │                               │
│  │Dataset │    └───────────┘    └─────┬─────┘                               │
│  └────────┘                           │                                      │
│                                       ├──────────▶┌────────────────┐        │
│                                       │           │  AlertEvent    │        │
│                                       │           └────────────────┘        │
│                                       │                                      │
│                                       └──────────▶┌────────────────┐        │
│                                                   │AlertNotification│       │
│  ┌──────────────┐                                └────────────────┘        │
│  │  AlertRule   │                                                           │
│  │SectorThreshold│─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─▶ (triggers RiskAlert)    │
│  └──────────────┘                                                           │
│                                                                              │
│  ┌──────────────┐                                                           │
│  │ SiteMetrics  │ (KPIs, time-series data)                                  │
│  └──────────────┘                                                           │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                              SECURITY & AUDIT                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────────┐                │
│  │  AuditLog   │    │ ResetToken   │    │ SoftwareConnector│               │
│  │  (actions)  │    │ OAuthState   │    │ (credentials enc)│               │
│  └─────────────┘    └──────────────┘    └─────────────────┘                │
│                                                                              │
│  ROLES:                                                                      │
│  - super_admin: GeoVision full access                                       │
│  - admin: GeoVision admin                                                   │
│  - manager: GeoVision day-to-day                                           │
│  - analyst: GeoVision read + reports                                       │
│  - client_admin: Client org admin                                          │
│  - client_manager: Client manager                                          │
│  - client_viewer: Client read-only                                         │
└─────────────────────────────────────────────────────────────────────────────┘

KEY RELATIONSHIPS:
==================
- Company has many Sites, each Site has many Datasets
- All entities have company_id for multi-tenant isolation
- Orders link to PaymentIntents for payment tracking
- RiskScores generate RiskAlerts based on AlertRules
- AuditLog tracks all significant actions across the system
- Documents can belong to Company, Site, or Dataset

INDICES (for performance):
=========================
- company_id on all tenant-scoped tables
- site_id for site-level queries
- created_at for time-based queries
- status fields for filtering
- email for user lookups
"""
