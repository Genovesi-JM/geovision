# app/models.py
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
    Integer,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _uuid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String, nullable=False, default="client")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    profile = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    addresses = relationship("UserAddress", back_populates="user", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="user")
    account_members = relationship("AccountMember", back_populates="user", cascade="all, delete-orphan", overlaps="accounts,users")
    accounts = relationship("Account", secondary="account_members", back_populates="users", overlaps="account_members,members")

    @property
    def memberships(self):
        return self.account_members

class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    full_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    entity_type: Mapped[str] = mapped_column(String, nullable=False, default="individual")
    org_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    company: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    nif: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="profile")

class UserAddress(Base):
    __tablename__ = "user_addresses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String, default="Default", nullable=False)
    line1: Mapped[str] = mapped_column(String, nullable=False)
    line2: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    city: Mapped[str] = mapped_column(String, nullable=False)
    region: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    country: Mapped[str] = mapped_column(String, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="addresses")


class Account(Base):
    __tablename__ = "accounts"
    # Alembic: `alembic revision --autogenerate -m "add accounts tables"` then `alembic upgrade head`

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    sector_focus: Mapped[str] = mapped_column(String, nullable=False)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    org_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    modules_enabled: Mapped[str] = mapped_column(Text, nullable=False, default='["kpi","projects","store","alerts"]')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    members = relationship("AccountMember", back_populates="account", cascade="all, delete-orphan", overlaps="accounts,users")
    users = relationship("User", secondary="account_members", back_populates="accounts", overlaps="account_members,members")


class AccountMember(Base):
    __tablename__ = "account_members"

    account_id: Mapped[str] = mapped_column(String(36), ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String, nullable=False, default="member")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    account = relationship("Account", back_populates="members", overlaps="accounts,users")
    user = relationship("User", back_populates="account_members", overlaps="accounts,users")

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    category_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)

    category = relationship("Category", back_populates="products")
    images = relationship("ProductImage", back_populates="product", cascade="all, delete-orphan")
    inventory = relationship("Inventory", back_populates="product", uselist=False, cascade="all, delete-orphan")

class ProductImage(Base):
    __tablename__ = "product_images"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    product = relationship("Product", back_populates="images")

class Inventory(Base):
    __tablename__ = "inventory"

    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    qty_on_hand: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    qty_reserved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reorder_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    product = relationship("Product", back_populates="inventory")

class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    status: Mapped[str] = mapped_column(String, default="pending", nullable=False)
    currency: Mapped[str] = mapped_column(String, default="AOA", nullable=False)

    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    shipping_fee: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    discount_total: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    total: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)

    # snapshot simples (em SQLite: guardamos JSON como texto)
    shipping_address_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("subtotal >= 0"),
        CheckConstraint("total >= 0"),
    )

class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)

    product_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    sku: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)

    order = relationship("Order", back_populates="items")

    __table_args__ = (
        CheckConstraint("qty > 0"),
        CheckConstraint("unit_price >= 0"),
        CheckConstraint("line_total >= 0"),
    )


class ResetToken(Base):
    __tablename__ = "reset_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    token: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User")


class OAuthState(Base):
    __tablename__ = "oauth_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    state: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


# ── Auth Identity Linking (Google, Microsoft, etc.) ──

class AuthIdentity(Base):
    """Links external OAuth providers to local users (prevents duplicates)."""
    __tablename__ = "auth_identities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)          # google, microsoft
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False)  # sub from OIDC
    email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    display_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)       # JSON dump of userinfo
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", backref="auth_identities")

    __table_args__ = (
        # One identity per provider per user
        # UniqueConstraint handled by index below
    )


class RefreshTokenModel(Base):
    """Rotatable refresh tokens for persistent sessions."""
    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    token_hash: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    family_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)  # for rotation detection
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User")


# ── Contact Methods (WhatsApp, Instagram, Email, etc.) ──

class ContactMethod(Base):
    """Configurable contact channels per environment."""
    __tablename__ = "contact_methods"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    channel: Mapped[str] = mapped_column(String(50), nullable=False)    # whatsapp, instagram, email, phone, sms
    label: Mapped[str] = mapped_column(String(100), nullable=False)     # "Suporte", "Vendas", "Financeiro"
    value: Mapped[str] = mapped_column(String(500), nullable=False)     # phone number, handle, email address
    environment: Mapped[str] = mapped_column(String(20), nullable=False, default="prod")  # dev, staging, prod
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


# ── KPI Definitions and Values ──

class KpiDefinition(Base):
    """Per-sector KPI definitions."""
    __tablename__ = "kpi_definitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    sector: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # agro, mining, etc.
    key: Mapped[str] = mapped_column(String(100), nullable=False)                # ndvi_avg, ore_grade, etc.
    label: Mapped[str] = mapped_column(String(200), nullable=False)              # Human-readable name
    unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)       # %, ha, ton, etc.
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    icon: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)      # CSS icon class
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class KpiValue(Base):
    """Actual KPI measurements per site/dataset."""
    __tablename__ = "kpi_values"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    kpi_definition_id: Mapped[str] = mapped_column(String(36), ForeignKey("kpi_definitions.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(36), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    site_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    dataset_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    value: Mapped[str] = mapped_column(String(500), nullable=False)              # String to support numeric + text KPIs
    numeric_value: Mapped[Optional[float]] = mapped_column(Numeric(14, 4), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    definition = relationship("KpiDefinition")
    account = relationship("Account")


# ── Audit Log ──

class AuditLog(Base):
    """Who did what, when, and where."""
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    user_email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)              # login, create_order, update_company, etc.
    resource_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # user, order, company, etc.
    resource_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)           # JSON with additional context
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)  # IPv4/IPv6
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


# Compatibility alias so routers can import Profile per spec
Profile = UserProfile
