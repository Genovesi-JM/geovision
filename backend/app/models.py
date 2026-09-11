# app/models.py
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional
from urllib.parse import urlsplit

from sqlalchemy import (
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Numeric,
    Integer,
    CheckConstraint,
    Float,
    UniqueConstraint,
    Index,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym, validates

from .core.database import Base
from .core.time import utc_now


def _uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String, nullable=False, default="client")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Incremented after credential-changing security events. Every GeoVision
    # access/refresh session is bound to the generation it was issued from.
    auth_generation: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    profile = relationship(
        "UserProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    addresses = relationship(
        "UserAddress", back_populates="user", cascade="all, delete-orphan"
    )
    orders = relationship("Order", back_populates="user")
    account_members = relationship(
        "AccountMember",
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="AccountMember.user_id",
        overlaps="accounts,users",
    )
    accounts = relationship(
        "Account",
        secondary="account_members",
        primaryjoin="User.id == AccountMember.user_id",
        secondaryjoin="Account.id == AccountMember.account_id",
        back_populates="users",
        overlaps="account_members,members",
    )
    internal_role_assignments = relationship(
        "InternalRoleAssignment",
        foreign_keys="InternalRoleAssignment.user_id",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index(
            "ix_users_email_normalized",
            func.lower(func.trim(email)),
            unique=True,
        ),
    )

    @property
    def memberships(self):
        return self.account_members


class InternalRoleAssignment(Base):
    """A GeoVision staff role kept separate from customer memberships."""

    __tablename__ = "internal_role_assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="1",
    )
    assigned_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("user_id", "role", name="uq_internal_role_user_role"),
        CheckConstraint(
            "role IN ('GV_SUPER_ADMIN', 'GV_OPERATIONS', 'GV_ANALYST', "
            "'GV_SUPPORT', 'GV_FINANCE', 'GV_INVENTORY', 'GV_SALES')",
            name="ck_internal_role_name",
        ),
    )


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    full_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    entity_type: Mapped[str] = mapped_column(
        String, nullable=False, default="individual"
    )
    org_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    company: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    nif: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    user = relationship("User", back_populates="profile")


class UserAddress(Base):
    __tablename__ = "user_addresses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label: Mapped[str] = mapped_column(String, default="Default", nullable=False)
    line1: Mapped[str] = mapped_column(String, nullable=False)
    line2: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    city: Mapped[str] = mapped_column(String, nullable=False)
    region: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    country: Mapped[str] = mapped_column(String, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    user = relationship("User", back_populates="addresses")


class Account(Base):
    __tablename__ = "accounts"
    # Alembic: `alembic revision --autogenerate -m "add accounts tables"` then `alembic upgrade head`

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    sector_focus: Mapped[str] = mapped_column(String, nullable=False)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    customer_type: Mapped[str] = mapped_column(String, nullable=False, default="farm")
    dashboard_profile: Mapped[str] = mapped_column(
        String, nullable=False, default="farm"
    )
    use_cases: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    org_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    modules_enabled: Mapped[str] = mapped_column(
        Text, nullable=False, default='["kpi","projects","store","alerts"]'
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        server_default="active",
    )
    # Set only on the one starter workspace created by onboarding. The unique
    # internal-user marker makes that operation durable and idempotent even on
    # databases (notably SQLite) where SELECT ... FOR UPDATE is ineffective.
    onboarding_user_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    members = relationship(
        "AccountMember",
        back_populates="account",
        cascade="all, delete-orphan",
        overlaps="accounts,users",
    )
    users = relationship(
        "User",
        secondary="account_members",
        primaryjoin="Account.id == AccountMember.account_id",
        secondaryjoin="User.id == AccountMember.user_id",
        back_populates="accounts",
        overlaps="account_members,members",
    )
    organization = relationship("Company", back_populates="workspaces")
    assets = relationship(
        "Asset",
        back_populates="workspace",
        foreign_keys="Asset.workspace_id",
    )

    __table_args__ = (
        UniqueConstraint(
            "id",
            "organization_id",
            name="uq_accounts_id_organization",
        ),
        Index("ix_accounts_onboarding_user_id", onboarding_user_id, unique=True),
    )


class AccountMember(Base):
    __tablename__ = "account_members"

    account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String, nullable=False, default="member")
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        server_default="active",
    )
    invited_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    invited_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    joined_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    account = relationship(
        "Account", back_populates="members", overlaps="accounts,users"
    )
    user = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="account_members",
        overlaps="accounts,users",
    )


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False)

    products = relationship("Product", back_populates="category")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    sku: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    brand: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    unit: Mapped[str] = mapped_column(String, default="un", nullable=False)

    price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String, default="AOA", nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    category_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )

    category = relationship("Category", back_populates="products")
    images = relationship(
        "ProductImage", back_populates="product", cascade="all, delete-orphan"
    )
    inventory = relationship(
        "Inventory",
        back_populates="product",
        uselist=False,
        cascade="all, delete-orphan",
    )


class ProductImage(Base):
    __tablename__ = "product_images"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    product_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    product = relationship("Product", back_populates="images")


class Inventory(Base):
    __tablename__ = "inventory"

    product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    qty_on_hand: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    qty_reserved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reorder_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    product = relationship("Product", back_populates="inventory")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    company_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    site_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    # Canonical commercial ownership. ``company_id``/``site_id`` remain as
    # compatibility aliases while callers move to organization/workspace IDs.
    organization_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    workspace_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    order_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="MIXED", server_default="MIXED", index=True
    )

    # ``status`` is the legacy projection consumed by existing clients. The
    # two canonical states below are authoritative and deliberately separate.
    fulfilment_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="DRAFT", server_default="DRAFT", index=True
    )
    payment_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="PENDING",
        server_default="PENDING",
        index=True,
    )
    previous_fulfilment_status: Mapped[Optional[str]] = mapped_column(
        String(30), nullable=True
    )
    lifecycle_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    checkout_idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(160), nullable=True, unique=True, index=True
    )

    status: Mapped[str] = mapped_column(String, default="pending", nullable=False)
    currency: Mapped[str] = mapped_column(String, default="AOA", nullable=False)

    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    shipping_fee: Mapped[float] = mapped_column(
        Numeric(12, 2), default=0, nullable=False
    )
    discount_total: Mapped[float] = mapped_column(
        Numeric(12, 2), default=0, nullable=False
    )
    total: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)

    # snapshot simples (em SQLite: guardamos JSON como texto)
    shipping_address_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Extended order fields
    order_number: Mapped[Optional[str]] = mapped_column(
        String(30), nullable=True, unique=True, index=True
    )
    payment_method: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    payment_intent_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    payment_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    payment_confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    coupon_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    tax_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    delivery_method: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    delivery_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    estimated_delivery: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    actual_delivery: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    assigned_team: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    scheduled_start: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    scheduled_end: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    actual_start: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    actual_end: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    customer_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    internal_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    billing_info_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    failed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    on_hold_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default="{}"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    user = relationship("User", back_populates="orders")
    items = relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("subtotal >= 0"),
        CheckConstraint("total >= 0"),
        CheckConstraint(
            "order_type IN ('PHYSICAL', 'SERVICE', 'MONITORING', 'MIXED')",
            name="ck_order_type",
        ),
        CheckConstraint(
            "fulfilment_status IN ('DRAFT', 'QUOTED', 'CONFIRMED', "
            "'PAYMENT_AUTHORIZED', 'PAID', 'SCHEDULING', 'ASSIGNED', "
            "'IN_PROGRESS', 'DATA_UPLOADED', 'PROCESSING', 'QA_REVIEW', "
            "'RESULTS_READY', 'DELIVERED', 'COMPLETED', 'CANCELLED', "
            "'FAILED', 'NEEDS_REFLIGHT', 'ON_HOLD')",
            name="ck_order_fulfilment_status",
        ),
        CheckConstraint(
            "payment_status IN ('NOT_REQUIRED', 'PENDING', 'AUTHORIZED', 'PAID', "
            "'FAILED', 'CANCELLED', 'PARTIALLY_REFUNDED', 'REFUNDED')",
            name="ck_order_payment_status",
        ),
        CheckConstraint("lifecycle_version > 0", name="ck_order_lifecycle_version"),
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    order_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    product_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    catalog_item_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        ForeignKey("catalog_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sku: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    product_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    catalog_item_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    currency: Mapped[str] = mapped_column(
        String(5), nullable=False, default="AOA", server_default="AOA"
    )
    pricing_snapshot_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    fulfilment_hints_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )

    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 4), nullable=True, default=0.14)
    tax_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=True, default=0)
    discount_amount: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0, server_default="0"
    )
    status: Mapped[Optional[str]] = mapped_column(
        String(30), nullable=True, default="pending"
    )
    scheduled_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    order = relationship("Order", back_populates="items")

    __table_args__ = (
        CheckConstraint("qty > 0"),
        CheckConstraint("unit_price >= 0"),
        CheckConstraint("line_total >= 0"),
        CheckConstraint(
            "discount_amount >= 0", name="ck_order_item_discount_nonnegative"
        ),
    )


class ResetToken(Base):
    __tablename__ = "reset_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # Historical column name remains ``token`` for a no-DDL transition, but
    # new rows store only a SHA-256 digest of the bearer secret.
    token_hash: Mapped[str] = mapped_column(
        "token",
        String,
        unique=True,
        index=True,
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # A reset link is valid only for the credential generation at which it was
    # issued. An atomic generation advance makes concurrent sibling links
    # mutually exclusive without relying on reset-token row lock ordering.
    auth_generation: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    user = relationship("User", foreign_keys=[user_id])


class OAuthState(Base):
    __tablename__ = "oauth_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    state: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    provider: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    code_verifier: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )


# â”€â”€ Auth Identity Linking (Google, Microsoft, etc.) â”€â”€


class AuthIdentity(Base):
    """Links external OAuth providers to local users (prevents duplicates)."""

    __tablename__ = "auth_identities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # google, microsoft
    # Compatibility key retained for legacy Google and Microsoft Graph rows.
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    issuer: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    subject: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    email_verified: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    display_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_data: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON dump of userinfo
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    user = relationship("User", backref="auth_identities")

    __table_args__ = (
        Index(
            "ix_auth_identities_provider_sub",
            "provider",
            "provider_user_id",
            unique=True,
        ),
        Index(
            "ix_auth_identities_issuer_subject",
            "issuer",
            "subject",
            unique=True,
        ),
    )


class RefreshTokenFamily(Base):
    """Authoritative state and identity provenance for one rotated session."""

    __tablename__ = "refresh_token_families"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    auth_identity_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("auth_identities.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    identity_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    # Legacy families cannot prove which configurable issuer minted them.
    identity_issuer: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    identity_subject: Mapped[str] = mapped_column(String(500), nullable=False)
    auth_generation: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    compromised_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    user = relationship("User")
    auth_identity = relationship("AuthIdentity")
    tokens = relationship(
        "RefreshTokenModel",
        back_populates="family",
        cascade="all, delete-orphan",
    )


class RefreshTokenModel(Base):
    """Rotatable refresh tokens for persistent sessions."""

    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    token_hash: Mapped[str] = mapped_column(
        String, unique=True, index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    family_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("refresh_token_families.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    user = relationship("User")
    family = relationship("RefreshTokenFamily", back_populates="tokens")


# â”€â”€ Contact Methods (WhatsApp, Instagram, Email, etc.) â”€â”€


class ContactMethod(Base):
    """Configurable contact channels per environment."""

    __tablename__ = "contact_methods"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    channel: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # whatsapp, instagram, email, phone, sms
    label: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # "Suporte", "Vendas", "Financeiro"
    value: Mapped[str] = mapped_column(
        String(500), nullable=False
    )  # phone number, handle, email address
    environment: Mapped[str] = mapped_column(
        String(20), nullable=False, default="prod"
    )  # dev, staging, prod
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )


# â”€â”€ KPI Definitions and Values â”€â”€


class KpiDefinition(Base):
    """Versioned, provider-neutral KPI definition registered by a sector module."""

    __tablename__ = "kpi_definitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    sector: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # agro, mining, etc.
    key: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # ndvi_avg, ore_grade, etc.
    label: Mapped[str] = mapped_column(
        String(200), nullable=False
    )  # Human-readable name
    # ``label`` remains the legacy field. ``name`` is the canonical API value.
    name: Mapped[str] = mapped_column(
        String(200), nullable=False, default="", server_default=""
    )
    unit: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # %, ha, ton, etc.
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    calculator: Mapped[str] = mapped_column(
        String(160), nullable=False, default="legacy", server_default="legacy"
    )
    calculator_version: Mapped[str] = mapped_column(
        String(40), nullable=False, default="legacy-1", server_default="legacy-1"
    )
    importance: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="TECHNICAL",
        server_default="TECHNICAL",
        index=True,
    )
    display_format_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    status_policy_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    icon: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )  # CSS icon class
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "importance IN ('PRIMARY', 'SECONDARY', 'TECHNICAL')",
            name="ck_kpi_definition_importance",
        ),
        Index(
            "ix_kpi_definitions_sector_key_version",
            "sector",
            "key",
            "calculator_version",
        ),
    )


