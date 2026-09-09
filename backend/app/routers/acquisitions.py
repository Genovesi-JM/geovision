"""Canonical customer and internal mission/acquisition API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.deps import get_authorization_context, get_current_user, get_db
from app.models import Acquisition, Asset, User
from app.modules.assets.services import AssetAccessError, get_asset
from app.modules.identity.domain import AuthorizationContext
from app.modules.missions.auth import MissionStaff
from app.modules.missions.domain import AcquisitionError, AcquisitionType
from app.modules.missions.schemas import (
    AcquisitionCreate,
    AcquisitionOut,
    AcquisitionStateUpdate,
    AcquisitionUpdate,
    InternalAcquisitionCreate,
    InternalAcquisitionOut,
    InternalAcquisitionUpdate,
)
from app.modules.missions.services import (
    acquisition_out,
    asset_acquisition_outputs,
    create_acquisition,
    list_acquisitions,
    transition_acquisition,
    update_acquisition,
)
from app.modules.organizations.domain import permission_granted


router = APIRouter(prefix="/missions", tags=["missions"])


def _raise_acquisition_error(exc: Exception) -> None:
    code = getattr(exc, "code", "invalid_acquisition")
    if code in {
        "acquisition_not_found",
        "asset_not_found",
        "order_not_found",
        "job_not_found",
        "aircraft_not_found",
        "operator_not_found",
        "contractor_not_found",
        "reflight_not_found",
    }:
        status_code = status.HTTP_404_NOT_FOUND
    elif code in {
        "version_conflict",
        "invalid_transition",
        "acquisition_locked",
        "schedule_locked",
        "job_asset_mismatch",
    }:
        status_code = status.HTTP_409_CONFLICT
    elif code in {"state_forbidden", "assignment_forbidden"}:
        status_code = status.HTTP_403_FORBIDDEN
    elif code == "workspace_required":
        status_code = status.HTTP_403_FORBIDDEN
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": str(exc)},
    ) from exc


def _customer_asset(
    db: Session,
    context: AuthorizationContext,
    asset_id: str,
    *,
    write: bool,
) -> Asset:
    try:
        return get_asset(
            db,
            context=context,
            asset_id=asset_id,
            permission="asset:update" if write else "asset:read",
        )
    except AssetAccessError as exc:
        _raise_acquisition_error(exc)


def _customer_acquisition(
    db: Session,
    context: AuthorizationContext,
    acquisition_id: str,
    *,
    write: bool,
) -> Acquisition:
    row = db.get(Acquisition, acquisition_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Acquisition not found")
    _customer_asset(db, context, row.asset_id, write=write)
    return row


@router.get("/internal", response_model=list[InternalAcquisitionOut])
def internal_acquisitions(
    actor: MissionStaff,
    organization_id: str | None = Query(default=None, max_length=36),
    workspace_id: str | None = Query(default=None, max_length=36),
    asset_id: str | None = Query(default=None, max_length=36),
    acquisition_type: AcquisitionType | None = None,
    acquisition_state: str | None = Query(default=None, alias="state", max_length=30),
    limit: int = Query(default=200, ge=1, le=1_000),
    db: Session = Depends(get_db),
):
    del actor
    rows = list_acquisitions(
        db,
        organization_id=organization_id,
        workspace_id=workspace_id,
        asset_id=asset_id,
        acquisition_type=acquisition_type.value if acquisition_type else None,
        state=acquisition_state,
        limit=limit,
    )
    return [acquisition_out(db, row, internal=True) for row in rows]


@router.post(
    "/internal",
    response_model=InternalAcquisitionOut,
    status_code=status.HTTP_201_CREATED,
)
def internal_create_acquisition(
    data: InternalAcquisitionCreate,
    actor: MissionStaff,
    db: Session = Depends(get_db),
):
    asset = db.get(Asset, data.asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    try:
        row = create_acquisition(db, actor=actor, asset=asset, data=data, internal=True)
        db.commit()
        db.refresh(row)
        return acquisition_out(db, row, internal=True)
    except (AcquisitionError, AssetAccessError, ValueError) as exc:
        db.rollback()
        _raise_acquisition_error(exc)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Acquisition conflicts with existing data") from exc


@router.get("/internal/{acquisition_id}", response_model=InternalAcquisitionOut)
def internal_acquisition(
    acquisition_id: str,
    actor: MissionStaff,
    db: Session = Depends(get_db),
):
    del actor
    row = db.get(Acquisition, acquisition_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Acquisition not found")
    return acquisition_out(db, row, internal=True)


@router.patch("/internal/{acquisition_id}", response_model=InternalAcquisitionOut)
def internal_update_acquisition(
    acquisition_id: str,
    data: InternalAcquisitionUpdate,
    actor: MissionStaff,
    db: Session = Depends(get_db),
):
    row = db.query(Acquisition).filter(Acquisition.id == acquisition_id).with_for_update().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Acquisition not found")
    try:
        update_acquisition(db, actor=actor, acquisition=row, data=data, internal=True)
        db.commit()
        db.refresh(row)
        return acquisition_out(db, row, internal=True)
    except (AcquisitionError, ValueError) as exc:
        db.rollback()
        _raise_acquisition_error(exc)


@router.patch(
    "/internal/{acquisition_id}/state", response_model=InternalAcquisitionOut
)
def internal_transition_acquisition(
    acquisition_id: str,
    data: AcquisitionStateUpdate,
    actor: MissionStaff,
    db: Session = Depends(get_db),
):
    row = db.query(Acquisition).filter(Acquisition.id == acquisition_id).with_for_update().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Acquisition not found")
    try:
        transition_acquisition(db, actor=actor, acquisition=row, data=data, internal=True)
        db.commit()
        db.refresh(row)
        return acquisition_out(db, row, internal=True)
    except AcquisitionError as exc:
        db.rollback()
        _raise_acquisition_error(exc)


@router.get("/assets/{asset_id}/history", response_model=list[AcquisitionOut])
def asset_history(
    asset_id: str,
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    _customer_asset(db, context, asset_id, write=False)
    rows = list_acquisitions(db, asset_id=asset_id, chronological=True, limit=10_000)
    return [acquisition_out(db, row) for row in rows]


@router.get("/assets/{asset_id}/outputs")
def asset_outputs(
    asset_id: str,
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    _customer_asset(db, context, asset_id, write=False)
    return asset_acquisition_outputs(db, asset_id)


@router.get("", response_model=list[AcquisitionOut])
def my_acquisitions(
    asset_id: str | None = Query(default=None, max_length=36),
    acquisition_type: AcquisitionType | None = None,
    acquisition_state: str | None = Query(default=None, alias="state", max_length=30),
    limit: int = Query(default=200, ge=1, le=500),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    if not context.active_organization_id or not permission_granted(
        context.permissions, "asset:read"
    ):
        raise HTTPException(status_code=403, detail="Active workspace access required")
    if asset_id:
        _customer_asset(db, context, asset_id, write=False)
    rows = list_acquisitions(
        db,
        organization_id=context.active_organization_id,
        workspace_id=context.active_workspace_id,
        asset_id=asset_id,
        acquisition_type=acquisition_type.value if acquisition_type else None,
        state=acquisition_state,
        limit=limit,
    )
    return [acquisition_out(db, row) for row in rows]


@router.post("", response_model=AcquisitionOut, status_code=status.HTTP_201_CREATED)
def customer_create_acquisition(
    data: AcquisitionCreate,
    user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    asset = _customer_asset(db, context, data.asset_id, write=True)
    try:
        row = create_acquisition(db, actor=user, asset=asset, data=data, internal=False)
        db.commit()
        db.refresh(row)
        return acquisition_out(db, row)
    except (AcquisitionError, ValueError) as exc:
        db.rollback()
        _raise_acquisition_error(exc)


@router.get("/{acquisition_id}", response_model=AcquisitionOut)
def my_acquisition(
    acquisition_id: str,
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    row = _customer_acquisition(db, context, acquisition_id, write=False)
    return acquisition_out(db, row)


@router.patch("/{acquisition_id}", response_model=AcquisitionOut)
def customer_update_acquisition(
    acquisition_id: str,
    data: AcquisitionUpdate,
    user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    row = _customer_acquisition(db, context, acquisition_id, write=True)
    try:
        update_acquisition(db, actor=user, acquisition=row, data=data, internal=False)
        db.commit()
        db.refresh(row)
        return acquisition_out(db, row)
    except AcquisitionError as exc:
        db.rollback()
        _raise_acquisition_error(exc)


@router.patch("/{acquisition_id}/state", response_model=AcquisitionOut)
def customer_transition_acquisition(
    acquisition_id: str,
    data: AcquisitionStateUpdate,
    user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    row = _customer_acquisition(db, context, acquisition_id, write=True)
    try:
        transition_acquisition(db, actor=user, acquisition=row, data=data, internal=False)
        db.commit()
        db.refresh(row)
        return acquisition_out(db, row)
    except AcquisitionError as exc:
        db.rollback()
        _raise_acquisition_error(exc)


__all__ = ["router"]
