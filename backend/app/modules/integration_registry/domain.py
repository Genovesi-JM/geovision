"""Stable domain values and validation for the integration registry."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import re
from typing import Any, Mapping, Protocol, runtime_checkable
from uuid import UUID


class ProviderFamily(str, Enum):
    CONSTRUCTION = "construction"
    ASSET_MANAGEMENT = "asset_management"
    GIS = "gis"
    MARITIME = "maritime"


class ConnectionStatus(str, Enum):
    PENDING_CONFIGURATION = "pending_configuration"
    DISABLED = "disabled"
    ACTIVE = "active"
    DEGRADED = "degraded"
    CIRCUIT_OPEN = "circuit_open"
    REVOKE_PENDING = "revoke_pending"
    REVOKED = "revoked"
    MIGRATION_REVIEW_REQUIRED = "migration_review_required"


class ConnectionHealth(str, Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class FeatureFlagHealthState(str, Enum):
    """Public, secret-free state of the rollout snapshot."""

    UNAVAILABLE = "unavailable"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class FeatureFlagHealth:
    state: FeatureFlagHealthState
    available: bool
    stale: bool
    reason_code: str
    snapshot_age_seconds: float | None = None
    last_refresh_at: datetime | None = None
    next_refresh_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class FeatureFlagTarget:
    """Non-PII targeting context built only from canonical UUID identifiers."""

    organization_id: UUID
    workspace_id: UUID | None = None
    user_id: UUID | None = None

    def __post_init__(self) -> None:
        for field_name in ("organization_id", "workspace_id", "user_id"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, UUID):
                raise TypeError(f"{field_name} must be a UUID")

    @property
    def organization_key(self) -> str:
        return f"organization:{self.organization_id}"

    @property
    def workspace_key(self) -> str | None:
        if self.workspace_id is None:
            return None
        return f"workspace:{self.workspace_id}"

    @property
    def user_key(self) -> str | None:
        if self.user_id is None:
            return None
        return f"user:{self.user_id}"

    def precedence_keys(self) -> tuple[str, ...]:
        return tuple(
            key
            for key in (self.user_key, self.workspace_key, self.organization_key)
            if key is not None
        )


@runtime_checkable
class FeatureFlagEvaluator(Protocol):
    """A rollout gate which cannot replace authorization or entitlement checks."""

    def allows_rollout(
        self,
        flag_name: str,
        *,
        target: FeatureFlagTarget,
        authorized: bool,
        entitled: bool,
    ) -> bool: ...

    def health(self) -> FeatureFlagHealth: ...


class SyncDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class SyncTrigger(str, Enum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    WEBHOOK = "webhook"
    RETRY = "retry"


class SyncStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    RETRY_SCHEDULED = "retry_scheduled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"
    CANCELLED = "cancelled"


class SyncOutcome(str, Enum):
    SUCCESS = "success"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    INVALID_REQUEST = "invalid_request"


class IntegrationRegistryError(RuntimeError):
    """Safe domain failure suitable for an API response."""

    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(message)


FEATURE_FLAG_PREFIXES = (
    "geovision.integrations.",
    "geovision.sectors.",
)


PROVIDERS_BY_FAMILY: Mapping[ProviderFamily, frozenset[str]] = {
    ProviderFamily.CONSTRUCTION: frozenset(
        {"fake", "autodesk_aps", "procore", "bentley_itwin", "trimble"}
    ),
    ProviderFamily.ASSET_MANAGEMENT: frozenset(
        {
            "fake",
            "sap_eam",
            "ibm_maximo",
            "dynamics_365_asset_management",
            "customer_cmms",
            "seequent",
            "mine_enterprise",
        }
    ),
    ProviderFamily.GIS: frozenset({"fake", "arcgis", "miteco"}),
    ProviderFamily.MARITIME: frozenset(
        {"fake", "marinetraffic", "kpler", "puertos_del_estado"}
    ),
}


CAPABILITIES_BY_FAMILY: Mapping[ProviderFamily, frozenset[str]] = {
    ProviderFamily.CONSTRUCTION: frozenset(
        {
            "project.read",
            "project.write",
            "inspection.read",
            "document.read",
        }
    ),
    ProviderFamily.ASSET_MANAGEMENT: frozenset(
        {
            "asset.read",
            "asset.write",
            "work_order.read",
            "work_order.write",
        }
    ),
    ProviderFamily.GIS: frozenset({"layer.read", "feature.read"}),
    ProviderFamily.MARITIME: frozenset({"context.read", "vessel.read"}),
}


# These are the normalized operations exposed by the provider-neutral ports.
# Direction selects the minimum capability needed for that data flow.
SYNC_CAPABILITY_BY_FAMILY: Mapping[
    ProviderFamily, Mapping[str, Mapping[SyncDirection, str]]
] = {
    ProviderFamily.CONSTRUCTION: {
        "synchronize_project": {
            SyncDirection.INBOUND: "project.read",
            SyncDirection.OUTBOUND: "project.write",
        }
    },
    ProviderFamily.ASSET_MANAGEMENT: {
        "synchronize_asset": {
            SyncDirection.INBOUND: "asset.read",
            SyncDirection.OUTBOUND: "asset.write",
        }
    },
    ProviderFamily.GIS: {
        "query_layers": {SyncDirection.INBOUND: "layer.read"},
    },
    ProviderFamily.MARITIME: {
        "operational_context": {SyncDirection.INBOUND: "context.read"},
    },
}


_STABLE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.:-]{1,99}$")
_SECRET_KEY = re.compile(
    r"(?i)(?:authorization|credential|password|secret|token|api[_-]?key|"
    r"private[_-]?key|client[_-]?secret|webhook[_-]?secret)"
)


def normalize_identifier(value: str, *, field: str) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    if not _STABLE_IDENTIFIER.fullmatch(normalized):
        raise ValueError(f"{field} must be a stable lowercase identifier")
    return normalized


def validate_provider(family: ProviderFamily | str, provider_code: str) -> str:
    normalized_family = ProviderFamily(family)
    normalized_provider = normalize_identifier(provider_code, field="provider_code")
    if normalized_provider not in PROVIDERS_BY_FAMILY[normalized_family]:
        raise ValueError(
            f"provider_code is not registered for {normalized_family.value}"
        )
    return normalized_provider


def validate_capabilities(
    family: ProviderFamily | str,
    capabilities: list[str] | tuple[str, ...] | set[str],
) -> list[str]:
    normalized_family = ProviderFamily(family)
    normalized = sorted(
        {normalize_identifier(value, field="capability") for value in capabilities}
    )
    unknown = set(normalized) - CAPABILITIES_BY_FAMILY[normalized_family]
    if unknown:
        raise ValueError(
            "capabilities are not registered for the selected provider family"
        )
    if not normalized:
        raise ValueError("at least one capability is required")
    return normalized


def required_sync_capability(
    family: ProviderFamily | str,
    direction: SyncDirection | str,
    operation: str,
) -> str:
    """Return the capability required by one normalized provider-port call."""

    normalized_family = ProviderFamily(str(getattr(family, "value", family)).lower())
    normalized_direction = SyncDirection(
        str(getattr(direction, "value", direction)).lower()
    )
    normalized_operation = normalize_identifier(operation, field="operation")
    directions = SYNC_CAPABILITY_BY_FAMILY[normalized_family].get(normalized_operation)
    if directions is None or normalized_direction not in directions:
        raise ValueError(
            "operation and direction are not registered for the provider family"
        )
    return directions[normalized_direction]


def reject_secret_like_settings(value: Any, *, path: str = "settings") -> None:
    """Reject secret-bearing keys at every depth; values remain non-sensitive config."""

    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized_key = str(key).strip()
            if not normalized_key or _SECRET_KEY.search(normalized_key):
                raise ValueError(f"{path} contains a forbidden or secret-bearing field")
            reject_secret_like_settings(nested, path=f"{path}.{normalized_key}")
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            reject_secret_like_settings(nested, path=f"{path}[{index}]")


__all__ = [
    "CAPABILITIES_BY_FAMILY",
    "PROVIDERS_BY_FAMILY",
    "SYNC_CAPABILITY_BY_FAMILY",
    "CircuitState",
    "ConnectionHealth",
    "ConnectionStatus",
    "FeatureFlagEvaluator",
    "FeatureFlagHealth",
    "FeatureFlagHealthState",
    "FeatureFlagTarget",
    "FEATURE_FLAG_PREFIXES",
    "IntegrationRegistryError",
    "ProviderFamily",
    "SyncDirection",
    "SyncOutcome",
    "SyncStatus",
    "SyncTrigger",
    "normalize_identifier",
    "required_sync_capability",
    "reject_secret_like_settings",
    "validate_capabilities",
    "validate_provider",
]
