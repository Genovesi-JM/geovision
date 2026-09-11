"""Read-only internal Operations and contractor experience projections."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.integration import sanitize_integration_message
from app.core.time import utc_now
from app.models import (
    Acquisition,
    Asset,
    Company,
    ContractorAssignment,
    EventOutbox,
    FulfilmentJob,
    IntegrationOutbox,
    NotificationDelivery,
    OperationsContractor,
    Order,
    ProcessingJob,
    Report,
    User,
)
from app.modules.operations.experience_schemas import (
    ContractorExperienceOut,
    InternalCapability,
    OperationsDashboardOut,
    OperationsExperienceOut,
    OperationsQueuesOut,
)
from app.modules.organizations.domain import internal_permissions
from app.modules.organizations.services import active_internal_roles


_CAPABILITY_ORDER: tuple[InternalCapability, ...] = (
    "dashboard",
    "organizations",
    "assets",
    "orders",
    "jobs",
    "missions",
    "processing",
    "reports_qa",
    "contractors",
    "inventory",
    "finance_sync",
    "integrations",
    "system_health",
)

_NAVIGATION = (
    ("dashboard", "Resumen", "/admin.html?view=dashboard"),
    ("organizations", "Clientes y organizaciones", "/admin.html?view=organizations"),
    ("assets", "Activos", "/admin.html?view=assets"),
    ("orders", "Pedidos", "/admin.html?view=orders"),
    ("jobs", "Tareas", "/admin.html?view=jobs"),
    ("missions", "Misiones", "/admin.html?view=missions"),
    ("processing", "Procesamiento", "/admin.html?view=processing"),
    ("reports_qa", "Calidad de informes", "/admin.html?view=reports-qa"),
    ("contractors", "Colaboradores", "/admin.html?view=contractors"),
    (
        "inventory",
        "Proveedores e inventario",
        "/admin.html?view=inventory",
    ),
    ("finance_sync", "Sincronización financiera", "/admin.html?view=finance-sync"),
    ("integrations", "Integraciones", "/admin.html?view=integrations"),
    ("system_health", "Estado del sistema", "/admin.html?view=system-health"),
)

# Finance staff receive the ERP accounting/commerce slice only. Integration
# administrators may inspect every integration domain queued in the shared table.
_FINANCE_INTEGRATION_RESOURCE_TYPES = frozenset(
    {"order", "invoice", "payment", "purchase", "stock"}
)


def _integration_scope_filters(
    capabilities: set[InternalCapability],
) -> list[Any]:
    if "integrations" in capabilities:
        return []
    if "finance_sync" in capabilities:
        return [
            IntegrationOutbox.aggregate_type.in_(
                _FINANCE_INTEGRATION_RESOURCE_TYPES
            )
        ]
    return [IntegrationOutbox.id.is_(None)]


def internal_actor_contract(
    db: Session,
    user: User,
) -> tuple[list[str], list[str], list[InternalCapability]]:
    roles = sorted(active_internal_roles(db, user))
    permissions = sorted(internal_permissions(roles))
    available = set(permissions)
    flags: dict[InternalCapability, bool] = {
        "dashboard": bool(roles),
        "organizations": bool(
            available.intersection(
                {"platform:admin", "operations:access", "support:access", "sales:internal"}
            )
        ),
        "assets": bool(
            available.intersection(
                {"platform:admin", "operations:access", "analytics:review", "support:access"}
            )
        ),
        "orders": bool(
            available.intersection(
                {
                    "platform:admin",
                    "operations:access",
                    "sales:internal",
                    "billing:internal",
                    "inventory:internal",
                }
            )
        ),
        "jobs": bool(available.intersection({"platform:admin", "operations:access"})),
        "missions": bool(
            available.intersection(
                {"platform:admin", "operations:access", "analytics:review"}
            )
        ),
        "processing": bool(
            available.intersection({"platform:admin", "operations:access"})
        ),
        "reports_qa": bool(
            available.intersection({"platform:admin", "analytics:review"})
        ),
        "contractors": bool(
            available.intersection({"platform:admin", "operations:access"})
        ),
        "inventory": bool(
            available.intersection(
                {
                    "platform:admin",
                    "operations:access",
                    "inventory:internal",
                    "sales:internal",
                }
            )
        ),
        "finance_sync": bool(
            available.intersection({"platform:admin", "billing:internal"})
        ),
        "integrations": "platform:admin" in available,
        "system_health": bool(
            available.intersection(
                {"platform:admin", "operations:access", "support:access"}
            )
        ),
    }
    capabilities = [item for item in _CAPABILITY_ORDER if flags[item]]
    return roles, permissions, capabilities


def operations_experience(db: Session, user: User) -> OperationsExperienceOut:
    roles, permissions, capabilities = internal_actor_contract(db, user)
    visible = set(capabilities)
    return OperationsExperienceOut(
        actor={
            "user_id": user.id,
            "roles": roles,
            "permissions": permissions,
        },
        capabilities=capabilities,
        navigation=[
            {
                "key": key,
                "label": label,
                "path": path,
                "capability": key,
            }
            for key, label, path in _NAVIGATION
            if key in visible
        ],
        generated_at=utc_now(),
    )


def _count(db: Session, model, *filters: Any) -> int:
    return db.query(model).filter(*filters).count()


def _recent_items(
    db: Session,
    capabilities: set[InternalCapability],
    *,
    limit: int = 12,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if "jobs" in capabilities:
        for row in (
            db.query(FulfilmentJob)
            .order_by(FulfilmentJob.updated_at.desc())
            .limit(limit)
            .all()
        ):
            items.append(
                {
                    "target_type": "JOB",
                    "target_id": row.id,
                    "title": row.title,
                    "status": row.state,
                    "updated_at": row.updated_at,
                }
            )
    if "processing" in capabilities:
        for row in (
            db.query(ProcessingJob)
            .order_by(ProcessingJob.updated_at.desc())
            .limit(limit)
            .all()
        ):
            items.append(
                {
                    "target_type": "PROCESSING",
                    "target_id": row.id,
                    "title": f"Processing {row.id[:8]}",
                    "status": row.status,
                    "updated_at": row.updated_at,
                }
            )
    if "reports_qa" in capabilities:
        for row in (
            db.query(Report)
            .filter(Report.status.in_(("REVIEW_REQUIRED", "APPROVED")))
            .order_by(Report.updated_at.desc())
            .limit(limit)
            .all()
        ):
            items.append(
                {
                    "target_type": "REPORT",
                    "target_id": row.id,
                    "title": row.title,
                    "status": row.status,
                    "updated_at": row.updated_at,
                }
            )
    items.sort(key=lambda item: item["updated_at"], reverse=True)
    return items[:limit]


def operations_dashboard(db: Session, user: User) -> OperationsDashboardOut:
    _, _, actor_capabilities = internal_actor_contract(db, user)
    capabilities = set(actor_capabilities)
    can_integrations = bool(capabilities.intersection({"finance_sync", "integrations"}))

    failed_processing = (
        _count(db, ProcessingJob, ProcessingJob.status == "FAILED")
        if "processing" in capabilities
        else 0
    )
    integration_dead_letters = (
        _count(
            db,
            IntegrationOutbox,
            IntegrationOutbox.status.in_(("dead_letter", "failed_terminal")),
            *_integration_scope_filters(capabilities),
        )
        if can_integrations
        else 0
    )
    health_processing_failures = (
        _count(db, ProcessingJob, ProcessingJob.status == "FAILED")
        if "system_health" in capabilities
        else 0
    )
    health_integration_dead_letters = (
        _count(
            db,
            IntegrationOutbox,
            IntegrationOutbox.status.in_(("dead_letter", "failed_terminal")),
        )
        if "system_health" in capabilities
        else 0
    )
    event_dead_letters = (
        _count(db, EventOutbox, EventOutbox.status == "dead_letter")
        if "system_health" in capabilities
        else 0
    )
    notification_dead_letters = (
        _count(
            db,
            NotificationDelivery,
            NotificationDelivery.status == "DEAD_LETTER",
        )
        if "system_health" in capabilities
        else 0
    )
    health = None
    if "system_health" in capabilities:
        degraded = any(
            (
                event_dead_letters,
                notification_dead_letters,
                health_integration_dead_letters,
                health_processing_failures,
            )
        )
        health = {
            "status": "DEGRADED" if degraded else "HEALTHY",
            "event_dead_letters": event_dead_letters,
            "notification_dead_letters": notification_dead_letters,
            "integration_dead_letters": health_integration_dead_letters,
            "processing_failures": health_processing_failures,
        }

    return OperationsDashboardOut(
        generated_at=utc_now(),
        totals={
            "organizations": (
                _count(db, Company, Company.status != "suspended")
                if "organizations" in capabilities
                else 0
            ),
            "assets": (
                _count(db, Asset, Asset.status != "archived")
                if "assets" in capabilities
                else 0
            ),
            "orders": _count(db, Order) if "orders" in capabilities else 0,
            "jobs": _count(db, FulfilmentJob) if "jobs" in capabilities else 0,
            "missions": _count(db, Acquisition) if "missions" in capabilities else 0,
            "processing_jobs": (
                _count(db, ProcessingJob) if "processing" in capabilities else 0
            ),
            "reports_review": (
                _count(db, Report, Report.status == "REVIEW_REQUIRED")
                if "reports_qa" in capabilities
                else 0
            ),
            "contractors": (
                _count(db, OperationsContractor, OperationsContractor.status == "ACTIVE")
                if "contractors" in capabilities
                else 0
            ),
        },
        attention={
            "failed_jobs": (
                _count(db, FulfilmentJob, FulfilmentJob.state == "FAILED")
                if "jobs" in capabilities
                else 0
            ),
            "blocked_jobs": (
                _count(db, FulfilmentJob, FulfilmentJob.state == "BLOCKED")
                if "jobs" in capabilities
                else 0
            ),
            "failed_processing": failed_processing,
            "retry_wait_processing": (
                _count(db, ProcessingJob, ProcessingJob.status == "RETRY_WAIT")
                if "processing" in capabilities
                else 0
            ),
            "needs_review_processing": (
                _count(db, ProcessingJob, ProcessingJob.status == "NEEDS_REVIEW")
                if "processing" in capabilities
                else 0
            ),
            "reports_awaiting_review": (
                _count(db, Report, Report.status == "REVIEW_REQUIRED")
                if "reports_qa" in capabilities
                else 0
            ),
            "dead_letter_integrations": integration_dead_letters,
        },
        health=health,
        recent=_recent_items(db, capabilities),
    )


def _assignee_type(job: FulfilmentJob) -> str:
    if job.assigned_contractor_id:
        return "CONTRACTOR"
    if job.assigned_user_id:
        return "STAFF"
    return "UNASSIGNED"


def operations_queues(
    db: Session,
    user: User,
    *,
    limit: int,
) -> OperationsQueuesOut:
    _, _, actor_capabilities = internal_actor_contract(db, user)
    capabilities = set(actor_capabilities)
    jobs = []
    processing = []
    reports = []
    integrations = []
    if "jobs" in capabilities:
        rows = (
            db.query(FulfilmentJob)
            .filter(
                FulfilmentJob.state.in_(
                    (
                        "READY",
                        "BLOCKED",
                        "ASSIGNED",
                        "SCHEDULED",
                        "IN_PROGRESS",
                        "WAITING_INPUT",
                        "QA_REVIEW",
                        "FAILED",
                    )
                )
            )
            .order_by(FulfilmentJob.updated_at.desc(), FulfilmentJob.id.desc())
            .limit(limit)
            .all()
        )
        jobs = [
            {
                "id": row.id,
                "job_number": row.job_number,
                "title": row.title,
                "state": row.state,
                "priority": row.priority,
                "scheduled_start": row.scheduled_start,
                "assignee_type": _assignee_type(row),
                "updated_at": row.updated_at,
            }
            for row in rows
        ]
    if "processing" in capabilities:
        rows = (
            db.query(ProcessingJob)
            .filter(
                ProcessingJob.status.in_(
                    (
                        "REQUESTED",
                        "VALIDATING",
                        "SUBMITTED",
                        "RUNNING",
                        "RETRY_WAIT",
                        "NEEDS_REVIEW",
                        "FAILED",
                    )
                )
            )
            .order_by(ProcessingJob.updated_at.desc(), ProcessingJob.id.desc())
            .limit(limit)
            .all()
        )
        processing = [
            {
                "id": row.id,
                "status": row.status,
                "stage": row.stage,
                "retry_count": row.retry_count,
                "max_retries": row.max_retries,
                "retries_remaining": max(0, row.max_retries - row.retry_count),
                "next_poll_at": row.next_poll_at,
                "error_code": row.error_code,
                "error_message": (
                    sanitize_integration_message(row.error_message)
                    if row.error_message
                    else None
                ),
                "updated_at": row.updated_at,
            }
            for row in rows
        ]
    if "reports_qa" in capabilities:
        rows = (
            db.query(Report)
            .filter(Report.status.in_(("REVIEW_REQUIRED", "APPROVED")))
            .order_by(Report.updated_at.desc(), Report.id.desc())
            .limit(limit)
            .all()
        )
        reports = [
            {
                "id": row.id,
                "title": row.title,
                "status": row.status,
                "qa_level": row.qa_level,
                "revision": row.revision,
                "lifecycle_version": row.lifecycle_version,
                "asset_id": row.asset_id,
                "updated_at": row.updated_at,
            }
            for row in rows
        ]
    if capabilities.intersection({"finance_sync", "integrations"}):
        rows = (
            db.query(IntegrationOutbox)
            .filter(
                IntegrationOutbox.status.in_(
                    (
                        "pending",
                        "processing",
                        "failed",
                        "failed_terminal",
                        "dead_letter",
                    )
                ),
                *_integration_scope_filters(capabilities),
            )
            .order_by(IntegrationOutbox.updated_at.desc(), IntegrationOutbox.id.desc())
            .limit(limit)
            .all()
        )
        integrations = [
            {
                "id": row.id,
                "provider": row.provider,
                "resource_type": row.aggregate_type,
                "status": row.status,
                "attempts": row.attempts,
                "max_attempts": row.max_attempts,
                "retries_remaining": max(0, row.max_attempts - row.attempts),
                "next_attempt_at": row.next_attempt_at,
                "error_code": row.last_error_code,
                "error_message": (
                    sanitize_integration_message(row.last_error)
                    if row.last_error
                    else None
                ),
                "updated_at": row.updated_at,
            }
            for row in rows
        ]
    return OperationsQueuesOut(
        generated_at=utc_now(),
        jobs=jobs,
        processing=processing,
        reports_qa=reports,
        integrations=integrations,
    )


def contractor_experience(
    db: Session,
    contractor: OperationsContractor,
) -> ContractorExperienceOut:
    jobs = db.query(FulfilmentJob).filter(
        FulfilmentJob.assigned_contractor_id == contractor.id
    )
    offered = _count(
        db,
        ContractorAssignment,
        ContractorAssignment.contractor_id == contractor.id,
        ContractorAssignment.status == "OFFERED",
    )
    capabilities = ["my_jobs", "job_status", "uploads", "profile", "documents"]
    navigation = (
        ("my_jobs", "Mis tareas", "/contractor.html?view=jobs"),
        ("profile", "Mi perfil", "/contractor.html?view=profile"),
        ("documents", "Documentación", "/contractor.html?view=documents"),
    )
    return ContractorExperienceOut(
        contractor={
            "id": contractor.id,
            "display_name": contractor.display_name,
            "resource_type": contractor.resource_type,
            "status": contractor.status,
            "availability": contractor.availability,
        },
        capabilities=capabilities,
        navigation=[
            {"key": key, "label": label, "path": path, "capability": key}
            for key, label, path in navigation
        ],
        job_counts={
            "offered": offered,
            "scheduled": jobs.filter(FulfilmentJob.state == "SCHEDULED").count(),
            "active": jobs.filter(
                FulfilmentJob.state.in_(
                    ("ASSIGNED", "SCHEDULED", "IN_PROGRESS", "WAITING_INPUT")
                )
            ).count(),
            "review": jobs.filter(FulfilmentJob.state == "QA_REVIEW").count(),
            "completed": jobs.filter(FulfilmentJob.state == "COMPLETED").count(),
        },
        generated_at=utc_now(),
    )


__all__ = [
    "contractor_experience",
    "internal_actor_contract",
    "operations_dashboard",
    "operations_experience",
    "operations_queues",
]