class KpiValue(Base):
    """Immutable KPI measurement with provenance and historical comparison data."""

    __tablename__ = "kpi_values"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    kpi_definition_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("kpi_definitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    workspace_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    asset_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    site_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, index=True
    )
    dataset_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("datasets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    mission_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("acquisitions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    value: Mapped[str] = mapped_column(
        String(500), nullable=False
    )  # String to support numeric + text KPIs
    numeric_value: Mapped[Optional[float]] = mapped_column(
        Numeric(14, 4), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="UNKNOWN",
        server_default="UNKNOWN",
        index=True,
    )
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0"
    )
    measured_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(
        String(160), nullable=False, default="legacy", server_default="legacy"
    )
    algorithm_version: Mapped[str] = mapped_column(
        String(40), nullable=False, default="legacy-1", server_default="legacy-1"
    )
    provenance_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    is_baseline: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0", index=True
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    definition = relationship("KpiDefinition")
    account = relationship("Account", foreign_keys=[account_id])

    __table_args__ = (
        CheckConstraint(
            "status IN ('GOOD', 'WATCH', 'WARNING', 'CRITICAL', 'UNKNOWN')",
            name="ck_kpi_value_status",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_kpi_value_confidence",
        ),
        Index(
            "ix_kpi_values_asset_definition_measured",
            "asset_id",
            "kpi_definition_id",
            "measured_at",
        ),
    )


class Observation(Base):
    """A structured, traceable finding produced from a dataset or measurement."""

    __tablename__ = "observations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    asset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mission_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("acquisitions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    dataset_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("datasets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    observation_type: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False, default="INFO", server_default="INFO", index=True
    )
    geometry_geojson: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    value_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    numeric_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    metadata_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0"
    )
    source: Mapped[str] = mapped_column(String(160), nullable=False)
    algorithm_key: Mapped[str] = mapped_column(String(160), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(40), nullable=False)
    provenance_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    validation_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="UNVALIDATED",
        server_default="UNVALIDATED",
        index=True,
    )
    validated_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "severity IN ('INFO', 'WATCH', 'WARNING', 'CRITICAL')",
            name="ck_observation_severity",
        ),
        CheckConstraint(
            "validation_status IN ('UNVALIDATED', 'NEEDS_REVIEW', 'VALIDATED', 'REJECTED')",
            name="ck_observation_validation_status",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_observation_confidence",
        ),
        Index("ix_observations_asset_detected", "asset_id", "detected_at"),
        Index(
            "ix_observations_asset_validation_severity",
            "asset_id",
            "validation_status",
            "severity",
        ),
    )


class Action(Base):
    """A customer-visible recommendation or assigned follow-up with an outcome."""

    __tablename__ = "intelligence_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    asset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_observation_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("observations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_rule_key: Mapped[str] = mapped_column(String(160), nullable=False)
    source_rule_version: Mapped[str] = mapped_column(String(40), nullable=False)
    priority: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="MEDIUM",
        server_default="MEDIUM",
        index=True,
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="OPEN", server_default="OPEN", index=True
    )
    due_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, index=True
    )
    assigned_to_user_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    recommended_catalog_item_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        ForeignKey("catalog_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    recommendation_refs_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    outcome_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    deduplication_key: Mapped[str] = mapped_column(String(240), nullable=False)
    lifecycle_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    created_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    completed_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "priority IN ('LOW', 'MEDIUM', 'HIGH', 'URGENT', 'CRITICAL')",
            name="ck_intelligence_action_priority",
        ),
        CheckConstraint(
            "status IN ('OPEN', 'IN_PROGRESS', 'COMPLETED', 'DISMISSED', 'CANCELLED')",
            name="ck_intelligence_action_status",
        ),
        CheckConstraint("lifecycle_version > 0", name="ck_intelligence_action_version"),
        UniqueConstraint(
            "organization_id",
            "deduplication_key",
            name="uq_intelligence_action_org_deduplication",
        ),
        Index(
            "ix_intelligence_actions_asset_status_priority",
            "asset_id",
            "status",
            "priority",
        ),
    )


# â”€â”€ Audit Log â”€â”€


class AuditLog(Base):
    """Who did what, when, and where."""

    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, index=True
    )
    user_email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    action: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # login, create_order, update_company, etc.
    resource_type: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )  # user, order, company, etc.
    resource_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    details: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON with additional context
    organization_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    company_id = synonym("organization_id")
    workspace_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    request_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True
    )
    correlation_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True
    )
    outcome: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="UNKNOWN",
        server_default="UNKNOWN",
        index=True,
    )
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45), nullable=True
    )  # IPv4/IPv6
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "outcome IN ('UNKNOWN', 'SUCCESS', 'FAILURE', 'DENIED')",
            name="ck_audit_log_outcome",
        ),
    )


class ProviderUsage(Base):
    """Provider-neutral metering with optional attributable monetary cost."""

    __tablename__ = "provider_usage"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    order_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    order_item_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("order_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    catalog_item_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        ForeignKey("catalog_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    asset_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    acquisition_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("acquisitions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    dataset_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("datasets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    processing_job_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("processing_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    fulfilment_job_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("fulfilment_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    intelligence_acquisition_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("intelligence_acquisitions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    notification_delivery_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("notification_deliveries.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    report_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("reports.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    service: Mapped[str] = mapped_column(String(100), nullable=False)
    usage_type: Mapped[str] = mapped_column(String(60), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    currency: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    unit_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6), nullable=True)
    total_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    provider_reference: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    created_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_provider_usage_quantity_positive"),
        CheckConstraint(
            "unit_cost IS NULL OR unit_cost >= 0",
            name="ck_provider_usage_unit_cost_nonnegative",
        ),
        CheckConstraint(
            "total_cost IS NULL OR total_cost >= 0",
            name="ck_provider_usage_total_cost_nonnegative",
        ),
        CheckConstraint(
            "(total_cost IS NULL AND currency IS NULL AND unit_cost IS NULL) OR "
            "(total_cost IS NOT NULL AND currency IS NOT NULL)",
            name="ck_provider_usage_cost_currency",
        ),
        Index(
            "ix_provider_usage_provider_reference",
            "provider",
            "provider_reference",
        ),
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_provider_usage_org_idempotency",
        ),
        Index(
            "ix_provider_usage_scope_currency",
            "organization_id",
            "order_id",
            "currency",
        ),
    )


class InternalCost(Base):
    """Immutable direct cost attributed to a GeoVision customer order."""

    __tablename__ = "internal_costs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    order_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    order_item_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("order_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    catalog_item_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        ForeignKey("catalog_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    asset_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    fulfilment_job_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("fulfilment_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    contractor_assignment_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("contractor_assignments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    cost_type: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(5), nullable=False)
    incurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    reference: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    created_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_internal_cost_amount_positive"),
        CheckConstraint(
            "cost_type IN ('CONTRACTOR', 'TRAVEL', 'PROCESSING', 'EQUIPMENT', "
            "'SHIPPING', 'SPECIALIST_REVIEW', 'PROVIDER', 'OTHER')",
            name="ck_internal_cost_type",
        ),
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_internal_cost_org_idempotency",
        ),
        Index(
            "ix_internal_costs_scope_currency",
            "organization_id",
            "order_id",
            "currency",
        ),
    )


# â”€â”€ Company / Client â”€â”€


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    tax_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email: Mapped[str] = mapped_column(String, nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Present in the production Alembic schema and required by migrated
    # databases.  Keep it mapped so ORM inserts do not fail outside tests.
    country: Mapped[str] = mapped_column(String(100), nullable=False, default="Spain")
    organization_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="customer",
        server_default="customer",
    )
    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="Europe/Madrid",
        server_default="Europe/Madrid",
    )
    sectors: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default="[]"
    )  # JSON list
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="trial")
    subscription_plan: Mapped[str] = mapped_column(
        String(20), nullable=False, default="trial"
    )
    max_users: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    max_sites: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    max_storage_gb: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    current_users: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_sites: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    storage_used_gb: Mapped[float] = mapped_column(
        Numeric(10, 2), default=0, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    sites = relationship("Site", back_populates="company", cascade="all, delete-orphan")
    connectors = relationship(
        "Connector", back_populates="company", cascade="all, delete-orphan"
    )
    company_users = relationship(
        "CompanyUser", back_populates="company", cascade="all, delete-orphan"
    )
    documents = relationship(
        "Document", back_populates="company", cascade="all, delete-orphan"
    )
    integrations = relationship(
        "Integration", back_populates="company", cascade="all, delete-orphan"
    )
    workspaces = relationship("Account", back_populates="organization")
    assets = relationship(
        "Asset",
        back_populates="organization",
        cascade="all, delete-orphan",
        foreign_keys="Asset.organization_id",
    )


class CompanyUser(Base):
    """Users assigned to a company (admin panel concept)."""

    __tablename__ = "company_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Nullable only for pending/legacy email invitations. Authorization must
    # use this immutable GeoVision user ID, never infer membership from email.
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    email: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String(30), nullable=False, default="viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        server_default="active",
    )
    invited_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    invited_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    joined_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    company = relationship("Company", back_populates="company_users")
    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "user_id",
            name="uq_company_users_company_user",
        ),
    )


class Invitation(Base):
    """One-time organization invitation bound to an authenticated identity.

    Only a SHA-256 digest of the bearer token is persisted. The clear token is
    returned once by the creation API and is expected to travel in a frontend
    URL fragment so it is not recorded in ordinary HTTP access logs.
    """

    __tablename__ = "invitations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(12), nullable=False)
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    membership_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("company_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_email: Mapped[str] = mapped_column(String, nullable=False)
    # Non-null only while pending. A portable unique constraint on this key
    # closes concurrent double-issue races without blocking later reissues.
    pending_email_key: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    identity_hint: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    intended_role: Mapped[str] = mapped_column(String(30), nullable=False)
    target_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="workspace", server_default="workspace"
    )
    target_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    metadata_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    invited_by_user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    accepted_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'accepted', 'revoked', 'expired')",
            name="ck_invitation_status",
        ),
        CheckConstraint(
            "intended_role IN ('admin', 'manager', 'member', 'viewer', 'finance')",
            name="ck_invitation_customer_role",
        ),
        CheckConstraint(
            "target_type IN ('workspace', 'asset', 'report', 'service_result', 'order')",
            name="ck_invitation_target_type",
        ),
        Index("ix_invitations_token_hash", token_hash, unique=True),
        Index("ix_invitations_status_expires", status, expires_at),
        UniqueConstraint(
            "organization_id",
            "pending_email_key",
            name="uq_invitations_pending_org_email",
        ),
    )


# Canonical Phase 4 vocabulary. The underlying table names intentionally stay
# stable so existing deployments and downstream foreign keys migrate without a
# destructive rename.
Organization = Company
Workspace = Account
OrganizationMembership = CompanyUser
WorkspaceMembership = AccountMember


# â”€â”€ Generic spatial assets and legacy site compatibility â”€â”€


class Asset(Base):
    """Cross-sector spatial asset owned by one customer organization.

    ``geometry_geojson`` is the portable source of truth used by SQLite and
    other lightweight test environments. The Phase 5 migration adds a
    generated PostGIS geometry column and GiST index when the target
    PostgreSQL server has PostGIS available.
    """

    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    parent_asset_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("assets.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    sector: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    asset_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="active",
        server_default="active",
        index=True,
    )
    external_reference: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
    )
    location_label: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )
    geometry_geojson: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bbox_min_x: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bbox_min_y: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bbox_max_x: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bbox_max_y: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    centroid_latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    centroid_longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
        server_default="{}",
    )
    legacy_source: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    legacy_source_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    archived_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    organization = relationship(
        "Company",
        back_populates="assets",
        foreign_keys=[organization_id],
    )
    workspace = relationship(
        "Account",
        back_populates="assets",
        foreign_keys=[workspace_id],
    )
    parent = relationship(
        "Asset",
        remote_side=[id],
        foreign_keys=[parent_asset_id],
        back_populates="children",
    )
    children = relationship(
        "Asset",
        foreign_keys=[parent_asset_id],
        back_populates="parent",
    )

    __table_args__ = (
        UniqueConstraint(
            "legacy_source",
            "legacy_source_id",
            name="uq_assets_legacy_source_id",
        ),
        CheckConstraint(
            "status IN ('draft', 'active', 'inactive', 'archived')",
            name="ck_assets_status",
        ),
        CheckConstraint(
            "parent_asset_id IS NULL OR parent_asset_id <> id",
            name="ck_assets_not_own_parent",
        ),
        CheckConstraint(
            "bbox_min_x IS NULL OR (bbox_min_x >= -180 AND bbox_min_x <= 180)",
            name="ck_assets_bbox_min_x",
        ),
        CheckConstraint(
            "bbox_max_x IS NULL OR (bbox_max_x >= -180 AND bbox_max_x <= 180)",
            name="ck_assets_bbox_max_x",
        ),
        CheckConstraint(
            "bbox_min_y IS NULL OR (bbox_min_y >= -90 AND bbox_min_y <= 90)",
            name="ck_assets_bbox_min_y",
        ),
        CheckConstraint(
            "bbox_max_y IS NULL OR (bbox_max_y >= -90 AND bbox_max_y <= 90)",
            name="ck_assets_bbox_max_y",
        ),
        Index(
            "ix_assets_scope_type_status",
            "organization_id",
            "workspace_id",
            "asset_type",
            "status",
        ),
        Index(
            "ix_assets_scope_parent",
            "organization_id",
            "workspace_id",
            "parent_asset_id",
        ),
        Index(
            "ix_assets_bbox",
            "bbox_min_x",
            "bbox_min_y",
            "bbox_max_x",
            "bbox_max_y",
        ),
    )


