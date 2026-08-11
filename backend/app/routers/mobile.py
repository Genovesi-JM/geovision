"""Authenticated API contracts used by the GeoVision Flutter application."""

import json
import asyncio
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import (
    AccountEvent,
    Company,
    DroneAircraft,
    DroneMission,
    MobileServiceRequest,
    Order,
    Payment,
    Site,
    User,
)
from app.routers.me import _get_user_company_id
from app.routers.kpi import get_kpis_for_sectors
from app.services.erp_sync import publish_account_event

router = APIRouter(prefix="/mobile", tags=["mobile"])

DJI_AUTOMATION_SUPPORT = {
    "DJI Mini 3": "mobile_sdk",
    "DJI Mini 3 Pro": "mobile_sdk",
    "DJI Mini 4 Pro": "mobile_sdk",
    "DJI Mavic 3 Enterprise": "mobile_sdk",
    "DJI Mavic 3M": "mobile_sdk",
    "DJI Matrice 30": "mobile_sdk",
    "DJI Matrice 30T": "mobile_sdk",
    "DJI Matrice 350 RTK": "mobile_sdk",
    "DJI Matrice 4E": "mobile_sdk",
    "DJI Matrice 4T": "mobile_sdk",
}


_MOBILE_KPI_SECTORS = {
    "agriculture": "agro",
    "agro": "agro",
    "home": "home",
    "infrastructure": "infrastructure",
    "mining": "mining",
}


def _site_kpis(site: Site) -> list[dict[str, Any]]:
    kpi_sector = _MOBILE_KPI_SECTORS.get(site.sector or "")
    if not kpi_sector:
        return []
    return [item.model_dump() for item in get_kpis_for_sectors([kpi_sector])]


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
        "kpis": _site_kpis(site),
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
        pattern="^(home|agriculture|livestock|infrastructure|mining|environment)$",
    )
    country: str = Field(min_length=2, max_length=100)
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
    publish_account_event(
        db,
        company_id=company.id,
        event_type="site.created",
        resource_type="site",
        resource_id=site.id,
        title=f"Novo local: {site.name}",
        payload={"name": site.name, "sector": site.sector},
    )
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
    if company_id:
        publish_account_event(
            db,
            company_id=company_id,
            event_type="service_request.created",
            resource_type="service_request",
            resource_id=item.id,
            title=f"Pedido de serviço recebido: {site.name}",
            payload={"status": item.status, "urgency": item.urgency},
        )
    db.commit()
    db.refresh(item)
    return _request_payload(item)


class AircraftCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    model: str = Field(min_length=2, max_length=100)
    serial_number: str | None = Field(default=None, max_length=150)
    site_id: str | None = None


def _aircraft_payload(item: DroneAircraft) -> dict[str, Any]:
    capabilities = json.loads(item.capabilities_json or "[]")
    return {
        "id": item.id,
        "name": item.name,
        "manufacturer": item.manufacturer,
        "model": item.model,
        "serial_number": item.serial_number,
        "site_id": item.site_id,
        "provider": item.provider,
        "connection_mode": item.connection_mode,
        "sdk_supported": item.sdk_supported,
        "status": item.status,
        "capabilities": capabilities,
        "automation_readiness": (
            "credentials_required" if item.sdk_supported else "media_import_only"
        ),
    }


