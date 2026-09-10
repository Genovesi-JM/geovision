"""Canonical notification values and safe contextual-target rules."""

from __future__ import annotations

from enum import Enum
import re


class NotificationError(RuntimeError):
    """Safe domain error exposed by notification application services."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class NotificationCategory(str, Enum):
    INVITATION = "INVITATION"
    REPORT = "REPORT"
    ACTION = "ACTION"
    DEVICE = "DEVICE"
    SERVICE = "SERVICE"
    ORDER = "ORDER"
    SHIPMENT = "SHIPMENT"
    SYSTEM = "SYSTEM"


class NotificationSeverity(str, Enum):
    INFO = "INFO"
    WATCH = "WATCH"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class NotificationTargetType(str, Enum):
    NONE = "NONE"
    ASSET = "ASSET"
    REPORT = "REPORT"
    ACTION = "ACTION"
    ORDER = "ORDER"
    SHIPMENT = "SHIPMENT"
    INVITATION = "INVITATION"
    SERVICE = "SERVICE"


class NotificationChannel(str, Enum):
    PUSH = "PUSH"
    EMAIL = "EMAIL"
    SMS = "SMS"


class NotificationDeliveryStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    RETRY = "RETRY"
    DELIVERED = "DELIVERED"
    SUPPRESSED = "SUPPRESSED"
    DEAD_LETTER = "DEAD_LETTER"


class NotificationEndpointPlatform(str, Enum):
    IOS = "IOS"
    ANDROID = "ANDROID"
    WEB = "WEB"


class NotificationEndpointStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    REVOKED = "REVOKED"


SEVERITY_RANK: dict[str, int] = {
    NotificationSeverity.INFO.value: 0,
    NotificationSeverity.WATCH.value: 1,
    NotificationSeverity.WARNING.value: 2,
    NotificationSeverity.CRITICAL.value: 3,
}

TARGET_REQUIRED_PERMISSION: dict[str, str] = {
    NotificationTargetType.ASSET.value: "asset:read",
    NotificationTargetType.REPORT.value: "report:read",
    NotificationTargetType.ACTION.value: "asset:read",
    NotificationTargetType.ORDER.value: "organization:read",
    NotificationTargetType.SHIPMENT.value: "organization:read",
    NotificationTargetType.SERVICE.value: "organization:read",
    NotificationTargetType.INVITATION.value: "workspace:read",
}

_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")


def normalize_notification_type(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _TYPE_PATTERN.fullmatch(normalized):
        raise NotificationError(
            "invalid_notification_type",
            "Notification type must be a lowercase dotted identifier",
        )
    return normalized


def severity_allows(*, actual: str, minimum: str) -> bool:
    return SEVERITY_RANK.get(actual, -1) >= SEVERITY_RANK.get(minimum, 0)


__all__ = [
    "NotificationCategory",
    "NotificationChannel",
    "NotificationDeliveryStatus",
    "NotificationEndpointPlatform",
    "NotificationEndpointStatus",
    "NotificationError",
    "NotificationSeverity",
    "NotificationTargetType",
    "SEVERITY_RANK",
    "TARGET_REQUIRED_PERMISSION",
    "normalize_notification_type",
    "severity_allows",
]