# The Site table remains as a compatibility facade while consumers migrate to
# Asset. New legacy Site writes are mirrored by the assets application service.


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    country: Mapped[str] = mapped_column(String(100), nullable=False, default="Spain")
    province: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    municipality: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Numeric(10, 6), nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Numeric(10, 6), nullable=True)
    area_hectares: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    sector: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    company = relationship("Company", back_populates="sites")


# ── IoT / operational telemetry ─────────────────────────────────────────────


class IotDevice(Base):
    """Provisioned field device or gateway.

    Device credentials are never stored in plaintext. ``secret_encrypted`` is
    required only to validate signed MQTT envelopes; ``token_hash`` validates
    the REST fallback bearer token.
    """

    __tablename__ = "iot_devices"
    __table_args__ = (
        Index(
            "uq_iot_devices_provider_identity",
            "provider_code",
            "provider_device_id",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    public_id: Mapped[str] = mapped_column(
        String(80), unique=True, nullable=False, index=True
    )
    company_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    site_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, index=True
    )
    core_asset_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    gateway_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, index=True
    )
    provider_code: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default="geovision",
        server_default="geovision",
        index=True,
    )
    provider_device_id: Mapped[Optional[str]] = mapped_column(
        String(160), nullable=True
    )
    protocol_version: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="geovision.telemetry.v1",
        server_default="geovision.telemetry.v1",
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    device_type: Mapped[str] = mapped_column(
        String(60), nullable=False, default="multi_sensor"
    )
    transport: Mapped[str] = mapped_column(String(30), nullable=False, default="mqtt")
    firmware_version: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    hardware_model: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="provisioned", index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    capabilities_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    configuration_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    allow_remote_control: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    connectivity_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="unknown",
        server_default="unknown",
        index=True,
    )
    battery_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    health_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="unknown",
        server_default="unknown",
        index=True,
    )
    last_latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_stream_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_sequence: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, index=True
    )
    last_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )


class IotAsset(Base):
    __tablename__ = "iot_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    site_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    asset_type: Mapped[str] = mapped_column(
        String(80), nullable=False, default="equipment"
    )
    external_reference: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True
    )
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )


class AssetInspection(Base):
    """A QR-driven construction / field inspection recorded against an asset."""

    __tablename__ = "asset_inspections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    asset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("iot_assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    site_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    inspected_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    inspector_name: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False, default="general")
    result: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pass"
    )  # pass | attention | fail
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    checklist_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    photos_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False, index=True
    )


class IotGateway(Base):
    __tablename__ = "iot_gateways"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    site_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    device_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("iot_devices.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    gateway_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="provisioned"
    )
    configuration_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )


class DeviceAssignment(Base):
    """Auditable assignment history between an IoT device and canonical asset."""

    __tablename__ = "iot_device_assignments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'ended')",
            name="ck_iot_device_assignment_status",
        ),
        CheckConstraint(
            "(status = 'active' AND ended_at IS NULL) OR "
            "(status = 'ended' AND ended_at IS NOT NULL)",
            name="ck_iot_device_assignment_end_state",
        ),
        Index("ix_iot_device_assignments_device_time", "device_id", "assigned_at"),
        Index(
            "uq_iot_device_assignments_active",
            "device_id",
            unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    device_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("iot_devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("assets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    legacy_iot_asset_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("iot_assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    gateway_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("iot_gateways.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        server_default="active",
        index=True,
    )
    reason: Mapped[str] = mapped_column(
        String(500), nullable=False, default="initial assignment"
    )
    assigned_by: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )


class SensorChannel(Base):
    __tablename__ = "sensor_channels"
    __table_args__ = (
        UniqueConstraint("device_id", "key", name="uq_sensor_channel_device_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("iot_devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("iot_assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    measurement_type: Mapped[str] = mapped_column(String(80), nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    data_type: Mapped[str] = mapped_column(String(20), nullable=False, default="number")
    minimum: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    maximum: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    precision: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )


class DeviceCredential(Base):
    __tablename__ = "device_credentials"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("iot_devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", index=True
    )
    issued_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class DeviceProvisioningToken(Base):
    __tablename__ = "device_provisioning_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("iot_devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )


class CalibrationRecord(Base):
    __tablename__ = "calibration_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    channel_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sensor_channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    offset: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    scale: Mapped[float] = mapped_column(Float, nullable=False, default=1)
    reference_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    measured_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    calibrated_by: Mapped[str] = mapped_column(String(36), nullable=False)
    calibrated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )


class CommissioningRecord(Base):
    __tablename__ = "commissioning_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("iot_devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    technician_id: Mapped[str] = mapped_column(String(36), nullable=False)
    checklist_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    result: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    commissioned_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )


class TelemetryReading(Base):
    """Normalized time-series reading, one row per channel and timestamp."""

    __tablename__ = "telemetry_readings"
    __table_args__ = (
        UniqueConstraint(
            "device_id", "message_id", "channel", name="uq_telemetry_message_channel"
        ),
        Index(
            "ix_telemetry_device_channel_time", "device_id", "channel", "recorded_at"
        ),
        Index("ix_telemetry_company_time", "company_id", "recorded_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    receipt_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("iot_telemetry_receipts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    device_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("iot_devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    site_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    core_asset_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    message_id: Mapped[str] = mapped_column(String(100), nullable=False)
    sequence: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    protocol_version: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)
    channel: Mapped[str] = mapped_column(String(100), nullable=False)
    numeric_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    text_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    boolean_value: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    quality: Mapped[str] = mapped_column(String(20), nullable=False, default="good")
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class TelemetryReceipt(Base):
    """One durable receipt per telemetry envelope, independent of its channels."""

    __tablename__ = "iot_telemetry_receipts"
    __table_args__ = (
        CheckConstraint(
            "measurement_count > 0",
            name="ck_iot_telemetry_receipt_measurements",
        ),
        CheckConstraint(
            "(stream_id IS NULL AND sequence IS NULL) OR "
            "(stream_id IS NOT NULL AND sequence IS NOT NULL AND sequence >= 0)",
            name="ck_iot_telemetry_receipt_sequence",
        ),
        CheckConstraint(
            "NOT replayed_from_edge OR queued_at IS NOT NULL",
            name="ck_iot_telemetry_receipt_replay_queue",
        ),
        UniqueConstraint(
            "device_id", "message_id", name="uq_iot_receipt_device_message"
        ),
        UniqueConstraint(
            "device_id",
            "stream_id",
            "sequence",
            name="uq_iot_receipt_device_stream_sequence",
        ),
        UniqueConstraint(
            "provider_code",
            "provider_message_id",
            name="uq_iot_receipt_provider_message",
        ),
        Index("ix_iot_receipts_device_recorded", "device_id", "recorded_at"),
        Index("ix_iot_receipts_asset_recorded", "core_asset_id", "recorded_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("iot_devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    site_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    core_asset_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    message_id: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    provider_message_id: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True
    )
    protocol_version: Mapped[str] = mapped_column(String(40), nullable=False)
    firmware_version: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    stream_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    sequence: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False, index=True
    )
    out_of_order: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    replayed_from_edge: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    queued_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    measurement_count: Mapped[int] = mapped_column(Integer, nullable=False)
    context_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )


class TelemetryAggregate(Base):
    """Portable five-minute rollup; usable with SQLite and PostgreSQL."""

    __tablename__ = "telemetry_aggregates"
    __table_args__ = (
        UniqueConstraint(
            "device_id",
            "channel",
            "bucket_start",
            "bucket_seconds",
            name="uq_telemetry_aggregate_bucket",
        ),
        Index(
            "ix_telemetry_aggregate_device_time", "device_id", "channel", "bucket_start"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("iot_devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    site_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(100), nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    bucket_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    bucket_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    minimum: Mapped[float] = mapped_column(Float, nullable=False)
    maximum: Mapped[float] = mapped_column(Float, nullable=False)
    average: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )


class IotAlertRule(Base):
    __tablename__ = "iot_alert_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    device_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("iot_devices.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    site_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    channel: Mapped[str] = mapped_column(String(100), nullable=False)
    operator: Mapped[str] = mapped_column(String(10), nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="warning")
    cooldown_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    sustained_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notification_channels_json: Mapped[str] = mapped_column(
        Text, nullable=False, default='["log"]'
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )


class IotAlert(Base):
    __tablename__ = "iot_alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("iot_devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rule_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("iot_alert_rules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="open", index=True
    )
    opened_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    assigned_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    assigned_to: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class IotCommand(Base):
    __tablename__ = "iot_commands"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("iot_devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requested_by: Mapped[str] = mapped_column(String(36), nullable=False)
    correlation_id: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    arguments_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    fail_safe_state: Mapped[str] = mapped_column(
        String(100), nullable=False, default="off"
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="queued", index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    result_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )


class IotMessageNonce(Base):
    """Replay protection for signed MQTT messages."""

    __tablename__ = "iot_message_nonces"
    __table_args__ = (
        UniqueConstraint("device_id", "nonce", name="uq_iot_device_nonce"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("iot_devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    nonce: Mapped[str] = mapped_column(String(100), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )


class MobileServiceRequest(Base):
    """Customer service request submitted from the mobile application."""

    __tablename__ = "mobile_service_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Canonical ownership and journey links.  These remain nullable so that
    # requests created before the canonical workspace model can still be
    # migrated and read through their legacy ``site_id``.  Every new request
    # is populated by the mobile service boundary.
    organization_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    workspace_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    asset_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    order_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    report_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("reports.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    site_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("sites.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    site_name: Mapped[str] = mapped_column(String(200), nullable=False)
    request_type: Mapped[str] = mapped_column(String(50), nullable=False)
    urgency: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="submitted")
    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attachments_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    assigned_team: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    request_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    lifecycle_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "lifecycle_version > 0",
            name="ck_mobile_service_request_version",
        ),
        CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name="ck_mobile_service_request_progress",
        ),
        CheckConstraint(
            "status IN ('submitted', 'scheduled', 'in_field', 'processing', "
            "'results_ready', 'delivered', 'completed', 'cancelled', 'rejected')",
            name="ck_mobile_service_request_status",
        ),
        CheckConstraint(
            "(idempotency_key IS NULL AND request_sha256 IS NULL) "
            "OR (idempotency_key IS NOT NULL AND organization_id IS NOT NULL "
            "AND length(request_sha256) = 64)",
            name="ck_mobile_service_request_idempotency_digest",
        ),
        Index(
            "uq_mobile_service_request_idempotency",
            "organization_id",
            "workspace_id",
            "user_id",
            "idempotency_key",
            unique=True,
            sqlite_where=text("idempotency_key IS NOT NULL"),
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )


class DroneAircraft(Base):
    """Customer-owned aircraft registry; credentials always live in integrations."""

    __tablename__ = "drone_aircraft"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    site_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("sites.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    manufacturer: Mapped[str] = mapped_column(String(50), nullable=False, default="DJI")
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    serial_number: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    provider: Mapped[str] = mapped_column(
        String(50), nullable=False, default="manual_import"
    )
    connection_mode: Mapped[str] = mapped_column(
        String(40), nullable=False, default="media_import"
    )
    sdk_supported: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="registered"
    )
    capabilities_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )


class DroneMission(Base):
    """Mission plan and audit state. Flight execution remains in the approved provider SDK."""

    __tablename__ = "drone_missions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    site_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    aircraft_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("drone_aircraft.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    mission_type: Mapped[str] = mapped_column(
        String(40), nullable=False, default="mapping_grid"
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    altitude_m: Mapped[int] = mapped_column(Integer, nullable=False, default=80)
    speed_mps: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=5)
    front_overlap_percent: Mapped[int] = mapped_column(
        Integer, nullable=False, default=80
    )
    side_overlap_percent: Mapped[int] = mapped_column(
        Integer, nullable=False, default=70
    )
    boundary_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    route_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    checklist_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    provider_reference: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )


class Acquisition(Base):
    """Provider-neutral data-acquisition mission attached to a generic asset."""

    __tablename__ = "acquisitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    acquisition_number: Mapped[str] = mapped_column(
        String(40), nullable=False, unique=True, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    asset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    fulfilment_job_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("fulfilment_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    acquisition_type: Mapped[str] = mapped_column(
        String(40), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(
        String(30), nullable=False, default="DRAFT", server_default="DRAFT", index=True
    )
    provider_code: Mapped[Optional[str]] = mapped_column(
        String(80), nullable=True, index=True
    )
    provider_reference: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True
    )
    provenance_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    metadata_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    output_refs_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    scheduled_start: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    scheduled_end: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    captured_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    lifecycle_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    legacy_source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    legacy_source_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "acquisition_type IN ('DRONE', 'SATELLITE', 'IOT', "
            "'MANUAL_INSPECTION', 'THIRD_PARTY_DATA')",
            name="ck_acquisition_type",
        ),
        CheckConstraint(
            "state IN ('DRAFT', 'PLANNED', 'SCHEDULED', 'IN_PROGRESS', "
            "'DATA_CAPTURED', 'PROCESSING', 'COMPLETED', 'CANCELLED', "
            "'FAILED', 'NEEDS_REFLIGHT')",
            name="ck_acquisition_state",
        ),
        CheckConstraint(
            "scheduled_end IS NULL OR scheduled_start IS NULL OR scheduled_end > scheduled_start",
            name="ck_acquisition_schedule_window",
        ),
        CheckConstraint("lifecycle_version > 0", name="ck_acquisition_version"),
        UniqueConstraint(
            "legacy_source", "legacy_source_id", name="uq_acquisition_legacy_source_id"
        ),
        Index("ix_acquisitions_asset_chronology", asset_id, created_at),
    )


class DroneAcquisitionDetail(Base):
    """Nullable drone-only extension; non-drone acquisitions have no row."""

    __tablename__ = "drone_acquisition_details"

    acquisition_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("acquisitions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    aircraft_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("drone_aircraft.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    payload_reference: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    operator_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    contractor_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("operations_contractors.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    mission_requirements_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    capture_area_geojson: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    flight_metadata_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    reflight_of_acquisition_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("acquisitions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reflight_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "NOT (operator_user_id IS NOT NULL AND contractor_id IS NOT NULL)",
            name="ck_drone_acquisition_single_operator",
        ),
        CheckConstraint(
            "reflight_of_acquisition_id IS NULL OR reflight_of_acquisition_id <> acquisition_id",
            name="ck_drone_acquisition_not_own_reflight",
        ),
    )


# â”€â”€ Connector â”€â”€


class Connector(Base):
    __tablename__ = "connectors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    connector_type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    api_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    api_secret: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    base_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    webhook_secret: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    config_json: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default="{}"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_sync: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sync_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="never"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    company = relationship("Company", back_populates="connectors")


# â”€â”€ Document â”€â”€


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    site_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    document_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="report"
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_confidential: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    is_official: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    uploaded_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    company = relationship("Company", back_populates="documents")


# â”€â”€ Integration â”€â”€


class Integration(Base):
    __tablename__ = "integrations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    connector_type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    api_key_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    api_secret_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    base_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    webhook_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_sync_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    sync_interval_hours: Mapped[int] = mapped_column(
        Integer, default=24, nullable=False
    )
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sync_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="never"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    company = relationship("Company", back_populates="integrations")


