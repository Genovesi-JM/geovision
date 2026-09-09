"""Provider-neutral acquisition lifecycle rules."""

from __future__ import annotations

from enum import Enum
import re
from typing import Any


class AcquisitionType(str, Enum):
    DRONE = "DRONE"
    SATELLITE = "SATELLITE"
    IOT = "IOT"
    MANUAL_INSPECTION = "MANUAL_INSPECTION"
    THIRD_PARTY_DATA = "THIRD_PARTY_DATA"


class AcquisitionState(str, Enum):
    DRAFT = "DRAFT"
    PLANNED = "PLANNED"
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    DATA_CAPTURED = "DATA_CAPTURED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    NEEDS_REFLIGHT = "NEEDS_REFLIGHT"


_TRANSITIONS = {
    AcquisitionState.DRAFT: frozenset(
        {AcquisitionState.PLANNED, AcquisitionState.CANCELLED}
    ),
    AcquisitionState.PLANNED: frozenset(
        {
            AcquisitionState.SCHEDULED,
            AcquisitionState.IN_PROGRESS,
            AcquisitionState.CANCELLED,
            AcquisitionState.FAILED,
        }
    ),
    AcquisitionState.SCHEDULED: frozenset(
        {
            AcquisitionState.IN_PROGRESS,
            AcquisitionState.CANCELLED,
            AcquisitionState.FAILED,
        }
    ),
    AcquisitionState.IN_PROGRESS: frozenset(
        {
            AcquisitionState.DATA_CAPTURED,
            AcquisitionState.NEEDS_REFLIGHT,
            AcquisitionState.CANCELLED,
            AcquisitionState.FAILED,
        }
    ),
    AcquisitionState.DATA_CAPTURED: frozenset(
        {
            AcquisitionState.PROCESSING,
            AcquisitionState.COMPLETED,
            AcquisitionState.NEEDS_REFLIGHT,
            AcquisitionState.FAILED,
        }
    ),
    AcquisitionState.PROCESSING: frozenset(
        {
            AcquisitionState.COMPLETED,
            AcquisitionState.NEEDS_REFLIGHT,
            AcquisitionState.FAILED,
        }
    ),
    AcquisitionState.NEEDS_REFLIGHT: frozenset(
        {AcquisitionState.PLANNED, AcquisitionState.CANCELLED}
    ),
    AcquisitionState.COMPLETED: frozenset(),
    AcquisitionState.CANCELLED: frozenset(),
    AcquisitionState.FAILED: frozenset(),
}


class AcquisitionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def require_acquisition_transition(current: str, target: str) -> None:
    try:
        current_state = AcquisitionState(current)
        target_state = AcquisitionState(target)
    except ValueError as exc:
        raise AcquisitionError("invalid_state", "Acquisition state is not supported") from exc
    if current_state == target_state:
        return
    if target_state not in _TRANSITIONS[current_state]:
        raise AcquisitionError(
            "invalid_transition",
            f"Acquisition cannot move from {current_state.value} to {target_state.value}",
        )


_SENSITIVE_KEY = re.compile(
    r"(^|_)(password|passwd|secret|token|api_key|authorization|credential|private_key)($|_)",
    re.IGNORECASE,
)


def reject_sensitive_metadata(value: Any, path: str = "metadata") -> Any:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = re.sub(r"[^A-Za-z0-9]+", "_", str(key)).strip("_")
            if _SENSITIVE_KEY.search(normalized):
                raise ValueError(f"{path} cannot contain credentials or secrets")
            reject_sensitive_metadata(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            reject_sensitive_metadata(nested, f"{path}[{index}]")
    return value


__all__ = [
    "AcquisitionError",
    "AcquisitionState",
    "AcquisitionType",
    "reject_sensitive_metadata",
    "require_acquisition_transition",
]
