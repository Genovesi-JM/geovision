"""Internal acquisition authorization dependency."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import User
from app.modules.organizations.domain import internal_permissions
from app.modules.organizations.services import active_internal_roles


def require_mission_staff(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    permissions = internal_permissions(active_internal_roles(db, user))
    if not permissions.intersection(
        {"platform:admin", "operations:access", "analytics:review"}
    ):
        raise HTTPException(status_code=403, detail="GeoVision mission staff permission required")
    return user


MissionStaff = Annotated[User, Depends(require_mission_staff)]


__all__ = ["MissionStaff", "require_mission_staff"]