# â”€â”€ Canonical Integration Registry â”€â”€

_STABLE_INTEGRATION_KEY = re.compile(r"^[a-z0-9][a-z0-9._-]{0,119}$")
_STABLE_INTEGRATION_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,79}$")
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_SECRET_KEY_NAMES = {
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "client_secret",
    "connection_string",
    "credential",
    "credentials",
    "password",
    "private_key",
    "refresh_token",
    "secret",
    "token",
    "webhook_secret",
}
_SECRET_TEXT_PATTERN = re.compile(
    r"(?i)(?:bearer\s+\S+|(?:api[_-]?key|password|client[_-]?secret|"
    r"access[_-]?token|refresh[_-]?token|authorization)\s*[:=]\s*\S+)"
)
_SECRET_REFERENCE_SCHEMES = {
    "azure-key-vault",
    "aws-secrets-manager",
    "env",
    "gcp-secret-manager",
    "keyvault",
    "secret",
    "vault",
}


def _integration_json(value: object, *, expected: type, field_name: str) -> str:
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must contain valid JSON") from exc
    else:
        decoded = value
    if not isinstance(decoded, expected):
        raise ValueError(f"{field_name} must contain a JSON {expected.__name__}")
    return json.dumps(
        decoded, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )


def _integration_settings_json(value: object) -> str:
    serialized = _integration_json(value, expected=dict, field_name="settings_json")
    decoded = json.loads(serialized)

    def visit(item: object) -> None:
        if isinstance(item, dict):
            for raw_key, child in item.items():
                key = str(raw_key).strip().casefold().replace("-", "_")
                if key in _SECRET_KEY_NAMES:
                    raise ValueError(
                        "settings_json cannot contain credentials or secret values; "
                        "store a secret reference instead"
                    )
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)
        elif isinstance(item, str):
            if _SECRET_TEXT_PATTERN.search(item) or re.search(r"://[^/@\s]+@", item):
                raise ValueError(
                    "settings_json cannot contain credentials or endpoint userinfo"
                )

    visit(decoded)
    return serialized


def _integration_capabilities_json(value: object) -> str:
    serialized = _integration_json(
        value,
        expected=list,
        field_name="capabilities_json",
    )
    decoded = json.loads(serialized)
    if any(
        not isinstance(item, str)
        or not _STABLE_INTEGRATION_KEY.fullmatch(item.strip().casefold())
        for item in decoded
    ):
        raise ValueError("capabilities_json must contain only stable capability keys")
    normalized = sorted({item.strip().casefold() for item in decoded})
    return json.dumps(normalized, separators=(",", ":"))


def _integration_endpoint(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    parsed = urlsplit(normalized)
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "integration endpoint_url must be an HTTPS URL without userinfo, query, or fragment"
        )
    return normalized


def _integration_secret_reference(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    parsed = urlsplit(normalized)
    valid_https_vault = (
        parsed.scheme.casefold() == "https"
        and bool(parsed.hostname)
        and parsed.hostname.casefold().endswith(".vault.azure.net")
        and parsed.path.startswith("/secrets/")
    )
    if (
        (
            parsed.scheme.casefold() not in _SECRET_REFERENCE_SCHEMES
            and not valid_https_vault
        )
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not parsed.netloc
    ):
        raise ValueError(
            "secret fields accept only opaque secret-manager references without userinfo"
        )
    return normalized


def _integration_nonsecret_reference(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized or re.search(r"://[^/@\s]+@", normalized):
        raise ValueError("configuration references cannot contain endpoint userinfo")
    if _SECRET_TEXT_PATTERN.search(normalized):
        raise ValueError("configuration references cannot contain secret material")
    return normalized


def _integration_safe_summary(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    if _SECRET_TEXT_PATTERN.search(normalized) or re.search(
        r"://[^/@\s]+@", normalized
    ):
        raise ValueError("integration error summaries must be sanitized")
    return normalized


def _integration_hash(value: str) -> str:
    normalized = value.strip().casefold()
    if not _SHA256_HEX.fullmatch(normalized):
        raise ValueError("payload_sha256 must be a lowercase SHA-256 hex digest")
    return normalized


class IntegrationConnection(Base):
    """Tenant-scoped, provider-neutral integration configuration."""

    __tablename__ = "integration_connections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, index=True
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, index=True
    )
    connection_key: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_family: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    provider_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="CONFIGURING", server_default="CONFIGURING"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    endpoint_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    configuration_reference: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    settings_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    credential_reference: Mapped[Optional[str]] = mapped_column(
        String(1000), nullable=True
    )
    webhook_secret_reference: Mapped[Optional[str]] = mapped_column(
        String(1000), nullable=True
    )
    capabilities_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    last_sync_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    last_sync_succeeded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    last_sync_failed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    last_error_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_error_code: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    last_error_summary: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    health_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="UNKNOWN", server_default="UNKNOWN"
    )
    health_checked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    timeout_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30, server_default="30"
    )
    retry_max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default="3"
    )
    retry_base_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30, server_default="30"
    )
    rate_limit_per_minute: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rate_limit_remaining: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rate_limit_reset_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    circuit_breaker_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="CLOSED", server_default="CLOSED"
    )
    circuit_breaker_failure_threshold: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5, server_default="5"
    )
    circuit_breaker_failure_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    circuit_breaker_opened_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    lifecycle_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    created_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    disconnected_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )
    disconnected_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "organization_id"],
            ["accounts.id", "accounts.organization_id"],
            name="fk_integration_connection_workspace_org",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["account_members.account_id", "account_members.user_id"],
            name="fk_integration_connection_workspace_user",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "organization_id",
            "connection_key",
            name="uq_integration_connection_org_key",
        ),
        UniqueConstraint(
            "id",
            "organization_id",
            name="uq_integration_connection_id_org",
        ),
        CheckConstraint(
            "length(trim(connection_key)) > 0 AND connection_key = lower(connection_key)",
            name="ck_integration_connection_key",
        ),
        CheckConstraint(
            "length(trim(provider_family)) > 0 AND provider_family = upper(provider_family)",
            name="ck_integration_connection_provider_family",
        ),
        CheckConstraint(
            "length(trim(provider_code)) > 0 AND provider_code = upper(provider_code)",
            name="ck_integration_connection_provider_code",
        ),
        CheckConstraint(
            "status IN ('CONFIGURING', 'ACTIVE', 'DEGRADED', 'DISCONNECTED')",
            name="ck_integration_connection_status",
        ),
        CheckConstraint(
            "health_status IN ('UNKNOWN', 'HEALTHY', 'DEGRADED', 'UNHEALTHY')",
            name="ck_integration_connection_health",
        ),
        CheckConstraint(
            "circuit_breaker_state IN ('CLOSED', 'OPEN', 'HALF_OPEN')",
            name="ck_integration_connection_circuit_state",
        ),
        CheckConstraint(
            "timeout_seconds BETWEEN 1 AND 600",
            name="ck_integration_connection_timeout",
        ),
        CheckConstraint(
            "retry_max_attempts BETWEEN 1 AND 20 AND retry_base_seconds BETWEEN 1 AND 86400",
            name="ck_integration_connection_retry",
        ),
        CheckConstraint(
            "rate_limit_per_minute IS NULL OR rate_limit_per_minute > 0",
            name="ck_integration_connection_rate_limit",
        ),
        CheckConstraint(
            "rate_limit_remaining IS NULL OR rate_limit_remaining >= 0",
            name="ck_integration_connection_rate_remaining",
        ),
        CheckConstraint(
            "circuit_breaker_failure_threshold BETWEEN 1 AND 100 "
            "AND circuit_breaker_failure_count >= 0",
            name="ck_integration_connection_circuit_counts",
        ),
        CheckConstraint(
            "user_id IS NULL OR workspace_id IS NOT NULL",
            name="ck_integration_connection_user_workspace",
        ),
        CheckConstraint(
            "configuration_reference IS NULL "
            "OR configuration_reference NOT LIKE '%://%@%'",
            name="ck_integration_connection_config_ref",
        ),
        CheckConstraint(
            "endpoint_url IS NULL OR (endpoint_url LIKE 'https://%' "
            "AND endpoint_url NOT LIKE '%://%@%' AND endpoint_url NOT LIKE '%?%' "
            "AND endpoint_url NOT LIKE '%#%')",
            name="ck_integration_connection_endpoint",
        ),
        CheckConstraint(
            "credential_reference IS NULL OR ((credential_reference LIKE 'azure-key-vault://%' "
            "OR credential_reference LIKE 'keyvault://%' OR credential_reference LIKE 'vault://%' "
            "OR credential_reference LIKE 'secret://%' OR credential_reference LIKE 'env://%' "
            "OR credential_reference LIKE 'aws-secrets-manager://%' "
            "OR credential_reference LIKE 'gcp-secret-manager://%' "
            "OR credential_reference LIKE 'https://%.vault.azure.net/secrets/%') "
            "AND credential_reference NOT LIKE '%://%@%' "
            "AND credential_reference NOT LIKE '%?%' AND credential_reference NOT LIKE '%#%')",
            name="ck_integration_connection_credential_ref",
        ),
        CheckConstraint(
            "webhook_secret_reference IS NULL OR ((webhook_secret_reference LIKE 'azure-key-vault://%' "
            "OR webhook_secret_reference LIKE 'keyvault://%' OR webhook_secret_reference LIKE 'vault://%' "
            "OR webhook_secret_reference LIKE 'secret://%' OR webhook_secret_reference LIKE 'env://%' "
            "OR webhook_secret_reference LIKE 'aws-secrets-manager://%' "
            "OR webhook_secret_reference LIKE 'gcp-secret-manager://%' "
            "OR webhook_secret_reference LIKE 'https://%.vault.azure.net/secrets/%') "
            "AND webhook_secret_reference NOT LIKE '%://%@%' "
            "AND webhook_secret_reference NOT LIKE '%?%' AND webhook_secret_reference NOT LIKE '%#%')",
            name="ck_integration_connection_webhook_ref",
        ),
        CheckConstraint(
            "lower(settings_json) NOT LIKE '%\"password\"%' "
            "AND lower(settings_json) NOT LIKE '%\"api_key\"%' "
            "AND lower(settings_json) NOT LIKE '%\"apikey\"%' "
            "AND lower(settings_json) NOT LIKE '%\"client_secret\"%' "
            "AND lower(settings_json) NOT LIKE '%\"access_token\"%' "
            "AND lower(settings_json) NOT LIKE '%\"refresh_token\"%' "
            "AND lower(settings_json) NOT LIKE '%\"connection_string\"%' "
            "AND settings_json NOT LIKE '%://%@%'",
            name="ck_integration_connection_settings_nonsecret",
        ),
        CheckConstraint(
            "(status = 'DISCONNECTED' AND disconnected_at IS NOT NULL AND enabled = false) "
            "OR (status <> 'DISCONNECTED' AND disconnected_at IS NULL "
            "AND disconnected_by_user_id IS NULL)",
            name="ck_integration_connection_disconnect",
        ),
        CheckConstraint(
            "(circuit_breaker_state = 'CLOSED' AND circuit_breaker_opened_at IS NULL) "
            "OR (circuit_breaker_state IN ('OPEN', 'HALF_OPEN') "
            "AND circuit_breaker_opened_at IS NOT NULL)",
            name="ck_integration_connection_circuit_timing",
        ),
        CheckConstraint(
            "health_status = 'UNKNOWN' OR health_checked_at IS NOT NULL",
            name="ck_integration_connection_health_timing",
        ),
        CheckConstraint(
            "last_error_at IS NOT NULL OR (last_error_code IS NULL AND last_error_summary IS NULL)",
            name="ck_integration_connection_error_timing",
        ),
        CheckConstraint(
            "lifecycle_version > 0",
            name="ck_integration_connection_version",
        ),
        Index(
            "ix_integration_connection_provider_scope",
            "organization_id",
            "workspace_id",
            "provider_family",
            "provider_code",
        ),
        Index(
            "ix_integration_connection_health_state",
            "status",
            "health_status",
            "circuit_breaker_state",
        ),
    )

    @validates("connection_key")
    def validate_connection_key(self, _key: str, value: str) -> str:
        normalized = value.strip().casefold()
        if not _STABLE_INTEGRATION_KEY.fullmatch(normalized):
            raise ValueError("connection_key must be a stable lowercase identifier")
        return normalized

    @validates("provider_family", "provider_code")
    def validate_provider_code(self, _key: str, value: str) -> str:
        normalized = value.strip().upper()
        if not _STABLE_INTEGRATION_CODE.fullmatch(normalized):
            raise ValueError("provider identifiers must be stable uppercase codes")
        return normalized

    @validates("endpoint_url")
    def validate_endpoint_url(self, _key: str, value: Optional[str]) -> Optional[str]:
        return _integration_endpoint(value)

    @validates("configuration_reference")
    def validate_configuration_reference(
        self, _key: str, value: Optional[str]
    ) -> Optional[str]:
        return _integration_nonsecret_reference(value)

    @validates("credential_reference", "webhook_secret_reference")
    def validate_secret_reference(
        self, _key: str, value: Optional[str]
    ) -> Optional[str]:
        return _integration_secret_reference(value)

    @validates("settings_json")
    def validate_settings_json(self, _key: str, value: object) -> str:
        return _integration_settings_json(value)

    @validates("capabilities_json")
    def validate_capabilities_json(self, _key: str, value: object) -> str:
        return _integration_capabilities_json(value)

    @validates("last_error_summary")
    def validate_last_error_summary(
        self, _key: str, value: Optional[str]
    ) -> Optional[str]:
        return _integration_safe_summary(value)


