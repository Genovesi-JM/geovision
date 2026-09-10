"""Internal GeoVision Operations API for durable processing jobs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.deps import get_db
from app.integrations.processing import create_processing_provider
from app.models import ProcessingJob
from app.modules.operations.auth import OperationsStaff
from app.modules.processing.domain import ProcessingJobError
from app.modules.processing.schemas import (
    ProcessingJobCancel,
    ProcessingJobCreate,
    ProcessingJobOut,
    ProcessingJobRetry,
)
from app.modules.processing.services import (
    cancel_processing_job,
    create_processing_job,
    list_processing_jobs,
    processing_job_out,
    retry_processing_job,
)


router = APIRouter(prefix="/processing", tags=["processing"])


def _raise_processing_error(exc: ProcessingJobError) -> None:
    if exc.code in {
        "source_dataset_not_found",
        "fulfilment_job_not_found",
        "processing_job_not_found",
    }:
        code = status.HTTP_404_NOT_FOUND
    elif exc.code in {
        "version_conflict",
        "idempotency_conflict",
        "processing_retry_not_allowed",
        "processing_cancel_not_allowed",
    }:
        code = status.HTTP_409_CONFLICT
    elif exc.code in {
        "provider_cancel_failed",
        "provider_unavailable",
        "timeout",
    } or exc.retryable:
        code = status.HTTP_502_BAD_GATEWAY
    else:
        code = status.HTTP_422_UNPROCESSABLE_ENTITY
    raise HTTPException(
        status_code=code,
        detail={"code": exc.code, "message": str(exc)},
    ) from exc


@router.get("/jobs", response_model=list[ProcessingJobOut])
def processing_jobs(
    actor: OperationsStaff,
    organization_id: str | None = Query(default=None, max_length=36),
    asset_id: str | None = Query(default=None, max_length=36),
    job_status: str | None = Query(default=None, alias="status", max_length=30),
    provider: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
):
    del actor
    rows = list_processing_jobs(
        db,
        organization_id=organization_id,
        asset_id=asset_id,
        status=job_status,
        provider=provider,
        limit=limit,
    )
    return [processing_job_out(row) for row in rows]


@router.post(
    "/jobs", response_model=ProcessingJobOut, status_code=status.HTTP_201_CREATED
)
def request_processing_job(
    data: ProcessingJobCreate,
    actor: OperationsStaff,
    db: Session = Depends(get_db),
):
    try:
        row = create_processing_job(db, data=data, actor=actor)
        db.commit()
        db.refresh(row)
        return processing_job_out(row)
    except ProcessingJobError as exc:
        db.rollback()
        _raise_processing_error(exc)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Processing request conflicts with existing data"
        ) from exc


@router.get("/jobs/{job_id}", response_model=ProcessingJobOut)
def processing_job(
    job_id: str,
    actor: OperationsStaff,
    db: Session = Depends(get_db),
):
    del actor
    row = db.get(ProcessingJob, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Processing job not found")
    return processing_job_out(row)


@router.post("/jobs/{job_id}/retry", response_model=ProcessingJobOut)
def retry_job(
    job_id: str,
    data: ProcessingJobRetry,
    actor: OperationsStaff,
    db: Session = Depends(get_db),
):
    row = db.get(ProcessingJob, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Processing job not found")
    try:
        retry_processing_job(
            db,
            job=row,
            actor=actor,
            expected_version=data.expected_version,
            provider_code=data.provider,
        )
        db.commit()
        db.refresh(row)
        return processing_job_out(row)
    except ProcessingJobError as exc:
        db.rollback()
        _raise_processing_error(exc)


@router.post("/jobs/{job_id}/cancel", response_model=ProcessingJobOut)
def cancel_job(
    job_id: str,
    data: ProcessingJobCancel,
    actor: OperationsStaff,
    db: Session = Depends(get_db),
):
    row = db.get(ProcessingJob, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Processing job not found")
    provider = create_processing_provider(provider_name=row.provider_code)
    try:
        cancel_processing_job(
            db,
            job=row,
            actor=actor,
            provider=provider,
            expected_version=data.expected_version,
        )
        db.commit()
        db.refresh(row)
        return processing_job_out(row)
    except ProcessingJobError as exc:
        db.rollback()
        _raise_processing_error(exc)
    finally:
        client = getattr(provider, "client", None)
        close = getattr(client, "close", None)
        if callable(close):
            close()


__all__ = ["router"]
