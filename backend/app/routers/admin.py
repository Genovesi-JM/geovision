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

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, EmailStr
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
    c = db.get(Company, company_id)
    if not c: raise HTTPException(404, "Company not found")
    conn = Connector(id=str(uuid.uuid4()), company_id=company_id,
                     connector_type=data.connector_type.value, name=data.name,
                     api_key=data.api_key, enabled=data.enabled)
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
    conn = db.get(Connector, connector_id)
    if not conn: raise HTTPException(404, "Connector not found")
    if conn.company_id != company_id: raise HTTPException(403, "Connector belongs to different company")
    conn.name = data.name; conn.enabled = data.enabled
    if data.api_key: conn.api_key = data.api_key
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
    total_sites = db.query(Site).count()
    total_datasets = db.query(Dataset).count()

    today = _utcnow().date()
    payments_today = db.query(Payment).filter(
        Payment.status == PS.COMPLETED.value,
    ).count()  # simplified — in prod filter by date
    payments_pending = db.query(Payment).filter(
        Payment.status.in_([PS.PENDING.value, PS.PROCESSING.value, PS.AWAITING_CONFIRMATION.value])
    ).count()

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

@router.post("/companies/{company_id}/documents", response_model=DocumentOut)
async def create_document(company_id: str, data: DocumentCreate,
                          site_id: Optional[str] = Query(None), db: Session = Depends(get_db)):
    from app.models import Company, Document as DocModel
    c = db.get(Company, company_id)
    if not c: raise HTTPException(404, "Company not found")
    doc = DocModel(id=str(uuid.uuid4()), company_id=company_id, site_id=site_id,
                   name=data.name, document_type=data.document_type,
                   is_confidential=data.is_confidential, is_official=data.is_official)
    db.add(doc)
    _log_audit(db, company_id, "document_created", "document", doc.id,
               details={"name": data.name, "type": data.document_type})
    db.commit(); db.refresh(doc)
    return DocumentOut(id=doc.id, company_id=company_id, site_id=site_id,
                       name=doc.name, document_type=doc.document_type,
                       description=data.description, status=doc.status or "draft",
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
    docs = q.all()
    return [DocumentOut(id=d.id, company_id=d.company_id, site_id=d.site_id,
            name=d.name, document_type=d.document_type,
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
    db.delete(doc); db.commit()
    return {"message": "Document deleted", "document_id": document_id}


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
