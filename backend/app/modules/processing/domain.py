"""Stable processing vocabulary and lifecycle rules."""

from __future__ import annotations

from enum import Enum
import re


class ProcessingJobState(str, Enum):
    REQUESTED = "REQUESTED"
    VALIDATING = "VALIDATING"
    SUBMITTED = "SUBMITTED"
    RUNNING = "RUNNING"
    RETRY_WAIT = "RETRY_WAIT"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL_PROCESSING_STATES = frozenset(
    {
        ProcessingJobState.NEEDS_REVIEW.value,
        ProcessingJobState.COMPLETED.value,
        ProcessingJobState.FAILED.value,
        ProcessingJobState.CANCELLED.value,
    }
)

PROCESSABLE_SOURCE_TYPES = frozenset(
    {"RGB_IMAGES", "MULTISPECTRAL_IMAGES", "THERMAL_IMAGES"}
)

SUPPORTED_PROCESSING_OUTPUTS = frozenset(
    {
        "ORTHOMOSAIC",
        "DSM",
        "DTM",
        "POINT_CLOUD",
        "MESH_3D",
        "NDVI",
        "NDRE",
        "GNDVI",
    }
)

_OUTPUT_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,79}$")


class ProcessingJobError(ValueError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(message)


def normalize_output_type(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "").strip())
    normalized = normalized.strip("_").upper()
    if not _OUTPUT_PATTERN.fullmatch(normalized):
        raise ValueError("processing output must be a stable uppercase identifier")
    if normalized not in SUPPORTED_PROCESSING_OUTPUTS:
        allowed = ", ".join(sorted(SUPPORTED_PROCESSING_OUTPUTS))
        raise ValueError(f"unsupported processing output; expected one of {allowed}")
    return normalized


def normalize_requested_outputs(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(normalize_output_type(value) for value in values))
    if not normalized:
        raise ValueError("at least one processing output is required")
    return normalized


__all__ = [
    "PROCESSABLE_SOURCE_TYPES",
    "SUPPORTED_PROCESSING_OUTPUTS",
    "TERMINAL_PROCESSING_STATES",
    "ProcessingJobError",
    "ProcessingJobState",
    "normalize_output_type",
    "normalize_requested_outputs",
]
