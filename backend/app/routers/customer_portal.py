"""Customer-only web portal read APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.deps import get_authorization_context, get_current_user
from app.models import User
from app.modules.customer_portal.schemas import (
    PortalAssetSummaryOut,
    PortalExperienceOut,
    PortalMapLayersOut,
)
from app.modules.customer_portal.services import (
    CustomerPortalError,
    portal_asset_summary,
    portal_experience,
    portal_map_layers,
)
from app.modules.identity.domain import AuthorizationContext


router = APIRouter(prefix="/portal", tags=["customer-portal"])


def _error(exc: CustomerPortalError) -> HTTPException:
    code = (
        status.HTTP_404_NOT_FOUND
        if exc.code in {"asset_not_found", "workspace_not_found"}
        else status.HTTP_403_FORBIDDEN
    )
    return HTTPException(status_code=code, detail=str(exc))


@router.get("/experience", response_model=PortalExperienceOut)
def customer_portal_experience(
    user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
) -> PortalExperienceOut:
    """Return backend-owned navigation for the selected customer workspace."""

    try:
        return portal_experience(db, user=user, context=context)
    except CustomerPortalError as exc:
        raise _error(exc) from exc


@router.get("/assets/summary", response_model=PortalAssetSummaryOut)
def customer_portal_asset_summary(
    asset_id: str | None = Query(default=None, min_length=1, max_length=36),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
) -> PortalAssetSummaryOut:
    """Return one cross-sector decision summary, optionally for a subtree."""

    try:
        return portal_asset_summary(db, context=context, asset_id=asset_id)
    except CustomerPortalError as exc:
        raise _error(exc) from exc


@router.get("/map-layers", response_model=PortalMapLayersOut)
def customer_portal_map_layers(
    asset_id: str | None = Query(default=None, min_length=1, max_length=36),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
) -> PortalMapLayersOut:
    """Return standardized GeoJSON layers for the selected workspace/subtree."""

    try:
        return portal_map_layers(db, context=context, asset_id=asset_id)
    except CustomerPortalError as exc:
        raise _error(exc) from exc


__all__ = ["router"]
