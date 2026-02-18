"""
Admin Router — DB-backed

Administrative endpoints for GeoVision platform:
- Company/Client management
- User management
- Connector configuration
- Audit logs
- System monitoring
"""
import uuid
import json
import logging
from typing import Optional, List
from datetime import datetime, timezone
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.deps import require_admin, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

def _utcnow():
    return datetime.now(timezone.utc)


# ============ ENUMS ============

class CompanyStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    TRIAL = "trial"
    PENDING = "pending"


class SubscriptionPlan(str, Enum):
    TRIAL = "trial"
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class ConnectorType(str, Enum):
    DJI_TERRA = "dji_terra"
    PIX4D = "pix4d"
    DRONEDEPLOY = "dronedeploy"
    BIM360 = "bim360"
    ARCGIS = "arcgis"
    PROCORE = "procore"


# ============ SCHEMAS ============

class CompanyCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    tax_id: Optional[str] = Field(None, description="NIF/Tax ID")
    email: EmailStr
    phone: Optional[str] = None
    address: Optional[str] = None
    sectors: List[str] = Field(default_factory=list)
    subscription_plan: SubscriptionPlan = SubscriptionPlan.TRIAL
    max_users: int = Field(default=5, ge=1)
    max_sites: int = Field(default=10, ge=1)
    max_storage_gb: int = Field(default=50, ge=1)


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    tax_id: Optional[str] = None
    address: Optional[str] = None
    sectors: Optional[List[str]] = None
    status: Optional[CompanyStatus] = None
    subscription_plan: Optional[SubscriptionPlan] = None
    max_users: Optional[int] = None
    max_sites: Optional[int] = None
    max_storage_gb: Optional[int] = None


class CompanyOut(BaseModel):
    id: str
    name: str
    tax_id: Optional[str] = None
    email: str
    phone: Optional[str] = None
    address: Optional[str] = None
    sectors: List[str]
    status: str
    subscription_plan: str
    max_users: int
    max_sites: int
    max_storage_gb: int
    current_users: int = 0
    current_sites: int = 0
    storage_used_gb: float = 0.0
    created_at: datetime
    updated_at: datetime


class UserInCompany(BaseModel):
    id: str
    email: str
    name: Optional[str] = None
    role: str
    is_active: bool
    last_login: Optional[datetime] = None
    created_at: datetime


class ConnectorConfig(BaseModel):
    connector_type: ConnectorType
    name: str = Field(..., max_length=100)
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    base_url: Optional[str] = None
    webhook_secret: Optional[str] = None
    metadata: Optional[dict] = None
    enabled: bool = True


class ConnectorOut(BaseModel):
    id: str
    company_id: str
    connector_type: str
    name: str
    enabled: bool
    last_sync: Optional[datetime] = None
    sync_status: str = "never"
    created_at: datetime


class AuditLogEntry(BaseModel):
    id: str
    company_id: str
    user_id: Optional[str] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    details: Optional[dict] = None
    ip_address: Optional[str] = None
    created_at: datetime


class SystemStats(BaseModel):
    total_companies: int
    active_companies: int
    total_users: int
    total_sites: int
    total_datasets: int
    total_storage_gb: float
    payments_today: int
    payments_pending: int


# ============ DB HELPERS ============

def _log_audit(db: Session, company_id: str, action: str, resource_type: str,
               resource_id: str = None, user_id: str = None, details: dict = None):
    from app.models import AuditLog
    detail_str = json.dumps(details) if details else json.dumps({"company_id": company_id})
    entry = AuditLog(id=str(uuid.uuid4()), user_id=user_id,
                     action=action, resource_type=resource_type, resource_id=resource_id,
                     details=detail_str)
    db.add(entry)


# ============ COMPANY MANAGEMENT ============

@router.post("/companies", response_model=CompanyOut)
async def create_company(data: CompanyCreate, db: Session = Depends(get_db)):
    """Create a new company/client account."""
    from app.models import Company
    company_id = str(uuid.uuid4())
    now = _utcnow()
    company = Company(
        id=company_id, name=data.name, tax_id=data.tax_id, email=data.email,
        phone=data.phone, address=data.address,
        sectors=json.dumps(data.sectors),
        status=CompanyStatus.TRIAL.value, subscription_plan=data.subscription_plan.value,
        max_users=data.max_users, max_sites=data.max_sites, max_storage_gb=data.max_storage_gb,
    )
    db.add(company)
    _log_audit(db, company_id, "company_created", "company", company_id,
               details={"name": data.name, "plan": data.subscription_plan.value})
    db.commit(); db.refresh(company)
    logger.info(f"Created company {company_id}: {data.name}")
    return _company_out(company, db)