class IntegrationSyncRun(Base):
    """Durable execution state for a connection sync."""

    __tablename__ = "integration_sync_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    connection_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="PENDING",
        server_default="PENDING",
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default="3"
    )
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    failure_code: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    failure_summary: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    requested_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    lifecycle_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["connection_id", "organization_id"],
            ["integration_connections.id", "integration_connections.organization_id"],
            name="fk_integration_sync_run_connection_org",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "organization_id"],
            ["accounts.id", "accounts.organization_id"],
            name="fk_integration_sync_run_workspace_org",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "connection_id",
            "workspace_id",
            "idempotency_key",
            name="uq_integration_sync_run_connection_idempotency",
        ),
        UniqueConstraint(
            "id",
            "connection_id",
            "organization_id",
            "workspace_id",
            name="uq_integration_sync_run_id_connection_org_workspace",
        ),
        CheckConstraint(
            "direction IN ('INBOUND', 'OUTBOUND')",
            name="ck_integration_sync_run_direction",
        ),
        CheckConstraint(
            "trigger_type IN ('SCHEDULED', 'MANUAL', 'WEBHOOK', 'EVENT', 'RETRY', 'BACKFILL')",
            name="ck_integration_sync_run_trigger",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'PARTIAL', "
            "'RETRY_SCHEDULED', 'FAILED', 'DEAD_LETTERED', 'CANCELLED')",
            name="ck_integration_sync_run_status",
        ),
        CheckConstraint(
            "attempt_count >= 0 AND max_attempts BETWEEN 1 AND 20 "
            "AND attempt_count <= max_attempts",
            name="ck_integration_sync_run_attempts",
        ),
        CheckConstraint(
            "length(payload_sha256) = 64 AND payload_sha256 = lower(payload_sha256)",
            name="ck_integration_sync_run_payload_hash",
        ),
        CheckConstraint(
            "next_retry_at IS NULL OR status = 'RETRY_SCHEDULED'",
            name="ck_integration_sync_run_retry_state",
        ),
        CheckConstraint(
            "finished_at IS NULL OR status IN "
            "('SUCCEEDED', 'PARTIAL', 'FAILED', 'DEAD_LETTERED', 'CANCELLED')",
            name="ck_integration_sync_run_finished_state",
        ),
        CheckConstraint(
            "finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at",
            name="ck_integration_sync_run_timing",
        ),
        CheckConstraint(
            "(failure_code IS NULL AND failure_summary IS NULL) OR status IN "
            "('RETRY_SCHEDULED', 'FAILED', 'DEAD_LETTERED')",
            name="ck_integration_sync_run_failure_state",
        ),
        CheckConstraint(
            "lifecycle_version > 0",
            name="ck_integration_sync_run_version",
        ),
        Index(
            "ix_integration_sync_run_queue",
            "status",
            "next_retry_at",
            "created_at",
        ),
        Index(
            "ix_integration_sync_run_scope_time",
            "organization_id",
            "workspace_id",
            "created_at",
        ),
    )

    @validates("payload_sha256")
    def validate_payload_sha256(self, _key: str, value: str) -> str:
        return _integration_hash(value)

    @validates("failure_summary")
    def validate_failure_summary(
        self, _key: str, value: Optional[str]
    ) -> Optional[str]:
        return _integration_safe_summary(value)


class IntegrationSyncEvent(Base):
    """Normalized per-resource work item within an integration sync run."""

    __tablename__ = "integration_sync_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    connection_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    resource_id: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    external_reference: Mapped[Optional[str]] = mapped_column(
        String(300), nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="PENDING",
        server_default="PENDING",
        index=True,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default="3"
    )
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    failure_code: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    failure_summary: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    occurred_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    lifecycle_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "connection_id", "organization_id", "workspace_id"],
            [
                "integration_sync_runs.id",
                "integration_sync_runs.connection_id",
                "integration_sync_runs.organization_id",
                "integration_sync_runs.workspace_id",
            ],
            name="fk_integration_sync_event_run_connection_org_workspace",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "organization_id"],
            ["accounts.id", "accounts.organization_id"],
            name="fk_integration_sync_event_workspace_org",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "connection_id",
            "workspace_id",
            "idempotency_key",
            name="uq_integration_sync_event_connection_idempotency",
        ),
        CheckConstraint(
            "direction IN ('INBOUND', 'OUTBOUND')",
            name="ck_integration_sync_event_direction",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'SUCCEEDED', 'RETRY_SCHEDULED', "
            "'FAILED', 'DEAD_LETTERED', 'SKIPPED')",
            name="ck_integration_sync_event_status",
        ),
        CheckConstraint(
            "(resource_type IS NULL AND resource_id IS NULL) "
            "OR (resource_type IS NOT NULL AND resource_id IS NOT NULL)",
            name="ck_integration_sync_event_resource_pair",
        ),
        CheckConstraint(
            "external_reference IS NULL OR external_reference NOT LIKE '%://%'",
            name="ck_integration_sync_event_external_opaque",
        ),
        CheckConstraint(
            "attempt_count >= 0 AND max_attempts BETWEEN 1 AND 20 "
            "AND attempt_count <= max_attempts",
            name="ck_integration_sync_event_attempts",
        ),
        CheckConstraint(
            "length(payload_sha256) = 64 AND payload_sha256 = lower(payload_sha256)",
            name="ck_integration_sync_event_payload_hash",
        ),
        CheckConstraint(
            "next_retry_at IS NULL OR status = 'RETRY_SCHEDULED'",
            name="ck_integration_sync_event_retry_state",
        ),
        CheckConstraint(
            "processed_at IS NULL OR status IN ('SUCCEEDED', 'FAILED', 'DEAD_LETTERED', 'SKIPPED')",
            name="ck_integration_sync_event_processed_state",
        ),
        CheckConstraint(
            "(failure_code IS NULL AND failure_summary IS NULL) OR status IN "
            "('RETRY_SCHEDULED', 'FAILED', 'DEAD_LETTERED')",
            name="ck_integration_sync_event_failure_state",
        ),
        CheckConstraint(
            "lifecycle_version > 0",
            name="ck_integration_sync_event_version",
        ),
        Index(
            "ix_integration_sync_event_queue",
            "status",
            "next_retry_at",
            "created_at",
        ),
        Index(
            "ix_integration_sync_event_resource",
            "organization_id",
            "workspace_id",
            "resource_type",
            "resource_id",
        ),
        Index(
            "ix_integration_sync_event_external",
            "connection_id",
            "external_reference",
        ),
    )

    @validates("payload_sha256")
    def validate_payload_sha256(self, _key: str, value: str) -> str:
        return _integration_hash(value)

    @validates("external_reference")
    def validate_external_reference(
        self, _key: str, value: Optional[str]
    ) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        if (
            not normalized
            or "://" in normalized
            or "\r" in normalized
            or "\n" in normalized
        ):
            raise ValueError("external_reference must be an opaque provider identifier")
        return normalized

    @validates("failure_summary")
    def validate_failure_summary(
        self, _key: str, value: Optional[str]
    ) -> Optional[str]:
        return _integration_safe_summary(value)


class FeatureFlagOverride(Base):
    """Workspace or workspace-member override mirrored from configuration state."""

    __tablename__ = "feature_flag_overrides"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, index=True
    )
    flag_key: Mapped[str] = mapped_column(String(120), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="GEOVISION", server_default="GEOVISION"
    )
    configuration_reference: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    etag: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    configuration_version: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True
    )
    lifecycle_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    created_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "organization_id"],
            ["accounts.id", "accounts.organization_id"],
            name="fk_feature_flag_override_workspace_org",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["account_members.account_id", "account_members.user_id"],
            name="fk_feature_flag_override_workspace_user",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "length(trim(flag_key)) > 0 AND flag_key = lower(flag_key)",
            name="ck_feature_flag_override_key",
        ),
        CheckConstraint(
            "source IN ('GEOVISION', 'AZURE_APP_CONFIGURATION')",
            name="ck_feature_flag_override_source",
        ),
        CheckConstraint(
            "configuration_reference IS NULL "
            "OR configuration_reference NOT LIKE '%://%@%'",
            name="ck_feature_flag_override_config_ref",
        ),
        CheckConstraint(
            "source <> 'AZURE_APP_CONFIGURATION' OR configuration_reference IS NOT NULL",
            name="ck_feature_flag_override_azure_ref",
        ),
        CheckConstraint(
            "lifecycle_version > 0",
            name="ck_feature_flag_override_version",
        ),
        Index(
            "uq_feature_flag_override_workspace_flag",
            "organization_id",
            "workspace_id",
            "flag_key",
            unique=True,
            sqlite_where=text("user_id IS NULL"),
            postgresql_where=text("user_id IS NULL"),
        ),
        Index(
            "uq_feature_flag_override_user_flag",
            "organization_id",
            "workspace_id",
            "user_id",
            "flag_key",
            unique=True,
            sqlite_where=text("user_id IS NOT NULL"),
            postgresql_where=text("user_id IS NOT NULL"),
        ),
        Index(
            "ix_feature_flag_override_lookup",
            "workspace_id",
            "user_id",
            "flag_key",
            "enabled",
        ),
    )

    @validates("flag_key")
    def validate_flag_key(self, _key: str, value: str) -> str:
        normalized = value.strip().casefold()
        if not _STABLE_INTEGRATION_KEY.fullmatch(normalized):
            raise ValueError("flag_key must be a stable lowercase identifier")
        return normalized

    @validates("configuration_reference")
    def validate_configuration_reference(
        self, _key: str, value: Optional[str]
    ) -> Optional[str]:
        return _integration_nonsecret_reference(value)


