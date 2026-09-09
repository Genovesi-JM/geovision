"""Application services for executable fulfilment jobs."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models import (
    Asset,
    AuditLog,
    FulfilmentJob,
    FulfilmentJobDependency,
    OperationsContractor,
    Order,
    OrderItem,
    User,
)
from app.modules.operations.domain import JobState, OperationsResourceError, require_job_transition
from app.modules.operations.events import DomainEventPublisher, publish_operational_event
from app.modules.operations.job_schemas import (
    JobAssignmentUpdate,
    JobCreate,
    JobScheduleUpdate,
    JobStateUpdate,
)
from app.modules.organizations.domain import internal_permissions
from app.modules.organizations.services import active_internal_roles


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _dict(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


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
    "contractor_jobs",
    "create_job",
    "customer_order_progress",
    "dependencies_complete",
    "job_internal",
    "job_restricted",
    "list_jobs",
    "plan_order_jobs",
    "schedule_job",
    "transition_job",
]
