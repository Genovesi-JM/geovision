"""Authorization dependencies for private financial telemetry."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import User
from app.modules.organizations.domain import internal_permissions
from app.modules.organizations.services import active_internal_roles


def _permissions(db: Session, user: User) -> frozenset[str]:
    return internal_permissions(active_internal_roles(db, user))


def require_economics_recorder(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    if not _permissions(db, user).intersection(
        {"platform:admin", "billing:internal", "operations:access"}
    ):
        raise HTTPException(status_code=403, detail="GeoVision cost-recording permission required")
    return user


def require_economics_viewer(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    if not _permissions(db, user).intersection({"platform:admin", "billing:internal"}):
        raise HTTPException(status_code=403, detail="GeoVision finance permission required")
    return user


EconomicsRecorder = Annotated[User, Depends(require_economics_recorder)]
EconomicsViewer = Annotated[User, Depends(require_economics_viewer)]


__all__ = [
    "EconomicsRecorder",
    "EconomicsViewer",
    "require_economics_recorder",
    "require_economics_viewer",
]
