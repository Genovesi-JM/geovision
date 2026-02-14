"""
E-Commerce Models for GeoVision Supply Hub / Loja

Supports:
- Product catalog (physical + digital + services)
- Shopping cart with coupons and tax calculation
- Full order lifecycle with tracking
- Deliverables management (reports, GeoTIFFs, etc.)
- Invoice generation and payment tracking
"""
import uuid
from datetime import datetime
from typing import Optional, List
from enum import Enum

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
    JSON,
    Index,
    Enum as SQLEnum,
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


# ============ ENUMS ============

class ProductType(str, Enum):
    """Type of product/service."""
    PHYSICAL = "physical"       # Hardware, seeds, sensors
    DIGITAL = "digital"         # Reports, GeoTIFFs, datasets
    SERVICE = "service"         # NDVI analysis, mapping, spraying
    SUBSCRIPTION = "subscription"  # Monthly monitoring


class ProductCategory(str, Enum):
    """Product categories."""
    MAPPING = "mapping"         # 3D mapping, orthomosaics
    ANALYSIS = "analysis"       # NDVI, crop health, terrain
    HARDWARE = "hardware"       # Drones, sensors, IoT
    SUPPLIES = "supplies"       # Seeds, fertilizer, feed
    MONITORING = "monitoring"   # Subscription services
    CONSULTING = "consulting"   # Expert services
    SPRAYING = "spraying"       # Crop spraying services


class OrderStatus(str, Enum):
    """Order lifecycle states."""
    CREATED = "created"
    AWAITING_PAYMENT = "awaiting_payment"
    PAID = "paid"
    PROCESSING = "processing"
    DISPATCHED = "dispatched"       # For physical products
    ASSIGNED = "assigned"           # For services (team assigned)
    IN_PROGRESS = "in_progress"     # Service being executed
    DELIVERED = "delivered"         # Physical product delivered
    COMPLETED = "completed"         # Service completed
    REFUNDED = "refunded"
    CANCELLED = "cancelled"
    PARTIALLY_REFUNDED = "partially_refunded"


class PaymentMethod(str, Enum):
    """Supported payment methods."""
    MULTICAIXA_EXPRESS = "multicaixa_express"
    VISA_MASTERCARD = "visa_mastercard"
    IBAN_ANGOLA = "iban_angola"
    IBAN_INTERNATIONAL = "iban_international"


class DeliverableType(str, Enum):
    """Types of deliverables."""
    PDF_REPORT = "pdf_report"
    GEOTIFF = "geotiff"
    ORTHOMOSAIC = "orthomosaic"
    POINTCLOUD = "pointcloud"
    VIDEO = "video"
    DATASET = "dataset"
    CERTIFICATE = "certificate"
    INVOICE = "invoice"
    OTHER = "other"


class EventType(str, Enum):
    """Order event types for timeline."""
    ORDER_CREATED = "order_created"
    PAYMENT_INITIATED = "payment_initiated"
    PAYMENT_CONFIRMED = "payment_confirmed"
    PAYMENT_FAILED = "payment_failed"
    ORDER_PROCESSING = "order_processing"
    TEAM_ASSIGNED = "team_assigned"
    SERVICE_SCHEDULED = "service_scheduled"
    SERVICE_STARTED = "service_started"
    SERVICE_COMPLETED = "service_completed"
    SHIPPED = "shipped"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    DELIVERABLE_READY = "deliverable_ready"
    REFUND_INITIATED = "refund_initiated"
    REFUND_COMPLETED = "refund_completed"
    CANCELLED = "cancelled"
    NOTE_ADDED = "note_added"


# ============ PRODUCT MODELS ============

