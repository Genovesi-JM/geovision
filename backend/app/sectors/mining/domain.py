"""Mining and quarry KPI definitions with fail-closed evidence semantics."""

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


SECTOR = "MINING"
ALGORITHM_VERSION = "1.0.0"

# Mining vocabulary extends the common Asset/Dataset core. ``industry`` is not
# an alias here because the canonical core maps it to PORTS_LOGISTICS.
SUPPORTED_ASSET_TYPES = frozenset(
    {
        "ENVIRONMENTAL_MONITORING_ZONE",
        "HAUL_ROAD",
        "MINE_SITE",
        "PIT",
        "QUARRY",
        "SLOPE",
        "STOCKPILE_ZONE",
        "TALUS",
    }
)
SUPPORTED_DATASET_TYPES = frozenset(
    {
        "DSM",
        "DTM",
        "LIDAR_POINT_CLOUD",
        "MESH_3D",
        "ORTHOMOSAIC",
        "POINT_CLOUD",
        "RGB_IMAGES",
        "RTK_OBSERVATIONS",
    }
)


class MiningError(ValueError):
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
class MiningSourceContext:
    evaluation: EvaluationContext
    availability: Mapping[str, Any]
    evidence: Mapping[str, Any]


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


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
        source=str(detail.get("source") or "mining.validated_evidence")[:160],
        confidence=max(0.0, min(1.0, confidence if confidence is not None else 0.5)),
        measured_at=measured_at,
        dataset_id=str(detail["dataset_id"]) if detail.get("dataset_id") else None,
        mission_id=str(detail["mission_id"]) if detail.get("mission_id") else None,
        provenance=(
            dict(detail.get("provenance", {}))
            if isinstance(detail.get("provenance"), Mapping)
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
            "interpretation_limit": (
                "survey indicator only; not a reserve, resource, grade, geotechnical, "
                "safety, or regulatory conclusion"
            ),
        },
        status=status,
        mission_id=measurement.mission_id,
        dataset_id=measurement.dataset_id,
    )


KPI_DEFINITIONS = (
    KpiDefinitionSpec(
        sector=SECTOR,
        key="stockpile_volume",
        name="Reviewed stockpile surface volume",
        unit="m³",
        calculator="mining.stockpile_volume",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.PRIMARY,
        display_format={"decimal_places": 1},
        status_policy={},
        description=(
            "Survey-derived surface volume published only when project tolerance evidence passes."
        ),
        sort_order=10,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="terrain_volume_change",
        name="Excavation/terrain volume change",
        unit="m³",
        calculator="mining.terrain_volume_change",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.PRIMARY,
        display_format={"decimal_places": 1, "positive_prefix": "+"},
        status_policy={},
        description="Difference between two validated, tolerance-compliant surface surveys.",
        sort_order=20,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="survey_freshness_days",
        name="Survey age",
        unit="days",
        calculator="mining.survey_freshness_days",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.PRIMARY,
        display_format={"decimal_places": 1},
        status_policy={
            "mode": "lower_is_better",
            "good_max": 14,
            "watch_max": 30,
            "warning_max": 90,
            "minimum_confidence": 0.7,
        },
        description="Age of the newest explicitly reviewed survey dataset.",
        sort_order=30,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="surface_change_area",
        name="Mapped surface-change area",
        unit="m²",
        calculator="mining.surface_change_area",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.SECONDARY,
        display_format={"decimal_places": 1},
        status_policy={},
        description="Reviewed candidate area from a compatible aligned surface pair.",
        sort_order=40,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="slope_review_candidate_count",
        name="Slope areas requiring review",
        unit="count",
        calculator="mining.slope_review_candidate_count",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.SECONDARY,
        display_format={"decimal_places": 0},
        status_policy={
            "mode": "lower_is_better",
            "good_max": 0,
            "watch_max": 1,
            "warning_max": 3,
            "minimum_confidence": 0.6,
        },
        description="Mapped change candidates only; no geotechnical interpretation.",
        sort_order=50,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="haul_road_review_candidate_count",
        name="Haul-road areas requiring review",
        unit="count",
        calculator="mining.haul_road_review_candidate_count",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.SECONDARY,
        display_format={"decimal_places": 0},
        status_policy={
            "mode": "lower_is_better",
            "good_max": 0,
            "watch_max": 1,
            "warning_max": 3,
            "minimum_confidence": 0.6,
        },
        description="Mapped surface-change candidates only; no automatic defect claim.",
        sort_order=60,
    ),
)


