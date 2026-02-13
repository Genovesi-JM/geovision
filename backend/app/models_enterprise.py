# app/models_enterprise.py
"""
Enterprise Multi-Tenant Models for GeoVision Platform

Implements:
- Company/Organization management
- Site/Project management
- Dataset management
- Document storage
- Software integrations
- Audit logging
- Role-based access control (RBAC)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional, List
from enum import Enum

from sqlalchemy import (
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
    Integer,
    CheckConstraint,
    Index,
    JSON,
    Enum as SQLEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _uuid():
    return str(uuid.uuid4())


# ============ ENUMS ============

class CompanyStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    TRIAL = "trial"
    PENDING = "pending"
    CANCELLED = "cancelled"


class SubscriptionPlan(str, Enum):
    TRIAL = "trial"
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class UserRole(str, Enum):
    SUPER_ADMIN = "super_admin"       # GeoVision internal - full access
    ADMIN = "admin"                   # GeoVision internal - admin functions
    MANAGER = "manager"               # GeoVision internal - day-to-day ops
    ANALYST = "analyst"               # GeoVision internal - read + reports
    CLIENT_ADMIN = "client_admin"     # Client org admin
    CLIENT_MANAGER = "client_manager" # Client manager
    CLIENT_VIEWER = "client_viewer"   # Client read-only


class DocumentType(str, Enum):
    REPORT = "report"
    ORTHOMOSAIC = "orthomosaic"
    CONTRACT = "contract"
    INVOICE = "invoice"
    GEOTIFF = "geotiff"
    POINT_CLOUD = "point_cloud"
    SHAPEFILE = "shapefile"
    DXF = "dxf"
    OTHER = "other"


class DocumentStatus(str, Enum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    OFFICIAL = "official"
    ARCHIVED = "archived"


class ConnectorType(str, Enum):
    DJI_TERRA = "dji_terra"
    PIX4D = "pix4d"
    DRONEDEPLOY = "dronedeploy"
    ARCGIS = "arcgis"
    PROCORE = "procore"
    AUTODESK_BIM360 = "autodesk_bim360"
    WEBHOOK = "webhook"
    FOLDER_WATCH = "folder_watch"
    MANUAL = "manual"


class SyncStatus(str, Enum):
    NEVER = "never"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


# ============ COMPANY / ORGANIZATION ============

class Company(Base):
    """
    Multi-tenant company/organization.
    Each client organization has isolated data.
    """
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    
    # Basic Info
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    legal_name: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    tax_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # NIF
    
    # Contact
    email: Mapped[str] = mapped_column(String, nullable=False, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    whatsapp: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Address
    address_line1: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    address_line2: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    province: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    country: Mapped[str] = mapped_column(String(100), nullable=False, default="Angola")
    
    # Sectors (stored as JSON array)
    sectors: Mapped[str] = mapped_column(Text, nullable=False, default='["agro"]')
    
    # Subscription & Limits
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=CompanyStatus.TRIAL.value)
    subscription_plan: Mapped[str] = mapped_column(String(30), nullable=False, default=SubscriptionPlan.TRIAL.value)
    subscription_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    max_users: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    max_sites: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    max_storage_gb: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    
    # Usage Tracking
    current_users: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_sites: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    storage_used_gb: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    
    # Branding
    logo_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    primary_color: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    
    # Settings (JSON)
    settings: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    members = relationship("CompanyMember", back_populates="company", cascade="all, delete-orphan")
    sites = relationship("Site", back_populates="company", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="company", cascade="all, delete-orphan")
    connectors = relationship("SoftwareConnector", back_populates="company", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="company", cascade="all, delete-orphan")
    invoices = relationship("Invoice", back_populates="company", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_companies_email", "email"),
        Index("idx_companies_status", "status"),
    )


class CompanyMember(Base):
    """
    User membership in a company with role.
    A user can belong to multiple companies.
    """
    __tablename__ = "company_members"

    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    
    role: Mapped[str] = mapped_column(String(30), nullable=False, default=UserRole.CLIENT_VIEWER.value)
    permissions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array of permissions
    
    is_primary_contact: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    company = relationship("Company", back_populates="members")
    user = relationship("User")

    __table_args__ = (
        Index("idx_company_members_user", "user_id"),
    )


# ============ SITES / PROJECTS ============

class Site(Base):
    """
    A physical site/project location for a company.
    E.g., a farm, mine, construction site.
    """
    __tablename__ = "sites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Internal reference code
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Location
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    province: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    municipality: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Numeric(10, 7), nullable=True)
    area_hectares: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    
    # Type and Sector
    sector: Mapped[str] = mapped_column(String(50), nullable=False, default="agro")
    site_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # farm, mine, construction, etc.
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    
    # Metadata (JSON)
    metadata: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    company = relationship("Company", back_populates="sites")
    datasets = relationship("Dataset", back_populates="site", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="site")
    alerts = relationship("Alert", back_populates="site")

    __table_args__ = (
        Index("idx_sites_company", "company_id"),
        Index("idx_sites_sector", "sector"),
    )


# ============ DATASETS ============

class Dataset(Base):
    """
    A data collection for a site.
    E.g., drone flight data, satellite imagery, sensor readings.
    """
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    site_id: Mapped[str] = mapped_column(String(36), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True)
    
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Type
    data_type: Mapped[str] = mapped_column(String(50), nullable=False, default="drone_imagery")
    # drone_imagery, satellite, sensor, lidar, photogrammetry, etc.
    
    # Source
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # dji_terra, pix4d, manual, etc.
    connector_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("software_connectors.id", ondelete="SET NULL"), nullable=True)
    
    # Collection Info
    collection_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    processing_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Storage
    storage_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    storage_size_mb: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    # Status
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    # pending, processing, ready, error, archived
    
    # Metadata (JSON) - GSD, overlap, flight params, etc.
    metadata: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    site = relationship("Site", back_populates="datasets")
    connector = relationship("SoftwareConnector")
    documents = relationship("Document", back_populates="dataset")

    __table_args__ = (
        Index("idx_datasets_site", "site_id"),
        Index("idx_datasets_status", "status"),
    )


# ============ DOCUMENTS ============

class Document(Base):
    """
    Documents and files associated with a company, site, or dataset.
    Supports various file types: PDF, GeoTIFF, LAS, SHP, etc.
    """
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    site_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True, index=True)
    dataset_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # File Info
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_extension: Mapped[str] = mapped_column(String(20), nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    # Storage
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    storage_provider: Mapped[str] = mapped_column(String(30), nullable=False, default="local")  # local, s3, azure
    
    # Classification
    document_type: Mapped[str] = mapped_column(String(30), nullable=False, default=DocumentType.OTHER.value)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default=DocumentStatus.DRAFT.value)
    
    # Access Control
    is_confidential: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_official: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    download_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    
    # Metadata
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    metadata: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    
    # Versioning
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    previous_version_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    
    # Upload Info
    uploaded_by_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    company = relationship("Company", back_populates="documents")
    site = relationship("Site", back_populates="documents")
    dataset = relationship("Dataset", back_populates="documents")
    uploaded_by = relationship("User")

    __table_args__ = (
        Index("idx_documents_company", "company_id"),
        Index("idx_documents_site", "site_id"),
        Index("idx_documents_type", "document_type"),
        Index("idx_documents_status", "status"),
    )


# ============ SOFTWARE CONNECTORS ============

class SoftwareConnector(Base):
    """
    External software integration configuration.
    Stores encrypted API keys and connection details.
    """
    __tablename__ = "software_connectors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    
    connector_type: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Credentials (encrypted in production)
    api_key_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    api_secret_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    access_token_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    refresh_token_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Connection Settings
    base_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    webhook_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    webhook_secret: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Folder Watch (if applicable)
    watch_folder_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Status
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sync_status: Mapped[str] = mapped_column(String(20), nullable=False, default=SyncStatus.NEVER.value)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_sync_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Auto-sync Settings
    auto_sync_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sync_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    
    # Metadata (JSON)
    metadata: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    company = relationship("Company", back_populates="connectors")
    datasets = relationship("Dataset", back_populates="connector")

    __table_args__ = (
        Index("idx_connectors_company", "company_id"),
        Index("idx_connectors_type", "connector_type"),
    )


# ============ ALERTS ============

class Alert(Base):
    """
    System alerts for companies and sites.
    """
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    site_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True, index=True)
    
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default=AlertSeverity.INFO.value)
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Status
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved_by_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    
    # Metadata
    metadata: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    company = relationship("Company", back_populates="alerts")
    site = relationship("Site", back_populates="alerts")

    __table_args__ = (
        Index("idx_alerts_company", "company_id"),
        Index("idx_alerts_severity", "severity"),
        Index("idx_alerts_resolved", "is_resolved"),
    )


# ============ INVOICES ============

class Invoice(Base):
    """
    Invoice records for billing.
    """
    __tablename__ = "invoices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    
    invoice_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    
    # Amounts
    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="AOA")
    
    # Status
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    # draft, sent, paid, overdue, cancelled
    
    # Dates
    issue_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Payment
    payment_method: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    payment_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Items (JSON)
    items: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # PDF
    pdf_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    company = relationship("Company", back_populates="invoices")

    __table_args__ = (
        Index("idx_invoices_company", "company_id"),
        Index("idx_invoices_status", "status"),
    )


# ============ AUDIT LOG ============

class AuditLog(Base):
    """
    Audit trail for all significant actions.
    """
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    
    # Actor
    user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    user_email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    user_role: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    
    # Target
    company_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    
    # Action
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    # create, update, delete, login, logout, view, download, etc.
    
    # Details
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    changes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON diff
    
    # Request Info
    ip_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = relationship("User")

    __table_args__ = (
        Index("idx_audit_company", "company_id"),
        Index("idx_audit_action", "action"),
        Index("idx_audit_resource", "resource_type", "resource_id"),
    )


# ============ ADMIN CONTACTS ============

class AdminContact(Base):
    """
    GeoVision administrative contact information.
    Not visible to clients.
    """
    __tablename__ = "admin_contacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    whatsapp: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_internal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # Not shown to clients
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


# ============ TWO-FACTOR AUTH ============

class TwoFactorAuth(Base):
    """
    Two-factor authentication for admin users.
    """
    __tablename__ = "two_factor_auth"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    backup_codes_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User")