@router.get("/companies", response_model=List[CompanyOut])
async def list_companies(
    status: Optional[CompanyStatus] = Query(None),
    plan: Optional[SubscriptionPlan] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    from app.models import Company
    q = db.query(Company)
    if status: q = q.filter(Company.status == status.value)
    if plan: q = q.filter(Company.subscription_plan == plan.value)
    if search:
        s = f"%{search}%"
        q = q.filter((Company.name.ilike(s)) | (Company.email.ilike(s)))
    total = q.count()
    companies = q.offset((page-1)*per_page).limit(per_page).all()
    return [_company_out(c, db) for c in companies]


@router.get("/companies/{company_id}", response_model=CompanyOut)
async def get_company(company_id: str, db: Session = Depends(get_db)):
    from app.models import Company
    c = db.get(Company, company_id)
    if not c: raise HTTPException(404, "Company not found")
    return _company_out(c, db)


@router.patch("/companies/{company_id}", response_model=CompanyOut)
async def update_company(company_id: str, data: CompanyUpdate, db: Session = Depends(get_db)):
    from app.models import Company
    c = db.get(Company, company_id)
    if not c: raise HTTPException(404, "Company not found")
    updates = data.dict(exclude_unset=True)
    for field, value in updates.items():
        if value is None: continue
        if field == "sectors":
            c.sectors = json.dumps(value)
        elif isinstance(value, Enum):
            setattr(c, field, value.value)
        else:
            setattr(c, field, value)
    c.updated_at = _utcnow()
    db.commit(); db.refresh(c)
    return _company_out(c, db)


@router.delete("/companies/{company_id}")
async def delete_company(company_id: str, db: Session = Depends(get_db)):
    from app.models import Company
    c = db.get(Company, company_id)
    if not c: raise HTTPException(404, "Company not found")
    c.status = CompanyStatus.SUSPENDED.value; c.updated_at = _utcnow()
    _log_audit(db, company_id, "company_suspended", "company", company_id)
    db.commit()
    return {"message": "Company suspended", "company_id": company_id}


@router.get("/companies/{company_id}/users", response_model=List[UserInCompany])
async def list_company_users(company_id: str, db: Session = Depends(get_db)):
    from app.models import Company, CompanyUser
    c = db.get(Company, company_id)
    if not c: raise HTTPException(404, "Company not found")
    users = db.query(CompanyUser).filter(CompanyUser.company_id == company_id).all()
    return [UserInCompany(id=u.id, email=u.email, name=u.name, role=u.role,
            is_active=u.is_active, last_login=None, created_at=u.created_at) for u in users]


@router.post("/companies/{company_id}/users")
async def add_user_to_company(
    company_id: str,
    email: str = Query(...),
    name: Optional[str] = Query(None),
    role: str = Query("viewer"),
    db: Session = Depends(get_db),
):
    from app.models import Company, CompanyUser
    c = db.get(Company, company_id)
    if not c: raise HTTPException(404, "Company not found")
    current = db.query(CompanyUser).filter(CompanyUser.company_id == company_id).count()
    if current >= c.max_users:
        raise HTTPException(400, f"User limit reached ({c.max_users}). Upgrade subscription.")
    u = CompanyUser(id=str(uuid.uuid4()), company_id=company_id, email=email, name=name, role=role)
    db.add(u); c.current_users = current + 1; db.commit(); db.refresh(u)
    return UserInCompany(id=u.id, email=u.email, name=u.name, role=u.role,
                         is_active=u.is_active, last_login=None, created_at=u.created_at)


# ============ CONNECTOR MANAGEMENT ============

@router.post("/companies/{company_id}/connectors", response_model=ConnectorOut)
async def create_connector(company_id: str, data: ConnectorConfig, db: Session = Depends(get_db)):
    from app.models import Company, Connector
    from app.crypto import encrypt
    c = db.get(Company, company_id)
    if not c: raise HTTPException(404, "Company not found")
    conn = Connector(id=str(uuid.uuid4()), company_id=company_id,
                     connector_type=data.connector_type.value, name=data.name,
                     api_key=encrypt(data.api_key), enabled=data.enabled)
    db.add(conn); db.commit(); db.refresh(conn)
    logger.info(f"Created connector {conn.id} for company {company_id}")
    return ConnectorOut(id=conn.id, company_id=company_id, connector_type=conn.connector_type,
                        name=conn.name, enabled=conn.enabled, last_sync=None,
                        sync_status=conn.sync_status or "never", created_at=conn.created_at)


@router.get("/companies/{company_id}/connectors", response_model=List[ConnectorOut])
async def list_connectors(company_id: str, db: Session = Depends(get_db)):
    from app.models import Company, Connector
    c = db.get(Company, company_id)
    if not c: raise HTTPException(404, "Company not found")
    conns = db.query(Connector).filter(Connector.company_id == company_id).all()
    return [ConnectorOut(id=cn.id, company_id=cn.company_id, connector_type=cn.connector_type,
            name=cn.name, enabled=cn.enabled, last_sync=None,
            sync_status=cn.sync_status or "never", created_at=cn.created_at) for cn in conns]


@router.patch("/companies/{company_id}/connectors/{connector_id}")
async def update_connector(company_id: str, connector_id: str, data: ConnectorConfig, db: Session = Depends(get_db)):
    from app.models import Connector
    from app.crypto import encrypt
    conn = db.get(Connector, connector_id)
    if not conn: raise HTTPException(404, "Connector not found")
    if conn.company_id != company_id: raise HTTPException(403, "Connector belongs to different company")
    conn.name = data.name; conn.enabled = data.enabled
    if data.api_key: conn.api_key = encrypt(data.api_key)
    db.commit(); db.refresh(conn)
    return ConnectorOut(id=conn.id, company_id=conn.company_id, connector_type=conn.connector_type,
                        name=conn.name, enabled=conn.enabled, last_sync=None,
                        sync_status=conn.sync_status or "never", created_at=conn.created_at)


@router.delete("/companies/{company_id}/connectors/{connector_id}")
async def delete_connector(company_id: str, connector_id: str, db: Session = Depends(get_db)):
    from app.models import Connector
    conn = db.get(Connector, connector_id)
    if not conn: raise HTTPException(404, "Connector not found")
    if conn.company_id != company_id: raise HTTPException(403, "Connector belongs to different company")
    db.delete(conn); db.commit()
    return {"message": "Connector deleted", "connector_id": connector_id}


@router.post("/companies/{company_id}/connectors/{connector_id}/sync")
async def trigger_connector_sync(company_id: str, connector_id: str, db: Session = Depends(get_db)):
    from app.models import Connector
    conn = db.get(Connector, connector_id)
    if not conn: raise HTTPException(404, "Connector not found")
    if conn.company_id != company_id: raise HTTPException(403, "Connector belongs to different company")
    if not conn.enabled: raise HTTPException(400, "Connector is disabled")
    conn.sync_status = "running"; db.commit()
    return {"message": "Sync triggered", "connector_id": connector_id, "connector_type": conn.connector_type}


# ============ AUDIT LOGS ============

@router.get("/audit-logs", response_model=List[AuditLogEntry])
async def get_audit_logs(
    company_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    from app.models import AuditLog
    q = db.query(AuditLog)
    if company_id: q = q.filter(AuditLog.company_id == company_id)
    if user_id: q = q.filter(AuditLog.user_id == user_id)
    if action: q = q.filter(AuditLog.action == action)
    if resource_type: q = q.filter(AuditLog.resource_type == resource_type)
    if start_date: q = q.filter(AuditLog.created_at >= start_date)
    if end_date: q = q.filter(AuditLog.created_at <= end_date)
    q = q.order_by(AuditLog.created_at.desc())
    logs = q.offset((page-1)*per_page).limit(per_page).all()
    return [AuditLogEntry(id=l.id, company_id=l.company_id, user_id=l.user_id,
            action=l.action, resource_type=l.resource_type, resource_id=l.resource_id,
            details=l.details, ip_address=l.ip_address, created_at=l.created_at) for l in logs]


# ============ SYSTEM MONITORING ============

@router.get("/stats", response_model=SystemStats)
async def get_system_stats(db: Session = Depends(get_db)):
    from app.models import Company, Site, Dataset, Payment
    from app.services.payments import PaymentStatus as PS

    companies = db.query(Company).all()
    active = len([c for c in companies if c.status == "active"])
    try:
        total_sites = db.query(Site).count()
    except Exception:
        db.rollback()
        total_sites = 0
    try:
        total_datasets = db.query(Dataset).count()
    except Exception:
        db.rollback()
        total_datasets = 0

    today = _utcnow().date()
    try:
        payments_today = db.query(Payment).filter(
            Payment.status == PS.COMPLETED.value,
            func.date(Payment.created_at) == today,
        ).count()
        payments_pending = db.query(Payment).filter(
            Payment.status.in_([PS.PENDING.value, PS.PROCESSING.value, PS.AWAITING_CONFIRMATION.value])
        ).count()
    except Exception:
        db.rollback()
        payments_today = 0
        payments_pending = 0

    return SystemStats(
        total_companies=len(companies), active_companies=active,
        total_users=sum(c.current_users or 0 for c in companies),
        total_sites=total_sites, total_datasets=total_datasets,
        total_storage_gb=sum(c.storage_used_gb or 0 for c in companies),
        payments_today=payments_today, payments_pending=payments_pending,
    )


@router.get("/health")
async def health_check():
    import os
    return {
        "status": "healthy", "timestamp": _utcnow().isoformat(),
        "version": os.getenv("APP_VERSION", "1.0.0"),
        "environment": os.getenv("ENVIRONMENT", "development"),
        "services": {
            "database": "ok",
            "storage": "ok" if os.getenv("S3_BUCKET") else "not_configured",
            "payments_multicaixa": "ok" if os.getenv("MULTICAIXA_API_KEY") else "not_configured",
            "payments_stripe": "ok" if os.getenv("STRIPE_SECRET_KEY") else "not_configured",
        }
    }


# ============ ADDITIONAL SCHEMAS ============

class SiteCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    description: Optional[str] = None
    country: str = Field(default="Angola")
    province: Optional[str] = None
    municipality: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    area_hectares: Optional[float] = None
    sector: Optional[str] = None


class SiteOut(BaseModel):
    id: str
    company_id: str
    name: str
    description: Optional[str] = None
    country: str
    province: Optional[str] = None
    municipality: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    area_hectares: Optional[float] = None
    sector: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class DatasetCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    description: Optional[str] = None
    data_type: str = Field(default="drone_imagery")
    source: Optional[str] = None
    metadata: Optional[dict] = None


class DatasetOut(BaseModel):
    id: str
    site_id: str
    company_id: str
    name: str
    description: Optional[str] = None
    data_type: str
    source: Optional[str] = None
    storage_path: Optional[str] = None
    size_bytes: int = 0
    status: str = "pending"
    created_at: datetime
    processed_at: Optional[datetime] = None


class DocumentCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    document_type: str = Field(default="report")
    description: Optional[str] = None
    is_confidential: bool = False
    is_official: bool = False


class DocumentOut(BaseModel):
    id: str
    company_id: str
    site_id: Optional[str] = None
    name: str
    document_type: str
    description: Optional[str] = None
    file_path: Optional[str] = None
    file_size_bytes: int = 0
    mime_type: Optional[str] = None
    status: str = "draft"
    version: int = 1
    is_confidential: bool = False
    is_official: bool = False
    uploaded_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class IntegrationCreate(BaseModel):
    connector_type: str
    name: str = Field(..., max_length=100)
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    base_url: Optional[str] = None
    webhook_url: Optional[str] = None
    auto_sync_enabled: bool = True
    sync_interval_hours: int = 24


class IntegrationOut(BaseModel):
    id: str
    company_id: str
    connector_type: str
    name: str
    base_url: Optional[str] = None
    is_active: bool
    auto_sync_enabled: bool
    sync_interval_hours: int
    last_sync_at: Optional[datetime] = None
    sync_status: str = "never"
    created_at: datetime


# ============ IN-MEMORY STORES REMOVED — using DB ============


def _company_out(c, db: Session) -> CompanyOut:
    sectors_raw = getattr(c, 'sectors_json', None) or getattr(c, 'sectors', None) or '[]'
    return CompanyOut(
        id=c.id, name=c.name, tax_id=c.tax_id, email=c.email,
        phone=c.phone, address=c.address,
        sectors=json.loads(sectors_raw) if isinstance(sectors_raw, str) else sectors_raw,
        status=c.status, subscription_plan=c.subscription_plan,
        max_users=c.max_users, max_sites=c.max_sites,
        max_storage_gb=c.max_storage_gb,
        current_users=c.current_users or 0,
        current_sites=c.current_sites or 0,
        storage_used_gb=c.storage_used_gb or 0.0,
        created_at=c.created_at, updated_at=c.updated_at,
    )


# ============ SITES MANAGEMENT ============

@router.post("/companies/{company_id}/sites", response_model=SiteOut)
async def create_site(company_id: str, data: SiteCreate, db: Session = Depends(get_db)):
    from app.models import Company, Site
    c = db.get(Company, company_id)
    if not c: raise HTTPException(404, "Company not found")
    current = db.query(Site).filter(Site.company_id == company_id).count()
    if current >= c.max_sites:
        raise HTTPException(400, f"Site limit reached ({c.max_sites}). Upgrade subscription.")
    site = Site(id=str(uuid.uuid4()), company_id=company_id, name=data.name,
                country=data.country, province=data.province,
                latitude=data.latitude, longitude=data.longitude,
                area_hectares=data.area_hectares, sector=data.sector)
    db.add(site); c.current_sites = current + 1
    _log_audit(db, company_id, "site_created", "site", site.id,
               details={"name": data.name, "sector": data.sector})
    db.commit(); db.refresh(site)
    return SiteOut(id=site.id, company_id=company_id, name=site.name,
                   description=data.description, country=site.country,
                   province=site.province, latitude=site.latitude,
                   longitude=site.longitude, area_hectares=site.area_hectares,
                   sector=site.sector, is_active=True,
                   created_at=site.created_at, updated_at=site.updated_at)


@router.get("/companies/{company_id}/sites", response_model=List[SiteOut])
async def list_company_sites(company_id: str, db: Session = Depends(get_db)):
    from app.models import Company, Site
    c = db.get(Company, company_id)
    if not c: raise HTTPException(404, "Company not found")
    sites = db.query(Site).filter(Site.company_id == company_id).all()
    return [SiteOut(id=s.id, company_id=s.company_id, name=s.name,
            country=s.country or "Angola", province=s.province,
            latitude=s.latitude, longitude=s.longitude,
            area_hectares=s.area_hectares, sector=s.sector,
            is_active=True, created_at=s.created_at, updated_at=s.updated_at) for s in sites]


@router.get("/sites", response_model=List[SiteOut])
async def list_all_sites(
    company_id: Optional[str] = Query(None),
    sector: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    from app.models import Site
    q = db.query(Site)
    if company_id: q = q.filter(Site.company_id == company_id)
    if sector: q = q.filter(Site.sector == sector)
    if search: q = q.filter(Site.name.ilike(f"%{search}%"))
    sites = q.all()
    return [SiteOut(id=s.id, company_id=s.company_id, name=s.name,
            country=s.country or "Angola", province=s.province,
            latitude=s.latitude, longitude=s.longitude,
            area_hectares=s.area_hectares, sector=s.sector,
            is_active=True, created_at=s.created_at, updated_at=s.updated_at) for s in sites]


@router.delete("/sites/{site_id}")
async def delete_site(site_id: str, db: Session = Depends(get_db)):
    from app.models import Site, Company
    site = db.get(Site, site_id)
    if not site: raise HTTPException(404, "Site not found")
    c = db.get(Company, site.company_id)
    if c and c.current_sites: c.current_sites = max(0, c.current_sites - 1)
    db.delete(site); db.commit()
    return {"message": "Site deleted", "site_id": site_id}


# ============ DATASETS MANAGEMENT ============

@router.post("/sites/{site_id}/datasets", response_model=DatasetOut)
async def create_dataset(site_id: str, data: DatasetCreate, db: Session = Depends(get_db)):
    from app.models import Site, Dataset as DSModel
    site = db.get(Site, site_id)
    if not site: raise HTTPException(404, "Site not found")
    ds = DSModel(id=str(uuid.uuid4()), company_id=site.company_id, site_id=site_id,
                 name=data.name, source_tool=data.data_type, status="pending")
    db.add(ds); db.commit(); db.refresh(ds)
    return DatasetOut(id=ds.id, site_id=site_id, company_id=site.company_id,
                      name=ds.name, data_type=ds.source_tool or "drone_imagery",
                      source=data.source, status=ds.status,
                      created_at=ds.created_at, processed_at=None)


@router.get("/datasets", response_model=List[DatasetOut])
async def list_all_datasets(
    company_id: Optional[str] = Query(None), site_id: Optional[str] = Query(None),
    data_type: Optional[str] = Query(None), status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    from app.models import Dataset as DSModel
    q = db.query(DSModel)
    if company_id: q = q.filter(DSModel.company_id == company_id)
    if site_id: q = q.filter(DSModel.site_id == site_id)
    if data_type: q = q.filter(DSModel.source_tool == data_type)
    if status: q = q.filter(DSModel.status == status)
    datasets = q.all()
    return [DatasetOut(id=d.id, site_id=d.site_id, company_id=d.company_id,
            name=d.name, data_type=d.source_tool or "drone_imagery", status=d.status,
            created_at=d.created_at, processed_at=None) for d in datasets]


@router.delete("/datasets/{dataset_id}")
async def delete_dataset(dataset_id: str, db: Session = Depends(get_db)):
    from app.models import Dataset as DSModel
    ds = db.get(DSModel, dataset_id)
    if not ds: raise HTTPException(404, "Dataset not found")
    db.delete(ds); db.commit()
    return {"message": "Dataset deleted", "dataset_id": dataset_id}


# ============ DOCUMENTS MANAGEMENT ============

from app.services.storage import get_storage_service, is_s3_key


@router.post("/companies/{company_id}/documents", response_model=DocumentOut)
async def create_document(
    company_id: str,
    name: str = Form(...),
    document_type: str = Form("report"),
    description: str = Form(""),
    is_confidential: bool = Form(False),
    is_official: bool = Form(False),
    site_id: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    from app.models import Company, Document as DocModel
    c = db.get(Company, company_id)
    if not c: raise HTTPException(404, "Company not found")

    doc_id = str(uuid.uuid4())
    file_path = None
    file_size = 0
    mime = None

    # Save uploaded file to DO Spaces (S3)
    if file and file.filename:
        storage = get_storage_service()
        s3_key = storage.generate_document_key(company_id, doc_id, file.filename)
        mime = file.content_type
        s3_key, file_size, _md5, _sha = storage.upload_file(
            file.file, s3_key, content_type=mime
        )
        file_path = s3_key  # Store S3 key instead of local path

    sid = site_id if site_id and site_id.strip() else None
    doc = DocModel(
        id=doc_id, company_id=company_id, site_id=sid,
        name=name, document_type=document_type, description=description or None,
        file_path=file_path, file_size_bytes=file_size, mime_type=mime,
        is_confidential=is_confidential, is_official=is_official,
        status="approved" if file_path else "draft",
    )
    db.add(doc)
    _log_audit(db, company_id, "document_created", "document", doc.id,
               details={"name": name, "type": document_type, "has_file": bool(file_path)})
    db.commit(); db.refresh(doc)
    return DocumentOut(id=doc.id, company_id=company_id, site_id=sid,
                       name=doc.name, document_type=doc.document_type,
                       description=doc.description, status=doc.status or "draft",
                       file_path=doc.file_path, file_size_bytes=doc.file_size_bytes,
                       mime_type=doc.mime_type,
                       version=doc.version or 1, is_confidential=doc.is_confidential or False,
                       is_official=doc.is_official or False,
                       created_at=doc.created_at, updated_at=doc.updated_at)


@router.get("/documents", response_model=List[DocumentOut])
async def list_all_documents(
    company_id: Optional[str] = Query(None), site_id: Optional[str] = Query(None),
    document_type: Optional[str] = Query(None), status: Optional[str] = Query(None),
    is_confidential: Optional[bool] = Query(None), db: Session = Depends(get_db),
):
    from app.models import Document as DocModel
    q = db.query(DocModel)
    if company_id: q = q.filter(DocModel.company_id == company_id)
    if site_id: q = q.filter(DocModel.site_id == site_id)
    if document_type: q = q.filter(DocModel.document_type == document_type)
    if status: q = q.filter(DocModel.status == status)
    if is_confidential is not None: q = q.filter(DocModel.is_confidential == is_confidential)
    docs = q.order_by(DocModel.created_at.desc()).all()
    return [DocumentOut(id=d.id, company_id=d.company_id, site_id=d.site_id,
            name=d.name, document_type=d.document_type,
            description=d.description,
            file_path=d.file_path, file_size_bytes=d.file_size_bytes or 0,
            mime_type=d.mime_type,
            status=d.status or "draft", version=d.version or 1,
            is_confidential=d.is_confidential or False,
            is_official=d.is_official or False,
            created_at=d.created_at, updated_at=d.updated_at) for d in docs]


@router.patch("/documents/{document_id}")
async def update_document(document_id: str, status: Optional[str] = Query(None),
                          is_official: Optional[bool] = Query(None), db: Session = Depends(get_db)):
    from app.models import Document as DocModel
    doc = db.get(DocModel, document_id)
    if not doc: raise HTTPException(404, "Document not found")
    if status: doc.status = status
    doc.updated_at = _utcnow(); db.commit(); db.refresh(doc)
    return DocumentOut(id=doc.id, company_id=doc.company_id, site_id=doc.site_id,
                       name=doc.name, document_type=doc.document_type,
                       status=doc.status or "draft", version=doc.version or 1,
                       is_confidential=doc.is_confidential or False,
                       is_official=doc.is_official or False,
                       created_at=doc.created_at, updated_at=doc.updated_at)


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str, db: Session = Depends(get_db)):
    from app.models import Document as DocModel
    doc = db.get(DocModel, document_id)
    if not doc: raise HTTPException(404, "Document not found")
    # Delete file from S3 if it's an S3 key
    if doc.file_path and is_s3_key(doc.file_path):
        try:
            storage = get_storage_service()
            storage.delete_file(doc.file_path)
        except Exception:
            pass  # File may already be gone
    db.delete(doc); db.commit()
    return {"message": "Document deleted", "document_id": document_id}


@router.get("/documents/{document_id}/download")
async def download_document(document_id: str, db: Session = Depends(get_db)):
    """Download a document file by its ID."""
    from app.models import Document as DocModel
    from starlette.responses import Response
    doc = db.get(DocModel, document_id)
    if not doc: raise HTTPException(404, "Document not found")
    if not doc.file_path:
        raise HTTPException(404, "Sem ficheiro associado a este documento")
    # S3-based download
    if is_s3_key(doc.file_path):
        try:
            storage = get_storage_service()
            content = storage.download_file(doc.file_path)
        except Exception:
            raise HTTPException(410, "Ficheiro indisponível no armazenamento.")
        ext = '.' + doc.file_path.rsplit('.', 1)[-1] if '.' in doc.file_path else ''
        filename = doc.name + ext
        return Response(
            content=content,
            media_type=doc.mime_type or "application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    # Legacy local file fallback (pre-migration documents)
    from pathlib import Path as _Path
    fp = _Path(doc.file_path)
    if not fp.exists():
        raise HTTPException(410, "Ficheiro indisponível — foi eliminado do servidor após re-deploy. Re-envie o documento.")
    return FileResponse(
        path=str(fp),
        filename=doc.name + (fp.suffix or ''),
        media_type=doc.mime_type or "application/octet-stream",
    )


# ============ INTEGRATIONS MANAGEMENT ============

@router.post("/companies/{company_id}/integrations", response_model=IntegrationOut)
async def create_integration(company_id: str, data: IntegrationCreate, db: Session = Depends(get_db)):
    from app.models import Company, Integration as IntModel
    c = db.get(Company, company_id)
    if not c: raise HTTPException(404, "Company not found")
    integ = IntModel(id=str(uuid.uuid4()), company_id=company_id,
                     connector_type=data.connector_type, name=data.name,
                     api_key_encrypted=data.api_key, base_url=data.base_url,
                     auto_sync_enabled=data.auto_sync_enabled,
                     sync_interval_hours=data.sync_interval_hours)
    db.add(integ); db.commit(); db.refresh(integ)
    return IntegrationOut(id=integ.id, company_id=company_id,
                          connector_type=integ.connector_type, name=integ.name,
                          base_url=integ.base_url, is_active=integ.is_active,
                          auto_sync_enabled=integ.auto_sync_enabled,
                          sync_interval_hours=integ.sync_interval_hours,
                          sync_status=integ.sync_status or "never",
                          created_at=integ.created_at)


@router.get("/integrations", response_model=List[IntegrationOut])
async def list_all_integrations(
    company_id: Optional[str] = Query(None),
    connector_type: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
):
    from app.models import Integration as IntModel
    q = db.query(IntModel)
    if company_id: q = q.filter(IntModel.company_id == company_id)
    if connector_type: q = q.filter(IntModel.connector_type == connector_type)
    if is_active is not None: q = q.filter(IntModel.is_active == is_active)
    integs = q.all()
    return [IntegrationOut(id=i.id, company_id=i.company_id,
            connector_type=i.connector_type, name=i.name, base_url=i.base_url,
            is_active=i.is_active, auto_sync_enabled=i.auto_sync_enabled,
            sync_interval_hours=i.sync_interval_hours,
            sync_status=i.sync_status or "never", created_at=i.created_at) for i in integs]


@router.post("/integrations/{integration_id}/sync")
async def trigger_integration_sync(integration_id: str, db: Session = Depends(get_db)):
    from app.models import Integration as IntModel
    integ = db.get(IntModel, integration_id)
    if not integ: raise HTTPException(404, "Integration not found")
    if not integ.is_active: raise HTTPException(400, "Integration is disabled")
    integ.sync_status = "running"; integ.last_sync_at = _utcnow(); db.commit()
    return {"message": "Sync triggered", "integration_id": integration_id,
            "connector_type": integ.connector_type}


@router.delete("/integrations/{integration_id}")
async def delete_integration(integration_id: str, db: Session = Depends(get_db)):
    from app.models import Integration as IntModel
    integ = db.get(IntModel, integration_id)
    if not integ: raise HTTPException(404, "Integration not found")
    db.delete(integ); db.commit()
    return {"message": "Integration deleted", "integration_id": integration_id}


# ============ ADMIN CONTACTS ============

class AdminContactOut(BaseModel):
    type: str
    label: str
    value: str
    icon: str


@router.get("/contacts", response_model=List[AdminContactOut])
async def get_admin_contacts():
    """Get GeoVision admin contact information."""
    
    return [
        AdminContactOut(type="whatsapp", label="WhatsApp Suporte", value="+244928917269", icon="fa-brands fa-whatsapp"),
        AdminContactOut(type="email", label="Email Suporte", value="suporte@geovisionops.com", icon="fa-solid fa-envelope"),
        AdminContactOut(type="phone", label="Telefone", value="+244928917269", icon="fa-solid fa-phone"),
        AdminContactOut(type="sms", label="SMS", value="+244928917269", icon="fa-solid fa-comment-sms"),
        AdminContactOut(type="instagram", label="Instagram", value="@Geovision.operations", icon="fa-brands fa-instagram"),
    ]


# ============ PRODUCTS MANAGEMENT ============

class ProductCreate(BaseModel):
    name: str
    slug: Optional[str] = None
    description: Optional[str] = None
    short_description: Optional[str] = None
    product_type: str = "service"
    category: str = "flight"
    execution_type: Optional[str] = None
    price: int = 0
    price_usd: int = 0
    price_eur: int = 0
    currency: str = "AOA"
    tax_rate: float = 0.14
    duration_hours: Optional[int] = None
    requires_site: bool = False
    min_area_ha: Optional[int] = None
    sectors: List[str] = []
    deliverables: List[str] = []
    image_url: Optional[str] = None
    is_active: bool = True
    is_featured: bool = False
    track_inventory: bool = False
    stock_quantity: int = 0

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    short_description: Optional[str] = None
    product_type: Optional[str] = None
    category: Optional[str] = None
    execution_type: Optional[str] = None
    price: Optional[int] = None
    price_usd: Optional[int] = None
    price_eur: Optional[int] = None
    currency: Optional[str] = None
    tax_rate: Optional[float] = None
    duration_hours: Optional[int] = None
    requires_site: Optional[bool] = None
    min_area_ha: Optional[int] = None
    sectors: Optional[List[str]] = None
    deliverables: Optional[List[str]] = None
    image_url: Optional[str] = None
    is_active: Optional[bool] = None
    is_featured: Optional[bool] = None
    track_inventory: Optional[bool] = None
    stock_quantity: Optional[int] = None

class StockAdjust(BaseModel):
    adjustment: int
    reason: Optional[str] = None


def _product_to_dict(p):
    import json as _json
    return {
        "id": p.id, "name": p.name, "slug": p.slug,
        "description": p.description, "short_description": p.short_description,
        "product_type": p.product_type, "category": p.category,
        "execution_type": p.execution_type,
        "price": p.price, "price_usd": p.price_usd, "price_eur": p.price_eur,
        "currency": p.currency, "tax_rate": float(p.tax_rate or 0.14),
        "duration_hours": p.duration_hours, "requires_site": p.requires_site,
        "min_area_ha": p.min_area_ha,
        "sectors": _json.loads(p.sectors_json) if p.sectors_json else [],
        "deliverables": _json.loads(p.deliverables_json) if p.deliverables_json else [],
        "image_url": p.image_url,
        "is_active": p.is_active, "is_featured": p.is_featured,
        "track_inventory": p.track_inventory, "stock_quantity": p.stock_quantity,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


@router.get("/products")
async def list_products(
    product_type: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
):
    """List all shop products with optional filters."""
    from app.models import ShopProduct as SP
    q = db.query(SP)
    if product_type:
        q = q.filter(SP.product_type == product_type)
    if category:
        q = q.filter(SP.category == category)
    if is_active is not None:
        q = q.filter(SP.is_active == is_active)
    products = q.order_by(SP.name).all()
    return [_product_to_dict(p) for p in products]


@router.post("/products")
async def create_product(data: ProductCreate, db: Session = Depends(get_db)):
    """Create a new shop product."""
    from app.models import ShopProduct as SP
    import re

    slug = data.slug or re.sub(r'[^a-z0-9]+', '-', data.name.lower()).strip('-')
    # Check slug uniqueness
    existing = db.query(SP).filter(SP.slug == slug).first()
    if existing:
        raise HTTPException(409, f"Produto com slug '{slug}' ja existe")

    product_id = f"prod_{slug.replace('-', '_')[:40]}"
    existing_id = db.get(SP, product_id)
    if existing_id:
        product_id = f"prod_{str(uuid.uuid4())[:8]}"

    p = SP(
        id=product_id, name=data.name, slug=slug,
        description=data.description, short_description=data.short_description,
        product_type=data.product_type, category=data.category,
        execution_type=data.execution_type,
        price=data.price, price_usd=data.price_usd, price_eur=data.price_eur,
        currency=data.currency, tax_rate=data.tax_rate,
        duration_hours=data.duration_hours, requires_site=data.requires_site,
        min_area_ha=data.min_area_ha,
        sectors_json=json.dumps(data.sectors),
        deliverables_json=json.dumps(data.deliverables),
        image_url=data.image_url,
        is_active=data.is_active, is_featured=data.is_featured,
        track_inventory=data.track_inventory, stock_quantity=data.stock_quantity,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return _product_to_dict(p)


@router.patch("/products/{product_id}")
async def update_product(product_id: str, data: ProductUpdate, db: Session = Depends(get_db)):
    """Update an existing shop product."""
    from app.models import ShopProduct as SP
    p = db.get(SP, product_id)
    if not p:
        raise HTTPException(404, "Produto nao encontrado")

    update_data = data.model_dump(exclude_unset=True)
    if "sectors" in update_data:
        p.sectors_json = json.dumps(update_data.pop("sectors"))
    if "deliverables" in update_data:
        p.deliverables_json = json.dumps(update_data.pop("deliverables"))
    for k, v in update_data.items():
        setattr(p, k, v)
    p.updated_at = _utcnow()
    db.commit()
    db.refresh(p)
    return _product_to_dict(p)


@router.delete("/products/{product_id}")
async def delete_product(product_id: str, db: Session = Depends(get_db)):
    """Delete a shop product."""
    from app.models import ShopProduct as SP
    p = db.get(SP, product_id)
    if not p:
        raise HTTPException(404, "Produto nao encontrado")
    db.delete(p)
    db.commit()
    return {"message": "Produto eliminado", "product_id": product_id}


@router.post("/products/{product_id}/stock")
async def adjust_stock(product_id: str, data: StockAdjust, db: Session = Depends(get_db)):
    """Adjust stock quantity for a product (positive to add, negative to remove)."""
    from app.models import ShopProduct as SP
    p = db.get(SP, product_id)
    if not p:
        raise HTTPException(404, "Produto nao encontrado")
    new_qty = p.stock_quantity + data.adjustment
    if new_qty < 0:
        raise HTTPException(400, f"Stock insuficiente. Atual: {p.stock_quantity}, ajuste: {data.adjustment}")
    p.stock_quantity = new_qty
    p.updated_at = _utcnow()
    _log_audit(db, None, "stock_adjusted", "product", product_id,
               details={"adjustment": data.adjustment, "new_quantity": new_qty, "reason": data.reason})
    db.commit()
    return {"product_id": product_id, "stock_quantity": new_qty, "adjustment": data.adjustment}


# ============ USERS MANAGEMENT ============

@router.get("/users")
async def list_all_users(db: Session = Depends(get_db)):
    """List all platform users with their profiles."""
    from app.models import User, UserProfile
    users = db.query(User).order_by(User.created_at.desc()).all()
    result = []
    for u in users:
        profile = db.query(UserProfile).filter(UserProfile.user_id == u.id).first()
        result.append({
            "id": u.id,
            "email": u.email,
            "role": u.role,
            "is_active": u.is_active,
            "full_name": profile.full_name if profile else None,
            "phone": profile.phone if profile else None,
            "company": profile.company if profile else (profile.org_name if profile else None),
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "updated_at": u.updated_at.isoformat() if u.updated_at else None,
        })
    return result


@router.patch("/users/{user_id}")
async def update_user(user_id: str, db: Session = Depends(get_db),
                      role: Optional[str] = Query(None),
                      is_active: Optional[bool] = Query(None)):
    """Update user role or active status."""
    from app.models import User
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if role is not None:
        u.role = role
    if is_active is not None:
        u.is_active = is_active
    u.updated_at = _utcnow()
    _log_audit(db, None, "user_updated", "user", user_id,
               details={"role": role, "is_active": is_active})
    db.commit()
    return {"message": "User updated", "user_id": user_id}


# ============ ORDERS MANAGEMENT (Admin) ============

@router.get("/orders")
async def list_all_orders(db: Session = Depends(get_db)):
    """List all orders for admin view."""
    from app.models import Order, User, UserProfile
    orders = db.query(Order).order_by(Order.created_at.desc()).all()
    result = []
    for o in orders:
        user_name = None
        user_email = None
        if o.user_id:
            user = db.query(User).filter(User.id == o.user_id).first()
            if user:
                user_email = user.email
                profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
                user_name = profile.full_name if profile else user.email
        result.append({
            "id": o.id,
            "order_number": o.order_number,
            "user_name": user_name,
            "user_email": user_email,
            "status": o.status,
            "currency": o.currency,
            "subtotal": float(o.subtotal),
            "total": float(o.total),
            "payment_method": o.payment_method,
            "payment_reference": o.payment_reference,
            "items_count": len(o.items) if o.items else 0,
            "created_at": o.created_at.isoformat() if o.created_at else None,
            "completed_at": o.completed_at.isoformat() if o.completed_at else None,
        })
    return result


@router.patch("/orders/{order_id}/status")
async def update_order_status(order_id: str, status: str = Query(...), db: Session = Depends(get_db)):
    """Update order status (e.g. pending -> processing -> completed)."""
    from app.models import Order
    o = db.get(Order, order_id)
    if not o:
        raise HTTPException(404, "Order not found")
    valid = ["pending", "processing", "confirmed", "in_progress", "completed", "cancelled", "refunded"]
    if status not in valid:
        raise HTTPException(400, f"Invalid status. Must be one of: {', '.join(valid)}")
    o.status = status
    o.updated_at = _utcnow()
    if status == "completed":
        o.completed_at = _utcnow()
    if status == "cancelled":
        o.cancelled_at = _utcnow()
    _log_audit(db, None, "order_status_changed", "order", order_id,
               details={"new_status": status})
    db.commit()
    return {"message": "Order status updated", "order_id": order_id, "status": status}


# ============ ADMIN ALERTS ============

@router.get("/alerts")
async def list_alerts(db: Session = Depends(get_db)):
    """Generate system alerts based on current state."""
    from app.models import Order, ShopProduct, Payment
    alerts = []

    # Low stock alerts
    try:
        low_stock = db.query(ShopProduct).filter(
            ShopProduct.track_inventory == True,
            ShopProduct.stock_quantity <= 5,
            ShopProduct.is_active == True
        ).all()
        for p in low_stock:
            alerts.append({
                "id": f"stock-{p.id}",
                "type": "warning",
                "category": "stock",
                "title": f"Stock baixo: {p.name}",
                "description": f"Apenas {p.stock_quantity} unidade(s) em stock.",
                "created_at": _utcnow().isoformat(),
            })
    except Exception:
        db.rollback()

    # Pending orders alerts
    try:
        pending_orders = db.query(Order).filter(Order.status == "pending").count()
        if pending_orders > 0:
            alerts.append({
                "id": "pending-orders",
                "type": "info",
                "category": "orders",
                "title": f"{pending_orders} encomenda(s) pendente(s)",
                "description": "Existem encomendas aguardando processamento.",
                "created_at": _utcnow().isoformat(),
            })
    except Exception:
        db.rollback()

    # Pending payments
    try:
        pending_payments = db.query(Payment).filter(
            Payment.status.in_(["pending", "processing", "awaiting_confirmation"])
        ).count()
        if pending_payments > 0:
            alerts.append({
                "id": "pending-payments",
                "type": "warning",
                "category": "payments",
                "title": f"{pending_payments} pagamento(s) pendente(s)",
                "description": "Pagamentos aguardando confirmação ou processamento.",
                "created_at": _utcnow().isoformat(),
            })
    except Exception:
        db.rollback()

    return alerts
