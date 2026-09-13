"""Server-owned navigation and aggregate queues for internal Operations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
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
from app.modules.operations.experience_services import internal_actor_contract
from app.modules.operations.provider_readiness import provider_inventory, public_provider_check
from app.core.config import settings


router = APIRouter(prefix="/operations", tags=["operations-experience"])


def _require_integration_admin(db: Session, actor: User) -> None:
    _, _, capabilities = internal_actor_contract(db, actor)
    if "integrations" not in capabilities:
        raise HTTPException(status_code=403, detail="Integration administrator required")


@router.get("/providers")
def integration_provider_inventory(actor: InternalActor, db: Session = Depends(get_db)):
    _require_integration_admin(db, actor)
    return provider_inventory(settings)


@router.post("/providers/{provider}/check")
async def check_public_integration(provider: str, request: Request, actor: InternalActor,
                                   db: Session = Depends(get_db)):
    _require_integration_admin(db, actor)
    if request.query_params:
        raise HTTPException(status_code=400, detail="This check accepts no configuration or customer data")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 2:
            raise HTTPException(status_code=400, detail="This check accepts no configuration or customer data")
        body.extend(chunk)
    if body not in (b"", b"{}"):
        raise HTTPException(status_code=400, detail="This check accepts no configuration or customer data")
    if provider not in {"copernicus", "miteco"}:
        raise HTTPException(status_code=404, detail="Public provider check not available")
    from starlette.concurrency import run_in_threadpool
    try:
        return await run_in_threadpool(public_provider_check, provider, settings)
    except ValueError:
        raise HTTPException(status_code=409, detail="Check unavailable; verify provider selection and wait 30 seconds between checks") from None


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
