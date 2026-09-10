"""Authenticated API contracts used by the GeoVision Flutter application."""

import json
import asyncio
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.time import utc_now
from app.deps import get_authorization_context, get_current_user
from app.models import (
    Acquisition,
    AccountEvent,
    Asset,
    DroneAircraft,
    DroneMission,
    MobileServiceRequest,
    Order,
    Payment,
    Site,
    User,
)
from app.modules.organizations.services import sole_active_workspace_id
from app.modules.assets.services import synchronize_legacy_site
from app.modules.missions.services import (
    acquisition_for_legacy,
    synchronize_legacy_drone_mission,
)
from app.modules.analytics.kpi_catalog import get_kpis_for_sectors
from app.modules.identity.domain import AuthorizationContext
from app.modules.operations.mobile_schemas import (
    MobileActionBucketsOut,
    MobileExperienceOut,
    MobileHomeOut,
    MobileServiceRequestOut,
)
from app.modules.operations.mobile_services import (
    MobileExperienceError,
    create_mobile_service_request,
    get_mobile_site,
    get_mobile_service_request,
    list_mobile_service_requests,
    list_mobile_sites,
    mobile_action_buckets,
    mobile_experience,
    mobile_home,
    mobile_service_result,
    require_mobile_workspace,
)
from app.services.erp_sync import publish_account_event
from app.sector_taxonomy import PUBLIC_SECTORS, normalize_public_sector

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
    "agriculture": "agriculture",
    "environment": "environment",
    "construction_infrastructure": "construction_infrastructure",
    "mining": "mining",
    "industry_energy_utilities": "industry_energy_utilities",
    "ports_logistics": "ports_logistics",
}


def _mobile_error(exc: MobileExperienceError) -> HTTPException:
    if exc.code in {
        "asset_not_found",
        "service_request_not_found",
        "site_not_found",
        "workspace_not_found",
    }:
        status_code = status.HTTP_404_NOT_FOUND
    elif exc.code == "idempotency_conflict":
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_403_FORBIDDEN
    return HTTPException(status_code=status_code, detail=str(exc))


@router.get("/experience", response_model=MobileExperienceOut)
def customer_mobile_experience(
    user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
) -> MobileExperienceOut:
    """Return server-authorized navigation and all accessible workspaces."""

    return mobile_experience(db, user=user, context=context)


@router.get("/home", response_model=MobileHomeOut)
def customer_mobile_home(
    priority_limit: int = Query(default=20, ge=1, le=100),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
) -> MobileHomeOut:
    """Answer what needs the selected workspace's attention now."""

    try:
        return mobile_home(
            db,
            context=context,
            priority_limit=priority_limit,
        )
    except MobileExperienceError as exc:
        raise _mobile_error(exc) from exc


@router.get("/actions", response_model=MobileActionBucketsOut)
def customer_mobile_actions(
    asset_id: str | None = Query(default=None, min_length=1, max_length=36),
    per_bucket_limit: int = Query(default=100, ge=1, le=500),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
) -> MobileActionBucketsOut:
    """Project the unified Action API into customer-facing work buckets."""

    try:
        return mobile_action_buckets(
            db,
            context=context,
            per_bucket_limit=per_bucket_limit,
            asset_id=asset_id,
        )
    except MobileExperienceError as exc:
        raise _mobile_error(exc) from exc


def _site_kpis(site: Site) -> list[dict[str, Any]]:
    kpi_sector = _MOBILE_KPI_SECTORS.get(normalize_public_sector(site.sector))
    if not kpi_sector:
        return []
    return [item.model_dump() for item in get_kpis_for_sectors([kpi_sector])]


