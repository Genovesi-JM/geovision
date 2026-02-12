"""
GeoVision Multi-Tenant Models v2

Complete multi-tenant architecture with:
- Companies/Accounts with data isolation
- Users, Roles, Permissions
- Sites/Projects per company
- Dataset Registry for external data ingestion
- Risk Engine results
- Alerts system
- Payment orchestration
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, List

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text, JSON,
    ForeignKey, Index, UniqueConstraint, Enum as SQLEnum
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


def generate_uuid() -> str:
    return str(uuid.uuid4())


# =============================================================================
# ENUMS
# =============================================================================

class SectorType(str, Enum):
    MINING = "mining"
    INFRASTRUCTURE = "infrastructure"
    AGRICULTURE = "agriculture"
    SOLAR = "solar"
    CONSTRUCTION = "construction"
    DEMINING = "demining"


class RoleType(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"
    OPERATOR = "operator"
    VIEWER = "viewer"


class DatasetSourceTool(str, Enum):
    # Drone/Photogrammetry
    DJI_TERRA = "dji_terra"
    PIX4D = "pix4d"
    METASHAPE = "metashape"
    DRONEDEPLOY = "dronedeploy"
    # GIS
    ARCGIS = "arcgis"
    QGIS = "qgis"
    # LiDAR
    LIDAR_GENERIC = "lidar_generic"
    # BIM/Infra
    AUTODESK_BIM360 = "autodesk_bim360"
    AUTODESK_ACC = "autodesk_acc"
    PROCORE = "procore"
    # Manual
    MANUAL_UPLOAD = "manual_upload"
    API_IMPORT = "api_import"


class DatasetStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"
    ARCHIVED = "archived"


class FileType(str, Enum):
    ORTHOMOSAIC = "orthomosaic"
    DSM = "dsm"
    DTM = "dtm"
    POINTCLOUD_LAS = "pointcloud_las"
    POINTCLOUD_LAZ = "pointcloud_laz"
    POINTCLOUD_E57 = "pointcloud_e57"
    POINTCLOUD_PLY = "pointcloud_ply"
    MODEL_OBJ = "model_obj"
    MODEL_FBX = "model_fbx"
    SHAPEFILE = "shapefile"
    GEOJSON = "geojson"
    GEOTIFF = "geotiff"
    DXF = "dxf"
    DWG = "dwg"
    PDF = "pdf"
    CSV = "csv"
    DOCX = "docx"
    IMAGE_JPG = "image_jpg"
    IMAGE_PNG = "image_png"
    OTHER = "other"


class AlertSeverity(str, Enum):
    INFO = "info"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class PaymentProvider(str, Enum):
    MULTICAIXA_EXPRESS = "multicaixa_express"
    VISA_MASTERCARD = "visa_mastercard"
    IBAN_TRANSFER = "iban_transfer"
    MANUAL = "manual"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class InvoiceStatus(str, Enum):
    DRAFT = "draft"
    SENT = "sent"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


# =============================================================================
# MULTI-TENANT CORE: COMPANY / ACCOUNT
# =============================================================================

class Company(Base):
    """
    Top-level tenant entity. All data is isolated by company_id.
    """
    __tablename__ = "companies"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    legal_name = Column(String(255))
    nif = Column(String(50))  # Tax ID (NIF Angola)
    
    # Contact
    email = Column(String(255))
    phone = Column(String(50))
    address = Column(Text)
    city = Column(String(100))
    country = Column(String(100), default="Angola")
    
    # Settings
    primary_sector = Column(SQLEnum(SectorType))
    sectors_enabled = Column(JSON)  # List of enabled sectors
    subscription_tier = Column(String(50), default="starter")  # starter, professional, enterprise
    
    # Status
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Storage quota
    storage_quota_gb = Column(Integer, default=50)
    storage_used_bytes = Column(Integer, default=0)
    
    # Relationships
    users = relationship("CompanyUser", back_populates="company", cascade="all, delete-orphan")
    sites = relationship("Site", back_populates="company", cascade="all, delete-orphan")
    datasets = relationship("Dataset", back_populates="company", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="company", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="company", cascade="all, delete-orphan")
    api_keys = relationship("APIKey", back_populates="company", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="company", cascade="all, delete-orphan")


class CompanyUser(Base):
    """
    User membership in a company with role.
    A user can belong to multiple companies.
    """
    __tablename__ = "company_users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(36), ForeignKey("users_v2.id", ondelete="CASCADE"), nullable=False)
    role = Column(SQLEnum(RoleType), default=RoleType.VIEWER)
    
    # Permissions override (JSON for fine-grained control)
    permissions = Column(JSON)  # e.g., {"can_upload": true, "can_delete": false}
    
    is_active = Column(Boolean, default=True)
    invited_at = Column(DateTime, default=datetime.utcnow)
    joined_at = Column(DateTime)
    
    company = relationship("Company", back_populates="users")
    user = relationship("UserV2", back_populates="company_memberships")

    __table_args__ = (
        UniqueConstraint("company_id", "user_id", name="uq_company_user"),
        Index("ix_company_users_company", "company_id"),
        Index("ix_company_users_user", "user_id"),
    )


class UserV2(Base):
    """
    User entity (can belong to multiple companies).
    """
    __tablename__ = "users_v2"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255))
    
    # Profile
    full_name = Column(String(255))
    phone = Column(String(50))
    avatar_url = Column(String(500))
    
    # Auth
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    last_login_at = Column(DateTime)
    
    # OAuth
    google_id = Column(String(255))
    microsoft_id = Column(String(255))
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # System admin flag (GeoVision staff)
    is_superadmin = Column(Boolean, default=False)
    
    company_memberships = relationship("CompanyUser", back_populates="user", cascade="all, delete-orphan")


# =============================================================================
# SITES / PROJECTS
# =============================================================================

class Site(Base):
    """
    A physical location or project within a company.
    All datasets, alerts, etc. are scoped to a site.
    """
    __tablename__ = "sites"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    
    name = Column(String(255), nullable=False)
    description = Column(Text)
    sector = Column(SQLEnum(SectorType), nullable=False)
    
    # Location
    address = Column(Text)
    city = Column(String(100))
    province = Column(String(100))
    country = Column(String(100), default="Angola")
    latitude = Column(Float)
    longitude = Column(Float)
    area_hectares = Column(Float)
    
    # Metadata
    project_code = Column(String(50))
    client_name = Column(String(255))  # If different from company
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    
    # Status
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    company = relationship("Company", back_populates="sites")
    datasets = relationship("Dataset", back_populates="site", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="site", cascade="all, delete-orphan")
    risk_assessments = relationship("RiskAssessment", back_populates="site", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_sites_company", "company_id"),
        Index("ix_sites_sector", "sector"),
    )


# =============================================================================
# DATASET REGISTRY
# =============================================================================

class Dataset(Base):
    """
    Registry of all datasets uploaded or ingested from external tools.
    Normalized schema for tracking data from drones, GIS, LiDAR, BIM, etc.
    """
    __tablename__ = "datasets"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    site_id = Column(String(36), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    
    # Source identification
    name = Column(String(255), nullable=False)
    description = Column(Text)
    source_tool = Column(SQLEnum(DatasetSourceTool), nullable=False)
    source_version = Column(String(50))  # e.g., "Pix4D 4.8.1"
    
    # Dates
    capture_date = Column(DateTime)  # When data was captured in field
    processing_date = Column(DateTime)  # When processed by external tool
    upload_date = Column(DateTime, default=datetime.utcnow)
    
    # Status
    status = Column(SQLEnum(DatasetStatus), default=DatasetStatus.PENDING)
    processing_progress = Column(Integer, default=0)  # 0-100
    error_message = Column(Text)
    
    # Metrics extracted from data
    metrics_json = Column(JSON)  # Flexible metrics per sector/tool
    # Example for mining: {"volume_m3": 12500, "slope_stability": 94}
    # Example for agro: {"ndvi_avg": 0.72, "stress_area_pct": 12}
    
    # Tags and categorization
    tags = Column(JSON)  # List of tags
    sector = Column(SQLEnum(SectorType))
    
    # Audit
    uploaded_by_user_id = Column(String(36), ForeignKey("users_v2.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    company = relationship("Company", back_populates="datasets")
    site = relationship("Site", back_populates="datasets")
    files = relationship("DatasetFile", back_populates="dataset", cascade="all, delete-orphan")
    risk_assessments = relationship("RiskAssessment", back_populates="dataset")

    __table_args__ = (
        Index("ix_datasets_company", "company_id"),
        Index("ix_datasets_site", "site_id"),
        Index("ix_datasets_status", "status"),
        Index("ix_datasets_source", "source_tool"),
    )


class DatasetFile(Base):
    """
    Individual files within a dataset.
    Stored in S3-compatible object storage.
    """
    __tablename__ = "dataset_files"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    dataset_id = Column(String(36), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    
    # File info
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255))
    file_type = Column(SQLEnum(FileType), nullable=False)
    mime_type = Column(String(100))
    size_bytes = Column(Integer, nullable=False)
    
    # Storage
    storage_bucket = Column(String(100), nullable=False)
    storage_key = Column(String(500), nullable=False)  # S3 key/path
    storage_url = Column(String(1000))  # Pre-signed URL (cached)
    
    # Checksums
    md5_hash = Column(String(32))
    sha256_hash = Column(String(64))
    
    # Processing status
    is_processed = Column(Boolean, default=False)
    processing_result = Column(JSON)  # Metadata extracted from file
    
    # Geo bounds (if applicable)
    bbox_minx = Column(Float)
    bbox_miny = Column(Float)
    bbox_maxx = Column(Float)
    bbox_maxy = Column(Float)
    crs = Column(String(50))  # e.g., "EPSG:32733"
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    dataset = relationship("Dataset", back_populates="files")

    __table_args__ = (
        Index("ix_dataset_files_dataset", "dataset_id"),
        Index("ix_dataset_files_type", "file_type"),
    )


# =============================================================================
# RISK ENGINE
# =============================================================================

class RiskAssessment(Base):
    """
    Risk assessment result from the rule-based Risk Engine.
    """
    __tablename__ = "risk_assessments"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    site_id = Column(String(36), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    dataset_id = Column(String(36), ForeignKey("datasets.id", ondelete="SET NULL"))
    
    # Assessment
    sector = Column(SQLEnum(SectorType), nullable=False)
    risk_score = Column(Float, nullable=False)  # 0-100
    risk_level = Column(String(20), nullable=False)  # low, medium, high, critical
    
    # Detailed results
    triggers = Column(JSON)  # List of triggered rules
    # e.g., [{"rule": "slope_stability_low", "value": 75, "threshold": 80, "severity": "high"}]
    
    metrics_analyzed = Column(JSON)  # Input metrics
    recommendations = Column(JSON)  # List of recommendations
    
    # Generated alerts
    alerts_generated = Column(JSON)  # IDs of alerts created from this assessment
    
    # Audit
    engine_version = Column(String(20), default="1.0")
    computed_at = Column(DateTime, default=datetime.utcnow)
    computed_by = Column(String(50), default="system")  # "system" or user_id
    
    site = relationship("Site", back_populates="risk_assessments")
    dataset = relationship("Dataset", back_populates="risk_assessments")

    __table_args__ = (
        Index("ix_risk_assessments_company", "company_id"),
        Index("ix_risk_assessments_site", "site_id"),
        Index("ix_risk_assessments_score", "risk_score"),
    )


# =============================================================================
# ALERTS
# =============================================================================

class Alert(Base):
    """
    Alert generated by Risk Engine or manual creation.
    """
    __tablename__ = "alerts"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    site_id = Column(String(36), ForeignKey("sites.id", ondelete="CASCADE"))
    
    # Alert details
    severity = Column(SQLEnum(AlertSeverity), nullable=False)
    status = Column(SQLEnum(AlertStatus), default=AlertStatus.ACTIVE)
    
    title = Column(String(255), nullable=False)
    description = Column(Text)
    sector = Column(SQLEnum(SectorType))
    
    # Source
    source_type = Column(String(50))  # "risk_engine", "sensor", "manual", "integration"
    source_id = Column(String(36))  # ID of source entity (risk_assessment_id, etc.)
    
    # Location
    location_name = Column(String(255))
    latitude = Column(Float)
    longitude = Column(Float)
    
    # Metadata
    metadata_json = Column(JSON)
    
    # Workflow
    acknowledged_by = Column(String(36), ForeignKey("users_v2.id"))
    acknowledged_at = Column(DateTime)
    resolved_by = Column(String(36), ForeignKey("users_v2.id"))
    resolved_at = Column(DateTime)
    resolution_notes = Column(Text)
    
    # Notifications
    email_sent = Column(Boolean, default=False)
    sms_sent = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    company = relationship("Company", back_populates="alerts")
    site = relationship("Site", back_populates="alerts")

    __table_args__ = (
        Index("ix_alerts_company", "company_id"),
        Index("ix_alerts_site", "site_id"),
        Index("ix_alerts_severity", "severity"),
        Index("ix_alerts_status", "status"),
        Index("ix_alerts_created", "created_at"),
    )


# =============================================================================
# PAYMENT ORCHESTRATOR
# =============================================================================

class Order(Base):
    """
    Order/purchase request from a company.
    """
    __tablename__ = "orders"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    
    # Order details
    order_number = Column(String(50), unique=True, nullable=False)
    description = Column(Text)
    
    # Items
    items = Column(JSON)  # List of line items
    # e.g., [{"type": "subscription", "plan": "professional", "months": 12, "amount": 500000}]
    
    # Amounts (in AOA centavos or smallest unit)
    subtotal = Column(Integer, nullable=False)  # Before tax
    tax_amount = Column(Integer, default=0)
    discount_amount = Column(Integer, default=0)
    total_amount = Column(Integer, nullable=False)
    currency = Column(String(3), default="AOA")
    
    # Status
    status = Column(String(20), default="pending")  # pending, paid, cancelled, refunded
    
    # Billing
    billing_name = Column(String(255))
    billing_nif = Column(String(50))
    billing_address = Column(Text)
    
    # Audit
    created_by = Column(String(36), ForeignKey("users_v2.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    company = relationship("Company", back_populates="orders")
    invoices = relationship("Invoice", back_populates="order")
    payment_intents = relationship("PaymentIntent", back_populates="order")

    __table_args__ = (
        Index("ix_orders_company", "company_id"),
        Index("ix_orders_number", "order_number"),
        Index("ix_orders_status", "status"),
    )


class Invoice(Base):
    """
    Invoice generated for an order.
    """
    __tablename__ = "invoices"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    order_id = Column(String(36), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    
    # Invoice details
    invoice_number = Column(String(50), unique=True, nullable=False)
    status = Column(SQLEnum(InvoiceStatus), default=InvoiceStatus.DRAFT)
    
    # Dates
    issue_date = Column(DateTime, default=datetime.utcnow)
    due_date = Column(DateTime)
    paid_date = Column(DateTime)
    
    # Amounts
    total_amount = Column(Integer, nullable=False)
    amount_paid = Column(Integer, default=0)
    currency = Column(String(3), default="AOA")
    
    # PDF
    pdf_storage_key = Column(String(500))
    pdf_url = Column(String(1000))
    
    # Metadata
    notes = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    order = relationship("Order", back_populates="invoices")

    __table_args__ = (
        Index("ix_invoices_order", "order_id"),
        Index("ix_invoices_number", "invoice_number"),
        Index("ix_invoices_status", "status"),
    )


class PaymentIntent(Base):
    """
    Payment intent - represents an attempt to collect payment.
    """
    __tablename__ = "payment_intents"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    order_id = Column(String(36), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    
    # Provider
    provider = Column(SQLEnum(PaymentProvider), nullable=False)
    provider_reference = Column(String(255))  # External reference from provider
    
    # Amount
    amount = Column(Integer, nullable=False)
    currency = Column(String(3), default="AOA")
    
    # Status
    status = Column(SQLEnum(PaymentStatus), default=PaymentStatus.PENDING)
    
    # Provider-specific data
    provider_data = Column(JSON)
    # Multicaixa: {"reference": "123456789", "entity": "12345"}
    # IBAN: {"iban": "AO06...", "reference": "GV-2026-001"}
    # Card: {"last4": "1234", "brand": "visa"}
    
    # Expiry (for references that expire)
    expires_at = Column(DateTime)
    
    # Idempotency
    idempotency_key = Column(String(100), unique=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    order = relationship("Order", back_populates="payment_intents")
    transactions = relationship("PaymentTransaction", back_populates="payment_intent")

    __table_args__ = (
        Index("ix_payment_intents_order", "order_id"),
        Index("ix_payment_intents_provider", "provider"),
        Index("ix_payment_intents_status", "status"),
        Index("ix_payment_intents_reference", "provider_reference"),
    )


class PaymentTransaction(Base):
    """
    Actual payment transaction record.
    """
    __tablename__ = "payment_transactions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    payment_intent_id = Column(String(36), ForeignKey("payment_intents.id", ondelete="CASCADE"), nullable=False)
    
    # Transaction details
    transaction_type = Column(String(20), nullable=False)  # payment, refund, chargeback
    amount = Column(Integer, nullable=False)
    currency = Column(String(3), default="AOA")
    
    # Status
    status = Column(SQLEnum(PaymentStatus), nullable=False)
    
    # Provider response
    provider_transaction_id = Column(String(255))
    provider_response = Column(JSON)
    
    # Error details
    error_code = Column(String(50))
    error_message = Column(Text)
    
    # Timestamps
    initiated_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    
    payment_intent = relationship("PaymentIntent", back_populates="transactions")

    __table_args__ = (
        Index("ix_payment_transactions_intent", "payment_intent_id"),
        Index("ix_payment_transactions_provider_id", "provider_transaction_id"),
    )


class WebhookEvent(Base):
    """
    Log of all webhook events received from payment providers.
    """
    __tablename__ = "webhook_events"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    
    # Source
    provider = Column(SQLEnum(PaymentProvider), nullable=False)
    event_type = Column(String(100), nullable=False)
    
    # Payload
    payload = Column(JSON, nullable=False)
    headers = Column(JSON)
    
    # Verification
    signature = Column(String(500))
    is_verified = Column(Boolean, default=False)
    
    # Processing
    is_processed = Column(Boolean, default=False)
    processed_at = Column(DateTime)
    processing_result = Column(JSON)
    error_message = Column(Text)
    
    # Related entities
    payment_intent_id = Column(String(36), ForeignKey("payment_intents.id"))
    
    received_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_webhook_events_provider", "provider"),
        Index("ix_webhook_events_type", "event_type"),
        Index("ix_webhook_events_processed", "is_processed"),
    )


# =============================================================================
# API KEYS & CONNECTORS
# =============================================================================

class APIKey(Base):
    """
    API keys for external integrations.
    """
    __tablename__ = "api_keys"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    
    name = Column(String(100), nullable=False)
    key_hash = Column(String(255), nullable=False)  # Hashed API key
    key_prefix = Column(String(10), nullable=False)  # First 8 chars for identification
    
    # Permissions
    scopes = Column(JSON)  # List of allowed scopes
    # e.g., ["datasets:read", "datasets:write", "alerts:read"]
    
    # Rate limiting
    rate_limit_per_minute = Column(Integer, default=60)
    
    # Status
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime)
    last_used_at = Column(DateTime)
    
    created_by = Column(String(36), ForeignKey("users_v2.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    company = relationship("Company", back_populates="api_keys")

    __table_args__ = (
        Index("ix_api_keys_company", "company_id"),
        Index("ix_api_keys_prefix", "key_prefix"),
    )


class Connector(Base):
    """
    External connector configuration (e.g., Pix4D API, BIM 360 API).
    """
    __tablename__ = "connectors"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    
    connector_type = Column(String(50), nullable=False)
    # e.g., "pix4d", "dronedeploy", "bim360", "arcgis_online"
    
    name = Column(String(100), nullable=False)
    
    # Credentials (encrypted)
    credentials_encrypted = Column(Text)
    # Store: {"api_key": "...", "api_secret": "...", "refresh_token": "..."}
    
    # Settings
    settings = Column(JSON)
    # e.g., {"auto_sync": true, "sync_interval_hours": 24, "project_id": "..."}
    
    # Status
    is_active = Column(Boolean, default=True)
    last_sync_at = Column(DateTime)
    last_error = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_connectors_company", "company_id"),
        Index("ix_connectors_type", "connector_type"),
    )


# =============================================================================
# AUDIT LOG
# =============================================================================

class AuditLog(Base):
    """
    Audit trail for all important actions.
    """
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"))
    
    # Actor
    user_id = Column(String(36), ForeignKey("users_v2.id"))
    user_email = Column(String(255))
    ip_address = Column(String(45))
    user_agent = Column(String(500))
    
    # Action
    action = Column(String(50), nullable=False)
    # e.g., "dataset.upload", "payment.complete", "user.login", "alert.acknowledge"
    
    resource_type = Column(String(50))  # e.g., "dataset", "order", "site"
    resource_id = Column(String(36))
    
    # Details
    details = Column(JSON)
    # e.g., {"filename": "ortho.tif", "size_mb": 250}
    
    # Result
    status = Column(String(20), default="success")  # success, failure
    error_message = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_audit_logs_company", "company_id"),
        Index("ix_audit_logs_user", "user_id"),
        Index("ix_audit_logs_action", "action"),
        Index("ix_audit_logs_resource", "resource_type", "resource_id"),
        Index("ix_audit_logs_created", "created_at"),
    )
