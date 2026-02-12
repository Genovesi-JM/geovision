"""
Admin Router

Administrative endpoints for GeoVision platform:
- Company/Client management
- User management
- Connector configuration
- Audit logs
- System monitoring
"""
import logging
from typing import Optional, List
from datetime import datetime
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, EmailStr

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


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


# ============ IN-MEMORY STORES ============

import uuid

_companies_store: dict = {}
_users_in_company_store: dict = {}  # company_id -> [users]
_connectors_store: dict = {}
_audit_log: list = []


# ============ COMPANY MANAGEMENT ============

@router.post("/companies", response_model=CompanyOut)
async def create_company(data: CompanyCreate):
    """Create a new company/client account."""
    
    company_id = str(uuid.uuid4())
    now = datetime.utcnow()
    
    company = {
        "id": company_id,
        "name": data.name,
        "tax_id": data.tax_id,
        "email": data.email,
        "phone": data.phone,
        "address": data.address,
        "sectors": data.sectors,
        "status": CompanyStatus.TRIAL.value,
        "subscription_plan": data.subscription_plan.value,
        "max_users": data.max_users,
        "max_sites": data.max_sites,
        "max_storage_gb": data.max_storage_gb,
        "current_users": 0,
        "current_sites": 0,
        "storage_used_gb": 0.0,
        "created_at": now,
        "updated_at": now,
    }
    
    _companies_store[company_id] = company
    _users_in_company_store[company_id] = []
    
    # Audit log
    _audit_log.append({
        "id": str(uuid.uuid4()),
        "company_id": company_id,
        "user_id": None,
        "action": "company_created",
        "resource_type": "company",
        "resource_id": company_id,
        "details": {"name": data.name, "plan": data.subscription_plan.value},
        "ip_address": None,
        "created_at": now,
    })
    
    logger.info(f"Created company {company_id}: {data.name}")
    
    return CompanyOut(**company)


