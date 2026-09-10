"""Server-owned navigation and aggregate queues for internal Operations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import User
from app.modules.operations.auth import InternalActor
from app.modules.operations.domain import OperationsResourceError
from app.modules.operations.experience_schemas import (
    ContractorExperienceOut,
    OperationsDashboardOut,
    OperationsExperienceOut,
    OperationsQueuesOut,
)
from app.modules.operations.experience_services import (
    contractor_experience,
    operations_dashboard,
    operations_experience,
    operations_queues,
)
from app.modules.operations.services import contractor_for_user


router = APIRouter(prefix="/operations", tags=["operations-experience"])


@router.get("/experience", response_model=OperationsExperienceOut)
def internal_operations_experience(
    actor: InternalActor,
    db: Session = Depends(get_db),
) -> OperationsExperienceOut:
    return operations_experience(db, actor)


@router.get("/dashboard", response_model=OperationsDashboardOut)
def internal_operations_dashboard(
    actor: InternalActor,
    db: Session = Depends(get_db),
) -> OperationsDashboardOut:
    return operations_dashboard(db, actor)


@router.get("/queues", response_model=OperationsQueuesOut)
def internal_operations_queues(
    actor: InternalActor,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> OperationsQueuesOut:
    return operations_queues(db, actor, limit=limit)


@router.get(
    "/contractor/me/experience",
    response_model=ContractorExperienceOut,
)
def contractor_operations_experience(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContractorExperienceOut:
    try:
        contractor = contractor_for_user(db, user)
    except OperationsResourceError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    return contractor_experience(db, contractor)


__all__ = ["router"]
