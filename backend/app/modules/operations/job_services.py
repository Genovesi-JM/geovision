"""Application services for executable fulfilment jobs."""

from __future__ import annotations

import hmac
import json
import uuid
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import utc_now
from app.models import (
    Acquisition,
    Asset,
    AuditLog,
    ContractorAssignment,
    Dataset,
    DatasetFile,
    FulfilmentJob,
    FulfilmentJobDependency,
    OperationsContractor,
    Order,
    OrderItem,
    User,
)
from app.modules.assets.domain import (
    AssetValidationError,
    geometry_display_center,
    normalize_geometry,
)
from app.modules.datasets.domain import DatasetError, validate_upload
from app.modules.datasets.services import (
    confirm_reserved_upload,
    reserve_upload,
)
from app.modules.operations.domain import (
    JobState,
    OperationsResourceError,
    contractor_safe_documents,
    contractor_safe_mapping,
    require_job_transition,
)
from app.modules.operations.events import DomainEventPublisher, publish_operational_event
from app.modules.operations.job_schemas import (
    ContractorJobStateUpdate,
    ContractorUploadComplete,
    ContractorUploadInitiate,
    JobAssignmentUpdate,
    JobCreate,
    JobScheduleUpdate,
    JobStateUpdate,
)
from app.modules.organizations.domain import internal_permissions
from app.modules.organizations.services import active_internal_roles
from app.services.storage import StorageService


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _dict(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _list(value: str | None) -> list[Any]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


_PRIVATE_REQUIREMENT_KEY_PARTS = (
    "billing",
    "contractor",
    "cost",
    "customer",
    "internal",
    "margin",
    "order_id",
    "order_item_id",
    "organization",
    "payment",
    "plan_key",
    "price",
    "source_catalog_item_id",
    "staff",
    "supplier",
    "user_id",
    "workspace",
)


def _restricted_requirements(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _restricted_requirements(nested)
            for key, nested in value.items()
            if not any(
                part in str(key).strip().lower()
                for part in _PRIVATE_REQUIREMENT_KEY_PARTS
            )
        }
    if isinstance(value, list):
        return [_restricted_requirements(item) for item in value]
    return value


def _audit(
    db: Session,
    *,
    actor: User,
    action: str,
    job: FulfilmentJob,
    details: dict[str, Any],
) -> None:
    db.add(
        AuditLog(
            user_id=actor.id,
            user_email=actor.email,
            action=action,
            resource_type="fulfilment_job",
            resource_id=job.id,
            details=_json({"order_id": job.order_id, **details}),
        )
    )


def _event(
    db: Session,
    *,
    job: FulfilmentJob,
    event_type: str,
    payload: dict[str, Any],
    suffix: str,
    publisher: DomainEventPublisher | None,
) -> None:
    publish_operational_event(
        db,
        aggregate_id=job.id,
        event_type=event_type,
        payload={"job_id": job.id, "order_id": job.order_id, **payload},
        idempotency_key=f"fulfilment-job:{job.id}:{suffix}",
        publisher=publisher,
    )


def _check_version(job: FulfilmentJob, expected: int | None) -> None:
    if expected is not None and job.lifecycle_version != expected:
        raise OperationsResourceError("version_conflict", "Job changed since it was last read")


def _validate_references(db: Session, data: JobCreate) -> tuple[Order, OrderItem | None]:
    order = db.get(Order, data.order_id)
    if order is None:
        raise OperationsResourceError("order_not_found", "Order was not found")
    item = None
    if data.order_item_id:
        item = db.get(OrderItem, data.order_item_id)
        if item is None or item.order_id != order.id:
            raise OperationsResourceError(
                "order_item_not_found", "Order item was not found on this order"
            )
    if data.asset_id:
        asset = db.get(Asset, data.asset_id)
        order_organization = order.organization_id or order.company_id
        if asset is None or asset.organization_id != order_organization:
            raise OperationsResourceError("asset_not_found", "Asset was not found for this order")
    return order, item


def create_job(
    db: Session,
    *,
    actor: User,
    data: JobCreate,
    plan_key: str | None = None,
    initial_state: JobState = JobState.PLANNED,
    publisher: DomainEventPublisher | None = None,
) -> FulfilmentJob:
    _validate_references(db, data)
    if plan_key:
        existing = (
            db.query(FulfilmentJob).filter(FulfilmentJob.plan_key == plan_key).one_or_none()
        )
        if existing is not None:
            return existing
    now = utc_now()
    job_id = str(uuid.uuid4())
    job = FulfilmentJob(
        id=job_id,
        job_number=f"GVJ-{now.year}-{job_id.split('-')[0].upper()}",
        order_id=data.order_id,
        order_item_id=data.order_item_id,
        asset_id=data.asset_id,
        job_type=data.job_type,
        title=data.title.strip(),
        priority=data.priority.value,
        state=initial_state.value,
        requirements_json=_json(data.requirements),
        direct_cost_amount=data.direct_cost_amount,
        cost_currency=data.cost_currency,
        cost_reference=data.cost_reference,
        plan_key=plan_key,
        lifecycle_version=1,
        created_by_user_id=actor.id,
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.flush()
    _audit(
        db,
        actor=actor,
        action="operations.job.created",
        job=job,
        details={"job_type": job.job_type, "state": job.state},
    )
    _event(
        db,
        job=job,
        event_type="fulfilment_job.created",
        payload={"job_type": job.job_type, "state": job.state},
        suffix="created",
        publisher=publisher,
    )
    return job


def _dependency_rows(db: Session, job_id: str) -> list[FulfilmentJob]:
    return (
        db.query(FulfilmentJob)
        .join(
            FulfilmentJobDependency,
            FulfilmentJobDependency.depends_on_job_id == FulfilmentJob.id,
        )
        .filter(FulfilmentJobDependency.job_id == job_id)
        .order_by(FulfilmentJob.created_at, FulfilmentJob.id)
        .all()
    )


def dependencies_complete(db: Session, job: FulfilmentJob) -> bool:
    return all(row.state == JobState.COMPLETED.value for row in _dependency_rows(db, job.id))


def _creates_cycle(db: Session, job_id: str, upstream_id: str) -> bool:
    frontier = [upstream_id]
    visited: set[str] = set()
    while frontier:
        current = frontier.pop()
        if current == job_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        frontier.extend(
            row.depends_on_job_id
            for row in db.query(FulfilmentJobDependency)
            .filter(FulfilmentJobDependency.job_id == current)
            .all()
        )
    return False


def add_dependency(
    db: Session,
    *,
    actor: User,
    job: FulfilmentJob,
    upstream: FulfilmentJob,
    publisher: DomainEventPublisher | None = None,
) -> FulfilmentJobDependency:
    if job.order_id != upstream.order_id:
        raise OperationsResourceError(
            "cross_order_dependency", "A job can depend only on work from the same order"
        )
    if job.id == upstream.id:
        raise OperationsResourceError("dependency_cycle", "A job cannot depend on itself")
    existing = db.get(FulfilmentJobDependency, (job.id, upstream.id))
    if existing is not None:
        return existing
    if _creates_cycle(db, job.id, upstream.id):
        raise OperationsResourceError("dependency_cycle", "Dependency would create a cycle")
    if job.state not in {JobState.PLANNED.value, JobState.READY.value, JobState.BLOCKED.value}:
        raise OperationsResourceError(
            "job_already_started", "Dependencies cannot change after a job is assigned or started"
        )
    edge = FulfilmentJobDependency(
        job_id=job.id,
        depends_on_job_id=upstream.id,
        created_by_user_id=actor.id,
        created_at=utc_now(),
    )
    db.add(edge)
    if upstream.state != JobState.COMPLETED.value and job.state == JobState.READY.value:
        job.state = JobState.BLOCKED.value
        job.resume_state = JobState.READY.value
    job.lifecycle_version = int(job.lifecycle_version or 0) + 1
    job.updated_at = utc_now()
    _audit(
        db,
        actor=actor,
        action="operations.job.dependency_added",
        job=job,
        details={"depends_on_job_id": upstream.id},
    )
    _event(
        db,
        job=job,
        event_type="fulfilment_job.dependency_added",
        payload={"depends_on_job_id": upstream.id},
        suffix=f"dependency:{upstream.id}",
        publisher=publisher,
    )
    return edge


def job_restricted(job: FulfilmentJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "job_number": job.job_number,
        "title": job.title,
        "job_type": job.job_type,
        "priority": job.priority,
        "state": job.state,
        "scheduled_start": _iso(job.scheduled_start),
        "scheduled_end": _iso(job.scheduled_end),
        "actual_start": _iso(job.actual_start),
        "completed_at": _iso(job.completed_at),
        "requirements": _restricted_requirements(_dict(job.requirements_json)),
        "lifecycle_version": job.lifecycle_version,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


_CONTRACTOR_LOCATION_FIELDS = (
    "name",
    "label",
    "site_name",
    "address",
    "latitude",
    "longitude",
    "meeting_point",
    "access_instructions",
    "access_notes",
    "timezone",
)
_CONTRACTOR_REQUIREMENT_FIELDS = (
    "capabilities",
    "skills",
    "certifications",
    "equipment",
    "safety_briefing",
    "safety_requirements",
    "instructions",
    "notes",
    "checklist",
    "deliverables",
    "required_outputs",
    "weather_constraints",
    "access_constraints",
    "technical_requirements",
    "flight_parameters",
    "capture_parameters",
)


def contractor_job_restricted(job: FulfilmentJob) -> dict[str, Any]:
    payload = job_restricted(job)
    payload["requirements"] = contractor_safe_mapping(
        _dict(job.requirements_json), _CONTRACTOR_REQUIREMENT_FIELDS
    )
    return payload


def contractor_assigned_job(
    db: Session,
    *,
    contractor_id: str,
    job_id: str,
) -> FulfilmentJob:
    job = db.get(FulfilmentJob, job_id)
    if job is None or job.assigned_contractor_id != contractor_id:
        # Do not disclose whether an unrelated customer or job exists.
        raise OperationsResourceError("job_not_found", "Job was not found")
    return job


def _contractor_assignment(
    db: Session,
    *,
    contractor_id: str,
    job_id: str,
    accepted_only: bool = False,
) -> ContractorAssignment | None:
    query = db.query(ContractorAssignment).filter(
        ContractorAssignment.contractor_id == contractor_id,
        ContractorAssignment.fulfilment_job_id == job_id,
    )
    if accepted_only:
        query = query.filter(ContractorAssignment.status.in_(("ACCEPTED", "ACTIVE")))
        return (
            query.order_by(
                ContractorAssignment.updated_at.desc(),
                ContractorAssignment.id.desc(),
            )
            .first()
        )
    current = (
        query.filter(ContractorAssignment.status.in_(("ACCEPTED", "ACTIVE")))
        .order_by(
            ContractorAssignment.updated_at.desc(),
            ContractorAssignment.id.desc(),
        )
        .first()
    )
    if current is not None:
        return current
    return (
        query.order_by(
            ContractorAssignment.updated_at.desc(),
            ContractorAssignment.id.desc(),
        )
        .first()
    )


def _contractor_location(
    db: Session,
    job: FulfilmentJob,
    assignment: ContractorAssignment | None,
) -> dict[str, Any]:
    if assignment is not None:
        configured = contractor_safe_mapping(
            _dict(assignment.location_json), _CONTRACTOR_LOCATION_FIELDS
        )
        if configured:
            return configured
    asset = db.get(Asset, job.asset_id) if job.asset_id else None
    if asset is None:
        return {}
    location: dict[str, Any] = {
        "asset_name": asset.name,
        "label": asset.location_label,
    }
    try:
        center = geometry_display_center(normalize_geometry(asset.geometry_geojson))
    except (AssetValidationError, TypeError, ValueError):
        center = None
    if center:
        location.update({"latitude": center[0], "longitude": center[1]})
    return {key: value for key, value in location.items() if value is not None}


def _configured_dataset_ids(assignment: ContractorAssignment | None) -> set[str]:
    if assignment is None:
        return set()
    value = _dict(assignment.upload_area_json)
    result: set[str] = set()
    direct = value.get("dataset_id")
    if isinstance(direct, str) and direct:
        result.add(direct)
    for item in value.get("dataset_ids", []):
        if isinstance(item, str) and item:
            result.add(item)
    for item in value.get("targets", []):
        if isinstance(item, dict):
            target = item.get("dataset_id")
            if isinstance(target, str) and target:
                result.add(target)
    return result


def contractor_upload_targets(
    db: Session,
    *,
    contractor_id: str,
    job: FulfilmentJob,
) -> list[Dataset]:
    order = db.get(Order, job.order_id)
    asset = db.get(Asset, job.asset_id) if job.asset_id else None
    if order is None or asset is None:
        return []
    organization_id = order.organization_id or order.company_id
    workspace_id = asset.workspace_id or order.workspace_id
    if not organization_id or not workspace_id:
        return []

    accepted = _contractor_assignment(
        db,
        contractor_id=contractor_id,
        job_id=job.id,
        accepted_only=True,
    )
    if accepted is None:
        return []
    configured_ids = _configured_dataset_ids(accepted)
    mission_ids = tuple(
        row.id
        for row in db.query(Acquisition.id)
        .filter(
            Acquisition.fulfilment_job_id == job.id,
            Acquisition.organization_id == organization_id,
            Acquisition.workspace_id == workspace_id,
            Acquisition.asset_id == asset.id,
        )
        .all()
    )
    if not configured_ids and not mission_ids:
        return []
    query = db.query(Dataset).filter(
        Dataset.company_id == organization_id,
        Dataset.workspace_id == workspace_id,
        Dataset.asset_id == asset.id,
        Dataset.status != "archived",
    )
    links = []
    if configured_ids:
        links.append(Dataset.id.in_(configured_ids))
    if mission_ids:
        links.append(Dataset.mission_id.in_(mission_ids))
    query = query.filter(links[0] if len(links) == 1 else (links[0] | links[1]))
    return query.order_by(Dataset.created_at.asc(), Dataset.id.asc()).all()


_CONTRACTOR_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "ASSIGNED": ("IN_PROGRESS",),
    "SCHEDULED": ("IN_PROGRESS",),
    "IN_PROGRESS": ("WAITING_INPUT", "QA_REVIEW"),
    "WAITING_INPUT": ("IN_PROGRESS",),
}


def contractor_allowed_transitions(job: FulfilmentJob) -> list[str]:
    return list(_CONTRACTOR_TRANSITIONS.get(job.state, ()))


def contractor_job_detail(
    db: Session,
    *,
    contractor_id: str,
    job: FulfilmentJob,
) -> dict[str, Any]:
    assignment = _contractor_assignment(
        db,
        contractor_id=contractor_id,
        job_id=job.id,
    )
    assignment_payload = None
    if assignment is not None:
        assignment_payload = {
            "id": assignment.id,
            "assignment_number": assignment.assignment_number,
            "title": assignment.title,
            "status": assignment.status,
            "location": contractor_safe_mapping(
                _dict(assignment.location_json), _CONTRACTOR_LOCATION_FIELDS
            ),
            "window_start": _iso(assignment.window_start),
            "window_end": _iso(assignment.window_end),
            "requirements": contractor_safe_mapping(
                _dict(assignment.requirements_json),
                _CONTRACTOR_REQUIREMENT_FIELDS,
            ),
            "required_documents": contractor_safe_documents(
                _list(assignment.required_documents_json)
            ),
            "lifecycle_version": assignment.lifecycle_version,
        }
    targets = contractor_upload_targets(
        db,
        contractor_id=contractor_id,
        job=job,
    )
    assignment_is_current = bool(
        assignment is not None and assignment.status in {"ACCEPTED", "ACTIVE"}
    )
    return {
        **contractor_job_restricted(job),
        "location": _contractor_location(db, job, assignment),
        "assignment": assignment_payload,
        "upload_targets": [
            {
                "dataset_id": row.id,
                "name": row.name,
                "status": row.status,
                "file_count": row.file_count,
            }
            for row in targets
        ],
        "allowed_transitions": (
            contractor_allowed_transitions(job) if assignment_is_current else []
        ),
    }


def transition_contractor_job(
    db: Session,
    *,
    actor: User,
    contractor_id: str,
    job: FulfilmentJob,
    data: ContractorJobStateUpdate,
) -> FulfilmentJob:
    if job.assigned_contractor_id != contractor_id:
        raise OperationsResourceError("job_not_found", "Job was not found")
    _accepted_job_assignment(
        db,
        contractor_id=contractor_id,
        job_id=job.id,
    )
    if data.state not in contractor_allowed_transitions(job):
        raise OperationsResourceError(
            "contractor_transition_denied",
            "This job transition is not available to the assigned contractor",
        )
    if data.state == "WAITING_INPUT" and not (data.reason or "").strip():
        raise OperationsResourceError(
            "reason_required", "WAITING_INPUT requires a reason"
        )
    return transition_job(
        db,
        actor=actor,
        job=job,
        data=JobStateUpdate(
            state=JobState(data.state),
            reason=data.reason,
            expected_version=data.expected_version,
        ),
    )


_UPLOAD_JOB_STATES = {
    "ASSIGNED",
    "SCHEDULED",
    "IN_PROGRESS",
    "WAITING_INPUT",
    "QA_REVIEW",
}


def _authorized_upload_dataset(
    db: Session,
    *,
    contractor_id: str,
    job: FulfilmentJob,
    dataset_id: str,
) -> Dataset:
    if job.state not in _UPLOAD_JOB_STATES:
        raise OperationsResourceError(
            "job_upload_locked", "This job is not accepting uploads"
        )
    target = next(
        (
            row
            for row in contractor_upload_targets(
                db,
                contractor_id=contractor_id,
                job=job,
            )
            if row.id == dataset_id
        ),
        None,
    )
    if target is None:
        raise OperationsResourceError(
            "upload_target_not_found", "Upload target was not found"
        )
    return target


def _accepted_job_assignment(
    db: Session,
    *,
    contractor_id: str,
    job_id: str,
) -> ContractorAssignment:
    assignment = _contractor_assignment(
        db,
        contractor_id=contractor_id,
        job_id=job_id,
        accepted_only=True,
    )
    if assignment is None:
        raise OperationsResourceError(
            "accepted_assignment_required",
            "Accept the current job assignment before changing work or uploading",
        )
    return assignment


def _upload_reservations(assignment: ContractorAssignment) -> list[dict[str, Any]]:
    value = _dict(assignment.upload_area_json).get("reservations", [])
    return [item for item in value if isinstance(item, dict)]


def _record_upload_reservation(
    db: Session,
    *,
    actor: User,
    assignment: ContractorAssignment,
    job: FulfilmentJob,
    dataset: Dataset,
    file: DatasetFile,
) -> None:
    upload_area = _dict(assignment.upload_area_json)
    reservations = _upload_reservations(assignment)
    reservations.append(
        {
            "upload_reference": file.id,
            "job_id": job.id,
            "dataset_id": dataset.id,
            "status": "RESERVED",
            "created_by_user_id": actor.id,
        }
    )
    upload_area["reservations"] = reservations
    assignment.upload_area_json = _json(upload_area)
    assignment.lifecycle_version = int(assignment.lifecycle_version or 0) + 1
    assignment.updated_at = utc_now()
    _audit(
        db,
        actor=actor,
        action="operations.job.upload_reserved",
        job=job,
        details={
            "assignment_id": assignment.id,
            "dataset_id": dataset.id,
            "upload_reference": file.id,
        },
    )
    db.commit()


def _owned_upload_reservation(
    assignment: ContractorAssignment,
    *,
    actor: User,
    job_id: str,
    dataset_id: str,
    upload_reference: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    reservations = _upload_reservations(assignment)
    row = next(
        (
            item
            for item in reservations
            if item.get("upload_reference") == upload_reference
            and item.get("job_id") == job_id
            and item.get("dataset_id") == dataset_id
            and item.get("created_by_user_id") == actor.id
        ),
        None,
    )
    if row is None:
        raise OperationsResourceError(
            "upload_reference_not_found", "Upload reference was not found"
        )
    return row, reservations


def contractor_local_upload_file(
    db: Session,
    *,
    storage_key: str,
) -> DatasetFile:
    """Resolve a signed local PUT to an active contractor reservation."""

    file = (
        db.query(DatasetFile)
        .filter(
            DatasetFile.storage_key == storage_key,
            DatasetFile.storage_provider == "local",
            DatasetFile.status == "pending_upload",
        )
        .one_or_none()
    )
    if file is None:
        raise OperationsResourceError(
            "upload_reference_not_found", "Upload reference was not found"
        )
    if file.upload_expires_at and file.upload_expires_at < utc_now():
        raise DatasetError("upload_expired", "Upload reservation has expired")
    candidates = (
        db.query(ContractorAssignment)
        .filter(
            ContractorAssignment.status.in_(("ACCEPTED", "ACTIVE")),
            ContractorAssignment.upload_area_json.like(f"%{file.id}%"),
        )
        .all()
    )
    for assignment in candidates:
        reservation = next(
            (
                item
                for item in _upload_reservations(assignment)
                if item.get("upload_reference") == file.id
                and item.get("dataset_id") == file.dataset_id
                and item.get("status") == "RESERVED"
            ),
            None,
        )
        if reservation is None:
            continue
        job_id = reservation.get("job_id")
        job = db.get(FulfilmentJob, job_id) if isinstance(job_id, str) else None
        contractor = db.get(OperationsContractor, assignment.contractor_id)
        if (
            job is not None
            and contractor is not None
            and contractor.status == "ACTIVE"
            and assignment.fulfilment_job_id == job.id
            and job.assigned_contractor_id == assignment.contractor_id
        ):
            return file
    raise OperationsResourceError(
        "upload_reference_not_found", "Upload reference was not found"
    )


def reserve_contractor_upload(
    db: Session,
    *,
    actor: User,
    contractor_id: str,
    job: FulfilmentJob,
    data: ContractorUploadInitiate,
    storage: StorageService,
) -> dict[str, Any]:
    assignment = _accepted_job_assignment(
        db,
        contractor_id=contractor_id,
        job_id=job.id,
    )
    dataset = _authorized_upload_dataset(
        db,
        contractor_id=contractor_id,
        job=job,
        dataset_id=data.dataset_id,
    )
    file, upload_url, expires_in = reserve_upload(
        db,
        actor=actor,
        dataset=dataset,
        filename=data.filename,
        content_type=data.content_type,
        size_bytes=data.size_bytes,
        storage=storage,
        object_area=data.object_area,
    )
    _record_upload_reservation(
        db,
        actor=actor,
        assignment=assignment,
        job=job,
        dataset=dataset,
        file=file,
    )
    headers: dict[str, str] = {}
    if data.content_type:
        headers["Content-Type"] = data.content_type
    if storage.provider_name == "azure_blob":
        headers["x-ms-blob-type"] = "BlockBlob"
    elif storage.provider_name == "local":
        parsed = urlsplit(upload_url)
        upload_url = urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                "/operations/contractor/uploads/local",
                parsed.query,
                "",
            )
        )
    return {
        "upload_url": upload_url,
        "upload_reference": file.id,
        "expires_in": expires_in,
        "required_headers": headers,
    }


def _contractor_upload_receipt(file: DatasetFile) -> dict[str, Any]:
    return {
        "upload_reference": file.id,
        "dataset_id": file.dataset_id,
        "filename": file.filename,
        "size_bytes": file.file_size,
        "status": file.status,
        "sha256_hash": file.sha256_hash,
        "confirmed_at": file.confirmed_at,
    }


def confirm_contractor_upload(
    db: Session,
    *,
    actor: User,
    contractor_id: str,
    job: FulfilmentJob,
    data: ContractorUploadComplete,
    storage: StorageService,
) -> dict[str, Any]:
    assignment = _accepted_job_assignment(
        db,
        contractor_id=contractor_id,
        job_id=job.id,
    )
    dataset = _authorized_upload_dataset(
        db,
        contractor_id=contractor_id,
        job=job,
        dataset_id=data.dataset_id,
    )
    reservation, reservations = _owned_upload_reservation(
        assignment,
        actor=actor,
        job_id=job.id,
        dataset_id=dataset.id,
        upload_reference=data.upload_reference,
    )
    file = db.get(DatasetFile, data.upload_reference)
    if file is None or file.dataset_id != dataset.id or not file.storage_key:
        raise OperationsResourceError(
            "upload_reference_not_found", "Upload reference was not found"
        )
    claimed_hash = data.sha256_hash.lower() if data.sha256_hash else None
    if reservation.get("status") == "CONFIRMED":
        recorded_size = reservation.get("size_bytes", file.file_size)
        recorded_hash = reservation.get("sha256_hash", file.sha256_hash)
        normalized_recorded_hash = (
            str(recorded_hash).lower() if recorded_hash is not None else None
        )
        if data.size_bytes != recorded_size or claimed_hash != normalized_recorded_hash:
            raise DatasetError(
                "upload_mismatch",
                "Confirmation payload does not match the completed upload",
            )
        return _contractor_upload_receipt(file)
    info = storage.stat_file(file.storage_key)
    provider_content_type = (
        str(info.get("content_type") or "").split(";", 1)[0].strip().lower()
        if info
        else ""
    )
    reserved_content_type = (
        str(file.mime_type or "").split(";", 1)[0].strip().lower()
    )
    try:
        if provider_content_type:
            validate_upload(
                filename=file.filename,
                content_type=provider_content_type,
                size_bytes=int(info.get("size_bytes") or 0),
                max_size_bytes=settings.dataset_signed_upload_max_bytes,
            )
        if (
            provider_content_type
            and reserved_content_type
            and not hmac.compare_digest(provider_content_type, reserved_content_type)
        ):
            raise DatasetError(
                "upload_mismatch",
                "Stored content type does not match the upload reservation",
            )
    except DatasetError:
        storage.delete_file(file.storage_key)
        file.status = "rejected"
        file.lifecycle_version += 1
        db.commit()
        raise
    try:
        confirmed = confirm_reserved_upload(
            db,
            actor=actor,
            dataset=dataset,
            storage_key=file.storage_key,
            filename=file.filename,
            claimed_size_bytes=data.size_bytes,
            sha256_hash=data.sha256_hash,
            storage=storage,
        )
    except DatasetError:
        raise
    if reservation.get("status") != "CONFIRMED":
        reservation["status"] = "CONFIRMED"
        reservation["size_bytes"] = data.size_bytes
        reservation["sha256_hash"] = claimed_hash
        upload_area = _dict(assignment.upload_area_json)
        upload_area["reservations"] = reservations
        assignment.upload_area_json = _json(upload_area)
        assignment.lifecycle_version = int(assignment.lifecycle_version or 0) + 1
        assignment.updated_at = utc_now()
        _audit(
            db,
            actor=actor,
            action="operations.job.upload_confirmed",
            job=job,
            details={
                "assignment_id": assignment.id,
                "dataset_id": dataset.id,
                "upload_reference": confirmed.id,
            },
        )
        db.commit()
    return _contractor_upload_receipt(confirmed)


def job_internal(db: Session, job: FulfilmentJob) -> dict[str, Any]:
    dependencies = _dependency_rows(db, job.id)
    return {
        **job_restricted(job),
        "order_id": job.order_id,
        "order_item_id": job.order_item_id,
        "asset_id": job.asset_id,
        "assigned_contractor_id": job.assigned_contractor_id,
        "assigned_user_id": job.assigned_user_id,
        "direct_cost_amount": job.direct_cost_amount,
        "cost_currency": job.cost_currency,
        "cost_reference": job.cost_reference,
        "plan_key": job.plan_key,
        "resume_state": job.resume_state,
        "dependencies": [
            {
                "job_id": row.id,
                "job_number": row.job_number,
                "job_type": row.job_type,
                "state": row.state,
            }
            for row in dependencies
        ],
    }


def list_jobs(
    db: Session,
    *,
    order_id: str | None = None,
    job_state: str | None = None,
    job_type: str | None = None,
    contractor_id: str | None = None,
    assigned_user_id: str | None = None,
    limit: int = 200,
) -> list[FulfilmentJob]:
    query = db.query(FulfilmentJob)
    if order_id:
        query = query.filter(FulfilmentJob.order_id == order_id)
    if job_state:
        query = query.filter(FulfilmentJob.state == job_state.upper())
    if job_type:
        query = query.filter(FulfilmentJob.job_type == job_type.upper())
    if contractor_id:
        query = query.filter(FulfilmentJob.assigned_contractor_id == contractor_id)
    if assigned_user_id:
        query = query.filter(FulfilmentJob.assigned_user_id == assigned_user_id)
    return (
        query.order_by(
            FulfilmentJob.scheduled_start.asc(),
            FulfilmentJob.priority.desc(),
            FulfilmentJob.created_at.asc(),
        )
        .limit(limit)
        .all()
    )


def _required_capabilities(job: FulfilmentJob) -> set[str]:
    raw = _dict(job.requirements_json).get("capabilities", [])
    return {str(value).strip().upper() for value in raw if isinstance(value, str)}


def assign_job(
    db: Session,
    *,
    actor: User,
    job: FulfilmentJob,
    data: JobAssignmentUpdate,
    publisher: DomainEventPublisher | None = None,
) -> FulfilmentJob:
    _check_version(job, data.expected_version)
    if job.state in {
        JobState.IN_PROGRESS.value,
        JobState.QA_REVIEW.value,
        JobState.COMPLETED.value,
        JobState.CANCELLED.value,
        JobState.FAILED.value,
    }:
        raise OperationsResourceError(
            "job_assignment_locked", "Assignment cannot change after work starts"
        )
    contractor_id = None
    user_id = None
    if not data.clear_assignment and data.contractor_id:
        contractor = db.get(OperationsContractor, data.contractor_id)
        if (
            contractor is None
            or contractor.status != "ACTIVE"
            or contractor.availability == "UNAVAILABLE"
        ):
            raise OperationsResourceError(
                "contractor_unavailable", "Contractor is not available for this job"
            )
        available = {link.capability.code for link in contractor.capability_links}
        missing = sorted(_required_capabilities(job) - available)
        if missing:
            raise OperationsResourceError(
                "contractor_capability_missing",
                f"Contractor lacks required capabilities: {', '.join(missing)}",
            )
        contractor_id = contractor.id
    elif not data.clear_assignment and data.user_id:
        assigned_user = db.get(User, data.user_id)
        if assigned_user is None or not assigned_user.is_active:
            raise OperationsResourceError("assignee_not_found", "Internal assignee is unavailable")
        permissions = internal_permissions(active_internal_roles(db, assigned_user))
        allowed = {"platform:admin", "operations:access"}
        if job.job_type in {"ANALYST_REVIEW", "SPECIALIST_REVIEW"}:
            allowed.add("analytics:review")
        if not permissions.intersection(allowed):
            raise OperationsResourceError(
                "assignee_not_internal", "Assignee lacks the required internal role"
            )
        user_id = assigned_user.id
    job.assigned_contractor_id = contractor_id
    job.assigned_user_id = user_id
    if data.clear_assignment and job.state == JobState.ASSIGNED.value:
        job.state = JobState.READY.value
    elif not data.clear_assignment and job.state == JobState.READY.value:
        if not dependencies_complete(db, job):
            raise OperationsResourceError(
                "dependency_incomplete", "Every upstream job must complete before assignment"
            )
        job.state = JobState.ASSIGNED.value
    job.lifecycle_version = int(job.lifecycle_version or 0) + 1
    job.updated_at = utc_now()
    _audit(
        db,
        actor=actor,
        action="operations.job.assignment_changed",
        job=job,
        details={
            "assigned_contractor_id": contractor_id,
            "assigned_user_id": user_id,
            "cleared": data.clear_assignment,
        },
    )
    _event(
        db,
        job=job,
        event_type="fulfilment_job.assignment_changed",
        payload={
            "assigned_contractor_id": contractor_id,
            "assigned_user_id": user_id,
            "state": job.state,
        },
        suffix=f"assignment:{job.lifecycle_version}",
        publisher=publisher,
    )
    return job


def schedule_job(
    db: Session,
    *,
    actor: User,
    job: FulfilmentJob,
    data: JobScheduleUpdate,
    publisher: DomainEventPublisher | None = None,
) -> FulfilmentJob:
    _check_version(job, data.expected_version)
    if job.state in {
        JobState.IN_PROGRESS.value,
        JobState.QA_REVIEW.value,
        JobState.COMPLETED.value,
        JobState.CANCELLED.value,
        JobState.FAILED.value,
    }:
        raise OperationsResourceError("job_schedule_locked", "Schedule is locked after work starts")
    if data.clear_schedule:
        job.scheduled_start = None
        job.scheduled_end = None
        if job.state == JobState.SCHEDULED.value:
            job.state = (
                JobState.ASSIGNED.value
                if job.assigned_contractor_id or job.assigned_user_id
                else JobState.READY.value
            )
    else:
        if not dependencies_complete(db, job):
            raise OperationsResourceError(
                "dependency_incomplete", "Every upstream job must complete before scheduling"
            )
        if not (job.assigned_contractor_id or job.assigned_user_id):
            raise OperationsResourceError("assignee_required", "Assign the job before scheduling")
        job.scheduled_start = data.scheduled_start
        job.scheduled_end = data.scheduled_end
        if job.state in {JobState.READY.value, JobState.ASSIGNED.value}:
            job.state = JobState.SCHEDULED.value
    job.lifecycle_version = int(job.lifecycle_version or 0) + 1
    job.updated_at = utc_now()
    _audit(
        db,
        actor=actor,
        action="operations.job.scheduled",
        job=job,
        details={"start": _iso(job.scheduled_start), "end": _iso(job.scheduled_end)},
    )
    _event(
        db,
        job=job,
        event_type="fulfilment_job.schedule_changed",
        payload={
            "scheduled_start": _iso(job.scheduled_start),
            "scheduled_end": _iso(job.scheduled_end),
            "state": job.state,
        },
        suffix=f"schedule:{job.lifecycle_version}",
        publisher=publisher,
    )
    return job


_DEPENDENCY_GATED_STATES = {
    JobState.READY,
    JobState.ASSIGNED,
    JobState.SCHEDULED,
    JobState.IN_PROGRESS,
}


def _unblock_dependents(
    db: Session,
    *,
    actor: User,
    completed_job: FulfilmentJob,
    publisher: DomainEventPublisher | None,
) -> None:
    dependents = (
        db.query(FulfilmentJob)
        .join(
            FulfilmentJobDependency,
            FulfilmentJobDependency.job_id == FulfilmentJob.id,
        )
        .filter(FulfilmentJobDependency.depends_on_job_id == completed_job.id)
        .all()
    )
    for dependent in dependents:
        if dependent.state != JobState.BLOCKED.value or not dependencies_complete(db, dependent):
            continue
        target = dependent.resume_state or JobState.READY.value
        if target not in {state.value for state in _DEPENDENCY_GATED_STATES}:
            target = JobState.READY.value
        if target in {JobState.ASSIGNED.value, JobState.SCHEDULED.value} and not (
            dependent.assigned_contractor_id or dependent.assigned_user_id
        ):
            target = JobState.READY.value
        elif target == JobState.READY.value and (
            dependent.assigned_contractor_id or dependent.assigned_user_id
        ):
            target = JobState.ASSIGNED.value
        if target == JobState.SCHEDULED.value and not (
            dependent.scheduled_start and dependent.scheduled_end
        ):
            target = JobState.ASSIGNED.value
        dependent.state = target
        dependent.resume_state = None
        dependent.lifecycle_version = int(dependent.lifecycle_version or 0) + 1
        dependent.updated_at = utc_now()
        _audit(
            db,
            actor=actor,
            action="operations.job.dependencies_satisfied",
            job=dependent,
            details={"completed_upstream_job_id": completed_job.id, "state": target},
        )
        _event(
            db,
            job=dependent,
            event_type="fulfilment_job.dependencies_satisfied",
            payload={"completed_upstream_job_id": completed_job.id, "state": target},
            suffix=f"unblocked:{dependent.lifecycle_version}",
            publisher=publisher,
        )


def transition_job(
    db: Session,
    *,
    actor: User,
    job: FulfilmentJob,
    data: JobStateUpdate,
    publisher: DomainEventPublisher | None = None,
) -> FulfilmentJob:
    _check_version(job, data.expected_version)
    target = data.state
    current = JobState(job.state)
    if target == current:
        return job
    require_job_transition(current.value, target.value)
    if target in {JobState.BLOCKED, JobState.FAILED, JobState.CANCELLED} and not (
        data.reason or ""
    ).strip():
        raise OperationsResourceError("reason_required", f"{target.value} requires a reason")
    dependencies = _dependency_rows(db, job.id)
    if target in _DEPENDENCY_GATED_STATES and any(
        upstream.state != JobState.COMPLETED.value for upstream in dependencies
    ):
        raise OperationsResourceError(
            "dependency_incomplete", "Every upstream job must complete before this transition"
        )
    if target in {JobState.ASSIGNED, JobState.SCHEDULED} and not (
        job.assigned_contractor_id or job.assigned_user_id
    ):
        raise OperationsResourceError("assignee_required", "The job needs an assignee")
    if target == JobState.SCHEDULED and not (job.scheduled_start and job.scheduled_end):
        raise OperationsResourceError("schedule_required", "The job needs a schedule window")
    requirements = _dict(job.requirements_json)
    if target == JobState.IN_PROGRESS:
        if not (job.assigned_contractor_id or job.assigned_user_id) and not requirements.get(
            "automation"
        ):
            raise OperationsResourceError("assignee_required", "The job needs an assignee")
        if job.job_type == "PROCESS_DATA" and not dependencies:
            raise OperationsResourceError(
                "input_dependency_required",
                "Processing must explicitly depend on a completed upload or acquisition job",
            )
    now = utc_now()
    if target == JobState.BLOCKED:
        job.resume_state = current.value
    elif current == JobState.BLOCKED:
        job.resume_state = None
    job.state = target.value
    if target == JobState.IN_PROGRESS and job.actual_start is None:
        job.actual_start = now
    if target == JobState.COMPLETED:
        job.completed_at = now
    job.lifecycle_version = int(job.lifecycle_version or 0) + 1
    job.updated_at = now
    _audit(
        db,
        actor=actor,
        action="operations.job.state_changed",
        job=job,
        details={"from": current.value, "to": target.value, "reason": data.reason},
    )
    _event(
        db,
        job=job,
        event_type="fulfilment_job.state_changed",
        payload={"from": current.value, "to": target.value, "reason": data.reason},
        suffix=f"state:{job.lifecycle_version}",
        publisher=publisher,
    )
    if target == JobState.COMPLETED:
        db.flush()
        _unblock_dependents(db, actor=actor, completed_job=job, publisher=publisher)
    return job


def _chain_for_item(item: OrderItem) -> tuple[str, ...]:
    hints = _dict(item.fulfilment_hints_json)
    fulfilment_type = str(hints.get("fulfilment_type") or "").upper()
    item_type = str(item.catalog_item_type or item.product_type or "").upper()
    if fulfilment_type == "PHYSICAL_SHIPMENT" or item_type == "PHYSICAL_PRODUCT":
        return ("DELIVER_PRODUCT",)
    if fulfilment_type == "FIELD_INSTALLATION" or item_type == "INSTALLATION":
        return ("SENSOR_INSTALLATION",)
    if fulfilment_type == "REMOTE_ANALYSIS" or item_type == "ANALYSIS":
        return (
            "SATELLITE_ACQUISITION",
            "PROCESS_DATA",
            "ANALYST_REVIEW",
            "PUBLISH_REPORT",
        )
    if fulfilment_type == "MONITORING_ACTIVATION" or item_type == "MONITORING_PLAN":
        return ("SENSOR_INSTALLATION", "PROCESS_DATA", "ANALYST_REVIEW", "PUBLISH_REPORT")
    return ("FLIGHT_CAPTURE", "PROCESS_DATA", "ANALYST_REVIEW", "PUBLISH_REPORT")


def plan_order_jobs(
    db: Session,
    *,
    actor: User,
    order: Order,
    publisher: DomainEventPublisher | None = None,
) -> tuple[list[FulfilmentJob], int, int]:
    items = (
        db.query(OrderItem)
        .filter(OrderItem.order_id == order.id)
        .order_by(OrderItem.id)
        .all()
    )
    if not items:
        raise OperationsResourceError("order_items_required", "Order has no executable lines")
    jobs: list[FulfilmentJob] = []
    created_count = 0
    existing_count = 0
    for item in items:
        previous: FulfilmentJob | None = None
        for sequence, job_type in enumerate(_chain_for_item(item), start=1):
            plan_key = f"order:{order.id}:item:{item.id}:step:{sequence}:{job_type}"
            existing = (
                db.query(FulfilmentJob)
                .filter(FulfilmentJob.plan_key == plan_key)
                .one_or_none()
            )
            if existing is not None:
                job = existing
                existing_count += 1
            else:
                hints = _dict(item.fulfilment_hints_json)
                requirements = {
                    "source_order_item_id": item.id,
                    "source_catalog_item_id": item.catalog_item_id,
                    "quantity": item.qty,
                    "sequence": sequence,
                    "capabilities": hints.get("capabilities", []),
                    "automation": job_type in {"SATELLITE_ACQUISITION"},
                }
                asset_id = hints.get("asset_id")
                job = create_job(
                    db,
                    actor=actor,
                    data=JobCreate(
                        order_id=order.id,
                        order_item_id=item.id,
                        asset_id=asset_id if isinstance(asset_id, str) else None,
                        job_type=job_type,
                        title=f"{job_type.replace('_', ' ').title()}: {item.name or item.sku or 'order line'}",
                        requirements=requirements,
                    ),
                    plan_key=plan_key,
                    initial_state=JobState.READY if previous is None else JobState.BLOCKED,
                    publisher=publisher,
                )
                if previous is not None:
                    job.resume_state = JobState.READY.value
                created_count += 1
            if previous is not None:
                add_dependency(
                    db,
                    actor=actor,
                    job=job,
                    upstream=previous,
                    publisher=publisher,
                )
            jobs.append(job)
            previous = job
    return jobs, created_count, existing_count


def contractor_jobs(
    db: Session, contractor_id: str, *, limit: int = 100
) -> list[FulfilmentJob]:
    return (
        db.query(FulfilmentJob)
        .filter(FulfilmentJob.assigned_contractor_id == contractor_id)
        .order_by(FulfilmentJob.scheduled_start.asc(), FulfilmentJob.created_at.asc())
        .limit(limit)
        .all()
    )


def _customer_step_status(state: str) -> str:
    return {
        "PLANNED": "queued",
        "READY": "queued",
        "BLOCKED": "queued",
        "ASSIGNED": "preparing",
        "SCHEDULED": "scheduled",
        "IN_PROGRESS": "in_progress",
        "WAITING_INPUT": "in_progress",
        "QA_REVIEW": "quality_review",
        "COMPLETED": "complete",
        "FAILED": "attention_required",
        "CANCELLED": "cancelled",
    }.get(state, "queued")


def customer_order_progress(db: Session, order: Order) -> dict[str, Any]:
    jobs = (
        db.query(FulfilmentJob)
        .filter(FulfilmentJob.order_id == order.id)
        .order_by(FulfilmentJob.created_at, FulfilmentJob.id)
        .all()
    )
    total = len(jobs)
    completed = sum(job.state == JobState.COMPLETED.value for job in jobs)
    progress = round(completed * 100 / total) if total else 0
    states = {job.state for job in jobs}
    if order.fulfilment_status == "CANCELLED":
        status = "cancelled"
    elif JobState.FAILED.value in states:
        status = "attention_required"
    elif total and completed == total:
        status = "complete"
    elif JobState.QA_REVIEW.value in states:
        status = "quality_review"
    elif states.intersection(
        {JobState.IN_PROGRESS.value, JobState.WAITING_INPUT.value}
    ):
        status = "in_progress"
    elif states.intersection({JobState.SCHEDULED.value, JobState.ASSIGNED.value}):
        status = "scheduled"
    elif total:
        status = "preparing"
    else:
        status = str(order.fulfilment_status or "preparing").lower()
        if order.fulfilment_status in {"COMPLETED", "DELIVERED"}:
            progress = 100
    updated_values = [order.updated_at, *(job.updated_at for job in jobs)]
    updated_at = max(value for value in updated_values if value is not None)
    return {
        "order_id": order.id,
        "order_number": order.order_number,
        "status": status,
        "progress_percent": progress,
        "total_steps": total,
        "completed_steps": completed,
        "steps": [
            {
                "job_type": job.job_type,
                "status": _customer_step_status(job.state),
                "scheduled_start": _iso(job.scheduled_start),
                "scheduled_end": _iso(job.scheduled_end),
            }
            for job in jobs
        ],
        "updated_at": updated_at.isoformat(),
    }


__all__ = [
    "add_dependency",
    "assign_job",
    "confirm_contractor_upload",
    "contractor_assigned_job",
    "contractor_job_detail",
    "contractor_job_restricted",
    "contractor_jobs",
    "contractor_local_upload_file",
    "create_job",
    "customer_order_progress",
    "dependencies_complete",
    "job_internal",
    "job_restricted",
    "list_jobs",
    "plan_order_jobs",
    "reserve_contractor_upload",
    "schedule_job",
    "transition_contractor_job",
    "transition_job",
]
