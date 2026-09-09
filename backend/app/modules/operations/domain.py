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


class AssignmentStatus(str, Enum):
    OFFERED = "OFFERED"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


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


__all__ = [
    "AssignmentStatus",
    "ContractorAvailability",
    "ContractorStatus",
    "OperationsResourceError",
    "normalize_code",
    "reject_sensitive_keys",
    "require_assignment_transition",
]
