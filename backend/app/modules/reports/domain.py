"""Lifecycle and validation rules for canonical GeoVision reports."""

from __future__ import annotations

from enum import Enum
import re


class ReportStatus(str, Enum):
    GENERATING = "GENERATING"
    DRAFT = "DRAFT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    SUPERSEDED = "SUPERSEDED"


class ReportQALevel(str, Enum):
    AUTO_APPROVED = "AUTO_APPROVED"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    SPECIALIST_REVIEW = "SPECIALIST_REVIEW"


class ReportError(ValueError):
    """Stable, transport-neutral report failure."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


_TRANSITIONS = {
    ReportStatus.GENERATING: frozenset({ReportStatus.DRAFT, ReportStatus.APPROVED}),
    ReportStatus.DRAFT: frozenset(
        {ReportStatus.REVIEW_REQUIRED, ReportStatus.APPROVED}
    ),
    ReportStatus.REVIEW_REQUIRED: frozenset({ReportStatus.APPROVED}),
    ReportStatus.APPROVED: frozenset(
        {ReportStatus.REVIEW_REQUIRED, ReportStatus.PUBLISHED}
    ),
    ReportStatus.PUBLISHED: frozenset({ReportStatus.SUPERSEDED}),
    ReportStatus.SUPERSEDED: frozenset(),
}

_IDENTIFIER = re.compile(r"^[A-Z][A-Z0-9_]{1,79}$")


def normalize_report_type(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "").strip())
    normalized = normalized.strip("_").upper()
    if not _IDENTIFIER.fullmatch(normalized):
        raise ReportError(
            "invalid_report_type",
            "report_type must be a stable uppercase identifier",
        )
    return normalized


def require_report_transition(current: str, target: str) -> None:
    try:
        current_status = ReportStatus(current)
        target_status = ReportStatus(target)
    except ValueError as exc:
        raise ReportError("invalid_status", "Report status is not supported") from exc
    if current_status == target_status:
        return
    if target_status not in _TRANSITIONS[current_status]:
        raise ReportError(
            "invalid_transition",
            f"Report cannot move from {current_status.value} to {target_status.value}",
        )


__all__ = [
    "ReportError",
    "ReportQALevel",
    "ReportStatus",
    "normalize_report_type",
    "require_report_transition",
]
