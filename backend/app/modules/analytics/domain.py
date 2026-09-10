"""Provider-neutral KPI, observation, and sector registration primitives."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import math
import re
from typing import Any

from app.modules.assets.domain import normalize_sector as normalize_asset_sector


class KpiImportance(str, Enum):
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"
    TECHNICAL = "TECHNICAL"


class KpiStatus(str, Enum):
    GOOD = "GOOD"
    WATCH = "WATCH"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


class ObservationSeverity(str, Enum):
    INFO = "INFO"
    WATCH = "WATCH"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class ValidationStatus(str, Enum):
    UNVALIDATED = "UNVALIDATED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"


class StatusPolicyMode(str, Enum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"
    TARGET_RANGE = "target_range"
    BOOLEAN = "boolean"


_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,159}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,39}$")
_IMPORTANCE_ORDER = {
    KpiImportance.PRIMARY: 0,
    KpiImportance.SECONDARY: 1,
    KpiImportance.TECHNICAL: 2,
}
_STATUS_ORDER = {
    KpiStatus.UNKNOWN: 0,
    KpiStatus.GOOD: 1,
    KpiStatus.WATCH: 2,
    KpiStatus.WARNING: 3,
    KpiStatus.CRITICAL: 4,
}


def _stable_identifier(value: str, field_name: str, *, uppercase: bool = False) -> str:
    normalized = str(value or "").strip()
    if uppercase:
        normalized = re.sub(r"[^A-Za-z0-9]+", "_", normalized).strip("_").upper()
    if not _IDENTIFIER.fullmatch(normalized):
        raise ValueError(f"{field_name} must be a stable identifier")
    return normalized


def _version_key(value: str) -> tuple[tuple[int, object], ...]:
    parts = re.findall(r"\d+|[A-Za-z]+", value)
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part.lower()) for part in parts
    )


def _stable_version(value: str, field_name: str = "version") -> str:
    normalized = str(value or "").strip()
    if not _VERSION.fullmatch(normalized):
        raise ValueError(f"{field_name} must be a stable version identifier")
    return normalized


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


@dataclass(frozen=True, slots=True)
class KpiDefinitionSpec:
    sector: str
    key: str
    name: str
    calculator: str
    version: str
    unit: str | None = None
    importance: KpiImportance = KpiImportance.TECHNICAL
    display_format: Mapping[str, Any] = field(default_factory=dict)
    status_policy: Mapping[str, Any] = field(default_factory=dict)
    description: str | None = None
    sort_order: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "sector",
            _stable_identifier(
                normalize_asset_sector(self.sector),
                "sector",
                uppercase=True,
            ),
        )
        object.__setattr__(self, "key", _stable_identifier(self.key, "key"))
        object.__setattr__(
            self, "calculator", _stable_identifier(self.calculator, "calculator")
        )
        object.__setattr__(self, "version", _stable_version(self.version))
        name = str(self.name or "").strip()
        if not name or len(name) > 200:
            raise ValueError("name must contain 1 to 200 characters")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "importance", KpiImportance(self.importance))
        if self.unit is not None and len(self.unit) > 50:
            raise ValueError("unit must not exceed 50 characters")
        if self.sort_order < 0:
            raise ValueError("sort_order must be non-negative")
        object.__setattr__(self, "display_format", dict(self.display_format))
        object.__setattr__(self, "status_policy", dict(self.status_policy))


@dataclass(frozen=True, slots=True)
class KpiCalculation:
    value: float | int | str
    measured_at: datetime
    source: str
    confidence: float
    provenance: Mapping[str, Any]
    status: KpiStatus | None = None
    mission_id: str | None = None
    dataset_id: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.value, float) and not math.isfinite(self.value):
            raise ValueError("KPI value must be finite")
        if not 0 <= float(self.confidence) <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if not str(self.source or "").strip():
            raise ValueError("source is required")
        object.__setattr__(self, "measured_at", _utc_naive(self.measured_at))
        if self.status is not None:
            object.__setattr__(self, "status", KpiStatus(self.status))
        if self.mission_id is not None and not str(self.mission_id).strip():
            raise ValueError("mission_id must not be blank")
        if self.dataset_id is not None and not str(self.dataset_id).strip():
            raise ValueError("dataset_id must not be blank")
        object.__setattr__(self, "provenance", dict(self.provenance))

    @property
    def numeric_value(self) -> float | None:
        if isinstance(self.value, bool):
            return None
        if isinstance(self.value, (int, float)):
            return float(self.value)
        return None


@dataclass(frozen=True, slots=True)
class ObservationProposal:
    key: str
    observation_type: str
    severity: ObservationSeverity
    detected_at: datetime
    source: str
    algorithm_key: str
    algorithm_version: str
    confidence: float
    value: Mapping[str, Any] = field(default_factory=dict)
    numeric_value: float | None = None
    unit: str | None = None
    geometry: Mapping[str, Any] | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, Any] = field(default_factory=dict)
    validation_status: ValidationStatus = ValidationStatus.UNVALIDATED
    mission_id: str | None = None
    dataset_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", _stable_identifier(self.key, "observation key"))
        object.__setattr__(
            self,
            "observation_type",
            _stable_identifier(
                self.observation_type, "observation_type", uppercase=True
            ),
        )
        object.__setattr__(
            self,
            "algorithm_key",
            _stable_identifier(self.algorithm_key, "algorithm_key"),
        )
        object.__setattr__(
            self,
            "algorithm_version",
            _stable_version(self.algorithm_version, "algorithm_version"),
        )
        object.__setattr__(self, "severity", ObservationSeverity(self.severity))
        object.__setattr__(
            self, "validation_status", ValidationStatus(self.validation_status)
        )
        if not str(self.source or "").strip():
            raise ValueError("source is required")
        if not 0 <= float(self.confidence) <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if self.numeric_value is not None and not math.isfinite(
            float(self.numeric_value)
        ):
            raise ValueError("observation numeric value must be finite")
        object.__setattr__(self, "detected_at", _utc_naive(self.detected_at))
        object.__setattr__(self, "value", dict(self.value))
        object.__setattr__(self, "metadata", dict(self.metadata))
        object.__setattr__(self, "provenance", dict(self.provenance))
        object.__setattr__(
            self, "geometry", dict(self.geometry) if self.geometry else None
        )


@dataclass(frozen=True, slots=True)
class ActionRecommendation:
    key: str
    priority: str
    title: str
    description: str
    source_observation_key: str | None = None
    due_date: datetime | None = None
    assigned_to_user_id: str | None = None
    recommended_catalog_item_id: str | None = None
    recommendation_refs: Sequence[Mapping[str, Any]] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", _stable_identifier(self.key, "action key"))
        object.__setattr__(self, "priority", str(self.priority).strip().upper())
        if not str(self.title or "").strip() or not str(self.description or "").strip():
            raise ValueError("action title and description are required")
        object.__setattr__(
            self,
            "recommendation_refs",
            tuple(dict(item) for item in self.recommendation_refs),
        )
        if self.due_date is not None:
            object.__setattr__(self, "due_date", _utc_naive(self.due_date))


@dataclass(frozen=True, slots=True)
class RuleOutcome:
    observations: tuple[ObservationProposal, ...] = ()
    actions: tuple[ActionRecommendation, ...] = ()


@dataclass(frozen=True, slots=True)
class EvaluationContext:
    asset_id: str
    sector: str
    measured_at: datetime
    measurements: Mapping[str, Any] = field(default_factory=dict)
    datasets: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    telemetry: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "sector", _stable_identifier(self.sector, "sector", uppercase=True)
        )
        object.__setattr__(self, "measured_at", _utc_naive(self.measured_at))
        object.__setattr__(self, "measurements", dict(self.measurements))
        object.__setattr__(
            self, "datasets", tuple(dict(item) for item in self.datasets)
        )
        object.__setattr__(
            self, "telemetry", tuple(dict(item) for item in self.telemetry)
        )
        object.__setattr__(self, "metadata", dict(self.metadata))


Calculator = Callable[[EvaluationContext], KpiCalculation | None]
Rule = Callable[[EvaluationContext, Mapping[str, KpiCalculation]], RuleOutcome | None]


@dataclass(frozen=True, slots=True)
class CalculatorRegistration:
    definition: KpiDefinitionSpec
    calculate: Calculator


@dataclass(frozen=True, slots=True)
class RuleRegistration:
    sector: str
    key: str
    version: str
    evaluate: Rule


class CalculatorRegistry:
    """Registry populated by sector packages without core-engine edits."""

    def __init__(self) -> None:
        self._items: dict[tuple[str, str, str], CalculatorRegistration] = {}

    def register(
        self,
        definition: KpiDefinitionSpec,
        calculate: Calculator,
        *,
        replace: bool = False,
    ) -> None:
        if not callable(calculate):
            raise TypeError("calculator must be callable")
        key = (definition.sector, definition.key, definition.version)
        if key in self._items and not replace:
            raise ValueError(f"calculator already registered: {'.'.join(key)}")
        self._items[key] = CalculatorRegistration(definition, calculate)

    def resolve(
        self, sector: str, key: str, version: str | None = None
    ) -> CalculatorRegistration:
        normalized_sector = _stable_identifier(sector, "sector", uppercase=True)
        normalized_key = _stable_identifier(key, "key")
        candidates = [
            item
            for (registered_sector, registered_key, _), item in self._items.items()
            if registered_key == normalized_key
            and registered_sector in {normalized_sector, "GLOBAL"}
            and (version is None or item.definition.version == version)
        ]
        if not candidates:
            raise KeyError(
                f"No KPI calculator registered for {normalized_sector}.{normalized_key}"
            )
        return max(
            candidates,
            key=lambda item: (
                item.definition.sector == normalized_sector,
                _version_key(item.definition.version),
            ),
        )

    def registrations(self, sector: str) -> tuple[CalculatorRegistration, ...]:
        normalized = _stable_identifier(sector, "sector", uppercase=True)
        latest: dict[str, CalculatorRegistration] = {}
        for registration in self._items.values():
            definition = registration.definition
            if definition.sector not in {normalized, "GLOBAL"}:
                continue
            current = latest.get(definition.key)
            if current is None or (
                definition.sector == normalized,
                _version_key(definition.version),
            ) > (
                current.definition.sector == normalized,
                _version_key(current.definition.version),
            ):
                latest[definition.key] = registration
        return tuple(
            sorted(
                latest.values(),
                key=lambda item: (
                    _IMPORTANCE_ORDER[item.definition.importance],
                    item.definition.sort_order,
                    item.definition.key,
                ),
            )
        )


class RuleRegistry:
    """Versioned sector-rule registry returning structured observations/actions."""

    def __init__(self) -> None:
        self._items: dict[tuple[str, str, str], RuleRegistration] = {}

    def register(
        self,
        *,
        sector: str,
        key: str,
        version: str,
        evaluate: Rule,
        replace: bool = False,
    ) -> None:
        normalized_sector = _stable_identifier(sector, "sector", uppercase=True)
        normalized_key = _stable_identifier(key, "rule key")
        normalized_version = _stable_version(version, "rule version")
        registry_key = (normalized_sector, normalized_key, normalized_version)
        if registry_key in self._items and not replace:
            raise ValueError(f"rule already registered: {'.'.join(registry_key)}")
        if not callable(evaluate):
            raise TypeError("rule must be callable")
        self._items[registry_key] = RuleRegistration(
            normalized_sector, normalized_key, normalized_version, evaluate
        )

    def registrations(self, sector: str) -> tuple[RuleRegistration, ...]:
        normalized = _stable_identifier(sector, "sector", uppercase=True)
        latest: dict[str, RuleRegistration] = {}
        for item in self._items.values():
            if item.sector not in {normalized, "GLOBAL"}:
                continue
            current = latest.get(item.key)
            if current is None or (
                item.sector == normalized,
                _version_key(item.version),
            ) > (
                current.sector == normalized,
                _version_key(current.version),
            ):
                latest[item.key] = item
        return tuple(latest[key] for key in sorted(latest))


def calculate_kpi_status(
    value: float | int | None,
    policy: Mapping[str, Any],
    *,
    confidence: float = 1.0,
) -> KpiStatus:
    """Apply one explicit backend policy; absent/weak evidence stays UNKNOWN."""

    if value is None or isinstance(value, bool):
        return KpiStatus.UNKNOWN
    number = float(value)
    if not math.isfinite(number):
        return KpiStatus.UNKNOWN
    try:
        minimum_confidence = float(policy.get("minimum_confidence", 0))
    except (TypeError, ValueError):
        return KpiStatus.UNKNOWN
    if confidence < minimum_confidence:
        return KpiStatus.UNKNOWN
    try:
        mode = StatusPolicyMode(str(policy["mode"]))
    except (KeyError, ValueError):
        return KpiStatus.UNKNOWN

    try:
        if mode is StatusPolicyMode.HIGHER_IS_BETTER:
            if number >= float(policy["good_min"]):
                return KpiStatus.GOOD
            if number >= float(policy["watch_min"]):
                return KpiStatus.WATCH
            if number >= float(policy["warning_min"]):
                return KpiStatus.WARNING
            return KpiStatus.CRITICAL
        if mode is StatusPolicyMode.LOWER_IS_BETTER:
            if number <= float(policy["good_max"]):
                return KpiStatus.GOOD
            if number <= float(policy["watch_max"]):
                return KpiStatus.WATCH
            if number <= float(policy["warning_max"]):
                return KpiStatus.WARNING
            return KpiStatus.CRITICAL
        if mode is StatusPolicyMode.TARGET_RANGE:
            ranges = (
                (KpiStatus.GOOD, "good_min", "good_max"),
                (KpiStatus.WATCH, "watch_min", "watch_max"),
                (KpiStatus.WARNING, "warning_min", "warning_max"),
            )
            for status, lower_key, upper_key in ranges:
                if float(policy[lower_key]) <= number <= float(policy[upper_key]):
                    return status
            return KpiStatus.CRITICAL
        expected = bool(policy.get("expected", True))
        return KpiStatus.GOOD if bool(number) is expected else KpiStatus.CRITICAL
    except (KeyError, TypeError, ValueError):
        # A malformed policy is not evidence that the underlying asset is safe.
        return KpiStatus.UNKNOWN


def format_kpi_value(
    value: float | int | str | None,
    unit: str | None,
    display_format: Mapping[str, Any],
) -> str:
    if value is None:
        return str(display_format.get("missing", "—"))
    prefix = str(display_format.get("prefix", ""))
    suffix = str(display_format.get("suffix", ""))
    separator = str(display_format.get("unit_separator", " "))
    if isinstance(value, bool):
        rendered = str(
            display_format.get(
                "true_label" if value else "false_label", str(value).lower()
            )
        )
    elif isinstance(value, (int, float)):
        if float(value) > 0 and "positive_prefix" in display_format:
            prefix = str(display_format["positive_prefix"])
        multiplier = float(display_format.get("multiplier", 1))
        decimals = max(0, min(8, int(display_format.get("decimal_places", 2))))
        rendered = f"{float(value) * multiplier:.{decimals}f}"
        if display_format.get("trim_trailing_zeros", True):
            rendered = rendered.rstrip("0").rstrip(".")
    else:
        rendered = str(value)
    rendered = f"{prefix}{rendered}{suffix}"
    return f"{rendered}{separator}{unit}" if unit else rendered


@dataclass(frozen=True, slots=True)
class HistoricalValue:
    numeric_value: float | None
    measured_at: datetime
    is_baseline: bool = False


@dataclass(frozen=True, slots=True)
class HistoricalComparison:
    current: float | None
    previous: float | None
    baseline: float | None
    change: float | None
    change_percent: float | None
    baseline_change: float | None
    baseline_change_percent: float | None


def _change(
    current: float | None, reference: float | None
) -> tuple[float | None, float | None]:
    if current is None or reference is None:
        return None, None
    delta = current - reference
    percent = None if reference == 0 else (delta / abs(reference)) * 100
    return delta, percent


def historical_comparison(values: Sequence[HistoricalValue]) -> HistoricalComparison:
    ordered = sorted(values, key=lambda item: item.measured_at, reverse=True)
    measurements = [item for item in ordered if not item.is_baseline]
    baselines = [item for item in ordered if item.is_baseline]
    current = measurements[0].numeric_value if measurements else None
    previous = measurements[1].numeric_value if len(measurements) > 1 else None
    baseline = baselines[0].numeric_value if baselines else None
    change, change_percent = _change(current, previous)
    baseline_change, baseline_change_percent = _change(current, baseline)
    return HistoricalComparison(
        current=current,
        previous=previous,
        baseline=baseline,
        change=change,
        change_percent=change_percent,
        baseline_change=baseline_change,
        baseline_change_percent=baseline_change_percent,
    )


def worst_kpi_status(statuses: Sequence[KpiStatus | str]) -> KpiStatus:
    normalized = [KpiStatus(item) for item in statuses]
    if not normalized:
        return KpiStatus.UNKNOWN
    return max(normalized, key=lambda item: _STATUS_ORDER[item])


calculator_registry = CalculatorRegistry()
rule_registry = RuleRegistry()


__all__ = [
    "ActionRecommendation",
    "CalculatorRegistry",
    "EvaluationContext",
    "HistoricalComparison",
    "HistoricalValue",
    "KpiCalculation",
    "KpiDefinitionSpec",
    "KpiImportance",
    "KpiStatus",
    "ObservationProposal",
    "ObservationSeverity",
    "RuleOutcome",
    "RuleRegistry",
    "ValidationStatus",
    "calculate_kpi_status",
    "calculator_registry",
    "format_kpi_value",
    "historical_comparison",
    "rule_registry",
    "worst_kpi_status",
]
