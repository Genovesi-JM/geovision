"""Customer action queue and permission-checked lifecycle endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.deps import get_authorization_context, get_current_user
from app.models import Action, Asset, User
from app.modules.actions.domain import ActionError
from app.modules.actions.schemas import (
    ActionListOut,
    ActionOut,
    ActionStatusUpdate,
    ActionUpdate,
)
from app.modules.actions.services import (
    action_payload,
    get_asset_action,
    list_asset_actions,
    update_action_assignment,
    update_action_status,
)
from app.modules.assets.services import AssetAccessError, get_asset
from app.modules.identity.domain import AuthorizationContext
from app.modules.organizations.domain import permission_granted


router = APIRouter(tags=["actions"])


def _error(exc: Exception) -> HTTPException:
    code = getattr(exc, "code", "invalid_action")
    if code in {"action_not_found", "asset_not_found"}:
        return HTTPException(status_code=404, detail=str(exc))
    if code in {
        "version_conflict",
        "invalid_transition",
        "action_closed",
        "outcome_required",
        "invalid_outcome",
    }:
        return HTTPException(status_code=409, detail=str(exc))
    if code.endswith("denied") or code == "workspace_required":
        return HTTPException(status_code=403, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


def _asset(
    db: Session,
    context: AuthorizationContext,
    asset_id: str,
    *,
    write: bool,
) -> Asset:
    return get_asset(
        db,
        context=context,
        asset_id=asset_id,
        permission="asset:update" if write else "asset:read",
    )


def _row_asset(
    db: Session,
    context: AuthorizationContext,
    action_id: str,
    *,
    write: bool,
) -> tuple[Asset, Action]:
    row = db.get(Action, action_id)
    if row is None:
        raise ActionError("action_not_found", "Action was not found")
    asset = _asset(db, context, row.asset_id, write=write)
    return asset, get_asset_action(db, asset=asset, action_id=action_id)


@router.get("/assets/{asset_id}/actions", response_model=ActionListOut)
def asset_actions(
    asset_id: str,
    status: Literal["OPEN", "IN_PROGRESS", "COMPLETED", "DISMISSED", "CANCELLED"]
    | None = None,
    assigned_to_user_id: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    try:
        asset = _asset(db, context, asset_id, write=False)
        rows = list_asset_actions(
            db,
            asset=asset,
            status=status,
            assigned_to_user_id=assigned_to_user_id,
            limit=limit,
        )
        return {"items": [action_payload(row) for row in rows], "total": len(rows)}
    except (ActionError, AssetAccessError, ValueError) as exc:
        raise _error(exc) from exc


@router.get("/actions", response_model=ActionListOut)
def workspace_actions(
    asset_id: str | None = None,
    status: Literal["OPEN", "IN_PROGRESS", "COMPLETED", "DISMISSED", "CANCELLED"]
    | None = None,
    assigned_to_me: bool = False,
    limit: int = Query(100, ge=1, le=500),
    user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    if (
        not context.active_organization_id
        or not context.active_workspace_id
        or not permission_granted(context.permissions, "asset:read")
    ):
        raise HTTPException(status_code=403, detail="Workspace action access denied")
    query = db.query(Action).filter(
        Action.organization_id == context.active_organization_id,
        Action.workspace_id == context.active_workspace_id,
    )
    if asset_id:
        try:
            _asset(db, context, asset_id, write=False)
        except (ActionError, AssetAccessError, ValueError) as exc:
            raise _error(exc) from exc
        query = query.filter(Action.asset_id == asset_id)
    if status:
        query = query.filter(Action.status == status)
    if assigned_to_me:
        query = query.filter(Action.assigned_to_user_id == user.id)
    total = query.count()
    rows = query.order_by(Action.due_date, Action.created_at.desc()).limit(limit).all()
    return {"items": [action_payload(row) for row in rows], "total": total}


@router.get("/actions/{action_id}", response_model=ActionOut)
def action_read(
    action_id: str,
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    try:
        _, row = _row_asset(db, context, action_id, write=False)
        return action_payload(row)
    except (ActionError, AssetAccessError, ValueError) as exc:
        raise _error(exc) from exc


@router.patch("/actions/{action_id}/status", response_model=ActionOut)
def action_status_change(
    action_id: str,
    payload: ActionStatusUpdate,
    user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    try:
        _, row = _row_asset(db, context, action_id, write=True)
        update_action_status(
            db,
            action=row,
            actor=user,
            target=payload.status.value,
            expected_version=payload.expected_version,
            outcome=payload.outcome,
        )
        db.commit()
        db.refresh(row)
        return action_payload(row)
    except (ActionError, AssetAccessError, ValueError) as exc:
        db.rollback()
        raise _error(exc) from exc


@router.patch("/actions/{action_id}", response_model=ActionOut)
def action_assignment_change(
    action_id: str,
    payload: ActionUpdate,
    user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    try:
        asset, row = _row_asset(db, context, action_id, write=True)
        update_action_assignment(
            db,
            asset=asset,
            action=row,
            actor=user,
            expected_version=payload.expected_version,
            assigned_to_user_id=payload.assigned_to_user_id,
            due_date=payload.due_date,
        )
        db.commit()
        db.refresh(row)
        return action_payload(row)
    except (ActionError, AssetAccessError, ValueError) as exc:
        db.rollback()
        raise _error(exc) from exc


__all__ = ["router"]
