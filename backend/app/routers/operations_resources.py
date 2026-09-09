"""GeoVision-only resource registry and least-privilege contractor access."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import ContractorAssignment, OperationalCapability, OperationsContractor, User
from app.modules.operations.domain import OperationsResourceError
from app.modules.operations.schemas import (
    AssignmentCreate,
    AssignmentDecision,
    AssignmentInternalOut,
    AssignmentRestrictedOut,
    AssignmentUpdate,
    CapabilityCreate,
    CapabilityOut,
    CapabilityUpdate,
    ContractorCreate,
    ContractorInternalOut,
    ContractorSelfProfileOut,
    ContractorUpdate,
)
from app.modules.operations.services import (
    assignment_internal,
    assignment_restricted,
    capability_out,
    contractor_for_user,
    contractor_internal,
    contractor_self_profile,
    create_assignment,
    create_capability,
    create_contractor,
    deactivate_contractor,
    decide_assignment,
    list_contractors,
    update_assignment,
    update_capability,
    update_contractor,
)
from app.modules.organizations.domain import internal_permissions
from app.modules.organizations.services import active_internal_roles


router = APIRouter(prefix="/operations", tags=["operations-resources"])


def require_operations_staff(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    permissions = internal_permissions(active_internal_roles(db, user))
    if not permissions.intersection({"platform:admin", "operations:access"}):
        raise HTTPException(status_code=403, detail="GeoVision Operations permission required")
    return user


OperationsStaff = Annotated[User, Depends(require_operations_staff)]


def _raise_resource_error(exc: OperationsResourceError) -> None:
    status_code = {
        "capability_not_found": status.HTTP_404_NOT_FOUND,
        "contractor_not_found": status.HTTP_404_NOT_FOUND,
        "order_not_found": status.HTTP_404_NOT_FOUND,
        "assignment_not_found": status.HTTP_404_NOT_FOUND,
        "contractor_access_denied": status.HTTP_403_FORBIDDEN,
        "capability_exists": status.HTTP_409_CONFLICT,
        "contractor_exists": status.HTTP_409_CONFLICT,
        "contractor_user_exists": status.HTTP_409_CONFLICT,
        "version_conflict": status.HTTP_409_CONFLICT,
        "invalid_assignment_transition": status.HTTP_409_CONFLICT,
    }.get(exc.code, status.HTTP_422_UNPROCESSABLE_ENTITY)
    raise HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": str(exc)},
    ) from exc


@router.get("/contractor/me/profile", response_model=ContractorSelfProfileOut)
def my_contractor_profile(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return contractor_self_profile(contractor_for_user(db, user))
    except OperationsResourceError as exc:
        _raise_resource_error(exc)


@router.get(
    "/contractor/me/assignments", response_model=list[AssignmentRestrictedOut]
)
def my_assignments(
    assignment_status: str | None = Query(default=None, alias="status", max_length=20),
    limit: int = Query(default=100, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        contractor = contractor_for_user(db, user)
    except OperationsResourceError as exc:
        _raise_resource_error(exc)
    query = db.query(ContractorAssignment).filter(
        ContractorAssignment.contractor_id == contractor.id
    )
    if assignment_status:
        query = query.filter(ContractorAssignment.status == assignment_status.upper())
    rows = (
        query.order_by(ContractorAssignment.created_at.desc(), ContractorAssignment.id.desc())
        .limit(limit)
        .all()
    )
    return [assignment_restricted(row) for row in rows]


@router.get(
    "/contractor/me/assignments/{assignment_id}",
    response_model=AssignmentRestrictedOut,
)
def my_assignment(
    assignment_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        contractor = contractor_for_user(db, user)
    except OperationsResourceError as exc:
        _raise_resource_error(exc)
    assignment = db.get(ContractorAssignment, assignment_id)
    if assignment is None or assignment.contractor_id != contractor.id:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return assignment_restricted(assignment)


@router.post(
    "/contractor/me/assignments/{assignment_id}/decision",
    response_model=AssignmentRestrictedOut,
)
def decide_my_assignment(
    assignment_id: str,
    data: AssignmentDecision,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        contractor = contractor_for_user(db, user)
        assignment = db.get(ContractorAssignment, assignment_id)
        if assignment is None:
            raise OperationsResourceError("assignment_not_found", "Assignment was not found")
        decide_assignment(
            db,
            actor=user,
            contractor=contractor,
            assignment=assignment,
            decision=data.decision,
            expected_version=data.expected_version,
        )
        db.commit()
        db.refresh(assignment)
        return assignment_restricted(assignment)
    except OperationsResourceError as exc:
        db.rollback()
        _raise_resource_error(exc)


@router.get("/capabilities", response_model=list[CapabilityOut])
def staff_capabilities(
    actor: OperationsStaff,
    category: str | None = Query(default=None, max_length=50),
    include_inactive: bool = False,
    db: Session = Depends(get_db),
):
    del actor
    query = db.query(OperationalCapability)
    if category:
        query = query.filter(OperationalCapability.category == category.upper())
    if not include_inactive:
        query = query.filter(OperationalCapability.is_active.is_(True))
    rows = query.order_by(OperationalCapability.category, OperationalCapability.code).all()
    return [capability_out(row) for row in rows]


@router.post(
    "/capabilities", response_model=CapabilityOut, status_code=status.HTTP_201_CREATED
)
def staff_create_capability(
    data: CapabilityCreate,
    actor: OperationsStaff,
    db: Session = Depends(get_db),
):
    try:
        row = create_capability(db, actor=actor, data=data)
        db.commit()
        db.refresh(row)
        return capability_out(row)
    except OperationsResourceError as exc:
        db.rollback()
        _raise_resource_error(exc)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Capability conflicts with existing data") from exc


@router.patch("/capabilities/{capability_id}", response_model=CapabilityOut)
def staff_update_capability(
    capability_id: str,
    data: CapabilityUpdate,
    actor: OperationsStaff,
    db: Session = Depends(get_db),
):
    row = db.get(OperationalCapability, capability_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Capability not found")
    try:
        update_capability(db, actor=actor, capability=row, data=data)
        db.commit()
        db.refresh(row)
        return capability_out(row)
    except OperationsResourceError as exc:
        db.rollback()
        _raise_resource_error(exc)


@router.get("/contractors", response_model=list[ContractorInternalOut])
def staff_contractors(
    actor: OperationsStaff,
    search: str | None = Query(default=None, max_length=200),
    country_code: str | None = Query(default=None, min_length=2, max_length=2),
    region: str | None = Query(default=None, max_length=120),
    capability: str | None = Query(default=None, max_length=80),
    sector: str | None = Query(default=None, max_length=80),
    resource_type: str | None = Query(default=None, max_length=50),
    availability: str | None = Query(default=None, max_length=20),
    contractor_status: str | None = Query(default=None, alias="status", max_length=20),
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
):
    del actor
    if capability and sector:
        raise HTTPException(status_code=422, detail="Use capability or sector, not both")
    rows = list_contractors(
        db,
        search=search,
        country_code=country_code,
        region=region,
        capability=capability or sector,
        resource_type=resource_type,
        availability=availability,
        status=contractor_status,
        limit=limit,
    )
    return [contractor_internal(row) for row in rows]


@router.post(
    "/contractors",
    response_model=ContractorInternalOut,
    status_code=status.HTTP_201_CREATED,
)
def staff_create_contractor(
    data: ContractorCreate,
    actor: OperationsStaff,
    db: Session = Depends(get_db),
):
    try:
        row = create_contractor(db, actor=actor, data=data)
        db.commit()
        db.refresh(row)
        return contractor_internal(row)
    except OperationsResourceError as exc:
        db.rollback()
        _raise_resource_error(exc)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Contractor conflicts with existing data") from exc


@router.get("/contractors/{contractor_id}", response_model=ContractorInternalOut)
def staff_contractor(
    contractor_id: str,
    actor: OperationsStaff,
    db: Session = Depends(get_db),
):
    del actor
    row = db.get(OperationsContractor, contractor_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Contractor not found")
    return contractor_internal(row)


@router.patch("/contractors/{contractor_id}", response_model=ContractorInternalOut)
def staff_update_contractor(
    contractor_id: str,
    data: ContractorUpdate,
    actor: OperationsStaff,
    db: Session = Depends(get_db),
):
    row = db.get(OperationsContractor, contractor_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Contractor not found")
    try:
        update_contractor(db, actor=actor, contractor=row, data=data)
        db.commit()
        db.refresh(row)
        return contractor_internal(row)
    except OperationsResourceError as exc:
        db.rollback()
        _raise_resource_error(exc)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Contractor update conflicts") from exc


@router.delete("/contractors/{contractor_id}", status_code=status.HTTP_204_NO_CONTENT)
def staff_deactivate_contractor(
    contractor_id: str,
    actor: OperationsStaff,
    db: Session = Depends(get_db),
):
    row = db.get(OperationsContractor, contractor_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Contractor not found")
    deactivate_contractor(db, actor=actor, contractor=row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/assignments", response_model=list[AssignmentInternalOut])
def staff_assignments(
    actor: OperationsStaff,
    contractor_id: str | None = Query(default=None, max_length=36),
    assignment_status: str | None = Query(default=None, alias="status", max_length=20),
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
):
    del actor
    query = db.query(ContractorAssignment)
    if contractor_id:
        query = query.filter(ContractorAssignment.contractor_id == contractor_id)
    if assignment_status:
        query = query.filter(ContractorAssignment.status == assignment_status.upper())
    rows = (
        query.order_by(ContractorAssignment.created_at.desc(), ContractorAssignment.id.desc())
        .limit(limit)
        .all()
    )
    return [assignment_internal(row) for row in rows]


@router.post(
    "/assignments",
    response_model=AssignmentInternalOut,
    status_code=status.HTTP_201_CREATED,
)
def staff_create_assignment(
    data: AssignmentCreate,
    actor: OperationsStaff,
    db: Session = Depends(get_db),
):
    try:
        row = create_assignment(db, actor=actor, data=data)
        db.commit()
        db.refresh(row)
        return assignment_internal(row)
    except OperationsResourceError as exc:
        db.rollback()
        _raise_resource_error(exc)


@router.get("/assignments/{assignment_id}", response_model=AssignmentInternalOut)
def staff_assignment(
    assignment_id: str,
    actor: OperationsStaff,
    db: Session = Depends(get_db),
):
    del actor
    row = db.get(ContractorAssignment, assignment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return assignment_internal(row)


@router.patch("/assignments/{assignment_id}", response_model=AssignmentInternalOut)
def staff_update_assignment(
    assignment_id: str,
    data: AssignmentUpdate,
    actor: OperationsStaff,
    db: Session = Depends(get_db),
):
    row = db.get(ContractorAssignment, assignment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    try:
        update_assignment(db, actor=actor, assignment=row, data=data)
        db.commit()
        db.refresh(row)
        return assignment_internal(row)
    except OperationsResourceError as exc:
        db.rollback()
        _raise_resource_error(exc)


__all__ = ["router"]