@router.get("/companies", response_model=List[CompanyOut])
async def list_companies(
    status: Optional[CompanyStatus] = Query(None),
    plan: Optional[SubscriptionPlan] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """List all companies with filtering."""
    
    companies = list(_companies_store.values())
    
    if status:
        companies = [c for c in companies if c["status"] == status.value]
    if plan:
        companies = [c for c in companies if c["subscription_plan"] == plan.value]
    if search:
        search_lower = search.lower()
        companies = [
            c for c in companies 
            if search_lower in c["name"].lower() or search_lower in c["email"].lower()
        ]
    
    # Paginate
    total = len(companies)
    start = (page - 1) * per_page
    companies = companies[start:start + per_page]
    
    return [CompanyOut(**c) for c in companies]


@router.get("/companies/{company_id}", response_model=CompanyOut)
async def get_company(company_id: str):
    """Get company details."""
    
    if company_id not in _companies_store:
        raise HTTPException(status_code=404, detail="Company not found")
    
    return CompanyOut(**_companies_store[company_id])


@router.patch("/companies/{company_id}", response_model=CompanyOut)
async def update_company(company_id: str, data: CompanyUpdate):
    """Update company details."""
    
    if company_id not in _companies_store:
        raise HTTPException(status_code=404, detail="Company not found")
    
    company = _companies_store[company_id]
    
    for field, value in data.dict(exclude_unset=True).items():
        if value is not None:
            if isinstance(value, Enum):
                company[field] = value.value
            else:
                company[field] = value
    
    company["updated_at"] = datetime.utcnow()
    
    return CompanyOut(**company)


@router.delete("/companies/{company_id}")
async def delete_company(company_id: str):
    """Delete a company (soft delete - sets status to suspended)."""
    
    if company_id not in _companies_store:
        raise HTTPException(status_code=404, detail="Company not found")
    
    company = _companies_store[company_id]
    company["status"] = CompanyStatus.SUSPENDED.value
    company["updated_at"] = datetime.utcnow()
    
    # Audit log
    _audit_log.append({
        "id": str(uuid.uuid4()),
        "company_id": company_id,
        "user_id": None,
        "action": "company_suspended",
        "resource_type": "company",
        "resource_id": company_id,
        "details": {},
        "ip_address": None,
        "created_at": datetime.utcnow(),
    })
    
    return {"message": "Company suspended", "company_id": company_id}


@router.get("/companies/{company_id}/users", response_model=List[UserInCompany])
async def list_company_users(company_id: str):
    """List users in a company."""
    
    if company_id not in _companies_store:
        raise HTTPException(status_code=404, detail="Company not found")
    
    users = _users_in_company_store.get(company_id, [])
    return [UserInCompany(**u) for u in users]


@router.post("/companies/{company_id}/users")
async def add_user_to_company(
    company_id: str,
    email: str = Query(...),
    name: Optional[str] = Query(None),
    role: str = Query("viewer"),
):
    """Add a user to a company."""
    
    if company_id not in _companies_store:
        raise HTTPException(status_code=404, detail="Company not found")
    
    company = _companies_store[company_id]
    
    # Check user limit
    if company["current_users"] >= company["max_users"]:
        raise HTTPException(
            status_code=400,
            detail=f"User limit reached ({company['max_users']}). Upgrade subscription."
        )
    
    user_id = str(uuid.uuid4())
    now = datetime.utcnow()
    
    user = {
        "id": user_id,
        "email": email,
        "name": name,
        "role": role,
        "is_active": True,
        "last_login": None,
        "created_at": now,
    }
    
    _users_in_company_store[company_id].append(user)
    company["current_users"] += 1
    
    return UserInCompany(**user)


# ============ CONNECTOR MANAGEMENT ============

@router.post("/companies/{company_id}/connectors", response_model=ConnectorOut)
async def create_connector(company_id: str, data: ConnectorConfig):
    """Configure a data connector for a company."""
    
    if company_id not in _companies_store:
        raise HTTPException(status_code=404, detail="Company not found")
    
    connector_id = str(uuid.uuid4())
    now = datetime.utcnow()
    
    connector = {
        "id": connector_id,
        "company_id": company_id,
        "connector_type": data.connector_type.value,
        "name": data.name,
        "api_key": data.api_key,  # Should be encrypted in production
        "api_secret": data.api_secret,
        "base_url": data.base_url,
        "webhook_secret": data.webhook_secret,
        "metadata": data.metadata or {},
        "enabled": data.enabled,
        "last_sync": None,
        "sync_status": "never",
        "created_at": now,
    }
    
    _connectors_store[connector_id] = connector
    
    logger.info(f"Created connector {connector_id} for company {company_id}")
    
    return ConnectorOut(**connector)


@router.get("/companies/{company_id}/connectors", response_model=List[ConnectorOut])
async def list_connectors(company_id: str):
    """List connectors for a company."""
    
    if company_id not in _companies_store:
        raise HTTPException(status_code=404, detail="Company not found")
    
    connectors = [
        c for c in _connectors_store.values()
        if c["company_id"] == company_id
    ]
    
    return [ConnectorOut(**c) for c in connectors]


@router.patch("/companies/{company_id}/connectors/{connector_id}")
async def update_connector(
    company_id: str,
    connector_id: str,
    data: ConnectorConfig,
):
    """Update connector configuration."""
    
    if connector_id not in _connectors_store:
        raise HTTPException(status_code=404, detail="Connector not found")
    
    connector = _connectors_store[connector_id]
    
    if connector["company_id"] != company_id:
        raise HTTPException(status_code=403, detail="Connector belongs to different company")
    
    connector["name"] = data.name
    connector["enabled"] = data.enabled
    if data.api_key:
        connector["api_key"] = data.api_key
    if data.api_secret:
        connector["api_secret"] = data.api_secret
    if data.base_url:
        connector["base_url"] = data.base_url
    if data.webhook_secret:
        connector["webhook_secret"] = data.webhook_secret
    if data.metadata:
        connector["metadata"].update(data.metadata)
    
    return ConnectorOut(**connector)


@router.delete("/companies/{company_id}/connectors/{connector_id}")
async def delete_connector(company_id: str, connector_id: str):
    """Delete a connector."""
    
    if connector_id not in _connectors_store:
        raise HTTPException(status_code=404, detail="Connector not found")
    
    connector = _connectors_store[connector_id]
    
    if connector["company_id"] != company_id:
        raise HTTPException(status_code=403, detail="Connector belongs to different company")
    
    del _connectors_store[connector_id]
    
    return {"message": "Connector deleted", "connector_id": connector_id}


@router.post("/companies/{company_id}/connectors/{connector_id}/sync")
async def trigger_connector_sync(company_id: str, connector_id: str):
    """Trigger manual sync for a connector."""
    
    if connector_id not in _connectors_store:
        raise HTTPException(status_code=404, detail="Connector not found")
    
    connector = _connectors_store[connector_id]
    
    if connector["company_id"] != company_id:
        raise HTTPException(status_code=403, detail="Connector belongs to different company")
    
    if not connector["enabled"]:
        raise HTTPException(status_code=400, detail="Connector is disabled")
    
    # TODO: Trigger actual sync job
    connector["sync_status"] = "running"
    
    return {
        "message": "Sync triggered",
        "connector_id": connector_id,
        "connector_type": connector["connector_type"],
    }


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
):
    """Get audit logs with filtering."""
    
    logs = list(_audit_log)
    
    if company_id:
        logs = [l for l in logs if l["company_id"] == company_id]
    if user_id:
        logs = [l for l in logs if l.get("user_id") == user_id]
    if action:
        logs = [l for l in logs if l["action"] == action]
    if resource_type:
        logs = [l for l in logs if l["resource_type"] == resource_type]
    if start_date:
        logs = [l for l in logs if l["created_at"] >= start_date]
    if end_date:
        logs = [l for l in logs if l["created_at"] <= end_date]
    
    # Sort by date descending
    logs.sort(key=lambda l: l["created_at"], reverse=True)
    
    # Paginate
    start = (page - 1) * per_page
    logs = logs[start:start + per_page]
    
    return [AuditLogEntry(**l) for l in logs]