def _site_payload(site: Site) -> dict[str, Any]:
    sector = normalize_public_sector(site.sector)
    if sector not in PUBLIC_SECTORS:
        raise ValueError("Site sector is not mapped to the public taxonomy")
    location = ", ".join(
        part for part in (site.municipality, site.province, site.country) if part
    )
    return {
        "id": site.id,
        "name": site.name,
        "sector": sector,
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
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    try:
        sites = list_mobile_sites(db, context=context)
        return [
            _site_payload(site)
            for site in sites
            if normalize_public_sector(site.sector) in PUBLIC_SECTORS
        ]
    except MobileExperienceError as exc:
        raise _mobile_error(exc) from exc


class SiteCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    sector: str = Field(min_length=2, max_length=50)
    country: str = Field(min_length=2, max_length=100)
    province: str = Field(min_length=2, max_length=100)
    municipality: str = Field(min_length=2, max_length=100)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    area_hectares: float | None = Field(default=None, gt=0, le=100_000_000)

    @field_validator("sector")
    @classmethod
    def canonical_sector(cls, value: str) -> str:
        canonical = normalize_public_sector(value)
        if canonical not in PUBLIC_SECTORS:
            raise ValueError("sector must be one of the six GeoVision public sectors")
        return canonical


@router.post("/sites", status_code=status.HTTP_201_CREATED)
def create_site(
    payload: SiteCreate,
    user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    """Create a site inside the authenticated customer's organisation."""
    try:
        workspace, company = require_mobile_workspace(
            db,
            context=context,
            permission="asset:create",
        )
    except MobileExperienceError as exc:
        raise _mobile_error(exc) from exc

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
        municipality=(payload.municipality.strip() if payload.municipality else None),
        latitude=payload.latitude,
        longitude=payload.longitude,
        area_hectares=payload.area_hectares,
        is_active=True,
    )
    db.add(site)
    db.flush()
    synchronize_legacy_site(
        db,
        site,
        actor_user_id=user.id,
        workspace_id=workspace.id,
    )
    company.current_sites = current + 1
    publish_account_event(
        db,
        company_id=company.id,
        workspace_id=workspace.id,
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


def _request_payload(
    item: MobileServiceRequest,
    *,
    result: Any = None,
) -> dict[str, Any]:
    try:
        attachments = json.loads(item.attachments_json or "[]")
    except (TypeError, json.JSONDecodeError):
        attachments = []
    return {
        "id": item.id,
        "organization_id": item.organization_id,
        "workspace_id": item.workspace_id,
        "asset_id": item.asset_id,
        "order_id": item.order_id,
        "report_id": item.report_id,
        "site_id": item.site_id or "",
        "site_name": item.site_name,
        "type": item.request_type,
        "urgency": item.urgency,
        "description": item.description,
        "status": item.status,
        "progress_percent": item.progress_percent,
        "attachments": attachments,
        "assigned_team": item.assigned_team,
        "lifecycle_version": item.lifecycle_version,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
        "result": result,
    }


@router.get("/service-requests", response_model=list[MobileServiceRequestOut])
def list_service_requests(
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    try:
        return [
            _request_payload(
                item,
                result=mobile_service_result(db, context=context, request=item),
            )
            for item in list_mobile_service_requests(db, context=context)
        ]
    except MobileExperienceError as exc:
        raise _mobile_error(exc) from exc


@router.get(
    "/service-requests/{request_id}",
    response_model=MobileServiceRequestOut,
)
def read_service_request(
    request_id: str,
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    """Read an existing service result within the selected workspace."""

    try:
        item = get_mobile_service_request(
            db,
            context=context,
            request_id=request_id,
        )
        return _request_payload(
            item,
            result=mobile_service_result(
                db,
                context=context,
                request=item,
            ),
        )
    except MobileExperienceError as exc:
        raise _mobile_error(exc) from exc


@router.post(
    "/service-requests",
    response_model=MobileServiceRequestOut,
    status_code=status.HTTP_201_CREATED,
)
def create_service_request(
    payload: ServiceRequestCreate,
    response: Response,
    user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        min_length=8,
        max_length=160,
    ),
):
    try:
        item, replayed = create_mobile_service_request(
            db,
            actor=user,
            context=context,
            site_id=payload.site_id,
            request_type=payload.type,
            urgency=payload.urgency,
            description=payload.description,
            attachments=payload.attachments,
            idempotency_key=idempotency_key,
        )
        db.commit()
        db.refresh(item)
    except MobileExperienceError as exc:
        db.rollback()
        raise _mobile_error(exc) from exc
    if replayed:
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotency-Replayed"] = "true"
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


def _drone_workspace(
    db: Session,
    *,
    context: AuthorizationContext,
    permission: str,
) -> tuple[str, str, bool]:
    """Resolve a customer Workspace before touching legacy drone resources."""

    try:
        workspace, company = require_mobile_workspace(
            db,
            context=context,
            permission=permission,
        )
    except MobileExperienceError as exc:
        raise _mobile_error(exc) from exc
    return (
        workspace.id,
        company.id,
        sole_active_workspace_id(db, company.id) == workspace.id,
    )


def _drone_site(
    db: Session,
    *,
    context: AuthorizationContext,
    site_id: str,
    permission: str,
) -> Site:
    try:
        return get_mobile_site(
            db,
            context=context,
            site_id=site_id,
            permission=permission,
        )
    except MobileExperienceError as exc:
        raise _mobile_error(exc) from exc


def _aircraft_is_in_workspace(
    db: Session,
    *,
    context: AuthorizationContext,
    aircraft: DroneAircraft,
    organization_id: str,
    sole_workspace: bool,
) -> bool:
    if aircraft.company_id != organization_id:
        return False
    if aircraft.site_id is None:
        # Aircraft created before Workspace ownership can be adopted only while
        # the Organization has one unambiguous active Workspace.
        return sole_workspace
    try:
        get_mobile_site(
            db,
            context=context,
            site_id=aircraft.site_id,
            permission="asset:read",
        )
    except MobileExperienceError:
        return False
    return True


def _mission_acquisition_scope(
    db: Session,
    *,
    context: AuthorizationContext,
    mission: DroneMission,
    sole_workspace: bool,
) -> tuple[Acquisition | None, bool]:
    """Revalidate a legacy mission's canonical Workspace projection."""

    acquisition = acquisition_for_legacy(
        db,
        source="drone_mission",
        source_id=mission.id,
    )
    if acquisition is None:
        return None, True
    asset = db.get(Asset, acquisition.asset_id)
    workspace_id = context.active_workspace_id
    organization_id = context.active_organization_id

    def workspace_matches(value: str | None) -> bool:
        return value == workspace_id or (value is None and sole_workspace)

    valid = bool(
        workspace_id
        and organization_id
        and acquisition.organization_id == organization_id
        and workspace_matches(acquisition.workspace_id)
        and asset is not None
        and asset.organization_id == organization_id
        and workspace_matches(asset.workspace_id)
        and asset.status != "archived"
        and asset.legacy_source == "site"
        and asset.legacy_source_id == mission.site_id
    )
    return acquisition, valid


@router.get("/drones")
def list_drones(
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    _, organization_id, sole_workspace = _drone_workspace(
        db,
        context=context,
        permission="asset:read",
    )
    try:
        site_ids = {site.id for site in list_mobile_sites(db, context=context)}
    except MobileExperienceError as exc:
        raise _mobile_error(exc) from exc
    filters = [DroneAircraft.site_id.in_(site_ids)]
    if sole_workspace:
        filters.append(DroneAircraft.site_id.is_(None))
    rows = (
        db.query(DroneAircraft)
        .filter(
            DroneAircraft.company_id == organization_id,
            or_(*filters),
        )
        .order_by(DroneAircraft.updated_at.desc())
        .all()
    )
    return [_aircraft_payload(row) for row in rows]


@router.post("/drones", status_code=status.HTTP_201_CREATED)
def register_drone(
    payload: AircraftCreate,
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    workspace_id, organization_id, sole_workspace = _drone_workspace(
        db,
        context=context,
        permission="workspace:contribute",
    )
    site = None
    if payload.site_id:
        site = _drone_site(
            db,
            context=context,
            site_id=payload.site_id,
            permission="workspace:contribute",
        )
        asset = synchronize_legacy_site(
            db,
            site,
            actor_user_id=context.user_id,
            workspace_id=workspace_id,
        )
        if (
            asset.organization_id != organization_id
            or asset.workspace_id != workspace_id
            or asset.status == "archived"
        ):
            raise HTTPException(status_code=404, detail="Site not found")
    elif not sole_workspace:
        raise HTTPException(
            status_code=409,
            detail="A site is required when an organisation has multiple workspaces",
        )
    canonical = payload.model.strip()
    sdk_supported = canonical in DJI_AUTOMATION_SUPPORT
    item = DroneAircraft(
        company_id=organization_id,
        site_id=site.id if site else None,
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


def _mission_payload(
    item: DroneMission, acquisition_id: str | None = None
) -> dict[str, Any]:
    payload = {
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
    if acquisition_id:
        payload["acquisition_id"] = acquisition_id
    return payload


@router.get("/drone-missions")
def list_drone_missions(
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    _, organization_id, sole_workspace = _drone_workspace(
        db,
        context=context,
        permission="asset:read",
    )
    try:
        site_ids = {site.id for site in list_mobile_sites(db, context=context)}
    except MobileExperienceError as exc:
        raise _mobile_error(exc) from exc
    rows = (
        db.query(DroneMission)
        .filter(
            DroneMission.company_id == organization_id,
            DroneMission.site_id.in_(site_ids),
        )
        .order_by(DroneMission.updated_at.desc())
        .all()
    )
    payloads: list[dict[str, Any]] = []
    for row in rows:
        acquisition, valid = _mission_acquisition_scope(
            db,
            context=context,
            mission=row,
            sole_workspace=sole_workspace,
        )
        if valid:
            payloads.append(
                _mission_payload(row, acquisition.id if acquisition else None)
            )
    return payloads


@router.post("/drone-missions", status_code=status.HTTP_201_CREATED)
def create_drone_mission(
    payload: MissionCreate,
    user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    workspace_id, organization_id, sole_workspace = _drone_workspace(
        db,
        context=context,
        permission="workspace:contribute",
    )
    site = _drone_site(
        db,
        context=context,
        site_id=payload.site_id,
        permission="workspace:contribute",
    )
    asset = synchronize_legacy_site(
        db,
        site,
        actor_user_id=user.id,
        workspace_id=workspace_id,
    )
    if (
        asset.organization_id != organization_id
        or asset.workspace_id != workspace_id
        or asset.status == "archived"
    ):
        raise HTTPException(status_code=404, detail="Site not found")
    aircraft = db.get(DroneAircraft, payload.aircraft_id)
    if not aircraft or not _aircraft_is_in_workspace(
        db,
        context=context,
        aircraft=aircraft,
        organization_id=organization_id,
        sole_workspace=sole_workspace,
    ):
        raise HTTPException(status_code=404, detail="Aircraft not found")
    if not aircraft.sdk_supported:
        raise HTTPException(
            status_code=409,
            detail="This aircraft supports media import only; automated missions require a supported SDK aircraft.",
        )
    item = DroneMission(
        company_id=organization_id,
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
    db.flush()
    acquisition = synchronize_legacy_drone_mission(db, item, actor=user)
    db.commit()
    db.refresh(item)
    return _mission_payload(item, acquisition.id)


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
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    workspace_id, organization_id, sole_workspace = _drone_workspace(
        db,
        context=context,
        permission="workspace:operate",
    )
    item = db.get(DroneMission, mission_id)
    if not item or item.company_id != organization_id:
        raise HTTPException(status_code=404, detail="Mission not found")
    site = _drone_site(
        db,
        context=context,
        site_id=item.site_id,
        permission="workspace:operate",
    )
    asset = synchronize_legacy_site(
        db,
        site,
        actor_user_id=user.id,
        workspace_id=workspace_id,
    )
    if (
        asset.organization_id != organization_id
        or asset.workspace_id != workspace_id
        or asset.status == "archived"
    ):
        raise HTTPException(status_code=404, detail="Mission not found")
    _, valid_acquisition = _mission_acquisition_scope(
        db,
        context=context,
        mission=item,
        sole_workspace=sole_workspace,
    )
    if not valid_acquisition:
        raise HTTPException(status_code=404, detail="Mission not found")
    checklist = payload.model_dump()
    if not all(checklist.values()):
        raise HTTPException(
            status_code=409, detail="Every safety check must be confirmed"
        )
    aircraft = db.get(DroneAircraft, item.aircraft_id)
    if not aircraft or not _aircraft_is_in_workspace(
        db,
        context=context,
        aircraft=aircraft,
        organization_id=organization_id,
        sole_workspace=sole_workspace,
    ):
        raise HTTPException(status_code=404, detail="Aircraft not found")
    if not aircraft.sdk_supported:
        raise HTTPException(
            status_code=409, detail="Aircraft cannot execute automated missions"
        )
    item.checklist_json = json.dumps(checklist)
    item.status = "approved_for_provider_handoff"
    acquisition = synchronize_legacy_drone_mission(db, item, actor=user)
    db.commit()
    db.refresh(item)
    return {
        **_mission_payload(item, acquisition.id),
        "execution": "provider_handoff_required",
        "message": "Open the approved DJI provider to upload and supervise this mission.",
    }


def _event_payload(item: AccountEvent) -> dict[str, Any]:
    try:
        data = json.loads(item.payload_json or "{}")
    except (TypeError, json.JSONDecodeError):
        data = {}
    if isinstance(data, dict):
        # Account events are customer-visible. Internal actor identifiers are
        # useful in the audit log, not in the mobile projection.
        data.pop("actor_user_id", None)
    else:
        data = {}
    return {
        "id": item.id,
        "workspace_id": item.workspace_id,
        "type": item.event_type,
        "resource_type": item.resource_type,
        "resource_id": item.resource_id,
        "title": item.title,
        "data": data,
        "created_at": item.created_at.isoformat(),
    }


def _scoped_account_events_query(
    db: Session,
    *,
    context: AuthorizationContext,
):
    workspace, company = require_mobile_workspace(
        db,
        context=context,
        permission="workspace:read",
    )
    return db.query(AccountEvent).filter(
        AccountEvent.company_id == company.id,
        AccountEvent.workspace_id == workspace.id,
    )


@router.get("/account/overview")
def account_overview(
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    """Workspace-isolated, customer-visible account snapshot for mobile."""

    try:
        workspace, company = require_mobile_workspace(
            db,
            context=context,
            permission="workspace:read",
        )
        requests = list_mobile_service_requests(db, context=context)
        sites = list_mobile_sites(db, context=context)
    except MobileExperienceError as exc:
        raise _mobile_error(exc) from exc

    orders = (
        db.query(Order)
        .filter(
            Order.workspace_id == workspace.id,
            or_(
                Order.organization_id == company.id,
                and_(
                    Order.organization_id.is_(None),
                    Order.company_id == company.id,
                ),
            ),
        )
        .order_by(Order.updated_at.desc())
        .limit(20)
        .all()
    )
    payments = (
        db.query(Payment)
        .join(Order, Order.id == Payment.order_id)
        .filter(
            Order.workspace_id == workspace.id,
            or_(
                Order.organization_id == company.id,
                and_(
                    Order.organization_id.is_(None),
                    Order.company_id == company.id,
                ),
            ),
            or_(
                Payment.organization_id == company.id,
                and_(
                    Payment.organization_id.is_(None),
                    Payment.company_id == company.id,
                ),
            ),
        )
        .order_by(Payment.updated_at.desc())
        .limit(20)
        .all()
    )
    outstanding = sum(
        int(payment.amount)
        for payment in payments
        if payment.status not in {"paid", "completed", "confirmed", "refunded"}
    )
    latest = max(
        [workspace.updated_at]
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
            "paid_payments": sum(
                1 for p in payments if p.status in {"paid", "completed", "confirmed"}
            ),
            "pending_payments": sum(
                1
                for p in payments
                if p.status not in {"paid", "completed", "confirmed", "refunded"}
            ),
        },
        "activity": {
            "sites": len(sites),
            "orders": len(orders),
            "active_orders": sum(
                1
                for o in orders
                if o.status not in {"completed", "cancelled", "refunded"}
            ),
            "service_requests": len(requests),
            "active_requests": sum(
                1 for r in requests if r.status not in {"completed", "cancelled"}
            ),
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
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    try:
        query = _scoped_account_events_query(db, context=context)
    except MobileExperienceError as exc:
        raise _mobile_error(exc) from exc
    if after:
        query = query.filter(AccountEvent.created_at > after)
    rows = query.order_by(AccountEvent.created_at.desc()).limit(limit).all()
    return [_event_payload(row) for row in reversed(rows)]


@router.get("/account/stream")
def account_stream(
    after: datetime | None = Query(default=None),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    """SSE feed with heartbeat; mobile uses polling fallback after disconnects."""
    try:
        scoped_query = _scoped_account_events_query(db, context=context)
    except MobileExperienceError as exc:
        raise _mobile_error(exc) from exc

    async def generate():
        cursor = after or utc_now()
        yield "event: ready\ndata: {}\n\n"
        while True:
            rows = (
                scoped_query.filter(AccountEvent.created_at > cursor)
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
