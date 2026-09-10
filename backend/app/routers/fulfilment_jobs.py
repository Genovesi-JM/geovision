"""Internal fulfilment queue and least-privilege contractor job API."""

from __future__ import annotations

import tempfile

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.deps import get_current_user, get_db
from app.models import FulfilmentJob, Order, User
from app.modules.operations.auth import OperationsStaff
from app.modules.operations.domain import OperationsResourceError
from app.modules.operations.job_schemas import (
    ContractorJobDetailOut,
    ContractorJobStateUpdate,
    ContractorUploadComplete,
    ContractorUploadInitiate,
    ContractorUploadInitiatedOut,
    ContractorUploadReceiptOut,
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
    confirm_contractor_upload,
    contractor_assigned_job,
    contractor_job_detail,
    contractor_job_restricted,
    contractor_jobs,
    contractor_local_upload_file,
    create_job,
    job_internal,
    job_restricted,
    list_jobs,
    plan_order_jobs,
    reserve_contractor_upload,
    schedule_job,
    transition_contractor_job,
    transition_job,
)
from app.modules.datasets.domain import DatasetError, validate_upload
from app.modules.operations.services import contractor_for_user
from app.services.storage import StorageService, get_storage_service


router = APIRouter(prefix="/operations", tags=["fulfilment-jobs"])


