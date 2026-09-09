"""Canonical tenant-scoped Asset HTTP API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.deps import get_authorization_context, get_current_user
from app.models import User
from app.modules.assets.domain import (
    ASSET_TYPE_REGISTRY,
    SUPPORTED_GEOMETRY_TYPES,
    AssetSector,
    AssetStatus,
    AssetValidationError,
)
from app.modules.assets.schemas import (
    AssetCreate,
    AssetOut,
    AssetRegistryOut,
    AssetUpdate,
)
from app.modules.assets.services import (
    AssetAccessError,
    archive_asset,
    asset_payload,
    create_asset,
    get_asset,
    list_assets,
    update_asset,
)
from app.modules.identity.domain import AuthorizationContext


router = APIRouter(prefix="/assets", tags=["assets"])


def _asset_error(exc: Exception) -> HTTPException:
    code = getattr(exc, "code", "invalid_asset")
    status_code = {
        "asset_not_found": status.HTTP_404_NOT_FOUND,
        "parent_not_found": status.HTTP_404_NOT_FOUND,
        "asset_access_denied": status.HTTP_404_NOT_FOUND,
        "workspace_required": status.HTTP_403_FORBIDDEN,
        "asset_archived": status.HTTP_409_CONFLICT,
        "active_children": status.HTTP_409_CONFLICT,
        "hierarchy_cycle": status.HTTP_409_CONFLICT,
        "invalid_metadata": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "invalid_bbox": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "invalid_parent": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "invalid_status": status.HTTP_422_UNPROCESSABLE_ENTITY,
    }.get(code, status.HTTP_422_UNPROCESSABLE_ENTITY)
    return HTTPException(status_code=status_code, detail=str(exc))


def _bbox(value: str | None) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    try:
        coordinates = tuple(float(item.strip()) for item in value.split(","))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail="bbox must contain min longitude, min latitude, max longitude, max latitude",
        ) from exc
    if len(coordinates) != 4:
        raise HTTPException(
            status_code=422,
            detail="bbox must contain exactly four coordinates",
        )
    min_x, min_y, max_x, max_y = coordinates
    if not (-180 <= min_x <= 180 and -180 <= max_x <= 180):
        raise HTTPException(status_code=422, detail="bbox longitude is outside EPSG:4326")
    if not (-90 <= min_y <= 90 and -90 <= max_y <= 90):
        raise HTTPException(status_code=422, detail="bbox latitude is outside EPSG:4326")
    return min_x, min_y, max_x, max_y


def _filtered_assets(
    db: Session,
    context: AuthorizationContext,
    *,
    organization_id: str | None,
    workspace_id: str | None,
    parent_asset_id: str | None,
    root_only: bool,
    sector: str | None,
    asset_type: str | None,
    asset_status: AssetStatus | None,
    include_archived: bool,
    bbox: str | None,
    limit: int,
    offset: int,
):
    try:
        return list_assets(
            db,
            context=context,
            organization_id=organization_id,
            workspace_id=workspace_id,
            parent_asset_id=parent_asset_id,
            root_only=root_only,
            sector=sector,
            asset_type=asset_type,
            status=asset_status.value if asset_status else None,
            include_archived=include_archived,
            bbox=_bbox(bbox),
            limit=limit,
            offset=offset,
        )
    except (AssetAccessError, AssetValidationError, ValueError) as exc:
        raise _asset_error(exc) from exc


@router.get("/registry", response_model=AssetRegistryOut)
def asset_registry(user: User = Depends(get_current_user)):
    del user
    return AssetRegistryOut(
        sectors=sorted(sector.value for sector in AssetSector),
        common_asset_types=sorted(ASSET_TYPE_REGISTRY),
        geometry_types=sorted(SUPPORTED_GEOMETRY_TYPES),
    )


@router.get("", response_model=list[AssetOut])
def assets_list(
    organization_id: str | None = None,
    workspace_id: str | None = None,
    parent_asset_id: str | None = None,
    root_only: bool = False,
    sector: str | None = None,
    asset_type: str | None = None,
    asset_status: AssetStatus | None = Query(default=None, alias="status"),
    include_archived: bool = False,
    bbox: str | None = Query(
        default=None,
        description="min_lon,min_lat,max_lon,max_lat in EPSG:4326",
    ),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    rows = _filtered_assets(
        db,
        context,
        organization_id=organization_id,
        workspace_id=workspace_id,
        parent_asset_id=parent_asset_id,
        root_only=root_only,
        sector=sector,
        asset_type=asset_type,
        asset_status=asset_status,
        include_archived=include_archived,
        bbox=bbox,
        limit=limit,
        offset=offset,
    )
    return [AssetOut(**asset_payload(db, row)) for row in rows]


@router.get("/map")
def assets_map(
    organization_id: str | None = None,
    workspace_id: str | None = None,
    parent_asset_id: str | None = None,
    root_only: bool = False,
    sector: str | None = None,
    asset_type: str | None = None,
    asset_status: AssetStatus | None = Query(default=None, alias="status"),
    include_archived: bool = False,
    bbox: str | None = None,
    limit: int = Query(default=500, ge=1, le=2_000),
    offset: int = Query(default=0, ge=0),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    rows = _filtered_assets(
        db,
        context,
        organization_id=organization_id,
        workspace_id=workspace_id,
        parent_asset_id=parent_asset_id,
        root_only=root_only,
        sector=sector,
        asset_type=asset_type,
        asset_status=asset_status,
        include_archived=include_archived,
        bbox=bbox,
        limit=limit,
        offset=offset,
    )
    features = []
    for row in rows:
        payload = asset_payload(db, row)
        if payload["geometry"] is None:
            continue
        features.append(
            {
                "type": "Feature",
                "id": row.id,
                "bbox": payload["bbox"],
                "geometry": payload["geometry"],
                "properties": {
                    "id": row.id,
                    "parent_asset_id": row.parent_asset_id,
                    "sector": row.sector,
                    "asset_type": row.asset_type,
                    "name": row.name,
                    "status": row.status,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


@router.post("", response_model=AssetOut, status_code=status.HTTP_201_CREATED)
def asset_create(
    payload: AssetCreate,
    user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    try:
        row = create_asset(
            db,
            actor=user,
            context=context,
            values=payload.model_dump(),
        )
        db.commit()
        db.refresh(row)
        return AssetOut(**asset_payload(db, row))
    except (AssetAccessError, AssetValidationError, ValueError) as exc:
        db.rollback()
        raise _asset_error(exc) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Asset could not be created") from exc


@router.get("/{asset_id}", response_model=AssetOut)
def asset_read(
    asset_id: str,
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    try:
        return AssetOut(**asset_payload(db, get_asset(db, context=context, asset_id=asset_id)))
    except (AssetAccessError, AssetValidationError, ValueError) as exc:
        raise _asset_error(exc) from exc


@router.patch("/{asset_id}", response_model=AssetOut)
def asset_update(
    asset_id: str,
    payload: AssetUpdate,
    user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    changed_fields = set(payload.model_fields_set)
    if not changed_fields:
        raise HTTPException(status_code=422, detail="At least one asset field is required")
    try:
        row = update_asset(
            db,
            actor=user,
            context=context,
            asset_id=asset_id,
            values=payload.model_dump(),
            changed_fields=changed_fields,
        )
        db.commit()
        db.refresh(row)
        return AssetOut(**asset_payload(db, row))
    except (AssetAccessError, AssetValidationError, ValueError) as exc:
        db.rollback()
        raise _asset_error(exc) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Asset could not be updated") from exc


@router.delete("/{asset_id}", response_model=AssetOut)
def asset_archive(
    asset_id: str,
    user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    try:
        row = archive_asset(
            db,
            actor=user,
            context=context,
            asset_id=asset_id,
        )
        db.commit()
        db.refresh(row)
        return AssetOut(**asset_payload(db, row))
    except (AssetAccessError, AssetValidationError, ValueError) as exc:
        db.rollback()
        raise _asset_error(exc) from exc


__all__ = ["router"]