_CATALOG_REF = {
    "volumetry": "prod_mining_volumetry_survey",
    "progress": "prod_mining_site_progress_survey",
    "lidar": "prod_mining_lidar_specialist_survey",
    "environmental": "prod_mining_environmental_monitoring",
    "monitoring": "prod_mining_repeat_monitoring_plan",
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
        kind = str(item.get("kind", "")).strip().lower()
        if kind not in {"surface", "slope", "haul_road"}:
            continue
        key = str(item.get("key") or "candidate")[:100]
        detected_at = item.get("detected_at", context.measured_at)
        if not isinstance(detected_at, datetime):
            detected_at = context.measured_at
        declared_confidence = _finite_number(item.get("confidence"))
        confidence = max(
            0.0,
            min(1.0, declared_confidence if declared_confidence is not None else 0.5),
        )
        declared_severity = str(item.get("severity", "WATCH")).upper()
        severity = (
            ObservationSeverity(declared_severity)
            if declared_severity in {member.value for member in ObservationSeverity}
            else ObservationSeverity.WATCH
        )
        observation_type = {
            "surface": "MINING_SURFACE_CHANGE_CANDIDATE",
            "slope": "SLOPE_CHANGE_CANDIDATE",
            "haul_road": "HAUL_ROAD_SURFACE_CHANGE_CANDIDATE",
        }[kind]
        observation_key = f"{kind}.{key}"
        observations.append(
            ObservationProposal(
                key=observation_key,
                observation_type=observation_type,
                severity=severity,
                detected_at=detected_at,
                source=str(item.get("source") or "mining.validated_analysis")[:160],
                algorithm_key="mining.review_candidates",
                algorithm_version=ALGORITHM_VERSION,
                confidence=confidence,
                value={
                    "candidate_label": str(
                        item.get("label") or "Mapped surface-change candidate"
                    )[:200],
                    "affected_area_m2": item.get("area_m2"),
                    "cause": None,
                    "diagnosis": None,
                    "defect": None,
                    "geotechnical_conclusion": None,
                    "safety_certification": None,
                },
                geometry=(
                    dict(item["geometry"])
                    if isinstance(item.get("geometry"), Mapping)
                    else None
                ),
                metadata={
                    "specialist_review_required": True,
                    "causation_assessed": False,
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
        recommendation_kind = str(item.get("recommendation_kind") or "progress")
        catalog_key = "lidar" if recommendation_kind == "lidar" else "progress"
        actions.append(
            ActionRecommendation(
                key=f"review.{observation_key}",
                priority=(
                    "HIGH"
                    if severity
                    in {ObservationSeverity.WARNING, ObservationSeverity.CRITICAL}
                    else "MEDIUM"
                ),
                title=(
                    "Acquire specialist LiDAR evidence for the mapped change"
                    if catalog_key == "lidar"
                    else "Review the mapped slope change"
                    if kind == "slope"
                    else "Review the mapped haul-road change"
                    if kind == "haul_road"
                    else "Review the mapped mining surface change"
                ),
                description=(
                    "Review the source survey and field conditions before making an operational, "
                    "geotechnical, safety, defect, or remediation decision."
                ),
                source_observation_key=observation_key,
                due_date=context.measured_at + timedelta(days=3),
                recommended_catalog_item_id=_CATALOG_REF[catalog_key],
                recommendation_refs=_catalog_reference(catalog_key),
            )
        )

    availability = context.metadata.get("source_availability", {})
    if isinstance(availability, Mapping):
        asset_type = str(context.metadata.get("asset_type") or "")
        if asset_type == "STOCKPILE_ZONE" and not availability.get("precise_volume"):
            actions.append(
                ActionRecommendation(
                    key="acquire.tolerance_compliant_volumetry",
                    priority="MEDIUM",
                    title="Acquire a tolerance-compliant volumetry survey",
                    description=(
                        "Acquire and review RTK/PPK photogrammetry or specialist LiDAR evidence "
                        "against the project's documented tolerances before publishing volume."
                    ),
                    recommended_catalog_item_id=_CATALOG_REF["volumetry"],
                    recommendation_refs=_catalog_reference("volumetry"),
                )
            )
        if not availability.get("reviewed_survey"):
            actions.append(
                ActionRecommendation(
                    key="acquire.reviewed_mining_survey",
                    priority="MEDIUM",
                    title="Acquire a reviewed mining site survey",
                    description=(
                        "Collect a traceable survey before reporting mining measurements or change."
                    ),
                    recommended_catalog_item_id=_CATALOG_REF["progress"],
                    recommendation_refs=_catalog_reference("progress"),
                )
            )
        if not availability.get("historical_comparison"):
            actions.append(
                ActionRecommendation(
                    key="establish.repeat_monitoring",
                    priority="LOW",
                    title="Establish repeatable mining survey history",
                    description=(
                        "Plan compatible repeat acquisitions so change can be measured against a "
                        "traceable baseline."
                    ),
                    recommended_catalog_item_id=_CATALOG_REF["monitoring"],
                    recommendation_refs=_catalog_reference("monitoring"),
                )
            )
        if asset_type == "ENVIRONMENTAL_MONITORING_ZONE" and not availability.get(
            "reviewed_survey"
        ):
            actions.append(
                ActionRecommendation(
                    key="establish.environmental_monitoring",
                    priority="LOW",
                    title="Establish mining environmental monitoring evidence",
                    description=(
                        "Acquire reviewed environmental observations without inferring compliance "
                        "or impact from mining survey geometry alone."
                    ),
                    recommended_catalog_item_id=_CATALOG_REF["environmental"],
                    recommendation_refs=_catalog_reference("environmental"),
                )
            )

    return RuleOutcome(tuple(observations), tuple(actions))


_CALCULATORS = {
    "stockpile_volume": lambda context: _calculation(
        context, "stockpile_volume", status=KpiStatus.UNKNOWN
    ),
    "terrain_volume_change": lambda context: _calculation(
        context, "terrain_volume_change", status=KpiStatus.UNKNOWN
    ),
    "survey_freshness_days": lambda context: _calculation(
        context, "survey_freshness_days"
    ),
    "surface_change_area": lambda context: _calculation(
        context, "surface_change_area", status=KpiStatus.UNKNOWN
    ),
    "slope_review_candidate_count": lambda context: _calculation(
        context, "slope_review_candidate_count"
    ),
    "haul_road_review_candidate_count": lambda context: _calculation(
        context, "haul_road_review_candidate_count"
    ),
}


def register_mining(
    *,
    calculators: CalculatorRegistry = calculator_registry,
    rules: RuleRegistry = rule_registry,
) -> None:
    """Idempotently activate Mining on the shared intelligence engine."""

    for definition in KPI_DEFINITIONS:
        calculators.register(definition, _CALCULATORS[definition.key], replace=True)
    rules.register(
        sector=SECTOR,
        key="mining.evidence_review",
        version=ALGORITHM_VERSION,
        evaluate=_finding_rule,
        replace=True,
    )


__all__ = [
    "ALGORITHM_VERSION",
    "KPI_DEFINITIONS",
    "MiningError",
    "MiningSourceContext",
    "SECTOR",
    "SUPPORTED_ASSET_TYPES",
    "SUPPORTED_DATASET_TYPES",
    "register_mining",
]
