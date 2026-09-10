"""Provider-neutral satellite/weather vocabulary and validation helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import re
from typing import Any, Mapping

from app.modules.datasets.domain import reject_sensitive_metadata


class IntelligenceKind(str, Enum):
    SATELLITE = "SATELLITE"
    WEATHER = "WEATHER"


class IntelligenceStatus(str, Enum):
    REQUESTED = "REQUESTED"
    RUNNING = "RUNNING"
    RETRY_WAIT = "RETRY_WAIT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class IntelligenceScheduleStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    DISABLED = "DISABLED"


class IntelligenceError(ValueError):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def provider_code(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    if not normalized or len(normalized) > 80:
        raise IntelligenceError("invalid_provider", "Provider must be a stable identifier")
    return {
        "cdse": "copernicus",
        "sentinel": "copernicus",
        "aemet_opendata": "aemet",
        "azure_maps_weather": "azure_maps",
        "deterministic": "fake",
    }.get(normalized, normalized)


def request_fingerprint(value: Mapping[str, Any]) -> str:
    try:
        reject_sensitive_metadata(dict(value), "request")
        payload = json.dumps(
            dict(value),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            default=lambda item: utc_naive(item).isoformat() if isinstance(item, datetime) else str(item),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise IntelligenceError("invalid_request", "Intelligence request is not serializable") from exc
    if len(payload) > 256 * 1024:
        raise IntelligenceError("invalid_request", "Intelligence request exceeds 256 KiB")
    return hashlib.sha256(payload).hexdigest()


def json_object(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def json_array(value: str | None) -> list[Any]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def json_dump(value: Any) -> str:
    reject_sensitive_metadata(value)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def aemet_covers(latitude: float, longitude: float) -> bool:
    """Broad Spain/territory guard; the adapter applies the exact station radius."""

    return -19.0 <= longitude <= 5.0 and 27.0 <= latitude <= 44.5


__all__ = [
    "IntelligenceError",
    "IntelligenceKind",
    "IntelligenceScheduleStatus",
    "IntelligenceStatus",
    "aemet_covers",
    "json_array",
    "json_dump",
    "json_object",
    "provider_code",
    "request_fingerprint",
    "utc_naive",
]
