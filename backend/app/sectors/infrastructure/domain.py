"""Infrastructure KPI definitions, calculators, and cautious review rules."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from typing import Any

from app.modules.analytics.domain import (
    ActionRecommendation,
    CalculatorRegistry,
    EvaluationContext,
    KpiCalculation,
    KpiDefinitionSpec,
    KpiImportance,
    KpiStatus,
    ObservationProposal,
    ObservationSeverity,
    RuleOutcome,
    RuleRegistry,
    ValidationStatus,
    calculator_registry,
    rule_registry,
)


SECTOR = "INFRASTRUCTURE"
ALGORITHM_VERSION = "1.0.0"

# Infrastructure vocabulary remains an extension of the common Asset/Dataset core.
SUPPORTED_ASSET_TYPES = frozenset(
    {
        "BUILDING",
        "BRIDGE",
        "FACILITY",
        "PIPELINE",
        "RAILWAY",
        "ROAD",
        "SITE",
        "STRUCTURE",
    }
)
SUPPORTED_DATASET_TYPES = frozenset(
    {
        "BIM_MODEL",
        "DSM",
        "DTM",
        "LIDAR_POINT_CLOUD",
        "MESH_3D",
        "ORTHOMOSAIC",
        "POINT_CLOUD",
        "PROJECT_REFERENCE",
        "RGB_IMAGES",
        "RTK_OBSERVATIONS",
        "THERMAL_IMAGES",
    }
)


class InfrastructureError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class Measurement:
    value: float
    source: str
    confidence: float
    measured_at: datetime
    dataset_id: str | None = None
    mission_id: str | None = None
    provenance: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class InfrastructureSourceContext:
    evaluation: EvaluationContext
    availability: Mapping[str, Any]
    evidence: Mapping[str, Any]


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _measurement(context: EvaluationContext, key: str) -> Measurement | None:
    value = _finite_number(context.measurements.get(key))
    if value is None:
        return None
    details = context.metadata.get("measurement_details", {})
    detail = details.get(key, {}) if isinstance(details, Mapping) else {}
    if not isinstance(detail, Mapping):
        detail = {}
    measured_at = detail.get("measured_at", context.measured_at)
    if not isinstance(measured_at, datetime):
        measured_at = context.measured_at
    confidence = _finite_number(detail.get("confidence"))
    return Measurement(
        value=value,
        source=str(detail.get("source") or "infrastructure.validated_evidence")[:160],
        confidence=max(0.0, min(1.0, confidence if confidence is not None else 0.5)),
        measured_at=measured_at,
        dataset_id=str(detail["dataset_id"]) if detail.get("dataset_id") else None,
        mission_id=str(detail["mission_id"]) if detail.get("mission_id") else None,
        provenance=(
            dict(detail.get("provenance", {}))
            if isinstance(detail.get("provenance", {}), Mapping)
            else {}
        ),
    )


def _calculation(
    context: EvaluationContext,
    key: str,
    *,
    status: KpiStatus | None = None,
) -> KpiCalculation | None:
    measurement = _measurement(context, key)
    if measurement is None:
        return None
    return KpiCalculation(
        value=measurement.value,
        measured_at=measurement.measured_at,
        source=measurement.source,
        confidence=measurement.confidence,
        provenance={
            **dict(measurement.provenance or {}),
            "sector": SECTOR,
            "measurement_key": key,
            "decision_limit": "evidence indicator; not an engineering certification",
        },
        status=status,
        mission_id=measurement.mission_id,
        dataset_id=measurement.dataset_id,
    )


KPI_DEFINITIONS = (
    KpiDefinitionSpec(
        sector=SECTOR,
        key="overall_progress",
        name="Overall progress",
        unit="%",
        calculator="infrastructure.overall_progress",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.PRIMARY,
        display_format={"decimal_places": 1},
        status_policy={},
        description="Progress from explicitly reviewed survey, quantity, or trusted 4D evidence.",
        sort_order=10,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="schedule_variance",
        name="Schedule variance",
        unit="days",
        calculator="infrastructure.schedule_variance",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.PRIMARY,
        display_format={"decimal_places": 1, "positive_prefix": "+"},
        status_policy={
            "mode": "lower_is_better",
            "good_max": 0,
            "watch_max": 3,
            "warning_max": 10,
            "minimum_confidence": 0.7,
            "policy_note": "available only from an explicitly trusted schedule baseline",
        },
        sort_order=20,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="review_area_count",
        name="Areas requiring review",
        unit="count",
        calculator="infrastructure.review_area_count",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.PRIMARY,
        display_format={"decimal_places": 0},
        status_policy={
            "mode": "lower_is_better",
            "good_max": 0,
            "watch_max": 2,
            "warning_max": 5,
            "minimum_confidence": 0.5,
        },
        sort_order=30,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="progress_change",
        name="Progress change since previous survey",
        unit="percentage points",
        calculator="infrastructure.progress_change",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.SECONDARY,
        display_format={"decimal_places": 1, "positive_prefix": "+"},
        status_policy={},
        sort_order=40,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="visual_anomaly_count",
        name="New visual anomalies",
        unit="count",
        calculator="infrastructure.visual_anomaly_count",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.SECONDARY,
        display_format={"decimal_places": 0},
        status_policy={
            "mode": "lower_is_better",
            "good_max": 0,
            "watch_max": 2,
            "warning_max": 5,
            "minimum_confidence": 0.5,
        },
        sort_order=50,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="thermal_anomaly_count",
        name="New thermal anomalies",
        unit="count",
        calculator="infrastructure.thermal_anomaly_count",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.SECONDARY,
        display_format={"decimal_places": 0},
        status_policy={
            "mode": "lower_is_better",
            "good_max": 0,
            "watch_max": 2,
            "warning_max": 5,
            "minimum_confidence": 0.5,
        },
        sort_order=60,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="area_change",
        name="Mapped area change",
        unit="m²",
        calculator="infrastructure.area_change",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.TECHNICAL,
        display_format={"decimal_places": 1, "positive_prefix": "+"},
        status_policy={},
        sort_order=100,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="volume_change",
        name="Surface volume change",
        unit="m³",
        calculator="infrastructure.volume_change",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.TECHNICAL,
        display_format={"decimal_places": 1, "positive_prefix": "+"},
        status_policy={},
        sort_order=110,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="cut_volume",
        name="Indicative cut volume",
        unit="m³",
        calculator="infrastructure.cut_volume",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.TECHNICAL,
        display_format={"decimal_places": 1},
        status_policy={},
        description="Calculated only from a validated, co-registered surface pair.",
        sort_order=120,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="fill_volume",
        name="Indicative fill volume",
        unit="m³",
        calculator="infrastructure.fill_volume",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.TECHNICAL,
        display_format={"decimal_places": 1},
        status_policy={},
        description="Calculated only from a validated, co-registered surface pair.",
        sort_order=130,
    ),
)


_CATALOG_REF = {
    "survey": "prod_infra_progress_survey",
    "visual": "prod_infra_technical_inspection",
    "thermal": "prod_infra_thermal_inspection",
    "mapping": "prod_infra_3d_mapping",
    "review": "prod_infra_specialist_review",
    "monitoring": "prod_infra_monitoring_plan",
}


def _catalog_reference(key: str) -> tuple[Mapping[str, Any], ...]:
    return ({"kind": "geovision_catalog_item", "id": _CATALOG_REF[key]},)


def _finding_rule(
    context: EvaluationContext,
    _values: Mapping[str, KpiCalculation],
) -> RuleOutcome:
    observations: list[ObservationProposal] = []
    actions: list[ActionRecommendation] = []
    findings = context.metadata.get("findings", ())
    if not isinstance(findings, (list, tuple)):
        findings = ()

    for item in findings:
        if not isinstance(item, Mapping):
            continue
        kind = str(item.get("kind", "")).lower()
        if kind not in {"visual", "thermal", "review_area"}:
            continue
        key = str(item.get("key", "finding"))[:100]
        detected_at = item.get("detected_at", context.measured_at)
        if not isinstance(detected_at, datetime):
            detected_at = context.measured_at
        confidence = _finite_number(item.get("confidence"))
        confidence = max(0.0, min(1.0, confidence if confidence is not None else 0.5))
        declared_severity = str(item.get("severity", "WATCH")).upper()
        severity = (
            ObservationSeverity(declared_severity)
            if declared_severity in {member.value for member in ObservationSeverity}
            else ObservationSeverity.WATCH
        )
        observation_type = {
            "visual": "VISUAL_ANOMALY_CANDIDATE",
            "thermal": "THERMAL_ANOMALY_CANDIDATE",
            "review_area": "INFRASTRUCTURE_REVIEW_AREA",
        }[kind]
        observation_key = f"{kind}.{key}"
        observations.append(
            ObservationProposal(
                key=observation_key,
                observation_type=observation_type,
                severity=severity,
                detected_at=detected_at,
                source=str(item.get("source") or "infrastructure.validated_analysis")[:160],
                algorithm_key="infrastructure.review_candidates",
                algorithm_version=ALGORITHM_VERSION,
                confidence=confidence,
                value={
                    "candidate_label": str(item.get("label") or "Review candidate")[:200],
                    "engineering_conclusion": None,
                },
                geometry=(
                    dict(item["geometry"])
                    if isinstance(item.get("geometry"), Mapping)
                    else None
                ),
                metadata={
                    "specialist_review_required": True,
                    "evidence_validation": "VALIDATED_SOURCE_NEEDS_INTERPRETATION",
                },
                provenance=(
                    dict(item.get("provenance", {}))
                    if isinstance(item.get("provenance"), Mapping)
                    else {}
                ),
                validation_status=ValidationStatus.NEEDS_REVIEW,
                dataset_id=str(item["dataset_id"]) if item.get("dataset_id") else None,
                mission_id=str(item["mission_id"]) if item.get("mission_id") else None,
            )
        )
        catalog_key = "visual" if kind == "visual" else "thermal" if kind == "thermal" else "review"
        actions.append(
            ActionRecommendation(
                key=f"review.{observation_key}",
                priority="HIGH" if severity in {ObservationSeverity.WARNING, ObservationSeverity.CRITICAL} else "MEDIUM",
                title={
                    "visual": "Review the visual anomaly candidate",
                    "thermal": "Review the thermal anomaly candidate",
                    "review_area": "Review the mapped area",
                }[kind],
                description=(
                    "Have an authorized specialist inspect the source evidence before making "
                    "an engineering, safety, quality, or remediation decision."
                ),
                source_observation_key=observation_key,
                due_date=context.measured_at + timedelta(days=3),
                recommended_catalog_item_id=_CATALOG_REF[catalog_key],
                recommendation_refs=_catalog_reference(catalog_key),
            )
        )

    availability = context.metadata.get("source_availability", {})
    if isinstance(availability, Mapping):
        if not availability.get("validated_progress"):
            actions.append(
                ActionRecommendation(
                    key="acquire.validated_progress_survey",
                    priority="MEDIUM",
                    title="Acquire a reviewed progress survey",
                    description=(
                        "Collect and review current survey evidence before reporting overall progress."
                    ),
                    recommended_catalog_item_id=_CATALOG_REF["survey"],
                    recommendation_refs=_catalog_reference("survey"),
                )
            )
        if not availability.get("paired_surface"):
            actions.append(
                ActionRecommendation(
                    key="acquire.paired_surface",
                    priority="LOW",
                    title="Create a comparable 3D surface baseline",
                    description=(
                        "Acquire co-registered surface evidence before calculating volume or cut/fill."
                    ),
                    recommended_catalog_item_id=_CATALOG_REF["mapping"],
                    recommendation_refs=_catalog_reference("mapping"),
                )
            )
        if not availability.get("historical_comparison"):
            actions.append(
                ActionRecommendation(
                    key="establish.monitoring_history",
                    priority="LOW",
                    title="Establish repeatable monitoring history",
                    description=(
                        "Plan repeat acquisitions with compatible reference systems for change review."
                    ),
                    recommended_catalog_item_id=_CATALOG_REF["monitoring"],
                    recommendation_refs=_catalog_reference("monitoring"),
                )
            )

    return RuleOutcome(tuple(observations), tuple(actions))


_CALCULATORS = {
    "overall_progress": lambda context: _calculation(
        context, "overall_progress", status=KpiStatus.UNKNOWN
    ),
    "schedule_variance": lambda context: _calculation(context, "schedule_variance"),
    "review_area_count": lambda context: _calculation(context, "review_area_count"),
    "progress_change": lambda context: _calculation(
        context, "progress_change", status=KpiStatus.UNKNOWN
    ),
    "visual_anomaly_count": lambda context: _calculation(
        context, "visual_anomaly_count"
    ),
    "thermal_anomaly_count": lambda context: _calculation(
        context, "thermal_anomaly_count"
    ),
    "area_change": lambda context: _calculation(
        context, "area_change", status=KpiStatus.UNKNOWN
    ),
    "volume_change": lambda context: _calculation(
        context, "volume_change", status=KpiStatus.UNKNOWN
    ),
    "cut_volume": lambda context: _calculation(
        context, "cut_volume", status=KpiStatus.UNKNOWN
    ),
    "fill_volume": lambda context: _calculation(
        context, "fill_volume", status=KpiStatus.UNKNOWN
    ),
}


def register_infrastructure(
    *,
    calculators: CalculatorRegistry = calculator_registry,
    rules: RuleRegistry = rule_registry,
) -> None:
    """Idempotently activate Infrastructure in the shared intelligence engine."""

    for definition in KPI_DEFINITIONS:
        calculators.register(definition, _CALCULATORS[definition.key], replace=True)
    rules.register(
        sector=SECTOR,
        key="infrastructure.evidence_review",
        version=ALGORITHM_VERSION,
        evaluate=_finding_rule,
        replace=True,
    )


__all__ = [
    "ALGORITHM_VERSION",
    "InfrastructureError",
    "InfrastructureSourceContext",
    "KPI_DEFINITIONS",
    "SECTOR",
    "SUPPORTED_ASSET_TYPES",
    "SUPPORTED_DATASET_TYPES",
    "register_infrastructure",
]
