"""Domain rules for private GeoVision operational resources."""

from __future__ import annotations

from enum import Enum
import re
from typing import Any


class ContractorStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ON_HOLD = "ON_HOLD"
    INACTIVE = "INACTIVE"
    BLOCKED = "BLOCKED"


class ContractorAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    LIMITED = "LIMITED"
    UNAVAILABLE = "UNAVAILABLE"


class ContractorResourceType(str, Enum):
    EMPLOYEE = "EMPLOYEE"
    FREELANCER = "FREELANCER"
    PARTNER_COMPANY = "PARTNER_COMPANY"
    FIELD_TECHNICIAN = "FIELD_TECHNICIAN"
    DRONE_OPERATOR = "DRONE_OPERATOR"
    SECTOR_SPECIALIST = "SECTOR_SPECIALIST"


_LEGACY_RESOURCE_TYPES = {
    "PILOT": ContractorResourceType.DRONE_OPERATOR.value,
    "TECHNICIAN": ContractorResourceType.FIELD_TECHNICIAN.value,
}


def normalize_contractor_resource_type(value: str) -> str:
    normalized = value.strip().upper().replace(" ", "_")
    normalized = _LEGACY_RESOURCE_TYPES.get(normalized, normalized)
    return ContractorResourceType(normalized).value


class AssignmentStatus(str, Enum):
    OFFERED = "OFFERED"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class JobPriority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


class JobState(str, Enum):
    PLANNED = "PLANNED"
    READY = "READY"
    BLOCKED = "BLOCKED"
    ASSIGNED = "ASSIGNED"
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_INPUT = "WAITING_INPUT"
    QA_REVIEW = "QA_REVIEW"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class ServiceRequestStatus(str, Enum):
    """Customer-visible service lifecycle states persisted by Operations."""

    SUBMITTED = "submitted"
    SCHEDULED = "scheduled"
    IN_FIELD = "in_field"
    PROCESSING = "processing"
    RESULTS_READY = "results_ready"
    DELIVERED = "delivered"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


STANDARD_JOB_TYPES = frozenset(
    {
        "FLIGHT_CAPTURE",
        "SATELLITE_ACQUISITION",
        "SENSOR_INSTALLATION",
        "PROCESS_DATA",
        "ANALYST_REVIEW",
        "SPECIALIST_REVIEW",
        "DELIVER_PRODUCT",
        "PUBLISH_REPORT",
    }
)


_JOB_TRANSITIONS = {
    JobState.PLANNED: frozenset(
        {JobState.READY, JobState.BLOCKED, JobState.CANCELLED}
    ),
    JobState.READY: frozenset(
        {
            JobState.ASSIGNED,
            JobState.SCHEDULED,
            JobState.IN_PROGRESS,
            JobState.BLOCKED,
            JobState.CANCELLED,
        }
    ),
    JobState.ASSIGNED: frozenset(
        {
            JobState.SCHEDULED,
            JobState.IN_PROGRESS,
            JobState.BLOCKED,
            JobState.CANCELLED,
        }
    ),
    JobState.SCHEDULED: frozenset(
        {JobState.IN_PROGRESS, JobState.BLOCKED, JobState.CANCELLED}
    ),
    JobState.IN_PROGRESS: frozenset(
        {
            JobState.WAITING_INPUT,
            JobState.QA_REVIEW,
            JobState.COMPLETED,
            JobState.BLOCKED,
            JobState.FAILED,
            JobState.CANCELLED,
        }
    ),
    JobState.WAITING_INPUT: frozenset(
        {
            JobState.READY,
            JobState.IN_PROGRESS,
            JobState.BLOCKED,
            JobState.CANCELLED,
        }
    ),
    JobState.QA_REVIEW: frozenset(
        {
            JobState.IN_PROGRESS,
            JobState.COMPLETED,
            JobState.BLOCKED,
            JobState.FAILED,
        }
    ),
    JobState.BLOCKED: frozenset(
        {
            JobState.READY,
            JobState.ASSIGNED,
            JobState.SCHEDULED,
            JobState.IN_PROGRESS,
            JobState.CANCELLED,
            JobState.FAILED,
        }
    ),
    JobState.COMPLETED: frozenset(),
    JobState.CANCELLED: frozenset(),
    JobState.FAILED: frozenset(),
}


_ASSIGNMENT_TRANSITIONS = {
    AssignmentStatus.OFFERED: frozenset(
        {AssignmentStatus.ACCEPTED, AssignmentStatus.DECLINED, AssignmentStatus.CANCELLED}
    ),
    AssignmentStatus.ACCEPTED: frozenset(
        {AssignmentStatus.ACTIVE, AssignmentStatus.CANCELLED}
    ),
    AssignmentStatus.ACTIVE: frozenset(
        {AssignmentStatus.COMPLETED, AssignmentStatus.CANCELLED}
    ),
    AssignmentStatus.DECLINED: frozenset(),
    AssignmentStatus.COMPLETED: frozenset(),
    AssignmentStatus.CANCELLED: frozenset(),
}


