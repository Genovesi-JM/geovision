"""Authorization dependency shared by operations transport adapters."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import User
from app.modules.organizations.domain import internal_permissions
from app.modules.organizations.services import active_internal_roles


def require_operations_staff(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    permissions = internal_permissions(active_internal_roles(db, user))
    if not permissions.intersection({"platform:admin", "operations:access"}):
        raise HTTPException(status_code=403, detail="GeoVision Operations permission required")
    return user


def require_internal_actor(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Admit any persisted GeoVision staff role to its filtered experience."""

    if not active_internal_roles(db, user):
        raise HTTPException(status_code=403, detail="GeoVision internal role required")
    return user


OperationsStaff = Annotated[User, Depends(require_operations_staff)]
InternalActor = Annotated[User, Depends(require_internal_actor)]


__all__ = [
    "InternalActor",
    "OperationsStaff",
    "require_internal_actor",
    "require_operations_staff",
]