class Product(Base):
    """Product/Service in the catalog."""
    __tablename__ = "shop_products"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Basic info
    name = Column(String(200), nullable=False)
    slug = Column(String(200), unique=True, nullable=False)
    description = Column(Text)
    short_description = Column(String(500))
    
    # Type and category
    product_type = Column(SQLEnum(ProductType), nullable=False, default=ProductType.SERVICE)
    category = Column(SQLEnum(ProductCategory), nullable=False)
    
    # Pricing (in smallest currency unit - centavos/cents)
    price = Column(Integer, nullable=False)  # Base price
    currency = Column(String(3), default="AOA")
    compare_at_price = Column(Integer)  # Original price (for discounts)
    cost_price = Column(Integer)  # Internal cost
    
    # Tax
    tax_rate = Column(Float, default=0.14)  # 14% IVA Angola
    tax_included = Column(Boolean, default=True)
    
    # Stock (for physical products)
    track_inventory = Column(Boolean, default=False)
    stock_quantity = Column(Integer, default=0)
    allow_backorder = Column(Boolean, default=False)
    
    # Service configuration
    duration_hours = Column(Float)  # Estimated service duration
    requires_site = Column(Boolean, default=False)  # Needs site_id
    requires_scheduling = Column(Boolean, default=False)
    sectors = Column(JSON, default=list)  # Applicable sectors ['agro', 'mining']
    
    # Media
    image_url = Column(String(500))
    gallery = Column(JSON, default=list)  # List of image URLs
    
    # Status
    is_active = Column(Boolean, default=True)
    is_featured = Column(Boolean, default=False)
    
    # SEO
    meta_title = Column(String(200))
    meta_description = Column(String(500))
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    variants = relationship("ProductVariant", back_populates="product", cascade="all, delete-orphan")
    order_items = relationship("OrderItem", back_populates="product")
    
    __table_args__ = (
        Index("ix_shop_products_category", "category"),
        Index("ix_shop_products_type", "product_type"),
        Index("ix_shop_products_active", "is_active"),
    )


class ProductVariant(Base):
    """Product variants (e.g., different sizes, areas, durations)."""
    __tablename__ = "shop_product_variants"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    product_id = Column(String(36), ForeignKey("shop_products.id", ondelete="CASCADE"), nullable=False)
    
    name = Column(String(200), nullable=False)  # e.g., "50 hectares", "Basic", "Premium"
    sku = Column(String(100), unique=True)
    
    # Pricing override
    price = Column(Integer)  # If null, use product price
    compare_at_price = Column(Integer)
    
    # Stock
    stock_quantity = Column(Integer, default=0)
    
    # Attributes
    attributes = Column(JSON, default=dict)  # {"area_ha": 50, "resolution": "5cm"}
    
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    product = relationship("Product", back_populates="variants")


# ============ CART MODELS ============

class Cart(Base):
    """Shopping cart."""
    __tablename__ = "shop_carts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Owner
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    company_id = Column(String(36))  # For B2B purchases
    session_id = Column(String(100))  # For guest carts
    
    # Coupon
    coupon_code = Column(String(50))
    discount_amount = Column(Integer, default=0)
    discount_type = Column(String(20))  # 'percentage' or 'fixed'
    
    # Delivery
    delivery_method = Column(String(50))
    delivery_cost = Column(Integer, default=0)
    delivery_address = Column(JSON)
    
    # Site association (for services)
    site_id = Column(String(36))
    
    # Totals (calculated)
    subtotal = Column(Integer, default=0)
    tax_amount = Column(Integer, default=0)
    total = Column(Integer, default=0)
    
    # Status
    is_active = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = Column(DateTime)
    
    # Relationships
    items = relationship("CartItem", back_populates="cart", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("ix_shop_carts_user", "user_id"),
        Index("ix_shop_carts_session", "session_id"),
    )


class CartItem(Base):
    """Item in shopping cart."""
    __tablename__ = "shop_cart_items"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    cart_id = Column(String(36), ForeignKey("shop_carts.id", ondelete="CASCADE"), nullable=False)
    
    product_id = Column(String(36), ForeignKey("shop_products.id"), nullable=False)
    variant_id = Column(String(36), ForeignKey("shop_product_variants.id"))
    
    quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(Integer, nullable=False)  # Price at time of adding
    
    # Service options
    scheduled_date = Column(DateTime)
    custom_options = Column(JSON, default=dict)  # {"flight_date": "...", "area_ha": 100}
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    cart = relationship("Cart", back_populates="items")


# ============ ORDER MODELS ============