# â”€â”€ Dataset (multi-tenant) â”€â”€


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    site_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("sites.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    asset_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    mission_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("acquisitions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_tool: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    data_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, default="drone_imagery"
    )
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    dataset_type: Mapped[str] = mapped_column(
        String(80), nullable=False, default="OTHER", server_default="OTHER", index=True
    )
    provider_code: Mapped[Optional[str]] = mapped_column(
        String(80), nullable=True, index=True
    )
    source_reference: Mapped[Optional[str]] = mapped_column(String(240), nullable=True)
    storage_provider: Mapped[str] = mapped_column(
        String(40), nullable=False, default="local", server_default="local"
    )
    object_prefix: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    crs: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    resolution: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    resolution_unit: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    processing_level: Mapped[str] = mapped_column(
        String(30), nullable=False, default="RAW", server_default="RAW", index=True
    )
    quality_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="UNREVIEWED",
        server_default="UNREVIEWED",
        index=True,
    )
    provenance_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="uploading", server_default="uploading"
    )
    sector: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    capture_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default="{}"
    )
    storage_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    lifecycle_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

    files = relationship(
        "DatasetFile",
        back_populates="dataset",
        passive_deletes="all",
    )

    __table_args__ = (
        CheckConstraint(
            "resolution IS NULL OR resolution > 0", name="ck_dataset_resolution"
        ),
        CheckConstraint("file_count >= 0", name="ck_dataset_file_count"),
        CheckConstraint("total_size_bytes >= 0", name="ck_dataset_total_size"),
        CheckConstraint("lifecycle_version > 0", name="ck_dataset_version"),
        Index("ix_datasets_asset_capture", asset_id, capture_date),
    )


class DatasetFile(Base):
    __tablename__ = "dataset_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    dataset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("datasets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String, nullable=False)
    storage_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    storage_provider: Mapped[str] = mapped_column(
        String(40), nullable=False, default="local", server_default="local"
    )
    storage_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    object_area: Mapped[str] = mapped_column(
        String(20), nullable=False, default="raw", server_default="raw"
    )
    file_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    md5_hash: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    sha256_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending_upload",
        server_default="pending_upload",
    )
    upload_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    lifecycle_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    dataset = relationship("Dataset", back_populates="files")

    __table_args__ = (
        CheckConstraint("file_size >= 0", name="ck_dataset_file_size"),
        CheckConstraint("lifecycle_version > 0", name="ck_dataset_file_version"),
        Index(
            "ix_dataset_files_storage_object", storage_provider, storage_key, deleted_at
        ),
    )


class Report(Base):
    """Versioned customer report built from an immutable structured context."""

    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    asset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    acquisition_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("acquisitions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    report_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    template_version: Mapped[str] = mapped_column(String(40), nullable=False)
    revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="GENERATING",
        server_default="GENERATING",
        index=True,
    )
    qa_level: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="HUMAN_REVIEW",
        server_default="HUMAN_REVIEW",
        index=True,
    )
    context_schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    context_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    context_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    narrative_provider: Mapped[str] = mapped_column(String(80), nullable=False)
    narrative_model: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    narrative_model_version: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        default="legacy-unversioned",
        server_default="legacy-unversioned",
    )
    narrative_schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    narrative_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    provenance_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    qa_result_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    output_dataset_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("datasets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    output_file_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("dataset_files.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    supersedes_report_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("reports.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    generation_key: Mapped[str] = mapped_column(
        String(200), nullable=False, unique=True
    )
    generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, index=True
    )
    approved_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    published_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    lifecycle_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('GENERATING', 'DRAFT', 'REVIEW_REQUIRED', 'APPROVED', "
            "'PUBLISHED', 'SUPERSEDED')",
            name="ck_report_status",
        ),
        CheckConstraint(
            "qa_level IN ('AUTO_APPROVED', 'HUMAN_REVIEW', 'SPECIALIST_REVIEW')",
            name="ck_report_qa_level",
        ),
        CheckConstraint("revision > 0", name="ck_report_revision"),
        CheckConstraint("lifecycle_version > 0", name="ck_report_lifecycle_version"),
        UniqueConstraint(
            "asset_id", "report_type", "revision", name="uq_report_asset_type_revision"
        ),
        Index("ix_reports_scope_status", "organization_id", "workspace_id", "status"),
        Index("ix_reports_asset_type_status", "asset_id", "report_type", "status"),
    )


class ProcessingJob(Base):
    """Provider-neutral, restart-safe photogrammetry processing request."""

    __tablename__ = "processing_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    asset_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    acquisition_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("acquisitions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    fulfilment_job_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("fulfilment_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    provider_job_reference: Mapped[Optional[str]] = mapped_column(
        String(240), nullable=True
    )
    requested_outputs_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    options_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="REQUESTED",
        server_default="REQUESTED",
        index=True,
    )
    progress_percent: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0"
    )
    stage: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    processor_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    processor_version: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    estimated_cost_amount: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    actual_cost_amount: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cost_currency: Mapped[str] = mapped_column(
        String(5), nullable=False, default="USD", server_default="USD"
    )
    error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quality_report_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    max_retries: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default="3"
    )
    poll_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    submission_generation: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    next_poll_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, index=True
    )
    claimed_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(
        String(200), nullable=False, unique=True, index=True
    )
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    lifecycle_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    source_links = relationship(
        "ProcessingJobSource", cascade="all, delete-orphan", back_populates="job"
    )
    output_links = relationship(
        "ProcessingJobOutput", cascade="all, delete-orphan", back_populates="job"
    )

    __table_args__ = (
        UniqueConstraint(
            "provider_code",
            "provider_job_reference",
            name="uq_processing_job_provider_reference",
        ),
        CheckConstraint(
            "status IN ('REQUESTED', 'VALIDATING', 'SUBMITTED', 'RUNNING', "
            "'RETRY_WAIT', 'NEEDS_REVIEW', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name="ck_processing_job_status",
        ),
        CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name="ck_processing_job_progress",
        ),
        CheckConstraint(
            "estimated_cost_amount IS NULL OR estimated_cost_amount >= 0",
            name="ck_processing_job_estimated_cost",
        ),
        CheckConstraint(
            "actual_cost_amount IS NULL OR actual_cost_amount >= 0",
            name="ck_processing_job_actual_cost",
        ),
        CheckConstraint(
            "retry_count >= 0 AND max_retries >= 0 AND poll_count >= 0 "
            "AND submission_generation >= 0",
            name="ck_processing_job_attempt_counts",
        ),
        CheckConstraint("lifecycle_version > 0", name="ck_processing_job_version"),
        Index("ix_processing_jobs_due", status, next_poll_at, created_at),
    )


class ProcessingJobSource(Base):
    """Ordered input datasets captured at processing-request time."""

    __tablename__ = "processing_job_sources"

    processing_job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("processing_jobs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    dataset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("datasets.id", ondelete="RESTRICT"),
        primary_key=True,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    job = relationship("ProcessingJob", back_populates="source_links")
    dataset = relationship("Dataset")

    __table_args__ = (
        CheckConstraint("sequence >= 0", name="ck_processing_job_source_sequence"),
    )


class ProcessingJobOutput(Base):
    """Canonical Dataset produced for one requested processing output."""

    __tablename__ = "processing_job_outputs"

    processing_job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("processing_jobs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    output_type: Mapped[str] = mapped_column(String(80), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("datasets.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    quality_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PASSED", server_default="PASSED"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    job = relationship("ProcessingJob", back_populates="output_links")
    dataset = relationship("Dataset")

    __table_args__ = (
        CheckConstraint(
            "quality_status IN ('PASSED', 'WARNING', 'FAILED')",
            name="ck_processing_job_output_quality",
        ),
    )


class IntelligenceSchedule(Base):
    """Recurring provider-neutral satellite or weather acquisition plan."""

    __tablename__ = "intelligence_schedules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    asset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    provider_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    cadence_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10080, server_default="10080"
    )
    lookback_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=14, server_default="14"
    )
    options_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="ACTIVE",
        server_default="ACTIVE",
        index=True,
    )
    next_run_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_success_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    claimed_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(
        String(200), nullable=False, unique=True
    )
    created_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    lifecycle_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "kind IN ('SATELLITE', 'WEATHER')", name="ck_intelligence_schedule_kind"
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'PAUSED', 'DISABLED')",
            name="ck_intelligence_schedule_status",
        ),
        CheckConstraint(
            "cadence_minutes > 0 AND lookback_days > 0 AND consecutive_failures >= 0",
            name="ck_intelligence_schedule_intervals",
        ),
        CheckConstraint(
            "lifecycle_version > 0", name="ck_intelligence_schedule_version"
        ),
        Index("ix_intelligence_schedules_due", status, next_run_at, created_at),
    )


class IntelligenceAcquisition(Base):
    """Auditable provider request, cache record, and retry state."""

    __tablename__ = "intelligence_acquisitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    asset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    schedule_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("intelligence_schedules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    acquisition_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("acquisitions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    provider_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    request_fingerprint: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    request_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    result_summary_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    dataset_ids_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="REQUESTED",
        server_default="REQUESTED",
        index=True,
    )
    cache_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, index=True
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default="3"
    )
    next_attempt_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, index=True
    )
    claimed_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(
        String(200), nullable=False, unique=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    lifecycle_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "kind IN ('SATELLITE', 'WEATHER')", name="ck_intelligence_acquisition_kind"
        ),
        CheckConstraint(
            "status IN ('REQUESTED', 'RUNNING', 'RETRY_WAIT', 'COMPLETED', 'FAILED')",
            name="ck_intelligence_acquisition_status",
        ),
        CheckConstraint(
            "attempt_count >= 0 AND max_attempts > 0",
            name="ck_intelligence_acquisition_attempts",
        ),
        CheckConstraint(
            "lifecycle_version > 0", name="ck_intelligence_acquisition_version"
        ),
        Index(
            "ix_intelligence_acquisitions_cache",
            organization_id,
            asset_id,
            kind,
            provider_code,
            request_fingerprint,
            status,
            cache_expires_at,
        ),
        Index("ix_intelligence_acquisitions_due", status, next_attempt_at, created_at),
    )


class SatelliteScene(Base):
    """Normalized STAC scene metadata linked to a canonical Dataset."""

    __tablename__ = "satellite_scenes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    intelligence_acquisition_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("intelligence_acquisitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("datasets.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    provider_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    provider_reference: Mapped[str] = mapped_column(String(240), nullable=False)
    collection: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    acquired_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    cloud_cover_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    resolution_meters: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    crs: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    bands_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    bbox_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    coverage_geojson: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    assets_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    provenance_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    source_link: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "asset_id",
            "provider_code",
            "provider_reference",
            name="uq_satellite_scene_asset_source",
        ),
        CheckConstraint(
            "cloud_cover_percent IS NULL OR "
            "(cloud_cover_percent >= 0 AND cloud_cover_percent <= 100)",
            name="ck_satellite_scene_cloud_cover",
        ),
        CheckConstraint(
            "resolution_meters IS NULL OR resolution_meters > 0",
            name="ck_satellite_scene_resolution",
        ),
        Index("ix_satellite_scenes_asset_time", asset_id, acquired_at),
    )


class WeatherObservation(Base):
    """Normalized weather measurement from a provider station or grid."""

    __tablename__ = "weather_observations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    intelligence_acquisition_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("intelligence_acquisitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("datasets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    provider_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_reference: Mapped[str] = mapped_column(
        String(160), nullable=False, index=True
    )
    source_name: Mapped[Optional[str]] = mapped_column(String(240), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    metric: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    quality: Mapped[str] = mapped_column(
        String(30), nullable=False, default="observed", server_default="observed"
    )
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    distance_km: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    provenance_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "asset_id",
            "provider_code",
            "source_reference",
            "observed_at",
            "metric",
            name="uq_weather_observation_asset_source_time_metric",
        ),
        CheckConstraint(
            "latitude IS NULL OR (latitude >= -90 AND latitude <= 90)",
            name="ck_weather_observation_latitude",
        ),
        CheckConstraint(
            "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
            name="ck_weather_observation_longitude",
        ),
        CheckConstraint(
            "distance_km IS NULL OR distance_km >= 0",
            name="ck_weather_observation_distance",
        ),
        Index(
            "ix_weather_observations_asset_metric_time", asset_id, metric, observed_at
        ),
    )


