"""Provider-neutral internal economics values and validation rules."""

from __future__ import annotations

import json
from enum import Enum
from typing import Any


class CostType(str, Enum):
    CONTRACTOR = "CONTRACTOR"
    TRAVEL = "TRAVEL"
    PROCESSING = "PROCESSING"
    EQUIPMENT = "EQUIPMENT"
    SHIPPING = "SHIPPING"
    SPECIALIST_REVIEW = "SPECIALIST_REVIEW"
    PROVIDER = "PROVIDER"
    OTHER = "OTHER"


class EconomicsScopeType(str, Enum):
    ORDER = "ORDER"
    CATALOG_ITEM = "CATALOG_ITEM"
    ORGANIZATION = "ORGANIZATION"


class EconomicsError(ValueError):
    """Expected economics-domain failure with a stable transport code."""

    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


_SENSITIVE_KEY_PARTS = frozenset(
    {
        "access_key",
        "api_key",
        "apikey",
        "authorization",
        "client_secret",
        "cookie",
        "credential",
        "connection_string",
        "password",
        "private_key",
        "raw_body",
        "raw_payload",
        "raw_request",
        "raw_response",
        "request_headers",
        "secret",
    }
)
_TOKEN_KEYS = frozenset(
    {
        "access_token",
        "auth_token",
        "bearer_token",
        "device_token",
        "id_token",
        "push_token",
        "refresh_token",
        "token",
    }
)


def sanitize_metadata(value: dict[str, Any], *, max_bytes: int = 8_192) -> dict[str, Any]:
    """Reject secrets and non-JSON data before economics metadata is persisted."""

    def inspect(item: Any) -> None:
        if isinstance(item, dict):
            for key, nested in item.items():
                normalized = str(key).strip().lower().replace("-", "_")
                if (
                    any(part in normalized for part in _SENSITIVE_KEY_PARTS)
                    or normalized in _TOKEN_KEYS
                    or normalized.endswith("_token")
                ):
                    raise ValueError("Economics metadata cannot contain credentials or raw payloads")
                inspect(nested)
        elif isinstance(item, list):
            for nested in item:
                inspect(nested)

    inspect(value)
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("Economics metadata must be valid JSON") from exc
    if len(encoded.encode("utf-8")) > max_bytes:
        raise ValueError(f"Economics metadata must be at most {max_bytes} bytes")
    return value


__all__ = [
    "CostType",
    "EconomicsError",
    "EconomicsScopeType",
    "sanitize_metadata",
]