@router.get("/drones")
def list_drones(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    company_id = _get_user_company_id(user, db)
    if not company_id:
        raise HTTPException(status_code=403, detail="Organisation not found")
    rows = (
        db.query(DroneAircraft)
        .filter(DroneAircraft.company_id == company_id)
        .order_by(DroneAircraft.updated_at.desc())
        .all()
    )
    return [_aircraft_payload(row) for row in rows]


@router.post("/drones", status_code=status.HTTP_201_CREATED)
def register_drone(
    payload: AircraftCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    company_id = _get_user_company_id(user, db)
    if not company_id:
        raise HTTPException(status_code=403, detail="Organisation not found")
    site = db.get(Site, payload.site_id) if payload.site_id else None
    if payload.site_id and (not site or site.company_id != company_id):
        raise HTTPException(status_code=404, detail="Site not found")
    canonical = payload.model.strip()
    sdk_supported = canonical in DJI_AUTOMATION_SUPPORT
    item = DroneAircraft(
        company_id=company_id,
        site_id=payload.site_id,
        name=payload.name.strip(),
        model=canonical,
        serial_number=payload.serial_number,
        provider="dji_mobile_sdk" if sdk_supported else "manual_import",
        connection_mode="sdk_handoff" if sdk_supported else "media_import",
        sdk_supported=sdk_supported,
        capabilities_json=json.dumps(
            ["mission_planning", "telemetry", "media_sync"]
            if sdk_supported
            else ["media_import", "operation_history"]
        ),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _aircraft_payload(item)


class MissionCreate(BaseModel):
    site_id: str
    aircraft_id: str
    name: str = Field(min_length=3, max_length=160)
    mission_type: str = Field(
        default="mapping_grid",
        pattern="^(mapping_grid|inspection|corridor|multispectral|thermal)$",
    )
    altitude_m: int = Field(default=80, ge=20, le=120)
    speed_mps: float = Field(default=5, gt=0, le=15)
    front_overlap_percent: int = Field(default=80, ge=50, le=95)
    side_overlap_percent: int = Field(default=70, ge=50, le=95)
    boundary: list[dict[str, float]] = Field(min_length=3, max_length=500)


def _mission_payload(item: DroneMission) -> dict[str, Any]:
    return {
        "id": item.id,
        "site_id": item.site_id,
        "aircraft_id": item.aircraft_id,
        "name": item.name,
        "mission_type": item.mission_type,
        "status": item.status,
        "altitude_m": item.altitude_m,
        "speed_mps": float(item.speed_mps),
        "front_overlap_percent": item.front_overlap_percent,
        "side_overlap_percent": item.side_overlap_percent,
        "boundary": json.loads(item.boundary_json or "[]"),
        "route": json.loads(item.route_json or "[]"),
        "checklist": json.loads(item.checklist_json or "{}"),
        "provider_reference": item.provider_reference,
        "updated_at": item.updated_at.isoformat(),
    }


@router.get("/drone-missions")
def list_drone_missions(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    company_id = _get_user_company_id(user, db)
    rows = (
        db.query(DroneMission)
        .filter(DroneMission.company_id == company_id)
        .order_by(DroneMission.updated_at.desc())
        .all()
    ) if company_id else []
    return [_mission_payload(row) for row in rows]


@router.post("/drone-missions", status_code=status.HTTP_201_CREATED)
def create_drone_mission(
    payload: MissionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    company_id = _get_user_company_id(user, db)
    site = db.get(Site, payload.site_id)
    aircraft = db.get(DroneAircraft, payload.aircraft_id)
    if not company_id or not site or site.company_id != company_id:
        raise HTTPException(status_code=404, detail="Site not found")
    if not aircraft or aircraft.company_id != company_id:
        raise HTTPException(status_code=404, detail="Aircraft not found")
    if not aircraft.sdk_supported:
        raise HTTPException(
            status_code=409,
            detail="This aircraft supports media import only; automated missions require a supported SDK aircraft.",
        )
    item = DroneMission(
        company_id=company_id,
        site_id=site.id,
        aircraft_id=aircraft.id,
        created_by=user.id,
        name=payload.name.strip(),
        mission_type=payload.mission_type,
        altitude_m=payload.altitude_m,
        speed_mps=payload.speed_mps,
        front_overlap_percent=payload.front_overlap_percent,
        side_overlap_percent=payload.side_overlap_percent,
        boundary_json=json.dumps(payload.boundary),
        # Provider SDK generates the final terrain-aware route during handoff.
        route_json=json.dumps(payload.boundary),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _mission_payload(item)


class MissionApproval(BaseModel):
    pilot_confirmed: bool
    airspace_checked: bool
    weather_checked: bool
    people_clear: bool
    aircraft_checked: bool


@router.post("/drone-missions/{mission_id}/approve")
def approve_drone_mission(
    mission_id: str,
    payload: MissionApproval,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    company_id = _get_user_company_id(user, db)
    item = db.get(DroneMission, mission_id)
    if not item or item.company_id != company_id:
        raise HTTPException(status_code=404, detail="Mission not found")
    checklist = payload.model_dump()
    if not all(checklist.values()):
        raise HTTPException(status_code=409, detail="Every safety check must be confirmed")
    aircraft = db.get(DroneAircraft, item.aircraft_id)
    if not aircraft or not aircraft.sdk_supported:
        raise HTTPException(status_code=409, detail="Aircraft cannot execute automated missions")
    item.checklist_json = json.dumps(checklist)
    item.status = "approved_for_provider_handoff"
    db.commit()
    db.refresh(item)
    return {
        **_mission_payload(item),
        "execution": "provider_handoff_required",
        "message": "Open the approved DJI provider to upload and supervise this mission.",
    }


def _event_payload(item: AccountEvent) -> dict[str, Any]:
    try:
        data = json.loads(item.payload_json or "{}")
    except (TypeError, json.JSONDecodeError):
        data = {}
    return {
        "id": item.id,
        "type": item.event_type,
        "resource_type": item.resource_type,
        "resource_id": item.resource_id,
        "title": item.title,
        "data": data,
        "created_at": item.created_at.isoformat(),
    }


@router.get("/account/overview")
def account_overview(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Tenant-isolated, customer-visible account snapshot for the mobile app."""
    company_id = _get_user_company_id(user, db)
    company = db.get(Company, company_id) if company_id else None
    if not company:
        raise HTTPException(status_code=403, detail="Organisation not found")

    orders = (
        db.query(Order)
        .filter((Order.company_id == company.id) | (Order.user_id == user.id))
        .order_by(Order.updated_at.desc())
        .limit(20)
        .all()
    )
    payments = (
        db.query(Payment)
        .filter(Payment.company_id == company.id)
        .order_by(Payment.updated_at.desc())
        .limit(20)
        .all()
    )
    requests = (
        db.query(MobileServiceRequest)
        .filter(MobileServiceRequest.user_id == user.id)
        .order_by(MobileServiceRequest.updated_at.desc())
        .limit(20)
        .all()
    )
    sites = db.query(Site).filter(Site.company_id == company.id).count()
    outstanding = sum(
        int(payment.amount)
        for payment in payments
        if payment.status not in {"paid", "completed", "confirmed", "refunded"}
    )
    latest = max(
        [company.updated_at]
        + [item.updated_at for item in orders]
        + [item.updated_at for item in payments]
        + [item.updated_at for item in requests]
    )
    return {
        "organisation": {
            "id": company.id,
            "name": company.name,
            "plan": company.subscription_plan,
            "status": company.status,
        },
        "financial": {
            "currency": "AOA",
            "outstanding_cents": outstanding,
            "paid_payments": sum(1 for p in payments if p.status in {"paid", "completed", "confirmed"}),
            "pending_payments": sum(1 for p in payments if p.status not in {"paid", "completed", "confirmed", "refunded"}),
        },
        "activity": {
            "sites": sites,
            "orders": len(orders),
            "active_orders": sum(1 for o in orders if o.status not in {"completed", "cancelled", "refunded"}),
            "service_requests": len(requests),
            "active_requests": sum(1 for r in requests if r.status not in {"completed", "cancelled"}),
        },
        "recent_orders": [
            {
                "id": order.id,
                "number": order.order_number or order.id[:8],
                "status": order.status,
                "total_cents": int(order.total),
                "currency": order.currency,
                "updated_at": order.updated_at.isoformat(),
            }
            for order in orders[:5]
        ],
        "last_updated_at": latest.isoformat(),
    }


@router.get("/account/events")
def account_events(
    after: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    company_id = _get_user_company_id(user, db)
    if not company_id:
        raise HTTPException(status_code=403, detail="Organisation not found")
    query = db.query(AccountEvent).filter(AccountEvent.company_id == company_id)
    if after:
        query = query.filter(AccountEvent.created_at > after)
    rows = query.order_by(AccountEvent.created_at.desc()).limit(limit).all()
    return [_event_payload(row) for row in reversed(rows)]


@router.get("/account/stream")
def account_stream(
    after: datetime | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """SSE feed with heartbeat; mobile uses polling fallback after disconnects."""
    company_id = _get_user_company_id(user, db)
    if not company_id:
        raise HTTPException(status_code=403, detail="Organisation not found")

    async def generate():
        cursor = after or datetime.utcnow()
        yield "event: ready\ndata: {}\n\n"
        while True:
            rows = (
                db.query(AccountEvent)
                .filter(AccountEvent.company_id == company_id, AccountEvent.created_at > cursor)
                .order_by(AccountEvent.created_at.asc())
                .limit(100)
                .all()
            )
            for row in rows:
                cursor = max(cursor, row.created_at)
                yield f"id: {row.id}\nevent: account\ndata: {json.dumps(_event_payload(row))}\n\n"
            if not rows:
                yield ": heartbeat\n\n"
            await asyncio.sleep(5)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
