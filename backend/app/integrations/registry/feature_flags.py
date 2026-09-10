"""Fail-closed feature-rollout policies for the integration registry.

Feature flags are an additional rollout condition.  They never grant application
authorization, subscription entitlement, or access to a configured provider.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import re
from threading import RLock
from typing import Any
from uuid import UUID

from app.modules.integration_registry.domain import (
    FEATURE_FLAG_PREFIXES,
    FeatureFlagEvaluator,
    FeatureFlagHealth,
    FeatureFlagHealthState,
    FeatureFlagTarget,
)


DEFAULT_FLAG_PREFIXES = FEATURE_FLAG_PREFIXES
_RAW_FEATURE_FLAG_PREFIX = ".appconfig.featureflag/"
_MAX_FLAGS = 256
_MAX_FLAG_NAME_LENGTH = 160
_MAX_FLAG_VALUE_BYTES = 64 * 1024
_MAX_CONFIG_NODES = 4_096
_MAX_CONFIG_STRING_LENGTH = 16_384
_MAX_FILTERS = 8
_MAX_TARGETS = 2_000
_SECRET_KEY_PATTERN = re.compile(
    r"(?:^|[_.-])(?:api[_-]?key|authorization|credential|password|private[_-]?key|"
    r"refresh[_-]?token|secret|token)(?:$|[_.-])",
    re.IGNORECASE,
)
_SECRET_VALUE_PATTERN = re.compile(
    r"(?:bearer\s+\S+|(?:api[_ -]?key|authorization|credential|password|secret|"
    r"token)\s*[:=])",
    re.IGNORECASE,
)
_FLAG_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,159}$")
_TARGET_KIND = frozenset({"organization", "workspace", "user"})


class NullFeatureFlagEvaluator:
    """Default evaluator: every optional rollout remains disabled."""

    def allows_rollout(
        self,
        flag_name: str,
        *,
        target: FeatureFlagTarget,
        authorized: bool,
        entitled: bool,
    ) -> bool:
        del flag_name, target, authorized, entitled
        return False

    def health(self) -> FeatureFlagHealth:
        return FeatureFlagHealth(
            state=FeatureFlagHealthState.UNAVAILABLE,
            available=False,
            stale=False,
            reason_code="feature_flags_not_configured",
        )

    def __repr__(self) -> str:
        return "<NullFeatureFlagEvaluator fail_closed=True>"


def _is_allowed_flag_name(name: object, prefixes: Sequence[str]) -> bool:
    return (
        isinstance(name, str)
        and len(name) <= _MAX_FLAG_NAME_LENGTH
        and _FLAG_NAME_PATTERN.fullmatch(name) is not None
        and any(name.startswith(prefix) for prefix in prefixes)
        and _SECRET_KEY_PATTERN.search(name) is None
    )


def _validate_prefixes(prefixes: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(prefix.strip().lower() for prefix in prefixes))
    if not normalized:
        raise ValueError("at least one GeoVision feature-flag prefix is required")
    if any(
        not prefix.startswith("geovision.")
        or not prefix.endswith(".")
        or _FLAG_NAME_PATTERN.fullmatch(prefix[:-1]) is None
        for prefix in normalized
    ):
        raise ValueError("feature-flag prefixes must be bounded GeoVision namespaces")
    return normalized


def _validate_target_key(value: object) -> str:
    if not isinstance(value, str) or value.count(":") != 1:
        raise ValueError("feature-flag target must use a typed UUID key")
    kind, raw_id = value.split(":", 1)
    if kind not in _TARGET_KIND:
        raise ValueError("feature-flag target kind is not supported")
    try:
        parsed = UUID(raw_id)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("feature-flag target must contain a UUID") from exc
    canonical = f"{kind}:{parsed}"
    if value != canonical:
        raise ValueError("feature-flag target UUID must use canonical form")
    return canonical


class DeterministicFeatureFlagEvaluator:
    """Injected deterministic rollout decisions for local and contract tests."""

    def __init__(
        self,
        decisions: Mapping[str, bool] | None = None,
        *,
        target_decisions: Mapping[tuple[str, str], bool] | None = None,
        allowed_prefixes: Sequence[str] = DEFAULT_FLAG_PREFIXES,
    ) -> None:
        self._prefixes = _validate_prefixes(allowed_prefixes)
        self._decisions: dict[str, bool] = {}
        self._target_decisions: dict[tuple[str, str], bool] = {}
        for name, decision in (decisions or {}).items():
            self._decisions[self._validated_name(name)] = self._validated_bool(decision)
        for (name, target_key), decision in (target_decisions or {}).items():
            self._target_decisions[
                (self._validated_name(name), _validate_target_key(target_key))
            ] = self._validated_bool(decision)

    def _validated_name(self, name: object) -> str:
        if not _is_allowed_flag_name(name, self._prefixes):
            raise ValueError("feature flag is outside the allowed GeoVision namespaces")
        return str(name)

    @staticmethod
    def _validated_bool(value: object) -> bool:
        if not isinstance(value, bool):
            raise ValueError("feature-flag decisions must be booleans")
        return value

    def allows_rollout(
        self,
        flag_name: str,
        *,
        target: FeatureFlagTarget,
        authorized: bool,
        entitled: bool,
    ) -> bool:
        if not authorized or not entitled:
            return False
        if not _is_allowed_flag_name(flag_name, self._prefixes):
            return False
        for target_key in target.precedence_keys():
            decision = self._target_decisions.get((flag_name, target_key))
            if decision is not None:
                return decision
        return self._decisions.get(flag_name, False)

    def health(self) -> FeatureFlagHealth:
        return FeatureFlagHealth(
            state=FeatureFlagHealthState.HEALTHY,
            available=True,
            stale=False,
            reason_code="deterministic_snapshot",
        )

    def __repr__(self) -> str:
        return (
            "<DeterministicFeatureFlagEvaluator "
            f"flags={len(self._decisions)} target_rules={len(self._target_decisions)}>"
        )


@dataclass(frozen=True, slots=True)
class _GroupRollout:
    name: str
    percentage: float


@dataclass(frozen=True, slots=True)
class _TargetingRule:
    users: frozenset[str]
    groups: tuple[_GroupRollout, ...]
    excluded_users: frozenset[str]
    excluded_groups: frozenset[str]
    default_percentage: float


@dataclass(frozen=True, slots=True)
class _FeatureFlagDefinition:
    enabled: bool
    targeting: _TargetingRule | None


def _has_secret_like_content(value: object, *, depth: int = 0) -> bool:
    if depth > 8:
        return True
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str) or _SECRET_KEY_PATTERN.search(key):
                return True
            if _has_secret_like_content(nested, depth=depth + 1):
                return True
        return False
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_has_secret_like_content(item, depth=depth + 1) for item in value)
    return isinstance(value, str) and _SECRET_VALUE_PATTERN.search(value) is not None


def _validate_config_bounds(value: object, *, depth: int = 0) -> int:
    """Bound an already-decoded flag before retaining it as a snapshot."""

    if depth > 8:
        raise ValueError("feature-flag configuration is nested too deeply")
    if isinstance(value, Mapping):
        nodes = 1
        for key, nested in value.items():
            if not isinstance(key, str) or len(key) > _MAX_FLAG_NAME_LENGTH:
                raise ValueError("feature-flag configuration key is invalid")
            nodes += _validate_config_bounds(nested, depth=depth + 1)
            if nodes > _MAX_CONFIG_NODES:
                raise ValueError("feature-flag configuration contains too many values")
        return nodes
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        nodes = 1
        for nested in value:
            nodes += _validate_config_bounds(nested, depth=depth + 1)
            if nodes > _MAX_CONFIG_NODES:
                raise ValueError("feature-flag configuration contains too many values")
        return nodes
    if isinstance(value, str) and len(value) > _MAX_CONFIG_STRING_LENGTH:
        raise ValueError("feature-flag configuration string is too large")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("feature-flag configuration number must be finite")
    if not isinstance(value, (str, int, float, bool, type(None))):
        raise ValueError("feature-flag configuration value type is unsupported")
    return 1


def _percentage(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a percentage")
    parsed = float(value)
    if not math.isfinite(parsed) or not 0 <= parsed <= 100:
        raise ValueError(f"{field_name} must be between zero and one hundred")
    return parsed


def _target_list(value: object, *, expected_kind: str) -> frozenset[str]:
    if not isinstance(value, list) or len(value) > _MAX_TARGETS:
        raise ValueError("feature-flag target list is invalid or too large")
    targets = frozenset(_validate_target_key(item) for item in value)
    if any(not target.startswith(f"{expected_kind}:") for target in targets):
        raise ValueError("feature-flag target type does not match its audience field")
    return targets


def _group_target_list(value: object) -> frozenset[str]:
    if not isinstance(value, list) or len(value) > _MAX_TARGETS:
        raise ValueError("feature-flag group list is invalid or too large")
    targets = frozenset(_validate_target_key(item) for item in value)
    if any(
        not target.startswith(("organization:", "workspace:")) for target in targets
    ):
        raise ValueError("feature-flag groups must be organization or workspace UUIDs")
    return targets


def _parse_targeting(parameters: object) -> _TargetingRule:
    if not isinstance(parameters, Mapping) or set(parameters) != {"Audience"}:
        raise ValueError("Microsoft.Targeting parameters must contain only Audience")
    audience = parameters["Audience"]
    if not isinstance(audience, Mapping):
        raise ValueError("Microsoft.Targeting Audience must be an object")
    allowed = {"Users", "Groups", "DefaultRolloutPercentage", "Exclusion"}
    if not set(audience).issubset(allowed):
        raise ValueError(
            "Microsoft.Targeting Audience contains unsupported configuration"
        )

    users = _target_list(audience.get("Users", []), expected_kind="user")
    raw_groups = audience.get("Groups", [])
    if not isinstance(raw_groups, list) or len(raw_groups) > _MAX_TARGETS:
        raise ValueError("Microsoft.Targeting Groups is invalid or too large")
    groups: list[_GroupRollout] = []
    for raw_group in raw_groups:
        if not isinstance(raw_group, Mapping) or set(raw_group) != {
            "Name",
            "RolloutPercentage",
        }:
            raise ValueError("Microsoft.Targeting group is invalid")
        name = _validate_target_key(raw_group["Name"])
        if not name.startswith(("organization:", "workspace:")):
            raise ValueError(
                "Microsoft.Targeting groups must be organization or workspace UUIDs"
            )
        groups.append(
            _GroupRollout(
                name=name,
                percentage=_percentage(
                    raw_group["RolloutPercentage"],
                    field_name="RolloutPercentage",
                ),
            )
        )

    exclusion = audience.get("Exclusion", {})
    if not isinstance(exclusion, Mapping) or not set(exclusion).issubset(
        {"Users", "Groups"}
    ):
        raise ValueError("Microsoft.Targeting Exclusion is invalid")
    excluded_users = _target_list(exclusion.get("Users", []), expected_kind="user")
    excluded_groups = _group_target_list(exclusion.get("Groups", []))

    return _TargetingRule(
        users=users,
        groups=tuple(groups),
        excluded_users=excluded_users,
        excluded_groups=excluded_groups,
        default_percentage=_percentage(
            audience.get("DefaultRolloutPercentage", 0),
            field_name="DefaultRolloutPercentage",
        ),
    )


def _decode_definition(raw_value: object) -> Mapping[str, Any]:
    if isinstance(raw_value, str):
        encoded = raw_value.encode("utf-8")
        if len(encoded) > _MAX_FLAG_VALUE_BYTES:
            raise ValueError("feature-flag definition is too large")
        try:
            decoded = json.loads(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError("feature-flag definition is not valid JSON") from exc
    else:
        decoded = raw_value
    if not isinstance(decoded, Mapping):
        raise ValueError("feature-flag definition must be an object")
    _validate_config_bounds(decoded)
    if _has_secret_like_content(decoded):
        raise ValueError(
            "feature-flag configuration contains forbidden secret-like data"
        )
    return decoded


def _parse_definition(flag_name: str, raw_value: object) -> _FeatureFlagDefinition:
    definition = _decode_definition(raw_value)
    allowed = {
        "id",
        "enabled",
        "conditions",
        "description",
        "display_name",
        "telemetry",
    }
    if not set(definition).issubset(allowed):
        raise ValueError("feature-flag definition contains unsupported configuration")
    if definition.get("id", flag_name) != flag_name:
        raise ValueError("feature-flag definition id does not match its key")
    enabled = definition.get("enabled")
    if not isinstance(enabled, bool):
        raise ValueError("feature-flag enabled must be a boolean")

    description = definition.get("description")
    display_name = definition.get("display_name")
    if description is not None and not isinstance(description, str):
        raise ValueError("feature-flag description must be text")
    if display_name is not None and not isinstance(display_name, str):
        raise ValueError("feature-flag display name must be text")
    telemetry = definition.get("telemetry")
    if telemetry is not None and (
        not isinstance(telemetry, Mapping)
        or set(telemetry) != {"enabled"}
        or not isinstance(telemetry["enabled"], bool)
    ):
        raise ValueError("feature-flag telemetry configuration is invalid")

    conditions = definition.get("conditions", {})
    if not isinstance(conditions, Mapping) or not set(conditions).issubset(
        {"client_filters", "requirement_type"}
    ):
        raise ValueError("feature-flag conditions are invalid")
    requirement_type = conditions.get("requirement_type", "Any")
    if requirement_type not in {"Any", "All"}:
        raise ValueError("feature-flag requirement type is invalid")
    filters = conditions.get("client_filters", [])
    if not isinstance(filters, list) or len(filters) > _MAX_FILTERS:
        raise ValueError("feature-flag filters are invalid or too large")
    if not filters:
        # Azure's All requirement with no filters evaluates false.
        return _FeatureFlagDefinition(
            enabled=enabled and requirement_type != "All",
            targeting=None,
        )
    if len(filters) != 1:
        raise ValueError("only one reviewed Microsoft.Targeting filter is supported")
    raw_filter = filters[0]
    if not isinstance(raw_filter, Mapping) or set(raw_filter) != {"name", "parameters"}:
        raise ValueError("feature-flag filter is invalid")
    if raw_filter["name"] != "Microsoft.Targeting":
        raise ValueError("unsupported feature-flag filter")
    return _FeatureFlagDefinition(
        enabled=enabled,
        targeting=_parse_targeting(raw_filter["parameters"]),
    )


def _stable_percentage(flag_name: str, target_key: str, *, discriminator: str) -> float:
    digest = hashlib.sha256(
        f"{flag_name}\x00{discriminator}\x00{target_key}".encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], "big") * 100.0 / (1 << 64)


def _targeting_allows(
    flag_name: str,
    targeting: _TargetingRule,
    target: FeatureFlagTarget,
) -> bool:
    user_key = target.user_key
    group_keys = frozenset(
        key
        for key in (target.workspace_key, target.organization_key)
        if key is not None
    )
    if (user_key is not None and user_key in targeting.excluded_users) or (
        group_keys & targeting.excluded_groups
    ):
        return False
    if user_key is not None and user_key in targeting.users:
        return True
    rollout_seed = user_key or target.workspace_key or target.organization_key
    for group in targeting.groups:
        if (
            group.name in group_keys
            and _stable_percentage(
                flag_name,
                rollout_seed,
                discriminator=group.name,
            )
            < group.percentage
        ):
            return True
    return (
        _stable_percentage(
            flag_name,
            rollout_seed,
            discriminator="default",
        )
        < targeting.default_percentage
    )


class AzureAppConfigurationFeatureFlagEvaluator:
    """Read-only Azure-compatible snapshot adapter with bounded refresh.

    ``snapshot_loader`` is deliberately injected.  It may wrap the official
    Azure App Configuration provider, but this policy object has no credentials,
    endpoint, SDK import, or write capability.  The loader must return raw
    ``.appconfig.featureflag/<id>`` values, a mapping keyed directly by flag id,
    or the official provider's ``feature_management.feature_flags`` mapping.
    """

    def __init__(
        self,
        snapshot_loader: Callable[[], Mapping[str, object]],
        *,
        refresh_interval: timedelta = timedelta(minutes=5),
        max_staleness: timedelta = timedelta(hours=1),
        allowed_prefixes: Sequence[str] = DEFAULT_FLAG_PREFIXES,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not callable(snapshot_loader):
            raise TypeError("snapshot_loader must be callable")
        if not timedelta(seconds=1) <= refresh_interval <= timedelta(hours=1):
            raise ValueError(
                "feature-flag refresh interval must be between one second and one hour"
            )
        if not refresh_interval <= max_staleness <= timedelta(hours=24):
            raise ValueError(
                "feature-flag staleness must cover refresh and stay within 24 hours"
            )
        self._snapshot_loader = snapshot_loader
        self._refresh_interval = refresh_interval
        self._max_staleness = max_staleness
        self._prefixes = _validate_prefixes(allowed_prefixes)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._snapshot: dict[str, _FeatureFlagDefinition] | None = None
        self._snapshot_at: datetime | None = None
        self._last_attempt_at: datetime | None = None
        self._last_refresh_failed = False
        self._lock = RLock()

    @staticmethod
    def _aware_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("feature-flag clock must return a timezone-aware datetime")
        return value.astimezone(timezone.utc)

    def _now(self) -> datetime:
        return self._aware_utc(self._clock())

    def _parse_snapshot(
        self, raw_snapshot: object
    ) -> dict[str, _FeatureFlagDefinition]:
        if not isinstance(raw_snapshot, Mapping):
            raise ValueError("feature-flag snapshot is invalid")
        if "feature_management" in raw_snapshot:
            feature_management = raw_snapshot["feature_management"]
            if not isinstance(feature_management, Mapping) or set(
                feature_management
            ) != {"feature_flags"}:
                raise ValueError("feature-management snapshot is invalid")
            raw_snapshot = feature_management["feature_flags"]
        else:
            # The provider can expose ordinary App Configuration values beside
            # raw feature-flag entries. Only the two reviewed feature formats
            # participate in rollout decisions; unrelated settings are ignored.
            selected: dict[str, object] = {}
            for key, value in raw_snapshot.items():
                if not isinstance(key, str):
                    raise ValueError("feature-flag key must be text")
                looks_like_direct_flag = isinstance(value, Mapping) and bool(
                    {"id", "enabled", "conditions"} & set(value)
                )
                if (
                    key.startswith(_RAW_FEATURE_FLAG_PREFIX)
                    or _is_allowed_flag_name(key, self._prefixes)
                    or looks_like_direct_flag
                ):
                    selected[key] = value
            raw_snapshot = selected
        if isinstance(raw_snapshot, list):
            if len(raw_snapshot) > _MAX_FLAGS:
                raise ValueError("feature-flag snapshot is too large")
            normalized: dict[str, object] = {}
            for value in raw_snapshot:
                if not isinstance(value, Mapping) or not isinstance(
                    value.get("id"), str
                ):
                    raise ValueError("feature-flag list item is invalid")
                name = value["id"]
                if name in normalized:
                    raise ValueError("feature-flag snapshot contains duplicate ids")
                normalized[name] = value
            raw_snapshot = normalized
        if not isinstance(raw_snapshot, Mapping) or len(raw_snapshot) > _MAX_FLAGS:
            raise ValueError("feature-flag snapshot is invalid or too large")
        parsed: dict[str, _FeatureFlagDefinition] = {}
        for raw_name, raw_definition in raw_snapshot.items():
            if not isinstance(raw_name, str):
                raise ValueError("feature-flag key must be text")
            name = (
                raw_name[len(_RAW_FEATURE_FLAG_PREFIX) :]
                if raw_name.startswith(_RAW_FEATURE_FLAG_PREFIX)
                else raw_name
            )
            if not _is_allowed_flag_name(name, self._prefixes):
                raise ValueError(
                    "feature flag is outside the allowed GeoVision namespaces"
                )
            if name in parsed:
                raise ValueError("feature-flag snapshot contains duplicate ids")
            parsed[name] = _parse_definition(name, raw_definition)
        return parsed

    def _refresh_if_due(self, now: datetime) -> None:
        with self._lock:
            if (
                self._last_attempt_at is not None
                and now - self._last_attempt_at < self._refresh_interval
            ):
                return
            self._last_attempt_at = now
        try:
            raw_snapshot = self._snapshot_loader()
            parsed = self._parse_snapshot(raw_snapshot)
        except Exception:
            # SDK/HTTP errors may contain endpoints, selectors, or credentials.
            # Preserve only a fixed public state and the last valid snapshot.
            with self._lock:
                self._last_refresh_failed = True
            return
        with self._lock:
            self._snapshot = parsed
            self._snapshot_at = now
            self._last_refresh_failed = False

    def _usable_snapshot(
        self, now: datetime
    ) -> Mapping[str, _FeatureFlagDefinition] | None:
        if self._snapshot is None or self._snapshot_at is None:
            return None
        if now - self._snapshot_at > self._max_staleness:
            return None
        return self._snapshot

    def allows_rollout(
        self,
        flag_name: str,
        *,
        target: FeatureFlagTarget,
        authorized: bool,
        entitled: bool,
    ) -> bool:
        if not authorized or not entitled:
            return False
        if not _is_allowed_flag_name(flag_name, self._prefixes):
            return False
        now = self._now()
        self._refresh_if_due(now)
        with self._lock:
            snapshot = self._usable_snapshot(now)
            definition = snapshot.get(flag_name) if snapshot is not None else None
        if definition is None or not definition.enabled:
            return False
        if definition.targeting is None:
            return True
        return _targeting_allows(flag_name, definition.targeting, target)

    def health(self) -> FeatureFlagHealth:
        now = self._now()
        with self._lock:
            snapshot_at = self._snapshot_at
            last_attempt_at = self._last_attempt_at
            refresh_failed = self._last_refresh_failed
        next_refresh_at = (
            last_attempt_at + self._refresh_interval
            if last_attempt_at is not None
            else now
        )
        if snapshot_at is None:
            return FeatureFlagHealth(
                state=FeatureFlagHealthState.UNAVAILABLE,
                available=False,
                stale=False,
                reason_code=(
                    "feature_flag_cold_start_failed"
                    if refresh_failed
                    else "feature_flag_cold_start"
                ),
                next_refresh_at=next_refresh_at,
            )
        age = max(0.0, (now - snapshot_at).total_seconds())
        if now - snapshot_at > self._max_staleness:
            return FeatureFlagHealth(
                state=FeatureFlagHealthState.EXPIRED,
                available=False,
                stale=True,
                reason_code="feature_flag_snapshot_expired",
                snapshot_age_seconds=age,
                last_refresh_at=snapshot_at,
                next_refresh_at=next_refresh_at,
            )
        overdue = now - snapshot_at >= self._refresh_interval
        if refresh_failed or overdue:
            return FeatureFlagHealth(
                state=FeatureFlagHealthState.DEGRADED,
                available=True,
                stale=True,
                reason_code=(
                    "feature_flag_refresh_failed"
                    if refresh_failed
                    else "feature_flag_snapshot_stale"
                ),
                snapshot_age_seconds=age,
                last_refresh_at=snapshot_at,
                next_refresh_at=next_refresh_at,
            )
        return FeatureFlagHealth(
            state=FeatureFlagHealthState.HEALTHY,
            available=True,
            stale=False,
            reason_code="feature_flag_snapshot_current",
            snapshot_age_seconds=age,
            last_refresh_at=snapshot_at,
            next_refresh_at=next_refresh_at,
        )

    def __repr__(self) -> str:
        with self._lock:
            loaded = self._snapshot is not None
        return f"<AzureAppConfigurationFeatureFlagEvaluator snapshot_loaded={loaded}>"


__all__ = [
    "AzureAppConfigurationFeatureFlagEvaluator",
    "DEFAULT_FLAG_PREFIXES",
    "DeterministicFeatureFlagEvaluator",
    "FeatureFlagEvaluator",
    "FeatureFlagHealth",
    "FeatureFlagHealthState",
    "FeatureFlagTarget",
    "NullFeatureFlagEvaluator",
]