_NOT_FOUND = {
    "order_not_found",
    "order_item_not_found",
    "asset_not_found",
    "job_not_found",
    "contractor_not_found",
    "assignee_not_found",
    "upload_target_not_found",
    "upload_reference_not_found",
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
    "accepted_assignment_required",
    "contractor_transition_denied",
    "job_upload_locked",
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


def _raise_upload_error(exc: DatasetError) -> None:
    if exc.code in {"upload_not_found", "file_not_found"}:
        code = status.HTTP_404_NOT_FOUND
    elif exc.code == "file_too_large":
        code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    elif exc.code == "upload_expired":
        code = status.HTTP_410_GONE
    elif exc.code in {"dataset_archived", "storage_provider_mismatch"}:
        code = status.HTTP_409_CONFLICT
    elif exc.code == "upload_missing":
        code = status.HTTP_400_BAD_REQUEST
    else:
        code = status.HTTP_422_UNPROCESSABLE_ENTITY
    raise HTTPException(
        status_code=code,
        detail={"code": exc.code, "message": str(exc)},
    ) from exc


def _storage() -> StorageService:
    return get_storage_service()


@router.put(
    "/contractor/uploads/local",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def put_contractor_local_upload(
    request: Request,
    key: str = Query(..., min_length=1, max_length=2_000),
    expires: int = Query(..., ge=1),
    upload: bool = Query(...),
    signature: str = Query(..., min_length=64, max_length=64),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(_storage),
):
    """Local-dev equivalent of a provider-signed direct object PUT."""

    provider = storage.provider
    validator = getattr(provider, "validate_signature", None)
    if storage.provider_name != "local" or not callable(validator):
        raise HTTPException(status_code=404, detail="Local storage is unavailable")
    if not upload or not validator(
        key=key,
        expires=expires,
        for_upload=True,
        signature=signature,
    ):
        raise HTTPException(status_code=403, detail="Upload URL is invalid or expired")
    try:
        reserved = contractor_local_upload_file(db, storage_key=key)
        size_bytes = 0
        with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as stream:
            async for chunk in request.stream():
                size_bytes += len(chunk)
                if size_bytes > settings.dataset_signed_upload_max_bytes:
                    raise DatasetError(
                        "file_too_large", "Signed upload exceeds its size limit"
                    )
                stream.write(chunk)
            validate_upload(
                filename=reserved.filename,
                content_type=request.headers.get("content-type") or reserved.mime_type,
                size_bytes=size_bytes,
                max_size_bytes=settings.dataset_signed_upload_max_bytes,
            )
            if reserved.file_size != size_bytes:
                raise DatasetError(
                    "file_size_mismatch",
                    "Uploaded file size does not match reservation",
                )
            stream.seek(0)
            stored_key, actual_size, _, _ = storage.upload_file(
                stream,
                key,
                request.headers.get("content-type") or reserved.mime_type,
                {"dataset_id": reserved.dataset_id, "file_id": reserved.id},
            )
            if stored_key != key or actual_size != size_bytes:
                raise RuntimeError("Local object storage returned an invalid receipt")
    except OperationsResourceError as exc:
        _raise_job_error(exc)
    except DatasetError as exc:
        _raise_upload_error(exc)
    except (RuntimeError, SQLAlchemyError) as exc:
        raise HTTPException(status_code=502, detail="Object upload failed") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    return [
        contractor_job_restricted(row)
        for row in contractor_jobs(db, contractor.id, limit=limit)
    ]


@router.get("/contractor/me/jobs/{job_id}", response_model=ContractorJobDetailOut)
def my_job(
    job_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        contractor = contractor_for_user(db, user)
    except OperationsResourceError as exc:
        _raise_job_error(exc)
    try:
        row = contractor_assigned_job(
            db,
            contractor_id=contractor.id,
            job_id=job_id,
        )
        return contractor_job_detail(
            db,
            contractor_id=contractor.id,
            job=row,
        )
    except OperationsResourceError as exc:
        _raise_job_error(exc)


@router.patch(
    "/contractor/me/jobs/{job_id}/state",
    response_model=ContractorJobDetailOut,
)
def transition_my_job(
    job_id: str,
    data: ContractorJobStateUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        contractor = contractor_for_user(db, user)
        row = (
            db.query(FulfilmentJob)
            .filter(FulfilmentJob.id == job_id)
            .with_for_update()
            .one_or_none()
        )
        if row is None or row.assigned_contractor_id != contractor.id:
            raise OperationsResourceError("job_not_found", "Job was not found")
        transition_contractor_job(
            db,
            actor=user,
            contractor_id=contractor.id,
            job=row,
            data=data,
        )
        db.commit()
        db.refresh(row)
        return contractor_job_detail(
            db,
            contractor_id=contractor.id,
            job=row,
        )
    except OperationsResourceError as exc:
        db.rollback()
        _raise_job_error(exc)


@router.post(
    "/contractor/me/jobs/{job_id}/uploads/initiate",
    response_model=ContractorUploadInitiatedOut,
    status_code=status.HTTP_201_CREATED,
)
def initiate_my_job_upload(
    job_id: str,
    data: ContractorUploadInitiate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(_storage),
):
    try:
        contractor = contractor_for_user(db, user)
        row = contractor_assigned_job(
            db,
            contractor_id=contractor.id,
            job_id=job_id,
        )
        return reserve_contractor_upload(
            db,
            actor=user,
            contractor_id=contractor.id,
            job=row,
            data=data,
            storage=storage,
        )
    except OperationsResourceError as exc:
        db.rollback()
        _raise_job_error(exc)
    except DatasetError as exc:
        db.rollback()
        _raise_upload_error(exc)
    except (RuntimeError, SQLAlchemyError) as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail="Object upload setup failed") from exc


@router.post(
    "/contractor/me/jobs/{job_id}/uploads/complete",
    response_model=ContractorUploadReceiptOut,
)
def complete_my_job_upload(
    job_id: str,
    data: ContractorUploadComplete,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(_storage),
):
    try:
        contractor = contractor_for_user(db, user)
        row = contractor_assigned_job(
            db,
            contractor_id=contractor.id,
            job_id=job_id,
        )
        return confirm_contractor_upload(
            db,
            actor=user,
            contractor_id=contractor.id,
            job=row,
            data=data,
            storage=storage,
        )
    except OperationsResourceError as exc:
        db.rollback()
        _raise_job_error(exc)
    except DatasetError as exc:
        db.rollback()
        _raise_upload_error(exc)
    except (RuntimeError, SQLAlchemyError) as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail="Object upload confirmation failed") from exc


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
