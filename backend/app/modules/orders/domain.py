"""Provider-independent order, fulfilment, and settlement domain values."""

from __future__ import annotations

from enum import Enum
from typing import Iterable


class OrderType(str, Enum):
    PHYSICAL = "PHYSICAL"
    SERVICE = "SERVICE"
    MONITORING = "MONITORING"
    MIXED = "MIXED"


class FulfilmentStatus(str, Enum):
    DRAFT = "DRAFT"
    QUOTED = "QUOTED"
    CONFIRMED = "CONFIRMED"
    PAYMENT_AUTHORIZED = "PAYMENT_AUTHORIZED"
    PAID = "PAID"
    SCHEDULING = "SCHEDULING"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    DATA_UPLOADED = "DATA_UPLOADED"
    PROCESSING = "PROCESSING"
    QA_REVIEW = "QA_REVIEW"
    RESULTS_READY = "RESULTS_READY"
    DELIVERED = "DELIVERED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    NEEDS_REFLIGHT = "NEEDS_REFLIGHT"
    ON_HOLD = "ON_HOLD"


class OrderPaymentStatus(str, Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    AUTHORIZED = "AUTHORIZED"
    PAID = "PAID"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
    REFUNDED = "REFUNDED"


TERMINAL_FULFILMENT_STATES = frozenset(
    {FulfilmentStatus.COMPLETED, FulfilmentStatus.CANCELLED, FulfilmentStatus.FAILED}
)


_TRANSITIONS: dict[FulfilmentStatus, frozenset[FulfilmentStatus]] = {
    FulfilmentStatus.DRAFT: frozenset(
        {FulfilmentStatus.QUOTED, FulfilmentStatus.CONFIRMED, FulfilmentStatus.CANCELLED}
    ),
    FulfilmentStatus.QUOTED: frozenset(
        {FulfilmentStatus.CONFIRMED, FulfilmentStatus.ON_HOLD, FulfilmentStatus.CANCELLED}
    ),
    FulfilmentStatus.CONFIRMED: frozenset(
        {
            FulfilmentStatus.PAYMENT_AUTHORIZED,
            FulfilmentStatus.PAID,
            FulfilmentStatus.SCHEDULING,
            FulfilmentStatus.ON_HOLD,
            FulfilmentStatus.CANCELLED,
        }
    ),
    FulfilmentStatus.PAYMENT_AUTHORIZED: frozenset(
        {
            FulfilmentStatus.PAID,
            FulfilmentStatus.SCHEDULING,
            FulfilmentStatus.ON_HOLD,
            FulfilmentStatus.CANCELLED,
            FulfilmentStatus.FAILED,
        }
    ),
    FulfilmentStatus.PAID: frozenset(
        {
            FulfilmentStatus.SCHEDULING,
            FulfilmentStatus.ASSIGNED,
            FulfilmentStatus.IN_PROGRESS,
            FulfilmentStatus.PROCESSING,
            FulfilmentStatus.DELIVERED,
            FulfilmentStatus.ON_HOLD,
            FulfilmentStatus.CANCELLED,
            FulfilmentStatus.FAILED,
        }
    ),
    FulfilmentStatus.SCHEDULING: frozenset(
        {
            FulfilmentStatus.ASSIGNED,
            FulfilmentStatus.IN_PROGRESS,
            FulfilmentStatus.ON_HOLD,
            FulfilmentStatus.CANCELLED,
            FulfilmentStatus.FAILED,
        }
    ),
    FulfilmentStatus.ASSIGNED: frozenset(
        {
            FulfilmentStatus.IN_PROGRESS,
            FulfilmentStatus.ON_HOLD,
            FulfilmentStatus.CANCELLED,
            FulfilmentStatus.FAILED,
        }
    ),
    FulfilmentStatus.IN_PROGRESS: frozenset(
        {
            FulfilmentStatus.DATA_UPLOADED,
            FulfilmentStatus.PROCESSING,
            FulfilmentStatus.RESULTS_READY,
            FulfilmentStatus.DELIVERED,
            FulfilmentStatus.NEEDS_REFLIGHT,
            FulfilmentStatus.ON_HOLD,
            FulfilmentStatus.FAILED,
        }
    ),
    FulfilmentStatus.DATA_UPLOADED: frozenset(
        {
            FulfilmentStatus.PROCESSING,
            FulfilmentStatus.NEEDS_REFLIGHT,
            FulfilmentStatus.ON_HOLD,
            FulfilmentStatus.FAILED,
        }
    ),
    FulfilmentStatus.PROCESSING: frozenset(
        {
            FulfilmentStatus.QA_REVIEW,
            FulfilmentStatus.RESULTS_READY,
            FulfilmentStatus.NEEDS_REFLIGHT,
            FulfilmentStatus.ON_HOLD,
            FulfilmentStatus.FAILED,
        }
    ),
    FulfilmentStatus.QA_REVIEW: frozenset(
        {
            FulfilmentStatus.PROCESSING,
            FulfilmentStatus.RESULTS_READY,
            FulfilmentStatus.NEEDS_REFLIGHT,
            FulfilmentStatus.ON_HOLD,
            FulfilmentStatus.FAILED,
        }
    ),
    FulfilmentStatus.RESULTS_READY: frozenset(
        {
            FulfilmentStatus.QA_REVIEW,
            FulfilmentStatus.DELIVERED,
            FulfilmentStatus.ON_HOLD,
            FulfilmentStatus.FAILED,
        }
    ),
    FulfilmentStatus.DELIVERED: frozenset({FulfilmentStatus.COMPLETED}),
    FulfilmentStatus.NEEDS_REFLIGHT: frozenset(
        {
            FulfilmentStatus.SCHEDULING,
            FulfilmentStatus.ASSIGNED,
            FulfilmentStatus.IN_PROGRESS,
            FulfilmentStatus.ON_HOLD,
            FulfilmentStatus.CANCELLED,
            FulfilmentStatus.FAILED,
        }
    ),
    FulfilmentStatus.ON_HOLD: frozenset(
        {
            FulfilmentStatus.PAID,
            FulfilmentStatus.SCHEDULING,
            FulfilmentStatus.ASSIGNED,
            FulfilmentStatus.IN_PROGRESS,
            FulfilmentStatus.DATA_UPLOADED,
            FulfilmentStatus.PROCESSING,
            FulfilmentStatus.QA_REVIEW,
            FulfilmentStatus.RESULTS_READY,
            FulfilmentStatus.CANCELLED,
            FulfilmentStatus.FAILED,
        }
    ),
    FulfilmentStatus.COMPLETED: frozenset(),
    FulfilmentStatus.CANCELLED: frozenset(),
    FulfilmentStatus.FAILED: frozenset(),
}


_LEGACY_STATUS = {
    FulfilmentStatus.DRAFT: "created",
    FulfilmentStatus.QUOTED: "created",
    FulfilmentStatus.CONFIRMED: "awaiting_payment",
    FulfilmentStatus.PAYMENT_AUTHORIZED: "awaiting_payment",
    FulfilmentStatus.PAID: "paid",
    FulfilmentStatus.SCHEDULING: "processing",
    FulfilmentStatus.ASSIGNED: "assigned",
    FulfilmentStatus.IN_PROGRESS: "in_progress",
    FulfilmentStatus.DATA_UPLOADED: "processing",
    FulfilmentStatus.PROCESSING: "processing",
    FulfilmentStatus.QA_REVIEW: "processing",
    FulfilmentStatus.RESULTS_READY: "processing",
    FulfilmentStatus.DELIVERED: "delivered",
    FulfilmentStatus.COMPLETED: "completed",
    FulfilmentStatus.CANCELLED: "cancelled",
    FulfilmentStatus.FAILED: "failed",
    FulfilmentStatus.NEEDS_REFLIGHT: "processing",
    FulfilmentStatus.ON_HOLD: "processing",
}


_CANONICAL_FROM_LEGACY = {
    "pending": FulfilmentStatus.DRAFT,
    "created": FulfilmentStatus.CONFIRMED,
    "awaiting_payment": FulfilmentStatus.CONFIRMED,
    "paid": FulfilmentStatus.PAID,
    "processing": FulfilmentStatus.PROCESSING,
    "dispatched": FulfilmentStatus.IN_PROGRESS,
    "assigned": FulfilmentStatus.ASSIGNED,
    "in_progress": FulfilmentStatus.IN_PROGRESS,
    "delivered": FulfilmentStatus.DELIVERED,
    "completed": FulfilmentStatus.COMPLETED,
    "refunded": FulfilmentStatus.COMPLETED,
    "partially_refunded": FulfilmentStatus.COMPLETED,
    "cancelled": FulfilmentStatus.CANCELLED,
    "failed": FulfilmentStatus.FAILED,
}


class OrderLifecycleError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def transition_allowed(current: FulfilmentStatus, target: FulfilmentStatus) -> bool:
    return target == current or target in _TRANSITIONS[current]


def require_transition(current: FulfilmentStatus, target: FulfilmentStatus) -> None:
    if not transition_allowed(current, target):
        raise OrderLifecycleError(
            "invalid_transition",
            f"Order cannot move from {current.value} to {target.value}",
        )


def legacy_status(status: FulfilmentStatus | str) -> str:
    value = status if isinstance(status, FulfilmentStatus) else FulfilmentStatus(status)
    return _LEGACY_STATUS[value]


def fulfilment_from_legacy(status: str | None) -> FulfilmentStatus:
    return _CANONICAL_FROM_LEGACY.get(
        str(status or "").strip().lower(), FulfilmentStatus.DRAFT
    )


def payment_from_provider(status: str) -> OrderPaymentStatus:
    normalized = str(status or "").strip().lower()
    return {
        "pending": OrderPaymentStatus.PENDING,
        "awaiting_confirmation": OrderPaymentStatus.PENDING,
        "processing": OrderPaymentStatus.AUTHORIZED,
        "authorized": OrderPaymentStatus.AUTHORIZED,
        "completed": OrderPaymentStatus.PAID,
        "paid": OrderPaymentStatus.PAID,
        "failed": OrderPaymentStatus.FAILED,
        "cancelled": OrderPaymentStatus.CANCELLED,
        "refunded": OrderPaymentStatus.REFUNDED,
        "partially_refunded": OrderPaymentStatus.PARTIALLY_REFUNDED,
    }.get(normalized, OrderPaymentStatus.PENDING)


def classify_order(item_types: Iterable[str | None]) -> OrderType:
    values = {str(value or "").strip().upper() for value in item_types}
    values.discard("")
    if values and values <= {"PHYSICAL_PRODUCT"}:
        return OrderType.PHYSICAL
    if values and values <= {"MONITORING_PLAN"}:
        return OrderType.MONITORING
    if values and not values.intersection({"PHYSICAL_PRODUCT", "MONITORING_PLAN"}):
        return OrderType.SERVICE
    return OrderType.MIXED


__all__ = [
    "FulfilmentStatus",
    "OrderLifecycleError",
    "OrderPaymentStatus",
    "OrderType",
    "TERMINAL_FULFILMENT_STATES",
    "classify_order",
    "fulfilment_from_legacy",
    "legacy_status",
    "payment_from_provider",
    "require_transition",
    "transition_allowed",
]