_SERVICE_REQUEST_TRANSITIONS = {
    ServiceRequestStatus.SUBMITTED: frozenset(
        {
            ServiceRequestStatus.SCHEDULED,
            ServiceRequestStatus.IN_FIELD,
            ServiceRequestStatus.PROCESSING,
            ServiceRequestStatus.RESULTS_READY,
            ServiceRequestStatus.DELIVERED,
            ServiceRequestStatus.COMPLETED,
            ServiceRequestStatus.CANCELLED,
            ServiceRequestStatus.REJECTED,
        }
    ),
    ServiceRequestStatus.SCHEDULED: frozenset(
        {
            ServiceRequestStatus.IN_FIELD,
            ServiceRequestStatus.PROCESSING,
            ServiceRequestStatus.RESULTS_READY,
            ServiceRequestStatus.DELIVERED,
            ServiceRequestStatus.COMPLETED,
            ServiceRequestStatus.CANCELLED,
            ServiceRequestStatus.REJECTED,
        }
    ),
    ServiceRequestStatus.IN_FIELD: frozenset(
        {
            ServiceRequestStatus.PROCESSING,
            ServiceRequestStatus.RESULTS_READY,
            ServiceRequestStatus.DELIVERED,
            ServiceRequestStatus.COMPLETED,
            ServiceRequestStatus.CANCELLED,
            ServiceRequestStatus.REJECTED,
        }
    ),
    ServiceRequestStatus.PROCESSING: frozenset(
        {
            ServiceRequestStatus.RESULTS_READY,
            ServiceRequestStatus.DELIVERED,
            ServiceRequestStatus.COMPLETED,
            ServiceRequestStatus.CANCELLED,
            ServiceRequestStatus.REJECTED,
        }
    ),
    ServiceRequestStatus.RESULTS_READY: frozenset(
        {ServiceRequestStatus.DELIVERED, ServiceRequestStatus.COMPLETED}
    ),
    ServiceRequestStatus.DELIVERED: frozenset({ServiceRequestStatus.COMPLETED}),
    ServiceRequestStatus.COMPLETED: frozenset(),
    ServiceRequestStatus.CANCELLED: frozenset(),
    ServiceRequestStatus.REJECTED: frozenset(),
}


class OperationsResourceError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def normalize_code(value: str, fallback: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", "_", str(value or "").strip().upper()).strip("_")
    return (normalized or fallback)[:80]


def require_assignment_transition(current: str, target: str) -> None:
    try:
        current_status = AssignmentStatus(current)
        target_status = AssignmentStatus(target)
    except ValueError as exc:
        raise OperationsResourceError(
            "invalid_assignment_status", "Assignment status is not supported"
        ) from exc
    if target_status == current_status:
        return
    if target_status not in _ASSIGNMENT_TRANSITIONS[current_status]:
        raise OperationsResourceError(
            "invalid_assignment_transition",
            f"Assignment cannot move from {current_status.value} to {target_status.value}",
        )


def require_job_transition(current: str, target: str) -> None:
    try:
        current_state = JobState(current)
        target_state = JobState(target)
    except ValueError as exc:
        raise OperationsResourceError(
            "invalid_job_state", "Fulfilment job state is not supported"
        ) from exc
    if target_state == current_state:
        return
    if target_state not in _JOB_TRANSITIONS[current_state]:
        raise OperationsResourceError(
            "invalid_job_transition",
            f"Fulfilment job cannot move from {current_state.value} to {target_state.value}",
        )


def require_service_request_transition(current: str, target: str) -> None:
    """Reject lifecycle regressions and changes away from terminal states."""

    try:
        current_status = ServiceRequestStatus(current)
        target_status = ServiceRequestStatus(target)
    except ValueError as exc:
        raise OperationsResourceError(
            "invalid_service_request_status",
            "Service request status is not supported",
        ) from exc
    if target_status == current_status:
        return
    if target_status not in _SERVICE_REQUEST_TRANSITIONS[current_status]:
        raise OperationsResourceError(
            "invalid_service_request_transition",
            "Service request cannot move "
            f"from {current_status.value} to {target_status.value}",
        )


_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "private_key",
    "credential",
    "connection_string",
)


def reject_sensitive_keys(value: Any, path: str = "metadata") -> Any:
    """Reject accidental credentials while allowing harmless document references."""

    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if any(part in normalized for part in _SENSITIVE_KEY_PARTS):
                raise ValueError(f"{path} cannot contain credential-like key '{key}'")
            reject_sensitive_keys(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            reject_sensitive_keys(nested, f"{path}[{index}]")
    return value


_CONTRACTOR_PRIVATE_KEY_PARTS = (
    "assigned_by",
    "billing",
    "contractor_id",
    "cost",
    "customer",
    "internal",
    "margin",
    "order_id",
    "organization",
    "payment",
    "price",
    "provider",
    "rate",
    "reviewer",
    "secret",
    "staff",
    "supplier",
    "token",
    "user_id",
    "workspace",
)


def contractor_safe_value(value: Any) -> Any:
    """Recursively remove staff/customer metadata from an approved field."""

    if isinstance(value, dict):
        return {
            key: contractor_safe_value(nested)
            for key, nested in value.items()
            if not any(
                part in str(key).strip().lower()
                for part in _CONTRACTOR_PRIVATE_KEY_PARTS
            )
        }
    if isinstance(value, list):
        return [contractor_safe_value(item) for item in value]
    return value


def contractor_safe_mapping(value: Any, allowed: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        key: contractor_safe_value(value[key])
        for key in allowed
        if key in value
    }


def contractor_safe_documents(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    allowed = (
        "document_id",
        "type",
        "name",
        "label",
        "filename",
        "status",
        "required",
        "issuer",
        "issued_at",
        "uploaded_at",
        "valid_from",
        "valid_until",
        "expires_at",
    )
    return [
        contractor_safe_mapping(item, allowed)
        for item in value
        if isinstance(item, dict)
    ]


__all__ = [
    "AssignmentStatus",
    "ContractorAvailability",
    "ContractorStatus",
    "JobPriority",
    "JobState",
    "OperationsResourceError",
    "ServiceRequestStatus",
    "STANDARD_JOB_TYPES",
    "contractor_safe_documents",
    "contractor_safe_mapping",
    "contractor_safe_value",
    "normalize_code",
    "reject_sensitive_keys",
    "require_assignment_transition",
    "require_job_transition",
    "require_service_request_transition",
]