# â”€â”€ Cart â”€â”€


class Cart(Base):
    __tablename__ = "carts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, index=True
    )
    company_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    session_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, index=True
    )
    site_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    coupon_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    discount_amount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    discount_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    delivery_method: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    delivery_cost: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    delivery_address_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    subtotal: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tax_amount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(5), nullable=False, default="EUR")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    cart_items = relationship(
        "CartItem", back_populates="cart", cascade="all, delete-orphan"
    )


class CartItem(Base):
    __tablename__ = "cart_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    cart_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("carts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[str] = mapped_column(String(36), nullable=False)
    variant_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    product_name: Mapped[str] = mapped_column(String, nullable=False)
    product_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="service"
    )
    product_image: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sku: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0.14)
    tax_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scheduled_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    custom_options_json: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    cart = relationship("Cart", back_populates="cart_items")


# â”€â”€ Coupon â”€â”€


class Coupon(Base):
    __tablename__ = "coupons"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    discount_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # percentage, fixed
    discount_value: Mapped[int] = mapped_column(Integer, nullable=False)
    minimum_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    maximum_discount: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    usage_limit: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    first_order_only: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )


# â”€â”€ Shop Product (rich catalog) â”€â”€


class ShopProduct(Base):
    """Rich product catalog for the shop (flight services, hardware, etc.)."""

    __tablename__ = "shop_products"

    id: Mapped[str] = mapped_column(
        String(50), primary_key=True
    )  # e.g. prod_mining_volumetric
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    short_description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    product_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="service"
    )
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="flight")
    execution_type: Mapped[Optional[str]] = mapped_column(
        String(30), nullable=True
    )  # pontual, recorrente
    price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    price_usd: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    price_eur: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # `price` is the legacy AOA list; Spain uses the explicit `price_eur` value.
    currency: Mapped[str] = mapped_column(String(5), nullable=False, default="AOA")
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0.14)
    duration_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    requires_site: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    min_area_ha: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sectors_json: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default="[]"
    )  # JSON list
    deliverables_json: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default="[]"
    )  # JSON list
    image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    track_inventory: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    stock_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )


class ProcurementSupplier(Base):
    """Internal procurement identity; never a customer-facing storefront."""

    __tablename__ = "procurement_suppliers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(
        String(80), nullable=False, unique=True, index=True
    )
    legal_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )
    contact_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    country_code: Mapped[Optional[str]] = mapped_column(
        String(2), nullable=True, index=True
    )
    region: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True, index=True
    )
    service_area_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    capabilities_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    certifications_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    insurance_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    document_refs_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    quality_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    last_reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    catalog_items = relationship("CatalogItem", back_populates="supplier")

    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE', 'ON_HOLD', 'INACTIVE')",
            name="ck_procurement_supplier_status",
        ),
        CheckConstraint(
            "quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 100)",
            name="ck_procurement_supplier_quality_score",
        ),
    )


class OperationalCapability(Base):
    """Extensible qualification taxonomy for flight and non-flight resources."""

    __tablename__ = "operational_capabilities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(
        String(80), nullable=False, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1", index=True
    )
    metadata_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )


class OperationsContractor(Base):
    """Private GeoVision operational resource, never a marketplace seller."""

    __tablename__ = "operations_contractors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(
        String(80), nullable=False, unique=True, index=True
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
        index=True,
    )
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    legal_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="ACTIVE",
        server_default="ACTIVE",
        index=True,
    )
    availability: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="AVAILABLE",
        server_default="AVAILABLE",
        index=True,
    )
    contact_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    country_code: Mapped[Optional[str]] = mapped_column(
        String(2), nullable=True, index=True
    )
    region: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True, index=True
    )
    service_area_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    certifications_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    insurance_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    equipment_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    document_refs_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    quality_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    internal_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    capability_links = relationship(
        "ContractorCapability",
        back_populates="contractor",
        cascade="all, delete-orphan",
    )
    assignments = relationship(
        "ContractorAssignment",
        back_populates="contractor",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE', 'ON_HOLD', 'INACTIVE', 'BLOCKED')",
            name="ck_operations_contractor_status",
        ),
        CheckConstraint(
            "availability IN ('AVAILABLE', 'LIMITED', 'UNAVAILABLE')",
            name="ck_operations_contractor_availability",
        ),
        CheckConstraint(
            "quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 100)",
            name="ck_operations_contractor_quality_score",
        ),
    )


class ContractorCapability(Base):
    __tablename__ = "contractor_capabilities"

    contractor_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("operations_contractors.id", ondelete="CASCADE"),
        primary_key=True,
    )
    capability_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("operational_capabilities.id", ondelete="CASCADE"),
        primary_key=True,
    )
    proficiency: Mapped[str] = mapped_column(
        String(20), nullable=False, default="QUALIFIED", server_default="QUALIFIED"
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    contractor = relationship("OperationsContractor", back_populates="capability_links")
    capability = relationship("OperationalCapability")

    __table_args__ = (
        CheckConstraint(
            "proficiency IN ('BASIC', 'QUALIFIED', 'EXPERT')",
            name="ck_contractor_capability_proficiency",
        ),
    )


class FulfilmentJob(Base):
    """Executable unit of work derived from, but independent of, a sale."""

    __tablename__ = "fulfilment_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_number: Mapped[str] = mapped_column(
        String(40), nullable=False, unique=True, index=True
    )
    order_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_item_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("order_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    asset_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    job_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    priority: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="NORMAL",
        server_default="NORMAL",
        index=True,
    )
    state: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="PLANNED",
        server_default="PLANNED",
        index=True,
    )
    resume_state: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    assigned_contractor_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("operations_contractors.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    assigned_user_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    scheduled_start: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    scheduled_end: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    actual_start: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    requirements_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    direct_cost_amount: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cost_currency: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    cost_reference: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    plan_key: Mapped[Optional[str]] = mapped_column(
        String(180), nullable=True, unique=True, index=True
    )
    lifecycle_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    created_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    dependencies = relationship(
        "FulfilmentJobDependency",
        foreign_keys="FulfilmentJobDependency.job_id",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "priority IN ('LOW', 'NORMAL', 'HIGH', 'URGENT')",
            name="ck_fulfilment_job_priority",
        ),
        CheckConstraint(
            "state IN ('PLANNED', 'READY', 'BLOCKED', 'ASSIGNED', 'SCHEDULED', "
            "'IN_PROGRESS', 'WAITING_INPUT', 'QA_REVIEW', 'COMPLETED', "
            "'CANCELLED', 'FAILED')",
            name="ck_fulfilment_job_state",
        ),
        CheckConstraint(
            "NOT (assigned_contractor_id IS NOT NULL AND assigned_user_id IS NOT NULL)",
            name="ck_fulfilment_job_single_assignee",
        ),
        CheckConstraint(
            "scheduled_end IS NULL OR scheduled_start IS NULL OR scheduled_end > scheduled_start",
            name="ck_fulfilment_job_schedule_window",
        ),
        CheckConstraint(
            "direct_cost_amount IS NULL OR direct_cost_amount >= 0",
            name="ck_fulfilment_job_cost_nonnegative",
        ),
        CheckConstraint("lifecycle_version > 0", name="ck_fulfilment_job_version"),
    )


class FulfilmentJobDependency(Base):
    """Explicit directed dependency edge between jobs on the same order."""

    __tablename__ = "fulfilment_job_dependencies"

    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("fulfilment_jobs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    depends_on_job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("fulfilment_jobs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "job_id <> depends_on_job_id", name="ck_fulfilment_job_no_self_dependency"
        ),
        Index("ix_fulfilment_job_dependencies_upstream", depends_on_job_id),
    )


class OperationalDomainEvent(Base):
    """Canonical transactional outbox (legacy table name retained in-place)."""

    __tablename__ = "operational_domain_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    aggregate_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    aggregate_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payload_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(200), nullable=False, unique=True, index=True
    )
    topic: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        default="geovision.domain.v1",
        server_default="geovision.domain.v1",
    )
    schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    correlation_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True
    )
    causation_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
        index=True,
    )
    publish_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    next_attempt_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, index=True
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    claimed_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    dead_lettered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "publish_attempts >= 0", name="ck_operational_domain_event_attempts"
        ),
        CheckConstraint(
            "schema_version > 0", name="ck_operational_domain_event_schema_version"
        ),
        CheckConstraint(
            "status IN ('pending', 'processing', 'retry', 'published', 'dead_letter')",
            name="ck_operational_domain_event_status",
        ),
        Index("ix_operational_domain_events_due", status, next_attempt_at, occurred_at),
    )


EventOutbox = OperationalDomainEvent


class EventConsumerReceipt(Base):
    """Inbox receipt that makes at-least-once event consumption idempotent."""

    __tablename__ = "event_consumer_receipts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    consumer_name: Mapped[str] = mapped_column(String(100), nullable=False)
    event_id: Mapped[str] = mapped_column(String(100), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("consumer_name", "event_id", name="uq_event_consumer_receipt"),
        Index("ix_event_consumer_receipts_consumer", consumer_name, processed_at),
    )


class EventDeliveryAttempt(Base):
    """Bounded, secret-free audit trail for outbox delivery and retries."""

    __tablename__ = "event_delivery_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    worker_id: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    error_code: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint("attempt_number > 0", name="ck_event_delivery_attempt_number"),
        CheckConstraint(
            "outcome IN ('published', 'retry', 'dead_letter')",
            name="ck_event_delivery_attempt_outcome",
        ),
        Index("ix_event_delivery_attempts_event_attempt", event_id, attempt_number),
    )


class ContractorAssignment(Base):
    """Phase-9 assignment shell; Phase 10 may attach a fulfilment job."""

    __tablename__ = "contractor_assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    assignment_number: Mapped[str] = mapped_column(
        String(40), nullable=False, unique=True, index=True
    )
    contractor_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("operations_contractors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    fulfilment_job_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("fulfilment_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="OFFERED",
        server_default="OFFERED",
        index=True,
    )
    location_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    window_start: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    window_end: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    requirements_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    upload_area_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    required_documents_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    agreed_cost_amount: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cost_currency: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    internal_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    assigned_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    lifecycle_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    contractor = relationship("OperationsContractor", back_populates="assignments")

    __table_args__ = (
        CheckConstraint(
            "status IN ('OFFERED', 'ACCEPTED', 'DECLINED', 'ACTIVE', 'COMPLETED', 'CANCELLED')",
            name="ck_contractor_assignment_status",
        ),
        CheckConstraint(
            "agreed_cost_amount IS NULL OR agreed_cost_amount >= 0",
            name="ck_contractor_assignment_cost_nonnegative",
        ),
        CheckConstraint(
            "lifecycle_version > 0", name="ck_contractor_assignment_lifecycle_version"
        ),
    )


class CatalogItem(Base):
    """Canonical first-party offer across products, services, and plans."""

    __tablename__ = "catalog_items"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True, index=True
    )
    slug: Mapped[str] = mapped_column(
        String(200), nullable=False, unique=True, index=True
    )
    item_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    sectors_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    asset_types_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    customer_content_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    deliverables_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    price_model: Mapped[str] = mapped_column(
        String(30), nullable=False, default="FIXED", server_default="FIXED"
    )
    currency: Mapped[str] = mapped_column(
        String(5), nullable=False, default="AOA", server_default="AOA"
    )
    unit_amount: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pricing_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    availability_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="AVAILABLE", server_default="AVAILABLE"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", server_default="DRAFT", index=True
    )
    recommendation_triggers_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    metadata_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_featured: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    requires_site: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    requires_scheduling: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    duration_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fulfilment_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    installed_product_type: Mapped[Optional[str]] = mapped_column(
        String(80), nullable=True
    )
    supplier_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("procurement_suppliers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    legacy_source: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    legacy_source_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    supplier = relationship("ProcurementSupplier", back_populates="catalog_items")

    __table_args__ = (
        UniqueConstraint(
            "legacy_source",
            "legacy_source_id",
            name="uq_catalog_items_legacy_source_id",
        ),
        CheckConstraint(
            "item_type IN ('PHYSICAL_PRODUCT', 'SERVICE', 'MONITORING_PLAN', "
            "'INSTALLATION', 'INSPECTION', 'ANALYSIS')",
            name="ck_catalog_item_type",
        ),
        CheckConstraint(
            "price_model IN ('FIXED', 'STARTING_AT', 'QUOTE', 'SUBSCRIPTION', 'USAGE')",
            name="ck_catalog_price_model",
        ),
        CheckConstraint(
            "availability_status IN ('AVAILABLE', 'UNAVAILABLE', 'PREORDER', 'ON_REQUEST')",
            name="ck_catalog_availability_status",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'PUBLISHED', 'UNAVAILABLE', 'ARCHIVED')",
            name="ck_catalog_item_status",
        ),
        CheckConstraint(
            "unit_amount IS NULL OR unit_amount >= 0",
            name="ck_catalog_unit_amount_nonnegative",
        ),
        CheckConstraint(
            "duration_hours IS NULL OR duration_hours > 0",
            name="ck_catalog_duration_positive",
        ),
    )


