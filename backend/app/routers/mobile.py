"""Authenticated API contracts used by the GeoVision Flutter application."""

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import MobileServiceRequest, Site, User
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
