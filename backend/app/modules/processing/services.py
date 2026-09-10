"""Restart-safe processing orchestration with injected provider and storage ports."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import uuid
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.event_names import EventNames
from app.core.integration import IntegrationResult, sanitize_integration_message
from app.core.time import utc_now
from app.models import (
    AuditLog,
    Dataset,
    DatasetFile,
    FulfilmentJob,
    Order,
    ProcessingJob,
    ProcessingJobOutput,
    ProcessingJobSource,
    User,
)
from app.modules.datasets.domain import (
    DatasetStatus,
    ProcessingLevel,
    QualityStatus,
    normalize_provider_code,
    reject_sensitive_metadata,
    validate_upload,
)
from app.modules.processing.domain import (
    PROCESSABLE_SOURCE_TYPES,
    TERMINAL_PROCESSING_STATES,
    ProcessingJobError,
    ProcessingJobState,
    normalize_requested_outputs,
)
from app.modules.processing.ports import (
    NormalizedProcessingOutput,
    ProcessingInput,
    ProcessingProvider,
    ProcessingRequest,
)
from app.modules.processing.schemas import ProcessingJobCreate
from app.services.event_outbox import enqueue_domain_event
from app.services.storage import StorageService


ProviderResolver = Callable[[str], ProcessingProvider]
_INPUT_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".tif", ".tiff"})
_NAMESPACE = uuid.UUID("58213d7f-f077-4db5-a95f-97a8c6d9c13d")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _object(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _array(value: str | None) -> list[Any]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _event(
    db: Session,
    job: ProcessingJob,
    name: str,
    key: str,
    payload: dict[str, Any] | None = None,
) -> None:
    enqueue_domain_event(
        db,
        name=name,
        aggregate_type="processing_job",
        aggregate_id=job.id,
        idempotency_key=key,
        correlation_id=job.id,
        payload={
            "processing_job_id": job.id,
            "organization_id": job.organization_id,
            "workspace_id": job.workspace_id,
            "asset_id": job.asset_id,
            "acquisition_id": job.acquisition_id,
            "fulfilment_job_id": job.fulfilment_job_id,
            "provider": job.provider_code,
            **(payload or {}),
        },
    )


def _audit(
    db: Session,
    *,
    actor: User | None,
    action: str,
    job: ProcessingJob,
    details: dict[str, Any] | None = None,
) -> None:
    if actor is None:
        return
    db.add(
        AuditLog(
            user_id=actor.id,
            user_email=actor.email,
            action=action,
            resource_type="processing_job",
            resource_id=job.id,
            details=_json(
                {
                    "organization_id": job.organization_id,
                    "provider": job.provider_code,
                    **(details or {}),
                }
            ),
        )
    )


def _source_datasets(db: Session, dataset_ids: list[str]) -> list[Dataset]:
    rows = db.query(Dataset).filter(Dataset.id.in_(dataset_ids)).all()
    by_id = {row.id: row for row in rows}
    if len(by_id) != len(dataset_ids):
        raise ProcessingJobError(
            "source_dataset_not_found", "A source dataset was not found"
        )
    return [by_id[dataset_id] for dataset_id in dataset_ids]


def _validate_source_scope(rows: list[Dataset]) -> Dataset:
    source = rows[0]
    for row in rows:
        if (
            row.company_id != source.company_id
            or row.workspace_id != source.workspace_id
            or row.asset_id != source.asset_id
        ):
            raise ProcessingJobError(
                "source_scope_mismatch",
                "All source datasets must belong to one workspace and asset",
            )
        if row.status != DatasetStatus.READY.value:
            raise ProcessingJobError(
                "source_dataset_not_ready", "Every source dataset must be ready"
            )
        if row.processing_level != ProcessingLevel.RAW.value:
            raise ProcessingJobError(
                "source_dataset_not_raw", "Processing sources must be raw datasets"
            )
        if row.dataset_type not in PROCESSABLE_SOURCE_TYPES:
            raise ProcessingJobError(
                "unsupported_source_type",
                "Processing sources must contain drone imagery",
            )
    return source


def _validate_fulfilment_link(
    db: Session,
    fulfilment_job_id: str | None,
    source: Dataset,
) -> None:
    if not fulfilment_job_id:
        return
    job = db.get(FulfilmentJob, fulfilment_job_id)
    order = db.get(Order, job.order_id) if job is not None else None
    if (
        job is None
        or order is None
        or job.job_type != "PROCESS_DATA"
        or order.company_id != source.company_id
        or (job.asset_id is not None and job.asset_id != source.asset_id)
    ):
        raise ProcessingJobError(
            "fulfilment_job_not_found",
            "Processing fulfilment job was not found for this asset",
        )


def create_processing_job(
    db: Session,
    *,
    data: ProcessingJobCreate,
    actor: User | None,
    config: Settings = settings,
) -> ProcessingJob:
    sources = _source_datasets(db, data.source_dataset_ids)
    source = _validate_source_scope(sources)
    _validate_fulfilment_link(db, data.fulfilment_job_id, source)
    outputs = normalize_requested_outputs(data.requested_outputs)
    provider = normalize_provider_code(data.provider or config.processing_provider) or "none"
    provider = {
        "deterministic": "fake",
        "opendronemap": "nodeodm",
    }.get(provider, provider)
    signature = hashlib.sha256(
        _json(
            {
                "sources": data.source_dataset_ids,
                "provider": provider,
                "outputs": outputs,
            }
        ).encode()
    ).hexdigest()
    identity = data.idempotency_key or f"processing:{source.id}:{signature}"
    existing = (
        db.query(ProcessingJob)
        .filter(ProcessingJob.idempotency_key == identity)
        .one_or_none()
    )
    if existing is not None:
        existing_sources = [
            link.dataset_id
            for link in sorted(existing.source_links, key=lambda item: item.sequence)
        ]
        if (
            existing_sources != data.source_dataset_ids
            or tuple(_array(existing.requested_outputs_json)) != outputs
            or existing.provider_code != provider
        ):
            raise ProcessingJobError(
                "idempotency_conflict",
                "Processing idempotency key is already bound to another request",
            )
        return existing

    acquisition_ids = {row.mission_id for row in sources}
    now = utc_now()
    job = ProcessingJob(
        id=str(uuid.uuid4()),
        organization_id=source.company_id,
        workspace_id=source.workspace_id,
        asset_id=source.asset_id,
        acquisition_id=(
            next(iter(acquisition_ids))
            if len(acquisition_ids) == 1 and None not in acquisition_ids
            else None
        ),
        fulfilment_job_id=data.fulfilment_job_id,
        provider_code=provider,
        requested_outputs_json=_json(outputs),
        options_json=_json(reject_sensitive_metadata(data.options, "options")),
        status=ProcessingJobState.REQUESTED.value,
        progress_percent=0.0,
        stage="queued_for_validation",
        estimated_cost_amount=data.estimated_cost_amount,
        cost_currency=data.cost_currency,
        retry_count=0,
        max_retries=(
            data.max_retries
            if data.max_retries is not None
            else config.processing_default_max_retries
        ),
        poll_count=0,
        submission_generation=0,
        next_poll_at=now,
        idempotency_key=identity,
        created_by_user_id=actor.id if actor else None,
        lifecycle_version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    for sequence, source_dataset in enumerate(sources):
        job.source_links.append(
            ProcessingJobSource(dataset_id=source_dataset.id, sequence=sequence)
        )
    _audit(
        db,
        actor=actor,
        action="processing.requested",
        job=job,
        details={"requested_outputs": list(outputs)},
    )
    _event(
        db,
        job,
        EventNames.PROCESSING_REQUESTED,
        f"processing:{job.id}:requested:0",
        {"source_dataset_ids": data.source_dataset_ids, "requested_outputs": list(outputs)},
    )
    return job


def ensure_automatic_processing_job(
    db: Session,
    *,
    dataset_id: str,
    config: Settings = settings,
) -> ProcessingJob | None:
    if not config.processing_auto_create_enabled:
        return None
    dataset = db.get(Dataset, dataset_id)
    if (
        dataset is None
        or dataset.status != DatasetStatus.READY.value
        or dataset.processing_level != ProcessingLevel.RAW.value
        or dataset.dataset_type not in PROCESSABLE_SOURCE_TYPES
    ):
        return None
    metadata = _object(dataset.metadata_json)
    if metadata.get("auto_process") is False:
        return None
    raw_options = metadata.get("processing_options") or {}
    options = raw_options if isinstance(raw_options, dict) else {}
    data = ProcessingJobCreate(
        source_dataset_ids=[dataset.id],
        requested_outputs=list(config.processing_default_output_list),
        provider=config.processing_provider,
        options=options,
        idempotency_key=(
            f"processing:auto:{dataset.id}:"
            + hashlib.sha256(
                ",".join(config.processing_default_output_list).encode()
            ).hexdigest()
        ),
    )
    return create_processing_job(db, data=data, actor=None, config=config)


def processing_job_out(job: ProcessingJob) -> dict[str, Any]:
    sources = [
        link.dataset_id for link in sorted(job.source_links, key=lambda item: item.sequence)
    ]
    outputs = [
        {
            "output_type": link.output_type,
            "dataset_id": link.dataset_id,
            "quality_status": link.quality_status,
        }
        for link in sorted(job.output_links, key=lambda item: item.output_type)
    ]
    return {
        "id": job.id,
        "organization_id": job.organization_id,
        "workspace_id": job.workspace_id,
        "asset_id": job.asset_id,
        "acquisition_id": job.acquisition_id,
        "fulfilment_job_id": job.fulfilment_job_id,
        "provider": job.provider_code,
        "provider_job_reference": job.provider_job_reference,
        "source_dataset_ids": sources,
        "requested_outputs": _array(job.requested_outputs_json),
        "generated_outputs": outputs,
        "status": job.status,
        "progress_percent": float(job.progress_percent or 0.0),
        "stage": job.stage,
        "processor_name": job.processor_name,
        "processor_version": job.processor_version,
        "estimated_cost_amount": job.estimated_cost_amount,
        "actual_cost_amount": job.actual_cost_amount,
        "cost_currency": job.cost_currency,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "quality_report": _object(job.quality_report_json),
        "retry_count": job.retry_count,
        "max_retries": job.max_retries,
        "poll_count": job.poll_count,
        "submission_generation": job.submission_generation,
        "next_poll_at": job.next_poll_at,
        "submitted_at": job.submitted_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "cancelled_at": job.cancelled_at,
        "lifecycle_version": job.lifecycle_version,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


def list_processing_jobs(
    db: Session,
    *,
    organization_id: str | None = None,
    asset_id: str | None = None,
    status: str | None = None,
    provider: str | None = None,
    limit: int = 200,
) -> list[ProcessingJob]:
    query = db.query(ProcessingJob)
    if organization_id:
        query = query.filter(ProcessingJob.organization_id == organization_id)
    if asset_id:
        query = query.filter(ProcessingJob.asset_id == asset_id)
    if status:
        query = query.filter(ProcessingJob.status == status.strip().upper())
    if provider:
        query = query.filter(ProcessingJob.provider_code == provider.strip().lower())
    return query.order_by(ProcessingJob.created_at.desc()).limit(limit).all()


def _check_version(job: ProcessingJob, expected: int | None) -> None:
    if expected is not None and job.lifecycle_version != expected:
        raise ProcessingJobError(
            "version_conflict", "Processing job changed since it was last read"
        )


def retry_processing_job(
    db: Session,
    *,
    job: ProcessingJob,
    actor: User,
    expected_version: int | None,
    provider_code: str | None = None,
) -> ProcessingJob:
    _check_version(job, expected_version)
    if job.status not in {
        ProcessingJobState.FAILED.value,
        ProcessingJobState.NEEDS_REVIEW.value,
    }:
        raise ProcessingJobError(
            "processing_retry_not_allowed",
            "Only failed or review-required processing jobs can be retried",
        )
    job.status = ProcessingJobState.REQUESTED.value
    if provider_code:
        normalized_provider = normalize_provider_code(provider_code) or job.provider_code
        job.provider_code = {
            "deterministic": "fake",
            "opendronemap": "nodeodm",
        }.get(normalized_provider, normalized_provider)
    job.stage = "operator_retry_requested"
    job.progress_percent = 0.0
    job.provider_job_reference = None
    job.error_code = None
    job.error_message = None
    job.quality_report_json = "{}"
    job.retry_count = 0
    job.poll_count = 0
    job.submission_generation += 1
    job.next_poll_at = utc_now()
    job.finished_at = None
    job.cancelled_at = None
    job.lifecycle_version += 1
    job.updated_at = utc_now()
    _audit(db, actor=actor, action="processing.retry_requested", job=job)
    _event(
        db,
        job,
        EventNames.PROCESSING_REQUESTED,
        f"processing:{job.id}:requested:{job.lifecycle_version}",
        {"operator_retry": True},
    )
    return job


def cancel_processing_job(
    db: Session,
    *,
    job: ProcessingJob,
    actor: User,
    provider: ProcessingProvider,
    expected_version: int | None,
) -> ProcessingJob:
    _check_version(job, expected_version)
    if job.status in TERMINAL_PROCESSING_STATES:
        if job.status == ProcessingJobState.CANCELLED.value:
            return job
        raise ProcessingJobError(
            "processing_cancel_not_allowed", "Completed processing cannot be cancelled"
        )
    if job.provider_job_reference:
        result = provider.cancel(job.provider_job_reference)
        if not result.ok:
            failure = result.failure
            raise ProcessingJobError(
                failure.code if failure else "provider_cancel_failed",
                failure.message if failure else "Processor did not accept cancellation",
                retryable=failure.retryable if failure else True,
            )
    _mark_cancelled(db, job, reason="operator_cancelled")
    _audit(db, actor=actor, action="processing.cancelled", job=job)
    return job


def _release(job: ProcessingJob) -> None:
    job.claimed_by = None
    job.claimed_at = None


def _retry_delay(job: ProcessingJob, config: Settings) -> float:
    return min(
        config.processing_retry_max_seconds,
        config.processing_retry_initial_seconds * (2 ** max(job.retry_count - 1, 0)),
    )


def _schedule_retry(
    job: ProcessingJob,
    *,
    resume_state: str,
    code: str,
    message: object,
    config: Settings,
) -> bool:
    safe_message = sanitize_integration_message(message)
    if job.retry_count >= job.max_retries:
        job.status = ProcessingJobState.FAILED.value
        job.stage = "retry_budget_exhausted"
        job.error_code = code
        job.error_message = safe_message
        job.finished_at = utc_now()
        job.next_poll_at = None
        _release(job)
        return False
    job.retry_count += 1
    job.status = ProcessingJobState.RETRY_WAIT.value
    job.stage = f"retry:{resume_state}"
    job.error_code = code
    job.error_message = safe_message
    job.next_poll_at = utc_now() + timedelta(seconds=_retry_delay(job, config))
    job.lifecycle_version += 1
    job.updated_at = utc_now()
    _release(job)
    return True


def _mark_failed(
    db: Session,
    job: ProcessingJob,
    *,
    code: str,
    message: object,
) -> None:
    job.status = ProcessingJobState.FAILED.value
    job.stage = "failed"
    job.error_code = code
    job.error_message = sanitize_integration_message(message)
    job.finished_at = utc_now()
    job.next_poll_at = None
    job.lifecycle_version += 1
    job.updated_at = utc_now()
    _release(job)
    _event(
        db,
        job,
        EventNames.PROCESSING_FAILED,
        f"processing:{job.id}:failed:{job.lifecycle_version}",
        {"error_code": code, "retry_count": job.retry_count},
    )


def _mark_needs_review(
    db: Session,
    job: ProcessingJob,
    *,
    code: str,
    message: object,
    report: dict[str, Any],
) -> None:
    job.status = ProcessingJobState.NEEDS_REVIEW.value
    job.stage = "quality_review_required"
    job.error_code = code
    job.error_message = sanitize_integration_message(message)
    job.quality_report_json = _json(report)
    job.finished_at = utc_now()
    job.next_poll_at = None
    job.lifecycle_version += 1
    job.updated_at = utc_now()
    _release(job)
    _event(
        db,
        job,
        EventNames.PROCESSING_NEEDS_REVIEW,
        f"processing:{job.id}:needs-review:{job.lifecycle_version}",
        {"quality_report": report},
    )


def _mark_cancelled(db: Session, job: ProcessingJob, *, reason: str) -> None:
    job.status = ProcessingJobState.CANCELLED.value
    job.stage = reason
    job.cancelled_at = utc_now()
    job.finished_at = job.cancelled_at
    job.next_poll_at = None
    job.lifecycle_version += 1
    job.updated_at = utc_now()
    _release(job)
    _event(
        db,
        job,
        EventNames.PROCESSING_CANCELLED,
        f"processing:{job.id}:cancelled",
    )


def _request_for_job(
    job: ProcessingJob,
    *,
    storage: StorageService,
    config: Settings,
) -> ProcessingRequest:
    inputs: list[ProcessingInput] = []
    total_bytes = 0
    for source_link in sorted(job.source_links, key=lambda item: item.sequence):
        source = source_link.dataset
        if (
            source.status != DatasetStatus.READY.value
            or source.processing_level != ProcessingLevel.RAW.value
            or source.dataset_type not in PROCESSABLE_SOURCE_TYPES
        ):
            raise ProcessingJobError(
                "source_dataset_invalid",
                "Source dataset is no longer ready raw imagery",
            )
        for file in sorted(source.files, key=lambda item: (item.created_at, item.id)):
            if file.status != "uploaded" or not file.storage_key:
                continue
            if Path(file.filename).suffix.lower() not in _INPUT_EXTENSIONS:
                continue
            if file.storage_provider != storage.provider_name:
                raise ProcessingJobError(
                    "source_storage_unavailable",
                    "Source dataset storage provider is unavailable to this worker",
                    retryable=True,
                )
            try:
                content = storage.download_file(file.storage_key)
            except RuntimeError as exc:
                raise ProcessingJobError(
                    "source_download_failed",
                    "Source image could not be read from object storage",
                    retryable=True,
                ) from exc
            total_bytes += len(content)
            if total_bytes > config.processing_max_input_bytes:
                raise ProcessingJobError(
                    "processing_input_too_large",
                    "Processing inputs exceed the configured worker safety limit",
                )
            digest = hashlib.sha256(content).hexdigest()
            if file.sha256_hash and digest.lower() != file.sha256_hash.lower():
                raise ProcessingJobError(
                    "source_checksum_mismatch",
                    "Source image checksum validation failed",
                )
            inputs.append(
                ProcessingInput(
                    filename=f"{len(inputs):05d}_{Path(file.filename).name}",
                    content=content,
                    content_type=file.mime_type or "application/octet-stream",
                    sha256_hash=digest,
                )
            )
    if len(inputs) < config.processing_minimum_images:
        raise ProcessingJobError(
            "insufficient_source_images",
            f"At least {config.processing_minimum_images} uploaded images are required",
        )
    return ProcessingRequest(
        job_id=job.id,
        name=f"GeoVision {job.id}",
        inputs=tuple(inputs),
        requested_outputs=tuple(_array(job.requested_outputs_json)),
        options=_object(job.options_json),
    )


def _result_failure(result: IntegrationResult[Any]) -> tuple[str, str, bool]:
    failure = result.failure
    if failure is None:
        return "provider_failed", "Processor returned no result", False
    return failure.code, failure.message, failure.retryable


def _submit_job(
    db: Session,
    job: ProcessingJob,
    *,
    provider: ProcessingProvider,
    storage: StorageService,
    config: Settings,
) -> str:
    job.status = ProcessingJobState.VALIDATING.value
    job.stage = "validating_sources"
    job.updated_at = utc_now()
    try:
        request = _request_for_job(job, storage=storage, config=config)
    except ProcessingJobError as exc:
        if exc.retryable:
            if _schedule_retry(
                job,
                resume_state=ProcessingJobState.REQUESTED.value,
                code=exc.code,
                message=exc,
                config=config,
            ):
                return "retried"
            _mark_failed(db, job, code=exc.code, message=exc)
            return "failed"
        _mark_needs_review(
            db,
            job,
            code=exc.code,
            message=exc,
            report={"source_validation": "failed", "issues": [exc.code]},
        )
        return "needs_review"
    result = provider.submit(
        request,
        idempotency_key=(
            f"processing:{job.id}:submission:{job.submission_generation}"
        ),
    )
    if not result.ok or result.value is None:
        code, message, retryable = _result_failure(result)
        if retryable and _schedule_retry(
            job,
            resume_state=ProcessingJobState.REQUESTED.value,
            code=code,
            message=message,
            config=config,
        ):
            return "retried"
        _mark_failed(db, job, code=code, message=message)
        return "failed"
    submission = result.value
    job.provider_job_reference = submission.external_reference
    job.processor_name = submission.processor_name
    job.processor_version = submission.processor_version
    if submission.estimated_cost_amount is not None:
        job.estimated_cost_amount = submission.estimated_cost_amount
    job.status = ProcessingJobState.SUBMITTED.value
    job.progress_percent = 0.0
    job.stage = "submitted"
    job.submitted_at = job.submitted_at or utc_now()
    job.next_poll_at = utc_now() + timedelta(seconds=config.processing_worker_poll_seconds)
    job.error_code = None
    job.error_message = None
    job.lifecycle_version += 1
    job.updated_at = utc_now()
    _release(job)
    return "submitted"


def _quality_check(
    outputs: tuple[NormalizedProcessingOutput, ...],
    *,
    requested: tuple[str, ...],
    config: Settings,
) -> tuple[dict[str, Any], dict[str, NormalizedProcessingOutput]]:
    by_type: dict[str, NormalizedProcessingOutput] = {}
    issues: list[str] = []
    total_bytes = 0
    for output in outputs:
        if output.dataset_type in by_type:
            issues.append(f"duplicate:{output.dataset_type}")
            continue
        try:
            validate_upload(
                filename=output.filename,
                content_type=output.content_type,
                size_bytes=len(output.content),
                max_size_bytes=config.processing_max_output_unpacked_bytes,
            )
        except ValueError:
            issues.append(f"invalid:{output.dataset_type}")
            continue
        total_bytes += len(output.content)
        by_type[output.dataset_type] = output
    missing = sorted(set(requested) - set(by_type))
    if total_bytes > config.processing_max_output_unpacked_bytes:
        issues.append("outputs_too_large")
    report = {
        "requested_outputs": list(requested),
        "recognized_outputs": sorted(by_type),
        "missing_outputs": missing,
        "issues": issues,
        "total_output_bytes": total_bytes,
        "checks": {
            "non_empty": not any(issue.startswith("invalid:") for issue in issues),
            "requested_outputs_present": not missing,
            "size_within_limit": "outputs_too_large" not in issues,
        },
    }
    return report, by_type


def _dataset_event(
    db: Session,
    dataset: Dataset,
    *,
    name: str,
    key: str,
    payload: dict[str, Any],
) -> None:
    enqueue_domain_event(
        db,
        name=name,
        aggregate_type="dataset",
        aggregate_id=dataset.id,
        idempotency_key=key,
        correlation_id=dataset.id,
        payload={
            "dataset_id": dataset.id,
            "organization_id": dataset.company_id,
            "workspace_id": dataset.workspace_id,
            "asset_id": dataset.asset_id,
            "mission_id": dataset.mission_id,
            **payload,
        },
    )


def _register_output_dataset(
    db: Session,
    job: ProcessingJob,
    output: NormalizedProcessingOutput,
    *,
    storage: StorageService,
) -> Dataset:
    output_type = output.dataset_type
    link = next(
        (item for item in job.output_links if item.output_type == output_type), None
    )
    dataset_id = (
        link.dataset_id
        if link is not None
        else str(uuid.uuid5(_NAMESPACE, f"{job.id}:dataset:{output_type}"))
    )
    file_id = str(uuid.uuid5(_NAMESPACE, f"{job.id}:file:{output_type}"))
    dataset = db.get(Dataset, dataset_id)
    source = sorted(job.source_links, key=lambda item: item.sequence)[0].dataset
    now = utc_now()
    if dataset is None:
        level = (
            ProcessingLevel.DERIVED.value
            if output_type in {"NDVI", "NDRE", "GNDVI"}
            else ProcessingLevel.PROCESSED.value
        )
        dataset = Dataset(
            id=dataset_id,
            company_id=job.organization_id,
            workspace_id=job.workspace_id,
            site_id=source.site_id,
            asset_id=job.asset_id,
            mission_id=job.acquisition_id,
            name=f"{source.name} — {output_type.replace('_', ' ').title()}",
            description="Automated photogrammetry output",
            source_tool=job.provider_code,
            data_type=output_type.lower(),
            source="automated_processing",
            dataset_type=output_type,
            provider_code=job.provider_code,
            source_reference=job.provider_job_reference,
            storage_provider=storage.provider_name,
            crs=source.crs,
            resolution=source.resolution,
            resolution_unit=source.resolution_unit,
            processing_level=level,
            quality_status=QualityStatus.PASSED.value,
            provenance_json=_json(
                {
                    "processing_job_id": job.id,
                    "provider": job.provider_code,
                    "processor": job.processor_name,
                    "processor_version": job.processor_version,
                    "source_dataset_ids": [
                        item.dataset_id
                        for item in sorted(
                            job.source_links, key=lambda candidate: candidate.sequence
                        )
                    ],
                    "provider_output_path": output.metadata.get("provider_path"),
                }
            ),
            status=DatasetStatus.PROCESSING.value,
            sector=source.sector,
            capture_date=source.capture_date,
            metadata_json=_json(
                reject_sensitive_metadata(dict(output.metadata), "output_metadata")
            ),
            file_count=0,
            total_size_bytes=0,
            lifecycle_version=1,
            created_at=now,
            updated_at=now,
        )
        db.add(dataset)
        _dataset_event(
            db,
            dataset,
            name=EventNames.DATASET_CREATED,
            key=f"dataset:{dataset.id}:created",
            payload={"dataset_type": output_type, "processing_job_id": job.id},
        )
    file = db.get(DatasetFile, file_id)
    if file is None:
        key = storage.generate_dataset_key(
            organization_id=job.organization_id,
            asset_id=job.asset_id or "standalone",
            mission_id=job.acquisition_id,
            dataset_id=dataset_id,
            file_id=file_id,
            area=(
                "derived"
                if output_type in {"NDVI", "NDRE", "GNDVI"}
                else "processed"
            ),
            filename=output.filename,
        )
        file = DatasetFile(
            id=file_id,
            dataset_id=dataset_id,
            filename=Path(output.filename).name,
            storage_key=key,
            storage_provider=storage.provider_name,
            storage_uri=storage.object_uri(key),
            object_area=(
                "derived"
                if output_type in {"NDVI", "NDRE", "GNDVI"}
                else "processed"
            ),
            file_size=len(output.content),
            mime_type=output.content_type,
            status="pending_upload",
            lifecycle_version=1,
            created_at=now,
        )
        db.add(file)
        dataset.object_prefix = key.rsplit("/", 1)[0]
    if link is None:
        link = ProcessingJobOutput(
            processing_job_id=job.id,
            output_type=output_type,
            dataset_id=dataset_id,
            quality_status=QualityStatus.PASSED.value,
            created_at=now,
        )
        db.add(link)
    job.claimed_at = now
    db.commit()  # Durable reservation before the provider-independent object write.
    if file.status == "uploaded" and dataset.status == DatasetStatus.READY.value:
        return dataset
    try:
        stored_key, size, md5_hash, sha256_hash = storage.upload_bytes(
            output.content,
            file.storage_key or "",
            output.content_type,
            {"processing_job_id": job.id, "dataset_id": dataset.id},
        )
    except RuntimeError as exc:
        dataset.status = DatasetStatus.ERROR.value
        dataset.quality_status = QualityStatus.FAILED.value
        link.quality_status = QualityStatus.FAILED.value
        db.commit()
        raise ProcessingJobError(
            "output_storage_failed",
            "Processed output could not be written to object storage",
            retryable=True,
        ) from exc
    file.storage_key = stored_key
    file.storage_uri = storage.object_uri(stored_key)
    file.file_size = size
    file.md5_hash = md5_hash
    file.sha256_hash = sha256_hash
    file.status = "uploaded"
    file.confirmed_at = utc_now()
    file.lifecycle_version += 1
    dataset.status = DatasetStatus.READY.value
    dataset.quality_status = QualityStatus.PASSED.value
    dataset.file_count = 1
    dataset.total_size_bytes = size
    dataset.processed_at = utc_now()
    dataset.updated_at = utc_now()
    dataset.lifecycle_version += 1
    link.quality_status = QualityStatus.PASSED.value
    _dataset_event(
        db,
        dataset,
        name=EventNames.DATASET_FILE_UPLOADED,
        key=f"dataset-file:{file.id}:uploaded",
        payload={"file_id": file.id, "size_bytes": size, "processing_job_id": job.id},
    )
    _dataset_event(
        db,
        dataset,
        name=EventNames.DATASET_READY,
        key=f"dataset:{dataset.id}:ready:{dataset.lifecycle_version}",
        payload={"file_count": 1, "processing_job_id": job.id},
    )
    job.claimed_at = utc_now()
    db.commit()
    return dataset


def _retrieve_and_register(
    db: Session,
    job: ProcessingJob,
    *,
    provider: ProcessingProvider,
    storage: StorageService,
    config: Settings,
) -> str:
    reference = job.provider_job_reference or ""
    retrieved = provider.retrieve_outputs(reference)
    if not retrieved.ok or retrieved.value is None:
        code, message, retryable = _result_failure(retrieved)
        if retryable and _schedule_retry(
            job,
            resume_state=ProcessingJobState.RUNNING.value,
            code=code,
            message=message,
            config=config,
        ):
            return "retried"
        _mark_failed(db, job, code=code, message=message)
        return "failed"
    normalized = provider.normalize_outputs(
        retrieved.value,
        requested_outputs=tuple(_array(job.requested_outputs_json)),
    )
    if not normalized.ok or normalized.value is None:
        code, message, _ = _result_failure(normalized)
        _mark_needs_review(
            db,
            job,
            code=code,
            message=message,
            report={"output_validation": "failed", "issues": [code]},
        )
        return "needs_review"
    requested = tuple(_array(job.requested_outputs_json))
    report, by_type = _quality_check(
        normalized.value, requested=requested, config=config
    )
    if report["missing_outputs"] or report["issues"]:
        _mark_needs_review(
            db,
            job,
            code="processing_output_quality_failed",
            message="Processed outputs are incomplete or invalid",
            report=report,
        )
        return "needs_review"
    generated_ids: list[str] = []
    for output_type in requested:
        try:
            dataset = _register_output_dataset(
                db, job, by_type[output_type], storage=storage
            )
        except ProcessingJobError as exc:
            if exc.retryable and _schedule_retry(
                job,
                resume_state=ProcessingJobState.RUNNING.value,
                code=exc.code,
                message=exc,
                config=config,
            ):
                return "retried"
            _mark_failed(db, job, code=exc.code, message=exc)
            return "failed"
        generated_ids.append(dataset.id)
    job.status = ProcessingJobState.COMPLETED.value
    job.progress_percent = 100.0
    job.stage = "outputs_registered"
    job.quality_report_json = _json(report)
    job.error_code = None
    job.error_message = None
    job.finished_at = utc_now()
    job.next_poll_at = None
    job.lifecycle_version += 1
    job.updated_at = utc_now()
    _release(job)
    _event(
        db,
        job,
        EventNames.PROCESSING_COMPLETED,
        f"processing:{job.id}:completed",
        {
            "generated_dataset_ids": generated_ids,
            "requested_outputs": list(requested),
            "processor": job.processor_name,
            "processor_version": job.processor_version,
        },
    )
    return "completed"


def _poll_job(
    db: Session,
    job: ProcessingJob,
    *,
    provider: ProcessingProvider,
    storage: StorageService,
    config: Settings,
) -> str:
    if not job.provider_job_reference:
        _mark_failed(
            db,
            job,
            code="provider_reference_missing",
            message="Processing job has no provider reference",
        )
        return "failed"
    result = provider.status(job.provider_job_reference)
    job.poll_count += 1
    if not result.ok or result.value is None:
        code, message, retryable = _result_failure(result)
        resume = (
            ProcessingJobState.RUNNING.value
            if job.progress_percent > 0
            else ProcessingJobState.SUBMITTED.value
        )
        if retryable and _schedule_retry(
            job,
            resume_state=resume,
            code=code,
            message=message,
            config=config,
        ):
            return "retried"
        _mark_failed(db, job, code=code, message=message)
        return "failed"
    status = result.value
    state = status.state.strip().upper()
    job.progress_percent = min(max(status.progress_percent, 0.0), 100.0)
    job.stage = status.stage or state.lower()
    job.actual_cost_amount = (
        status.actual_cost_amount
        if status.actual_cost_amount is not None
        else job.actual_cost_amount
    )
    job.error_code = status.error_code
    job.error_message = (
        sanitize_integration_message(status.error_message)
        if status.error_message
        else None
    )
    job.updated_at = utc_now()
    if state == ProcessingJobState.SUBMITTED.value:
        job.status = state
        job.next_poll_at = utc_now() + timedelta(seconds=config.processing_worker_poll_seconds)
        job.lifecycle_version += 1
        _release(job)
        return "running"
    if state == ProcessingJobState.RUNNING.value:
        job.status = state
        job.started_at = job.started_at or utc_now()
        job.next_poll_at = utc_now() + timedelta(seconds=config.processing_worker_poll_seconds)
        job.lifecycle_version += 1
        _release(job)
        return "running"
    if state == ProcessingJobState.COMPLETED.value:
        job.progress_percent = 100.0
        return _retrieve_and_register(
            db, job, provider=provider, storage=storage, config=config
        )
    if state == ProcessingJobState.CANCELLED.value:
        _mark_cancelled(db, job, reason="provider_cancelled")
        return "cancelled"
    if state == ProcessingJobState.FAILED.value:
        if _schedule_retry(
            job,
            resume_state=ProcessingJobState.REQUESTED.value,
            code=status.error_code or "provider_processing_failed",
            message=status.error_message or "Processor reported a failed task",
            config=config,
        ):
            job.provider_job_reference = None
            job.submission_generation += 1
            return "retried"
        _mark_failed(
            db,
            job,
            code=status.error_code or "provider_processing_failed",
            message=status.error_message or "Processor reported a failed task",
        )
        return "failed"
    _mark_needs_review(
        db,
        job,
        code="provider_state_unknown",
        message="Processor returned an unsupported state",
        report={"provider_state": state, "issues": ["provider_state_unknown"]},
    )
    return "needs_review"


def claim_processing_jobs(
    db: Session,
    *,
    worker_id: str,
    limit: int,
    config: Settings = settings,
) -> list[str]:
    now = utc_now()
    stale_before = now - timedelta(
        seconds=config.processing_worker_claim_timeout_seconds
    )
    (
        db.query(ProcessingJob)
        .filter(
            ProcessingJob.claimed_at.is_not(None),
            ProcessingJob.claimed_at < stale_before,
            ProcessingJob.status.notin_(TERMINAL_PROCESSING_STATES),
        )
        .update(
            {ProcessingJob.claimed_by: None, ProcessingJob.claimed_at: None},
            synchronize_session=False,
        )
    )
    query = (
        db.query(ProcessingJob)
        .filter(
            ProcessingJob.status.in_(
                (
                    ProcessingJobState.REQUESTED.value,
                    ProcessingJobState.SUBMITTED.value,
                    ProcessingJobState.RUNNING.value,
                    ProcessingJobState.RETRY_WAIT.value,
                )
            ),
            ProcessingJob.claimed_by.is_(None),
            or_(
                ProcessingJob.next_poll_at.is_(None),
                ProcessingJob.next_poll_at <= now,
            ),
        )
        .order_by(ProcessingJob.next_poll_at.asc(), ProcessingJob.created_at.asc())
        .limit(limit)
    )
    if db.get_bind().dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    rows = query.all()
    for row in rows:
        row.claimed_by = worker_id
        row.claimed_at = now
    db.commit()
    return [row.id for row in rows]


def run_processing_cycle(
    db: Session,
    *,
    worker_id: str,
    provider_resolver: ProviderResolver,
    storage: StorageService,
    config: Settings = settings,
    limit: int | None = None,
) -> dict[str, int]:
    ids = claim_processing_jobs(
        db,
        worker_id=worker_id,
        limit=limit or config.processing_worker_batch_size,
        config=config,
    )
    stats = {
        "claimed": len(ids),
        "submitted": 0,
        "running": 0,
        "completed": 0,
        "needs_review": 0,
        "failed": 0,
        "retried": 0,
        "cancelled": 0,
    }
    for job_id in ids:
        outcome = "failed"
        try:
            job = db.get(ProcessingJob, job_id)
            if job is None or job.claimed_by != worker_id:
                db.rollback()
                continue
            provider = provider_resolver(job.provider_code)
            if provider.provider_name != job.provider_code and not (
                job.provider_code == "deterministic" and provider.provider_name == "fake"
            ):
                _mark_failed(
                    db,
                    job,
                    code="processing_provider_mismatch",
                    message="Configured processor does not match the job provider",
                )
                outcome = "failed"
            else:
                resume = (
                    job.stage.split(":", 1)[1]
                    if job.status == ProcessingJobState.RETRY_WAIT.value
                    and (job.stage or "").startswith("retry:")
                    else job.status
                )
                if resume == ProcessingJobState.REQUESTED.value:
                    outcome = _submit_job(
                        db,
                        job,
                        provider=provider,
                        storage=storage,
                        config=config,
                    )
                else:
                    outcome = _poll_job(
                        db,
                        job,
                        provider=provider,
                        storage=storage,
                        config=config,
                    )
            db.commit()
        except Exception as exc:
            db.rollback()
            job = db.get(ProcessingJob, job_id)
            if job is not None:
                if _schedule_retry(
                    job,
                    resume_state=(
                        ProcessingJobState.REQUESTED.value
                        if not job.provider_job_reference
                        else ProcessingJobState.RUNNING.value
                    ),
                    code="processing_worker_error",
                    message=exc,
                    config=config,
                ):
                    outcome = "retried"
                else:
                    _mark_failed(
                        db,
                        job,
                        code="processing_worker_error",
                        message=exc,
                    )
                    outcome = "failed"
                db.commit()
        stats[outcome] += 1
    return stats


__all__ = [
    "cancel_processing_job",
    "claim_processing_jobs",
    "create_processing_job",
    "ensure_automatic_processing_job",
    "list_processing_jobs",
    "processing_job_out",
    "retry_processing_job",
    "run_processing_cycle",
]
