"""Internal fulfilment queue and least-privilege contractor job API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import FulfilmentJob, Order, User
from app.modules.operations.domain import OperationsResourceError
from app.modules.operations.auth import OperationsStaff
from app.modules.operations.job_schemas import (
    JobAssignmentUpdate,
    JobCreate,
    JobDependencyCreate,
    JobInternalOut,
    JobPlanOut,
    JobRestrictedOut,
    JobScheduleUpdate,
    JobStateUpdate,
)
from app.modules.operations.job_services import (
    add_dependency,
    assign_job,
    contractor_jobs,
    create_job,
    job_internal,
    job_restricted,
    list_jobs,
    plan_order_jobs,
    schedule_job,
    transition_job,
)
from app.modules.operations.services import contractor_for_user


router = APIRouter(prefix="/operations", tags=["fulfilment-jobs"])


_NOT_FOUND = {
    "order_not_found",
    "order_item_not_found",
    "asset_not_found",
    "job_not_found",
    "contractor_not_found",
    "assignee_not_found",
}
_CONFLICT = {
    "version_conflict",
    "invalid_job_transition",
    "dependency_incomplete",
    "dependency_cycle",
    "cross_order_dependency",
    "job_already_started",
    "job_assignment_locked",
    "job_schedule_locked",
}


def _raise_job_error(exc: OperationsResourceError) -> None:
    if exc.code in _NOT_FOUND:
        code = status.HTTP_404_NOT_FOUND
    elif exc.code == "contractor_access_denied":
        code = status.HTTP_403_FORBIDDEN
    elif exc.code in _CONFLICT:
        code = status.HTTP_409_CONFLICT
    else:
        code = status.HTTP_422_UNPROCESSABLE_ENTITY
    raise HTTPException(
        status_code=code,
        detail={"code": exc.code, "message": str(exc)},
    ) from exc


@router.get("/contractor/me/jobs", response_model=list[JobRestrictedOut])
def my_jobs(
    limit: int = Query(default=100, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        contractor = contractor_for_user(db, user)
    except OperationsResourceError as exc:
        _raise_job_error(exc)
    return [job_restricted(row) for row in contractor_jobs(db, contractor.id, limit=limit)]


@router.get("/contractor/me/jobs/{job_id}", response_model=JobRestrictedOut)
def my_job(
    job_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        contractor = contractor_for_user(db, user)
    except OperationsResourceError as exc:
        _raise_job_error(exc)
    row = db.get(FulfilmentJob, job_id)
    if row is None or row.assigned_contractor_id != contractor.id:
        raise HTTPException(status_code=404, detail="Job not found")
    return job_restricted(row)


@router.get("/jobs", response_model=list[JobInternalOut])
def staff_jobs(
    actor: OperationsStaff,
    order_id: str | None = Query(default=None, max_length=36),
    job_state: str | None = Query(default=None, alias="state", max_length=30),
    job_type: str | None = Query(default=None, max_length=80),
    contractor_id: str | None = Query(default=None, max_length=36),
    assigned_user_id: str | None = Query(default=None, max_length=36),
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
):
    del actor
    rows = list_jobs(
        db,
        order_id=order_id,
        job_state=job_state,
        job_type=job_type,
        contractor_id=contractor_id,
        assigned_user_id=assigned_user_id,
        limit=limit,
    )
    return [job_internal(db, row) for row in rows]


@router.post(
    "/jobs", response_model=JobInternalOut, status_code=status.HTTP_201_CREATED
)
def staff_create_job(
    data: JobCreate,
    actor: OperationsStaff,
    db: Session = Depends(get_db),
):
    try:
        row = create_job(db, actor=actor, data=data)
        db.commit()
        db.refresh(row)
        return job_internal(db, row)
    except OperationsResourceError as exc:
        db.rollback()
        _raise_job_error(exc)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Job conflicts with existing data") from exc


@router.post("/jobs/plan-order/{order_id}", response_model=JobPlanOut)
def staff_plan_order(
    order_id: str,
    actor: OperationsStaff,
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(Order.id == order_id).with_for_update().one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    try:
        jobs, created_count, existing_count = plan_order_jobs(db, actor=actor, order=order)
        db.commit()
        for row in jobs:
            db.refresh(row)
        return {
            "order_id": order.id,
            "created_count": created_count,
            "existing_count": existing_count,
            "jobs": [job_internal(db, row) for row in jobs],
        }
    except OperationsResourceError as exc:
        db.rollback()
        _raise_job_error(exc)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Order planning conflict") from exc


@router.get("/jobs/{job_id}", response_model=JobInternalOut)
def staff_job(
    job_id: str,
    actor: OperationsStaff,
    db: Session = Depends(get_db),
):
    del actor
    row = db.get(FulfilmentJob, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job_internal(db, row)


@router.post(
    "/jobs/{job_id}/dependencies",
    response_model=JobInternalOut,
    status_code=status.HTTP_201_CREATED,
)
def staff_add_dependency(
    job_id: str,
    data: JobDependencyCreate,
    actor: OperationsStaff,
    db: Session = Depends(get_db),
):
    job = db.get(FulfilmentJob, job_id)
    upstream = db.get(FulfilmentJob, data.depends_on_job_id)
    if job is None or upstream is None:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        add_dependency(db, actor=actor, job=job, upstream=upstream)
        db.commit()
        db.refresh(job)
        return job_internal(db, job)
    except OperationsResourceError as exc:
        db.rollback()
        _raise_job_error(exc)


@router.patch("/jobs/{job_id}/assignment", response_model=JobInternalOut)
def staff_assign_job(
    job_id: str,
    data: JobAssignmentUpdate,
    actor: OperationsStaff,
    db: Session = Depends(get_db),
):
    job = db.query(FulfilmentJob).filter(FulfilmentJob.id == job_id).with_for_update().one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        assign_job(db, actor=actor, job=job, data=data)
        db.commit()
        db.refresh(job)
        return job_internal(db, job)
    except OperationsResourceError as exc:
        db.rollback()
        _raise_job_error(exc)


@router.patch("/jobs/{job_id}/schedule", response_model=JobInternalOut)
def staff_schedule_job(
    job_id: str,
    data: JobScheduleUpdate,
    actor: OperationsStaff,
    db: Session = Depends(get_db),
):
    job = db.query(FulfilmentJob).filter(FulfilmentJob.id == job_id).with_for_update().one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        schedule_job(db, actor=actor, job=job, data=data)
        db.commit()
        db.refresh(job)
        return job_internal(db, job)
    except OperationsResourceError as exc:
        db.rollback()
        _raise_job_error(exc)


@router.patch("/jobs/{job_id}/state", response_model=JobInternalOut)
def staff_transition_job(
    job_id: str,
    data: JobStateUpdate,
    actor: OperationsStaff,
    db: Session = Depends(get_db),
):
    job = db.query(FulfilmentJob).filter(FulfilmentJob.id == job_id).with_for_update().one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        transition_job(db, actor=actor, job=job, data=data)
        db.commit()
        db.refresh(job)
        return job_internal(db, job)
    except OperationsResourceError as exc:
        db.rollback()
        _raise_job_error(exc)


__all__ = ["router"]