class Order(Base):
    """Customer order."""
    __tablename__ = "shop_orders"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_number = Column(String(20), unique=True, nullable=False)  # GV-2026-001234
    
    # Customer
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    company_id = Column(String(36))
    
    # Status
    status = Column(SQLEnum(OrderStatus), nullable=False, default=OrderStatus.CREATED)
    
    # Site association (for services)
    site_id = Column(String(36))
    project_name = Column(String(200))
    
    # Payment
    payment_method = Column(SQLEnum(PaymentMethod))
    payment_intent_id = Column(String(36))  # Link to payment system
    payment_reference = Column(String(100))  # IBAN reference
    payment_confirmed_at = Column(DateTime)
    
    # Pricing
    currency = Column(String(3), default="AOA")
    subtotal = Column(Integer, nullable=False)
    discount_amount = Column(Integer, default=0)
    coupon_code = Column(String(50))
    tax_amount = Column(Integer, default=0)
    delivery_cost = Column(Integer, default=0)
    total = Column(Integer, nullable=False)
    
    # Delivery info
    delivery_method = Column(String(50))
    delivery_address = Column(JSON)
    delivery_notes = Column(Text)
    estimated_delivery = Column(DateTime)
    actual_delivery = Column(DateTime)
    
    # Service info
    assigned_team = Column(String(200))
    scheduled_start = Column(DateTime)
    scheduled_end = Column(DateTime)
    actual_start = Column(DateTime)
    actual_end = Column(DateTime)
    
    # Customer notes
    customer_notes = Column(Text)
    internal_notes = Column(Text)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime)
    cancelled_at = Column(DateTime)
    
    # Extra data
    extra_data = Column(JSON, default=dict)
    
    # Relationships
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    events = relationship("OrderEvent", back_populates="order", cascade="all, delete-orphan", order_by="OrderEvent.created_at")
    deliverables = relationship("Deliverable", back_populates="order", cascade="all, delete-orphan")
    invoices = relationship("Invoice", back_populates="order", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("ix_shop_orders_user", "user_id"),
        Index("ix_shop_orders_status", "status"),
        Index("ix_shop_orders_number", "order_number"),
        Index("ix_shop_orders_site", "site_id"),
    )


class OrderItem(Base):
    """Line item in an order."""
    __tablename__ = "shop_order_items"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column(String(36), ForeignKey("shop_orders.id", ondelete="CASCADE"), nullable=False)
    
    product_id = Column(String(36), ForeignKey("shop_products.id"))
    variant_id = Column(String(36))
    
    # Snapshot at time of purchase
    product_name = Column(String(200), nullable=False)
    product_type = Column(SQLEnum(ProductType))
    sku = Column(String(100))
    
    quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(Integer, nullable=False)
    total_price = Column(Integer, nullable=False)
    
    # Tax
    tax_rate = Column(Float, default=0)
    tax_amount = Column(Integer, default=0)
    
    # Service options
    scheduled_date = Column(DateTime)
    custom_options = Column(JSON, default=dict)
    
    # Status tracking per item
    status = Column(String(50), default="pending")
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    order = relationship("Order", back_populates="items")
    product = relationship("Product", back_populates="order_items")


class OrderEvent(Base):
    """Timeline event for order tracking."""
    __tablename__ = "shop_order_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column(String(36), ForeignKey("shop_orders.id", ondelete="CASCADE"), nullable=False)
    
    event_type = Column(SQLEnum(EventType), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    
    # Actor
    user_id = Column(String(36))  # Who triggered the event
    actor_name = Column(String(200))  # "Sistema", "João Silva", etc.
    
    # Data
    extra_data = Column(JSON, default=dict)
    
    # Visibility
    is_customer_visible = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    order = relationship("Order", back_populates="events")
    
    __table_args__ = (
        Index("ix_shop_order_events_order", "order_id"),
    )


# ============ DELIVERABLES ============

class Deliverable(Base):
    """Deliverable files/reports for an order."""
    __tablename__ = "shop_deliverables"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column(String(36), ForeignKey("shop_orders.id", ondelete="CASCADE"), nullable=False)
    order_item_id = Column(String(36))  # Optional link to specific item
    
    # File info
    name = Column(String(200), nullable=False)
    description = Column(Text)
    deliverable_type = Column(SQLEnum(DeliverableType), nullable=False)
    
    # Storage
    storage_key = Column(String(500))  # S3 key
    file_size = Column(Integer)
    mime_type = Column(String(100))
    
    # Access
    download_url = Column(String(1000))  # Presigned URL (temporary)
    download_count = Column(Integer, default=0)
    expires_at = Column(DateTime)  # URL expiry
    
    # Status
    is_ready = Column(Boolean, default=False)
    generated_at = Column(DateTime)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    order = relationship("Order", back_populates="deliverables")
    
    __table_args__ = (
        Index("ix_shop_deliverables_order", "order_id"),
    )


# ============ INVOICES ============

class Invoice(Base):
    """Invoice for an order."""
    __tablename__ = "shop_invoices"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    invoice_number = Column(String(50), unique=True, nullable=False)  # FT 2026/00001
    
    order_id = Column(String(36), ForeignKey("shop_orders.id", ondelete="CASCADE"), nullable=False)
    
    # Type
    invoice_type = Column(String(20), default="invoice")  # invoice, receipt, proforma, credit_note
    
    # Customer info snapshot
    customer_name = Column(String(200))
    customer_email = Column(String(200))
    customer_tax_id = Column(String(50))  # NIF
    customer_address = Column(JSON)
    
    # Company info
    company_name = Column(String(200), default="GeoVision Lda")
    company_tax_id = Column(String(50))
    company_address = Column(JSON)
    
    # Amounts
    currency = Column(String(3), default="AOA")
    subtotal = Column(Integer, nullable=False)
    discount = Column(Integer, default=0)
    tax_amount = Column(Integer, default=0)
    total = Column(Integer, nullable=False)
    
    # Status
    status = Column(String(20), default="draft")  # draft, issued, paid, cancelled
    issued_at = Column(DateTime)
    due_date = Column(DateTime)
    paid_at = Column(DateTime)
    
    # PDF
    pdf_url = Column(String(500))
    pdf_storage_key = Column(String(500))
    
    # Legal
    atcud = Column(String(100))  # Angola tax code
    hash_code = Column(String(100))
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    order = relationship("Order", back_populates="invoices")
    
    __table_args__ = (
        Index("ix_shop_invoices_order", "order_id"),
        Index("ix_shop_invoices_number", "invoice_number"),
    )


# ============ COUPONS ============

class Coupon(Base):
    """Discount coupons."""
    __tablename__ = "shop_coupons"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    code = Column(String(50), unique=True, nullable=False)
    description = Column(String(200))
    
    # Discount
    discount_type = Column(String(20), nullable=False)  # 'percentage' or 'fixed'
    discount_value = Column(Integer, nullable=False)  # Percentage (0-100) or fixed amount
    
    # Limits
    minimum_order = Column(Integer, default=0)
    maximum_discount = Column(Integer)  # Cap for percentage discounts
    usage_limit = Column(Integer)  # Total uses allowed
    usage_count = Column(Integer, default=0)
    usage_limit_per_user = Column(Integer, default=1)
    
    # Restrictions
    applicable_products = Column(JSON)  # List of product IDs, null = all
    applicable_categories = Column(JSON)  # List of categories
    excluded_products = Column(JSON)
    
    # Validity
    starts_at = Column(DateTime)
    expires_at = Column(DateTime)
    is_active = Column(Boolean, default=True)
    
    # Targeting
    first_order_only = Column(Boolean, default=False)
    specific_users = Column(JSON)  # List of user IDs
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index("ix_shop_coupons_code", "code"),
    )