# ============ SYSTEM MONITORING ============

@router.get("/stats", response_model=SystemStats)
async def get_system_stats():
    """Get system-wide statistics."""
    
    from app.services.payments import get_payment_orchestrator, PaymentStatus
    
    orchestrator = get_payment_orchestrator()
    
    # Get payment stats
    all_payments = orchestrator.list_payments(limit=10000)
    today = datetime.utcnow().date()
    payments_today = len([
        p for p in all_payments
        if p.created_at.date() == today and p.status == PaymentStatus.COMPLETED
    ])
    payments_pending = len([
        p for p in all_payments
        if p.status in [PaymentStatus.PENDING, PaymentStatus.PROCESSING, PaymentStatus.AWAITING_CONFIRMATION]
    ])
    
    # Company stats
    companies = list(_companies_store.values())
    active_companies = len([c for c in companies if c["status"] == "active"])
    
    return SystemStats(
        total_companies=len(companies),
        active_companies=active_companies,
        total_users=sum(c.get("current_users", 0) for c in companies),
        total_sites=sum(c.get("current_sites", 0) for c in companies),
        total_datasets=0,  # TODO: Get from datasets store
        total_storage_gb=sum(c.get("storage_used_gb", 0) for c in companies),
        payments_today=payments_today,
        payments_pending=payments_pending,
    )


@router.get("/health")
async def health_check():
    """System health check."""
    
    import os
    
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": os.getenv("APP_VERSION", "1.0.0"),
        "environment": os.getenv("ENVIRONMENT", "development"),
        "services": {
            "database": "ok",  # TODO: Check actual DB connection
            "storage": "ok" if os.getenv("S3_BUCKET") else "not_configured",
            "payments_multicaixa": "ok" if os.getenv("MULTICAIXA_API_KEY") else "not_configured",
            "payments_stripe": "ok" if os.getenv("STRIPE_SECRET_KEY") else "not_configured",
        }
    }