# â”€â”€ Payment â”€â”€


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    order_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    organization_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(5), nullable=False, default="AOA")
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, unique=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    provider_reference: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True
    )
    refunded_amount: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    metadata_json: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    authorized_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    failed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payment_amount_positive"),
        CheckConstraint("refunded_amount >= 0", name="ck_payment_refunded_nonnegative"),
    )


class PaymentWebhookEvent(Base):
    """Verified provider notification receipt without retaining raw payloads."""

    __tablename__ = "payment_webhook_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    event_id: Mapped[str] = mapped_column(String(200), nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    signature_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    provider_reference: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True
    )
    payment_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("payments.id", ondelete="SET NULL"), nullable=True
    )
    order_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )
    provider_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    outcome: Mapped[str] = mapped_column(
        String(30), nullable=False, default="RECEIVED", server_default="RECEIVED"
    )
    error_code: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "provider", "event_id", name="uq_payment_webhook_provider_event"
        ),
        Index("ix_payment_webhook_ledger_payment_id", "payment_id"),
        Index("ix_payment_webhook_ledger_order_id", "order_id"),
        CheckConstraint(
            "outcome IN ('RECEIVED', 'PROCESSED', 'IGNORED')",
            name="ck_payment_webhook_outcome",
        ),
    )


# â”€â”€ Risk Assessment History â”€â”€


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    site_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    sector: Mapped[str] = mapped_column(String(50), nullable=False)
    risk_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    triggered_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    details_json: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default="{}"
    )
    assessed_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )


# â”€â”€ Order Event (timeline) â”€â”€


class OrderEvent(Base):
    __tablename__ = "order_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    order_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    actor_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_customer_visible: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    metadata_json: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    order = relationship("Order", backref="events_rel")


class IntegrationOutbox(Base):
    """Durable, idempotent queue for ERP and other external integrations."""

    __tablename__ = "integration_outbox"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False, default="erpnext")
    aggregate_type: Mapped[str] = mapped_column(String(50), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(100), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    idempotency_key: Mapped[str] = mapped_column(
        String(160), nullable=False, unique=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default="3"
    )
    external_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    external_model: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    last_error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    next_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    claimed_by: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True
    )
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, index=True
    )
    dead_lettered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ErpExternalReference(Base):
    """Provider mapping/projection; GeoVision's internal ID remains authoritative."""

    __tablename__ = "erp_external_references"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    internal_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    external_model: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    external_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    invoice_status: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    stock_status: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    purchase_status: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    provider_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    last_callback_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "resource_type",
            "internal_id",
            name="uq_erp_reference_internal",
        ),
        UniqueConstraint(
            "provider",
            "external_model",
            "external_id",
            name="uq_erp_reference_external",
        ),
        Index(
            "ix_erp_reference_company_resource",
            "company_id",
            "resource_type",
        ),
    )


class ErpCallbackReceipt(Base):
    """Replay-safe audit receipt for authenticated ERP status callbacks."""

    __tablename__ = "erp_callback_receipts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    event_id: Mapped[str] = mapped_column(String(160), nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    signature_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    internal_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("provider", "event_id", name="uq_erp_callback_provider_event"),
        CheckConstraint(
            "outcome IN ('PROCESSED', 'DUPLICATE', 'IGNORED')",
            name="ck_erp_callback_outcome",
        ),
    )


class AccountEvent(Base):
    """Customer-visible event feed used by mobile polling/SSE clients."""

    __tablename__ = "account_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    workspace_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False, index=True
    )


class Notification(Base):
    """Durable, provider-neutral notification shown in the customer inbox.

    ``recipient_key`` is an opaque correlation key (for example ``user:<id>``
    or ``invitation:<id>``), never an email address.  Navigation is represented
    only by the typed ``target_type``/``target_id`` pair; provider URLs do not
    belong in the notification record.
    """

    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    recipient_user_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    recipient_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    recipient_key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    notification_type: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False, default="INFO", server_default="INFO", index=True
    )
    target_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="NONE", server_default="NONE", index=True
    )
    target_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True
    )
    deduplication_key: Mapped[str] = mapped_column(String(240), nullable=False)
    aggregation_key: Mapped[Optional[str]] = mapped_column(
        String(240), nullable=True, index=True
    )
    occurrence_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    first_occurred_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now
    )
    last_occurred_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now, index=True
    )
    aggregation_window_ends_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, index=True
    )
    read_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now, onupdate=utc_now
    )

    __table_args__ = (
        CheckConstraint(
            "recipient_kind IN ('USER', 'PRE_ACCOUNT')",
            name="ck_notification_recipient_kind",
        ),
        CheckConstraint(
            "(recipient_kind = 'USER' AND recipient_user_id IS NOT NULL) OR "
            "(recipient_kind = 'PRE_ACCOUNT' AND recipient_user_id IS NULL)",
            name="ck_notification_recipient_identity",
        ),
        CheckConstraint(
            "severity IN ('INFO', 'WATCH', 'WARNING', 'CRITICAL')",
            name="ck_notification_severity",
        ),
        CheckConstraint(
            "target_type IN ('NONE', 'ASSET', 'REPORT', 'ACTION', 'ORDER', "
            "'SHIPMENT', 'INVITATION', 'SERVICE')",
            name="ck_notification_target_type",
        ),
        CheckConstraint(
            "(target_type = 'NONE' AND target_id IS NULL) OR "
            "(target_type <> 'NONE' AND target_id IS NOT NULL)",
            name="ck_notification_typed_target",
        ),
        CheckConstraint(
            "occurrence_count > 0", name="ck_notification_occurrence_count"
        ),
        UniqueConstraint(
            "organization_id",
            "recipient_key",
            "deduplication_key",
            name="uq_notification_recipient_deduplication",
        ),
        Index(
            "ix_notifications_recipient_inbox",
            "recipient_user_id",
            "read_at",
            "last_occurred_at",
        ),
        Index(
            "ix_notifications_scope_recipient",
            "organization_id",
            "workspace_id",
            "recipient_key",
        ),
        Index(
            "ix_notifications_aggregation_window",
            "organization_id",
            "recipient_key",
            "aggregation_key",
            "aggregation_window_ends_at",
        ),
    )


class NotificationEventLink(Base):
    """Idempotent source-event linkage, including events folded into an aggregate."""

    __tablename__ = "notification_event_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    notification_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("notifications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("operational_domain_events.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    recipient_key: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now
    )

    __table_args__ = (
        UniqueConstraint(
            "event_id", "recipient_key", name="uq_notification_event_recipient"
        ),
        UniqueConstraint(
            "notification_id", "event_id", name="uq_notification_event_link"
        ),
    )


class NotificationEndpoint(Base):
    """Encrypted push endpoint registered to one authenticated installation."""

    __tablename__ = "notification_endpoints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    installation_id: Mapped[str] = mapped_column(
        String(200), nullable=False, unique=True
    )
    platform: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    handle_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    handle_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    encryption_key_id: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="ACTIVE",
        server_default="ACTIVE",
        index=True,
    )
    last_registered_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now
    )
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    lifecycle_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now, onupdate=utc_now
    )

    __table_args__ = (
        CheckConstraint(
            "platform IN ('IOS', 'ANDROID', 'WEB')",
            name="ck_notification_endpoint_platform",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'DISABLED', 'REVOKED')",
            name="ck_notification_endpoint_status",
        ),
        CheckConstraint(
            "lifecycle_version > 0", name="ck_notification_endpoint_version"
        ),
        UniqueConstraint(
            "provider", "handle_digest", name="uq_notification_endpoint_provider_handle"
        ),
        Index("ix_notification_endpoints_user_status", "user_id", "status"),
    )


class NotificationPreference(Base):
    """Per-user, optionally per-organization notification channel policy."""

    __tablename__ = "notification_preferences"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    scope_key: Mapped[str] = mapped_column(String(40), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    in_app_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    push_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    email_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    sms_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    minimum_severity: Mapped[str] = mapped_column(
        String(20), nullable=False, default="INFO", server_default="INFO"
    )
    quiet_hours_start: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    quiet_hours_end: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="UTC", server_default="UTC"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now, onupdate=utc_now
    )

    __table_args__ = (
        CheckConstraint(
            "minimum_severity IN ('INFO', 'WATCH', 'WARNING', 'CRITICAL')",
            name="ck_notification_preference_severity",
        ),
        CheckConstraint(
            "(organization_id IS NULL AND scope_key = 'GLOBAL') OR "
            "(organization_id IS NOT NULL AND scope_key = organization_id)",
            name="ck_notification_preference_scope",
        ),
        CheckConstraint(
            "(quiet_hours_start IS NULL AND quiet_hours_end IS NULL) OR "
            "(quiet_hours_start IS NOT NULL AND quiet_hours_end IS NOT NULL)",
            name="ck_notification_preference_quiet_hours",
        ),
        UniqueConstraint(
            "user_id",
            "scope_key",
            "category",
            name="uq_notification_preference_scope_category",
        ),
    )


class NotificationDelivery(Base):
    """Retryable external-delivery projection; inbox state remains independent."""

    __tablename__ = "notification_deliveries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    notification_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("notifications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    endpoint_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("notification_endpoints.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PENDING",
        server_default="PENDING",
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(240), nullable=False, unique=True, index=True
    )
    payload_ciphertext: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload_key_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    payload_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5, server_default="5"
    )
    next_attempt_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, index=True
    )
    claimed_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    provider_message_id: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True
    )
    last_error_code: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    last_error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    dead_lettered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now, onupdate=utc_now
    )

    __table_args__ = (
        CheckConstraint(
            "channel IN ('PUSH', 'EMAIL', 'SMS')",
            name="ck_notification_delivery_channel",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'RETRY', 'DELIVERED', "
            "'SUPPRESSED', 'DEAD_LETTER')",
            name="ck_notification_delivery_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_notification_delivery_attempts"),
        CheckConstraint(
            "max_attempts > 0", name="ck_notification_delivery_max_attempts"
        ),
        CheckConstraint(
            "(payload_ciphertext IS NULL AND payload_key_id IS NULL AND "
            "payload_sha256 IS NULL) OR (payload_ciphertext IS NOT NULL AND "
            "payload_key_id IS NOT NULL AND payload_sha256 IS NOT NULL)",
            name="ck_notification_delivery_encrypted_payload",
        ),
        Index(
            "ix_notification_deliveries_due",
            "status",
            "next_attempt_at",
            "created_at",
        ),
        Index(
            "ix_notification_deliveries_notification_channel",
            "notification_id",
            "channel",
            "status",
        ),
        Index(
            "ix_notification_deliveries_claim",
            "status",
            "lease_expires_at",
        ),
    )


# â”€â”€ Deliverable â”€â”€


class Deliverable(Base):
    __tablename__ = "deliverables"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    order_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_item_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    deliverable_type: Mapped[str] = mapped_column(String(50), nullable=False)
    storage_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    download_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    download_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_ready: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    order = relationship("Order", backref="deliverables_rel")


class CompanyEntitlement(Base):
    """Prepaid commercial entitlement for a company.

    Angola's card/subscription rails are unreliable, so GeoVision sells prepaid
    windows (a validity period + a sensor allowance for a tier/kit) rather than
    auto-recurring subscriptions. One row per company; days-remaining is derived
    from ``valid_until`` at read time.
    """

    __tablename__ = "company_entitlements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    tier: Mapped[str] = mapped_column(String(40), nullable=False, default="starter")
    kit: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    sensor_allowance: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )


class Recommendation(Base):
    """The decision layer between an alert and an action.

    Per the GeoVision dossier the platform loop is
    sense -> alert -> **recommendation** -> action (service/command/catalogue).
    A recommendation turns a raw alert into human-readable advice and, where
    useful, links to a GeoVision catalogue item so action can be taken at the
    moment of need. The stored ``marketplace`` action is a legacy wire alias.
    """

    __tablename__ = "recommendations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    site_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("sites.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    device_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("iot_devices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    alert_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("iot_alerts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    category: Mapped[str] = mapped_column(
        String(40), nullable=False
    )  # irrigation, replacement, inspection, drone_mission, investigate
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(String(800), nullable=False)
    priority: Mapped[str] = mapped_column(
        String(20), nullable=False, default="medium"
    )  # low|medium|high|critical
    action_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="review"
    )  # marketplace (legacy catalogue alias)|service_request|command|drone_mission|review
    product_id: Mapped[Optional[str]] = mapped_column(
        String(50), ForeignKey("shop_products.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="open", index=True
    )  # open|accepted|dismissed|done
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


# Compatibility alias so routers can import Profile per spec
Profile = UserProfile
