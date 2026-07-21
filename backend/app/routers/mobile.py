"""Authenticated API contracts used by the GeoVision Flutter application."""

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Company, MobileServiceRequest, Site, User
from app.routers.me import _get_user_company_id

router = APIRouter(prefix="/mobile", tags=["mobile"])


def _site_payload(site: Site) -> dict[str, Any]:
    location = ", ".join(
        part for part in (site.municipality, site.province, site.country) if part
    )
    return {
        "id": site.id,
        "name": site.name,
        "sector": site.sector or "agriculture",
        "status": "active" if site.is_active else "offline",
        "location": location,
        "center": {
            "lat": float(site.latitude or 0),
            "lng": float(site.longitude or 0),
        },
        "boundary": [],
        "areas": [],
        "kpis": [],
        "total_hectares": float(site.area_hectares or 0),
        "open_alerts": 0,
    }


@router.get("/sites")
def list_sites(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    company_id = _get_user_company_id(user, db)
    if not company_id:
        return []
    sites = (
        db.query(Site)
        .filter(Site.company_id == company_id)
        .order_by(Site.updated_at.desc())
        .all()
    )
    return [_site_payload(site) for site in sites]


class SiteCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    sector: str = Field(
        default="agriculture",
        pattern="^(agriculture|livestock|infrastructure|mining|environment)$",
    )
    country: str = Field(default="Angola", pattern="^Angola$")
    province: str = Field(min_length=2, max_length=100)
    municipality: str = Field(min_length=2, max_length=100)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    area_hectares: float | None = Field(default=None, gt=0, le=100_000_000)


@router.post("/sites", status_code=status.HTTP_201_CREATED)
def create_site(
    payload: SiteCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a site inside the authenticated customer's organisation."""
    company_id = _get_user_company_id(user, db)
    company = db.get(Company, company_id) if company_id else None
    if not company:
        raise HTTPException(status_code=403, detail="Organisation not found")

    current = db.query(Site).filter(Site.company_id == company.id).count()
    if current >= company.max_sites:
        raise HTTPException(
            status_code=409,
            detail=f"Site limit reached ({company.max_sites})",
        )

    site = Site(
        id=str(uuid.uuid4()),
        company_id=company.id,
        name=payload.name.strip(),
        sector=payload.sector,
        country=payload.country.strip(),
        province=payload.province.strip() if payload.province else None,
        municipality=(
            payload.municipality.strip() if payload.municipality else None
        ),
        latitude=payload.latitude,
        longitude=payload.longitude,
        area_hectares=payload.area_hectares,
        is_active=True,
    )
    db.add(site)
    company.current_sites = current + 1
    db.commit()
    db.refresh(site)
    return _site_payload(site)


class ServiceRequestCreate(BaseModel):
    site_id: str
    site_name: str = Field(min_length=1, max_length=200)
    type: str = Field(min_length=1, max_length=50)
    urgency: str = Field(default="normal", pattern="^(low|normal|high|critical)$")
    description: str = Field(min_length=1, max_length=5000)
    attachments: list[str] = Field(default_factory=list, max_length=20)


def _request_payload(item: MobileServiceRequest) -> dict[str, Any]:
    try:
        attachments = json.loads(item.attachments_json or "[]")
    except (TypeError, json.JSONDecodeError):
        attachments = []
    return {
        "id": item.id,
        "site_id": item.site_id or "",
        "site_name": item.site_name,
        "type": item.request_type,
        "urgency": item.urgency,
        "description": item.description,
        "status": item.status,
        "progress_percent": item.progress_percent,
        "attachments": attachments,
        "assigned_team": item.assigned_team,
        "created_at": item.created_at.isoformat(),
    }


@router.get("/service-requests")
def list_service_requests(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items = (
        db.query(MobileServiceRequest)
        .filter(MobileServiceRequest.user_id == user.id)
        .order_by(MobileServiceRequest.created_at.desc())
        .all()
    )
    return [_request_payload(item) for item in items]


@router.post("/service-requests", status_code=status.HTTP_201_CREATED)
def create_service_request(
    payload: ServiceRequestCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    company_id = _get_user_company_id(user, db)
    site = db.get(Site, payload.site_id)
    if not site or not company_id or site.company_id != company_id:
        raise HTTPException(status_code=404, detail="Site not found")
    item = MobileServiceRequest(
        user_id=user.id,
        site_id=site.id,
        site_name=site.name,
        request_type=payload.type,
        urgency=payload.urgency,
        description=payload.description,
        attachments_json=json.dumps(payload.attachments),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _request_payload(item)
