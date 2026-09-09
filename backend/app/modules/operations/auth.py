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


OperationsStaff = Annotated[User, Depends(require_operations_staff)]


__all__ = ["OperationsStaff", "require_operations_staff"]
