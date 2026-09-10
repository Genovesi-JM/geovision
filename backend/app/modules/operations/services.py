"""Application services for private suppliers, contractors, and assignments."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models import (
    AuditLog,
    ContractorAssignment,
    ContractorCapability,
    FulfilmentJob,
    OperationalCapability,
    OperationsContractor,
    Order,
    User,
)
from app.modules.operations.domain import (
    AssignmentStatus,
    OperationsResourceError,
    contractor_safe_documents,
    contractor_safe_mapping,
    contractor_safe_value,
    normalize_code,
    require_assignment_transition,
)
from app.modules.operations.schemas import (
    AssignmentCreate,
    AssignmentUpdate,
    CapabilityCreate,
    CapabilityUpdate,
    ContractorCreate,
    ContractorSelfUpdate,
    ContractorUpdate,
)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _value(value: str | None, fallback: Any) -> Any:
    try:
        parsed = json.loads(value or "")
    except (TypeError, ValueError):
        return fallback
    return parsed if isinstance(parsed, type(fallback)) else fallback


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _audit(
    db: Session,
    *,
    actor: User,
    action: str,
    resource_type: str,
    resource_id: str,
    details: dict[str, Any],
) -> None:
    db.add(
        AuditLog(
            user_id=actor.id,
            user_email=actor.email,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=_json(details),
        )
    )


def capability_out(capability: OperationalCapability) -> dict[str, Any]:
    return {
        "id": capability.id,
        "code": capability.code,
        "name": capability.name,
        "category": capability.category,
        "description": capability.description,
        "is_active": capability.is_active,
        "metadata": _value(capability.metadata_json, {}),
        "created_at": capability.created_at.isoformat(),
        "updated_at": capability.updated_at.isoformat(),
    }


def create_capability(
    db: Session, *, actor: User, data: CapabilityCreate
) -> OperationalCapability:
    code = normalize_code(data.code, "CAPABILITY")
    if db.query(OperationalCapability).filter(OperationalCapability.code == code).first():
        raise OperationsResourceError("capability_exists", "Capability code already exists")
    now = utc_now()
    capability = OperationalCapability(
        id=str(uuid.uuid4()),
        code=code,
        name=data.name.strip(),
        category=normalize_code(data.category, "OTHER")[:50],
        description=data.description,
        metadata_json=_json(data.metadata),
        created_at=now,
        updated_at=now,
    )
    db.add(capability)
    db.flush()
    _audit(
        db,
        actor=actor,
        action="operations.capability.created",
        resource_type="operational_capability",
        resource_id=capability.id,
        details={"code": capability.code, "category": capability.category},
    )
    return capability


def update_capability(
    db: Session,
    *,
    actor: User,
    capability: OperationalCapability,
    data: CapabilityUpdate,
) -> OperationalCapability:
    changes = data.model_dump(exclude_unset=True, mode="json")
    if "metadata" in changes:
        capability.metadata_json = _json(changes.pop("metadata") or {})
    if "category" in changes and changes["category"]:
        changes["category"] = normalize_code(changes["category"], "OTHER")[:50]
    for field, value in changes.items():
        setattr(capability, field, value)
    capability.updated_at = utc_now()
    _audit(
        db,
        actor=actor,
        action="operations.capability.updated",
        resource_type="operational_capability",
        resource_id=capability.id,
        details={"fields": sorted(data.model_fields_set)},
    )
    return capability


def _capability_rows(db: Session, codes: list[str]) -> list[OperationalCapability]:
    normalized = list(dict.fromkeys(normalize_code(code, "") for code in codes))
    normalized = [code for code in normalized if code]
    if not normalized:
        return []
    rows = (
        db.query(OperationalCapability)
        .filter(
            OperationalCapability.code.in_(normalized),
            OperationalCapability.is_active.is_(True),
        )
        .all()
    )
    found = {row.code for row in rows}
    missing = sorted(set(normalized) - found)
    if missing:
        raise OperationsResourceError(
            "capability_not_found", f"Unknown or inactive capabilities: {', '.join(missing)}"
        )
    return sorted(rows, key=lambda row: row.code)


def _replace_capabilities(
    db: Session, contractor: OperationsContractor, codes: list[str]
) -> None:
    rows = _capability_rows(db, codes)
    contractor.capability_links[:] = [
        ContractorCapability(contractor=contractor, capability=row) for row in rows
    ]


def _validate_contractor_user(
    db: Session,
    user_id: str | None,
    *,
    contractor_id: str | None = None,
) -> None:
    if user_id is None:
        return
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise OperationsResourceError("contractor_user_not_found", "Contractor user is unavailable")
    existing = (
        db.query(OperationsContractor)
        .filter(OperationsContractor.user_id == user_id)
        .first()
    )
    if existing is not None and existing.id != contractor_id:
        raise OperationsResourceError(
            "contractor_user_exists", "User is already linked to another contractor profile"
        )


def contractor_internal(contractor: OperationsContractor) -> dict[str, Any]:
    capability_links = sorted(
        contractor.capability_links,
        key=lambda link: link.capability.code,
    )
    return {
        "id": contractor.id,
        "code": contractor.code,
        "user_id": contractor.user_id,
        "display_name": contractor.display_name,
        "legal_name": contractor.legal_name,
        "resource_type": contractor.resource_type,
        "status": contractor.status,
        "availability": contractor.availability,
        "contact_email": contractor.contact_email,
        "contact_phone": contractor.contact_phone,
        "country_code": contractor.country_code,
        "region": contractor.region,
        "service_area": _value(contractor.service_area_json, []),
        "certifications": _value(contractor.certifications_json, []),
        "insurance": _value(contractor.insurance_json, {}),
        "equipment": _value(contractor.equipment_json, []),
        "document_refs": _value(contractor.document_refs_json, []),
        "quality_score": (
            float(contractor.quality_score) if contractor.quality_score is not None else None
        ),
        "internal_notes": contractor.internal_notes,
        "capabilities": [
            {
                "id": link.capability.id,
                "code": link.capability.code,
                "name": link.capability.name,
                "category": link.capability.category,
                "proficiency": link.proficiency,
                "verified_at": _iso(link.verified_at),
                "expires_at": _iso(link.expires_at),
            }
            for link in capability_links
        ],
        "created_at": contractor.created_at.isoformat(),
        "updated_at": contractor.updated_at.isoformat(),
    }


def contractor_self_profile(contractor: OperationsContractor) -> dict[str, Any]:
    internal = contractor_internal(contractor)
    allowed = {
        "id",
        "display_name",
        "resource_type",
        "status",
        "availability",
        "contact_email",
        "contact_phone",
        "country_code",
        "region",
        "service_area",
        "certifications",
        "equipment",
        "document_refs",
        "capabilities",
    }
    profile = {key: value for key, value in internal.items() if key in allowed}
    profile["service_area"] = contractor_safe_value(profile["service_area"])
    profile["certifications"] = contractor_safe_documents(profile["certifications"])
    profile["equipment"] = contractor_safe_value(profile["equipment"])
    profile["document_refs"] = contractor_safe_documents(profile["document_refs"])
    return profile


def update_contractor_self(
    db: Session,
    *,
    actor: User,
    contractor: OperationsContractor,
    data: ContractorSelfUpdate,
) -> OperationsContractor:
    changes = data.model_dump(exclude_unset=True, mode="json")
    json_fields = {
        "service_area": "service_area_json",
        "equipment": "equipment_json",
    }
    for field, column in json_fields.items():
        if field in changes:
            setattr(contractor, column, _json(changes.pop(field) or []))
    for field, value in changes.items():
        setattr(contractor, field, value.strip() if isinstance(value, str) else value)
    contractor.updated_at = utc_now()
    _audit(
        db,
        actor=actor,
        action="operations.contractor.self_updated",
        resource_type="operations_contractor",
        resource_id=contractor.id,
        details={"fields": sorted(data.model_fields_set)},
    )
    return contractor


def create_contractor(
    db: Session, *, actor: User, data: ContractorCreate
) -> OperationsContractor:
    code = normalize_code(data.code, "CONTRACTOR")
    if db.query(OperationsContractor).filter(OperationsContractor.code == code).first():
        raise OperationsResourceError("contractor_exists", "Contractor code already exists")
    _validate_contractor_user(db, data.user_id)
    now = utc_now()
    contractor = OperationsContractor(
        id=str(uuid.uuid4()),
        code=code,
        user_id=data.user_id,
        display_name=data.display_name.strip(),
        legal_name=data.legal_name,
        resource_type=data.resource_type,
        status=data.status.value,
        availability=data.availability.value,
        contact_email=data.contact_email,
        contact_phone=data.contact_phone,
        country_code=data.country_code,
        region=data.region,
        service_area_json=_json(data.service_area),
        certifications_json=_json(data.certifications),
        insurance_json=_json(data.insurance),
        equipment_json=_json(data.equipment),
        document_refs_json=_json(data.document_refs),
        quality_score=data.quality_score,
        internal_notes=data.internal_notes,
        created_at=now,
        updated_at=now,
    )
    db.add(contractor)
    _replace_capabilities(db, contractor, data.capability_codes)
    db.flush()
    _audit(
        db,
        actor=actor,
        action="operations.contractor.created",
        resource_type="operations_contractor",
        resource_id=contractor.id,
        details={
            "code": contractor.code,
            "resource_type": contractor.resource_type,
            "capabilities": data.capability_codes,
        },
    )
    return contractor


def update_contractor(
    db: Session,
    *,
    actor: User,
    contractor: OperationsContractor,
    data: ContractorUpdate,
) -> OperationsContractor:
    changes = data.model_dump(exclude_unset=True, mode="json")
    capability_codes = changes.pop("capability_codes", None)
    if "user_id" in changes:
        _validate_contractor_user(
            db, changes["user_id"], contractor_id=contractor.id
        )
    json_fields = {
        "service_area": "service_area_json",
        "certifications": "certifications_json",
        "insurance": "insurance_json",
        "equipment": "equipment_json",
        "document_refs": "document_refs_json",
    }
    for field, column in json_fields.items():
        if field in changes:
            setattr(contractor, column, _json(changes.pop(field) or ([] if field != "insurance" else {})))
    for field, value in changes.items():
        setattr(contractor, field, value)
    if capability_codes is not None:
        _replace_capabilities(db, contractor, capability_codes)
    contractor.updated_at = utc_now()
    _audit(
        db,
        actor=actor,
        action="operations.contractor.updated",
        resource_type="operations_contractor",
        resource_id=contractor.id,
        details={"fields": sorted(data.model_fields_set)},
    )
    return contractor


def deactivate_contractor(
    db: Session, *, actor: User, contractor: OperationsContractor
) -> OperationsContractor:
    contractor.status = "INACTIVE"
    contractor.availability = "UNAVAILABLE"
    contractor.updated_at = utc_now()
    _audit(
        db,
        actor=actor,
        action="operations.contractor.deactivated",
        resource_type="operations_contractor",
        resource_id=contractor.id,
        details={"code": contractor.code},
    )
    return contractor


def list_contractors(
    db: Session,
    *,
    search: str | None = None,
    country_code: str | None = None,
    region: str | None = None,
    capability: str | None = None,
    resource_type: str | None = None,
    availability: str | None = None,
    status: str | None = None,
    limit: int = 200,
) -> list[OperationsContractor]:
    query = db.query(OperationsContractor)
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                OperationsContractor.code.ilike(term),
                OperationsContractor.display_name.ilike(term),
                OperationsContractor.legal_name.ilike(term),
            )
        )
    if country_code:
        query = query.filter(OperationsContractor.country_code == country_code.upper())
    if region:
        query = query.filter(OperationsContractor.region.ilike(f"%{region.strip()}%"))
    if resource_type:
        query = query.filter(OperationsContractor.resource_type == resource_type.upper())
    if availability:
        query = query.filter(OperationsContractor.availability == availability.upper())
    if status:
        query = query.filter(OperationsContractor.status == status.upper())
    if capability:
        query = (
            query.join(OperationsContractor.capability_links)
            .join(ContractorCapability.capability)
            .filter(OperationalCapability.code == normalize_code(capability, ""))
        )
    return (
        query.distinct()
        .order_by(OperationsContractor.display_name, OperationsContractor.id)
        .limit(limit)
        .all()
    )


def contractor_for_user(db: Session, user: User) -> OperationsContractor:
    contractor = (
        db.query(OperationsContractor)
        .filter(OperationsContractor.user_id == user.id)
        .one_or_none()
    )
    if contractor is None or contractor.status != "ACTIVE":
        raise OperationsResourceError(
            "contractor_access_denied", "No active contractor access profile is available"
        )
    return contractor


def assignment_restricted(assignment: ContractorAssignment) -> dict[str, Any]:
    location = contractor_safe_mapping(
        _value(assignment.location_json, {}),
        (
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
        ),
    )
    requirements = contractor_safe_mapping(
        _value(assignment.requirements_json, {}),
        (
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
        ),
    )
    upload_area = contractor_safe_mapping(
        _value(assignment.upload_area_json, {}),
        (
            "method",
            "scope",
            "dataset_id",
            "dataset_ids",
            "targets",
            "object_area",
            "accepted_content_types",
            "max_size_bytes",
        ),
    )
    required_documents = contractor_safe_documents(
        _value(assignment.required_documents_json, [])
    )
    document_profile = contractor_safe_documents(
        _value(assignment.contractor.document_refs_json, [])
    )
    return {
        "id": assignment.id,
        "assignment_number": assignment.assignment_number,
        "title": assignment.title,
        "status": assignment.status,
        "location": location,
        "window_start": _iso(assignment.window_start),
        "window_end": _iso(assignment.window_end),
        "requirements": requirements,
        "upload_area": upload_area,
        "required_documents": required_documents,
        "document_profile": document_profile,
        "lifecycle_version": assignment.lifecycle_version,
        "created_at": assignment.created_at.isoformat(),
        "updated_at": assignment.updated_at.isoformat(),
    }


def assignment_internal(assignment: ContractorAssignment) -> dict[str, Any]:
    return {
        **assignment_restricted(assignment),
        "location": _value(assignment.location_json, {}),
        "requirements": _value(assignment.requirements_json, {}),
        "upload_area": _value(assignment.upload_area_json, {}),
        "required_documents": _value(assignment.required_documents_json, []),
        "document_profile": _value(assignment.contractor.document_refs_json, []),
        "contractor_id": assignment.contractor_id,
        "order_id": assignment.order_id,
        "fulfilment_job_id": assignment.fulfilment_job_id,
        "agreed_cost_amount": assignment.agreed_cost_amount,
        "cost_currency": assignment.cost_currency,
        "internal_notes": assignment.internal_notes,
        "assigned_by_user_id": assignment.assigned_by_user_id,
    }


def create_assignment(
    db: Session, *, actor: User, data: AssignmentCreate
) -> ContractorAssignment:
    contractor = db.get(OperationsContractor, data.contractor_id)
    if contractor is None:
        raise OperationsResourceError("contractor_not_found", "Contractor was not found")
    if contractor.status != "ACTIVE" or contractor.availability == "UNAVAILABLE":
        raise OperationsResourceError(
            "contractor_unavailable", "Contractor is not available for assignment"
        )
    assignment_order_id = data.order_id
    if assignment_order_id and db.get(Order, assignment_order_id) is None:
        raise OperationsResourceError("order_not_found", "Order was not found")
    if data.fulfilment_job_id:
        job = db.get(FulfilmentJob, data.fulfilment_job_id)
        if job is None:
            raise OperationsResourceError("job_not_found", "Fulfilment job was not found")
        if assignment_order_id and job.order_id != assignment_order_id:
            raise OperationsResourceError(
                "assignment_job_mismatch", "Assignment order does not match the fulfilment job"
            )
        if job.assigned_contractor_id and job.assigned_contractor_id != contractor.id:
            raise OperationsResourceError(
                "assignment_job_mismatch", "Fulfilment job belongs to another contractor"
            )
        assignment_order_id = job.order_id
    now = utc_now()
    assignment_id = str(uuid.uuid4())
    upload_area = data.upload_area or {
        "method": "platform-upload",
        "scope": f"contractor-assignments/{assignment_id}",
    }
    assignment = ContractorAssignment(
        id=assignment_id,
        assignment_number=f"GVA-{now.year}-{assignment_id.split('-')[0].upper()}",
        contractor_id=contractor.id,
        order_id=assignment_order_id,
        fulfilment_job_id=data.fulfilment_job_id,
        title=data.title.strip(),
        status=AssignmentStatus.OFFERED.value,
        location_json=_json(data.location),
        window_start=data.window_start,
        window_end=data.window_end,
        requirements_json=_json(data.requirements),
        upload_area_json=_json(upload_area),
        required_documents_json=_json(data.required_documents),
        agreed_cost_amount=data.agreed_cost_amount,
        cost_currency=data.cost_currency,
        internal_notes=data.internal_notes,
        assigned_by_user_id=actor.id,
        created_at=now,
        updated_at=now,
    )
    db.add(assignment)
    db.flush()
    _audit(
        db,
        actor=actor,
        action="operations.assignment.created",
        resource_type="contractor_assignment",
        resource_id=assignment.id,
        details={
            "contractor_id": contractor.id,
            "order_id": assignment.order_id,
            "status": assignment.status,
        },
    )
    return assignment


def update_assignment(
    db: Session,
    *,
    actor: User,
    assignment: ContractorAssignment,
    data: AssignmentUpdate,
) -> ContractorAssignment:
    if data.expected_version is not None and assignment.lifecycle_version != data.expected_version:
        raise OperationsResourceError(
            "version_conflict", "Assignment changed since it was last read"
        )
    changes = data.model_dump(exclude_unset=True)
    changes.pop("expected_version", None)
    target_status = changes.pop("status", None)
    previous_status = assignment.status
    activate_linked_job = False
    revoke_linked_job = False
    if target_status:
        target_status = (
            target_status.value
            if isinstance(target_status, AssignmentStatus)
            else target_status
        )
        require_assignment_transition(assignment.status, target_status)
        assignment.status = target_status
        now = utc_now()
        if target_status == AssignmentStatus.ACCEPTED.value:
            assignment.accepted_at = assignment.accepted_at or now
            activate_linked_job = bool(
                assignment.fulfilment_job_id
                and previous_status != AssignmentStatus.ACCEPTED.value
            )
        elif target_status == AssignmentStatus.COMPLETED.value:
            assignment.completed_at = assignment.completed_at or now
        elif target_status in {
            AssignmentStatus.CANCELLED.value,
            AssignmentStatus.DECLINED.value,
        }:
            revoke_linked_job = bool(assignment.fulfilment_job_id)
    json_fields = {
        "location": "location_json",
        "requirements": "requirements_json",
        "upload_area": "upload_area_json",
        "required_documents": "required_documents_json",
    }
    for field, column in json_fields.items():
        if field in changes:
            setattr(assignment, column, _json(changes.pop(field) or ([] if field == "required_documents" else {})))
    for field, value in changes.items():
        setattr(assignment, field, value)
    if (
        assignment.window_start
        and assignment.window_end
        and assignment.window_end <= assignment.window_start
    ):
        raise OperationsResourceError(
            "invalid_assignment_window", "Assignment end must be after its start"
        )
    if assignment.agreed_cost_amount is not None and not assignment.cost_currency:
        raise OperationsResourceError(
            "assignment_currency_required", "Cost currency is required for an agreed cost"
        )
    if (activate_linked_job or revoke_linked_job) and assignment.fulfilment_job_id:
        from app.modules.operations.job_schemas import (
            JobAssignmentUpdate,
            JobScheduleUpdate,
        )
        from app.modules.operations.job_services import assign_job, schedule_job

        job = db.get(FulfilmentJob, assignment.fulfilment_job_id)
        if job is None:
            raise OperationsResourceError(
                "job_not_found", "Fulfilment job was not found"
            )
        if (
            job.assigned_user_id is not None
            or (
                job.assigned_contractor_id is not None
                and job.assigned_contractor_id != assignment.contractor_id
            )
        ):
            raise OperationsResourceError(
                "assignment_job_mismatch",
                "Fulfilment job belongs to another assignee",
            )
        if activate_linked_job:
            assign_job(
                db,
                actor=actor,
                job=job,
                data=JobAssignmentUpdate(contractor_id=assignment.contractor_id),
            )
            if (
                assignment.window_start
                and assignment.window_end
                and job.state in {"READY", "ASSIGNED", "SCHEDULED"}
            ):
                schedule_job(
                    db,
                    actor=actor,
                    job=job,
                    data=JobScheduleUpdate(
                        scheduled_start=assignment.window_start,
                        scheduled_end=assignment.window_end,
                        expected_version=job.lifecycle_version,
                    ),
                )
        elif job.assigned_contractor_id == assignment.contractor_id:
            if job.state == "SCHEDULED":
                schedule_job(
                    db,
                    actor=actor,
                    job=job,
                    data=JobScheduleUpdate(
                        clear_schedule=True,
                        expected_version=job.lifecycle_version,
                    ),
                )
            assign_job(
                db,
                actor=actor,
                job=job,
                data=JobAssignmentUpdate(
                    clear_assignment=True,
                    expected_version=job.lifecycle_version,
                ),
            )
    assignment.lifecycle_version = int(assignment.lifecycle_version or 0) + 1
    assignment.updated_at = utc_now()
    _audit(
        db,
        actor=actor,
        action="operations.assignment.updated",
        resource_type="contractor_assignment",
        resource_id=assignment.id,
        details={"fields": sorted(data.model_fields_set), "status": assignment.status},
    )
    return assignment


def decide_assignment(
    db: Session,
    *,
    actor: User,
    contractor: OperationsContractor,
    assignment: ContractorAssignment,
    decision: str,
    expected_version: int | None,
) -> ContractorAssignment:
    if assignment.contractor_id != contractor.id:
        raise OperationsResourceError("assignment_not_found", "Assignment was not found")
    payload = AssignmentUpdate(
        status=AssignmentStatus(decision), expected_version=expected_version
    )
    return update_assignment(db, actor=actor, assignment=assignment, data=payload)


__all__ = [
    "assignment_internal",
    "assignment_restricted",
    "capability_out",
    "contractor_for_user",
    "contractor_internal",
    "contractor_self_profile",
    "create_assignment",
    "create_capability",
    "create_contractor",
    "deactivate_contractor",
    "decide_assignment",
    "list_contractors",
    "update_assignment",
    "update_capability",
    "update_contractor",
    "update_contractor_self",
]
