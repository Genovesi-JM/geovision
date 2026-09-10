"""Lifecycle rules for recommendations and assigned operational actions."""

from __future__ import annotations

from enum import Enum


class ActionPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"
    CRITICAL = "CRITICAL"


class ActionStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    DISMISSED = "DISMISSED"
    CANCELLED = "CANCELLED"


_TRANSITIONS: dict[ActionStatus, frozenset[ActionStatus]] = {
    ActionStatus.OPEN: frozenset(
        {
            ActionStatus.IN_PROGRESS,
            ActionStatus.COMPLETED,
            ActionStatus.DISMISSED,
            ActionStatus.CANCELLED,
        }
    ),
    ActionStatus.IN_PROGRESS: frozenset(
        {ActionStatus.OPEN, ActionStatus.COMPLETED, ActionStatus.CANCELLED}
    ),
    ActionStatus.COMPLETED: frozenset(),
    ActionStatus.DISMISSED: frozenset({ActionStatus.OPEN}),
    ActionStatus.CANCELLED: frozenset(),
}


class ActionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def require_action_transition(current: str, target: str) -> None:
    try:
        current_status = ActionStatus(current)
        target_status = ActionStatus(target)
    except ValueError as exc:
        raise ActionError("invalid_status", "Action status is not supported") from exc
    if current_status == target_status:
        return
    if target_status not in _TRANSITIONS[current_status]:
        raise ActionError(
            "invalid_transition",
            f"Action cannot move from {current_status.value} to {target_status.value}",
        )


__all__ = [
    "ActionError",
    "ActionPriority",
    "ActionStatus",
    "require_action_transition",
]