# ============ TAX CONFIGURATION ============

class TaxRate(Base):
    """Tax rates by country/region."""
    __tablename__ = "shop_tax_rates"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    name = Column(String(100), nullable=False)  # "IVA Angola", "VAT EU"
    country_code = Column(String(2), nullable=False)  # "AO", "PT", "US"
    region = Column(String(100))  # State/province if applicable
    
    rate = Column(Float, nullable=False)  # 0.14 = 14%
    
    # Applicability
    applies_to = Column(JSON)  # Product types or categories
    
    is_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index("ix_shop_tax_rates_country", "country_code"),
    )


# ============ DELIVERY CONFIGURATION ============

class DeliveryZone(Base):
    """Delivery zones and pricing."""
    __tablename__ = "shop_delivery_zones"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    name = Column(String(100), nullable=False)  # "Luanda", "Províncias", "Internacional"
    
    # Area definition
    country_codes = Column(JSON)  # ["AO"]
    regions = Column(JSON)  # ["Luanda", "Bengo"]
    zip_codes = Column(JSON)  # Optional postal codes
    
    # Pricing
    base_cost = Column(Integer, default=0)  # In smallest currency unit
    cost_per_kg = Column(Integer, default=0)
    free_shipping_threshold = Column(Integer)  # Order value for free shipping
    
    # Timing
    estimated_days_min = Column(Integer)
    estimated_days_max = Column(Integer)
    
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)


# ============ PAYMENT PROOF (for bank transfers) ============

class PaymentProof(Base):
    """Proof of payment uploaded by customer for bank transfers."""
    __tablename__ = "shop_payment_proofs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column(String(36), ForeignKey("shop_orders.id", ondelete="CASCADE"), nullable=False)
    
    # File
    filename = Column(String(200))
    storage_key = Column(String(500))
    file_size = Column(Integer)
    mime_type = Column(String(100))
    
    # Transfer details
    bank_name = Column(String(200))
    transfer_reference = Column(String(100))
    transfer_date = Column(DateTime)
    amount = Column(Integer)
    
    # Validation
    status = Column(String(20), default="pending")  # pending, approved, rejected
    validated_by = Column(String(36))  # Admin user ID
    validated_at = Column(DateTime)
    rejection_reason = Column(Text)
    
    # Customer info
    uploaded_by = Column(String(36))
    notes = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index("ix_shop_payment_proofs_order", "order_id"),
    )
