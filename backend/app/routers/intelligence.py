"""Tenant-safe satellite/weather intelligence and internal schedule API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.deps import get_authorization_context, get_current_user, get_db
from app.integrations.satellite import create_satellite_provider
from app.integrations.storage import create_object_storage_provider
from app.integrations.weather import create_weather_provider
from app.models import IntelligenceAcquisition, IntelligenceSchedule, User
from app.modules.assets.services import AssetAccessError, get_asset
from app.modules.identity.domain import AuthorizationContext
from app.modules.monitoring.intelligence_domain import IntelligenceError
from app.modules.monitoring.intelligence_schemas import (
    IntelligenceAcquisitionOut,
    IntelligenceScheduleCreate,
    IntelligenceScheduleOut,
    IntelligenceScheduleUpdate,
    SatelliteIntelligenceOut,
    SatelliteIntelligenceRequest,
    SatelliteSceneOut,
    WeatherIntelligenceOut,
    WeatherIntelligenceRequest,
    WeatherObservationOut,
)
from app.modules.monitoring.intelligence_services import (
    acquisition_out,
    create_intelligence_schedule,
    list_asset_scenes,
    list_asset_weather,
    observation_out,
    observations_for_run,
    request_satellite_intelligence,
    request_weather_intelligence,
    scene_out,
    scenes_for_run,
    schedule_out,
    update_intelligence_schedule,
)
from app.modules.operations.auth import OperationsStaff
from app.services.storage import StorageService


router = APIRouter(prefix="/intelligence", tags=["intelligence"])


def _close(provider) -> None:
    client = getattr(provider, "client", None)
    close = getattr(client, "close", None)
    if callable(close):
        close()


def _raise_error(exc: Exception) -> None:
    code = getattr(exc, "code", "invalid_intelligence_request")
    status_code = {
        "asset_not_found": status.HTTP_404_NOT_FOUND,
        "asset_access_denied": status.HTTP_404_NOT_FOUND,
        "workspace_required": status.HTTP_403_FORBIDDEN,
        "schedule_not_found": status.HTTP_404_NOT_FOUND,
        "acquisition_not_found": status.HTTP_404_NOT_FOUND,
        "version_conflict": status.HTTP_409_CONFLICT,
        "idempotency_conflict": status.HTTP_409_CONFLICT,
        "provider_not_configured": status.HTTP_503_SERVICE_UNAVAILABLE,
        "provider_dependency_missing": status.HTTP_503_SERVICE_UNAVAILABLE,
        "storage_dependency_missing": status.HTTP_503_SERVICE_UNAVAILABLE,
        "provider_coverage_mismatch": status.HTTP_422_UNPROCESSABLE_ENTITY,
    }.get(code, status.HTTP_422_UNPROCESSABLE_ENTITY)
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": str(exc)},
    ) from exc


def _allow_force(context: AuthorizationContext, force_refresh: bool) -> None:
    if force_refresh and not context.permissions.intersection(
        {"operations:access", "platform:admin"}
    ):
        raise HTTPException(
            status_code=403,
            detail="Only GeoVision Operations may bypass provider caches",
        )


@router.post("/satellite/search", response_model=SatelliteIntelligenceOut)
def satellite_search(
    data: SatelliteIntelligenceRequest,
    actor: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    _allow_force(context, data.force_refresh)
    provider = create_satellite_provider()
    storage = StorageService(create_object_storage_provider())
    try:
        row, cache_hit = request_satellite_intelligence(
            db,
            actor=actor,
            context=context,
            data=data,
            provider=provider,
            storage=storage,
        )
        return {
            "acquisition": acquisition_out(row, cache_hit=cache_hit),
            "scenes": [scene_out(item) for item in scenes_for_run(db, row)],
        }
    except (AssetAccessError, IntelligenceError) as exc:
        db.rollback()
        _raise_error(exc)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Intelligence request already exists") from exc
    finally:
        _close(provider)


@router.post("/weather/observations", response_model=WeatherIntelligenceOut)
def weather_observations(
    data: WeatherIntelligenceRequest,
    actor: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    _allow_force(context, data.force_refresh)
    provider = create_weather_provider()
    try:
        row, cache_hit = request_weather_intelligence(
            db, actor=actor, context=context, data=data, provider=provider
        )
        return {
            "acquisition": acquisition_out(row, cache_hit=cache_hit),
            "observations": [
                observation_out(item) for item in observations_for_run(db, row)
            ],
        }
    except (AssetAccessError, IntelligenceError) as exc:
        db.rollback()
        _raise_error(exc)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Intelligence request already exists") from exc
    finally:
        _close(provider)


@router.get(
    "/assets/{asset_id}/satellite", response_model=list[SatelliteSceneOut]
)
def asset_satellite_scenes(
    asset_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    try:
        return [
            scene_out(item)
            for item in list_asset_scenes(
                db, context=context, asset_id=asset_id, limit=limit
            )
        ]
    except AssetAccessError as exc:
        _raise_error(exc)


@router.get(
    "/assets/{asset_id}/weather", response_model=list[WeatherObservationOut]
)
def asset_weather_observations(
    asset_id: str,
    metric: str | None = Query(default=None, min_length=2, max_length=100),
    limit: int = Query(default=500, ge=1, le=2000),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    try:
        return [
            observation_out(item)
            for item in list_asset_weather(
                db,
                context=context,
                asset_id=asset_id,
                metric=metric,
                limit=limit,
            )
        ]
    except AssetAccessError as exc:
        _raise_error(exc)


@router.get(
    "/acquisitions/{acquisition_id}", response_model=IntelligenceAcquisitionOut
)
def intelligence_acquisition(
    acquisition_id: str,
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    row = db.get(IntelligenceAcquisition, acquisition_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Intelligence acquisition not found")
    try:
        get_asset(db, context=context, asset_id=row.asset_id, permission="asset:read")
    except AssetAccessError as exc:
        _raise_error(exc)
    return acquisition_out(row)


@router.get("/schedules", response_model=list[IntelligenceScheduleOut])
def intelligence_schedules(
    actor: OperationsStaff,
    organization_id: str | None = Query(default=None, max_length=36),
    asset_id: str | None = Query(default=None, max_length=36),
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
):
    del actor
    query = db.query(IntelligenceSchedule)
    if organization_id:
        query = query.filter(IntelligenceSchedule.organization_id == organization_id)
    if asset_id:
        query = query.filter(IntelligenceSchedule.asset_id == asset_id)
    return [
        schedule_out(item)
        for item in query.order_by(IntelligenceSchedule.created_at.desc()).limit(limit).all()
    ]


@router.post(
    "/schedules",
    response_model=IntelligenceScheduleOut,
    status_code=status.HTTP_201_CREATED,
)
def create_schedule(
    data: IntelligenceScheduleCreate,
    actor: OperationsStaff,
    db: Session = Depends(get_db),
):
    try:
        return schedule_out(create_intelligence_schedule(db, actor=actor, data=data))
    except IntelligenceError as exc:
        db.rollback()
        _raise_error(exc)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Intelligence schedule already exists") from exc


@router.patch("/schedules/{schedule_id}", response_model=IntelligenceScheduleOut)
def update_schedule(
    schedule_id: str,
    data: IntelligenceScheduleUpdate,
    actor: OperationsStaff,
    db: Session = Depends(get_db),
):
    del actor
    schedule = db.get(IntelligenceSchedule, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Intelligence schedule not found")
    try:
        return schedule_out(update_intelligence_schedule(db, schedule=schedule, data=data))
    except IntelligenceError as exc:
        db.rollback()
        _raise_error(exc)


__all__ = ["router"]
