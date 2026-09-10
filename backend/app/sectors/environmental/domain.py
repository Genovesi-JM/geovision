"""Environmental KPI definitions and evidence-cautious operational rules."""

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


SECTOR = "ENVIRONMENTAL"
ALGORITHM_VERSION = "1.0.0"

# Environmental vocabulary is an extension of the common Asset/Dataset core.
SUPPORTED_ASSET_TYPES = frozenset(
    {
        "COASTAL_AREA",
        "ENVIRONMENTAL_SITE",
        "FOREST",
        "HABITAT",
        "LAND_PARCEL",
        "PROTECTED_AREA",
        "RESTORATION_SITE",
        "SITE",
        "WATER_BODY",
        "WETLAND",
    }
)
SUPPORTED_DATASET_TYPES = frozenset(
    {
        "DSM",
        "DTM",
        "ENVIRONMENTAL_REFERENCE",
        "LAND_COVER_CLASSIFICATION",
        "MULTISPECTRAL_IMAGES",
        "NDVI",
        "ORTHOMOSAIC",
        "RGB_IMAGES",
        "SATELLITE_IMAGE",
        "TELEMETRY",
        "THERMAL_IMAGES",
        "WEATHER_DATA",
    }
)


class EnvironmentalError(ValueError):
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
class EnvironmentalSourceContext:
    evaluation: EvaluationContext
    availability: Mapping[str, Any]
    evidence: Mapping[str, Any]
    context: Mapping[str, Any]


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
        source=str(detail.get("source") or "environmental.validated_evidence")[:160],
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
            "interpretation_limit": (
                "environmental indicator only; no causal, regulatory, or ecological diagnosis"
            ),
        },
        status=status,
        mission_id=measurement.mission_id,
        dataset_id=measurement.dataset_id,
    )


KPI_DEFINITIONS = (
    KpiDefinitionSpec(
        sector=SECTOR,
        key="affected_area",
        name="Mapped area requiring review",
        unit="ha",
        calculator="environmental.affected_area",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.PRIMARY,
        display_format={"decimal_places": 2},
        status_policy={},
        description="Mapped change-candidate area; not a damage or impact diagnosis.",
        sort_order=10,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="vegetation_cover",
        name="Reviewed vegetation cover",
        unit="%",
        calculator="environmental.vegetation_cover",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.PRIMARY,
        display_format={"decimal_places": 1},
        status_policy={},
        description="Vegetation cover from an explicitly reviewed classification.",
        sort_order=20,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="vegetation_cover_change",
        name="Vegetation-cover change",
        unit="percentage points",
        calculator="environmental.vegetation_cover_change",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.PRIMARY,
        display_format={"decimal_places": 1, "positive_prefix": "+"},
        status_policy={},
        description="Aligned multi-date change; direction alone is not an impact diagnosis.",
        sort_order=30,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="land_cover_change_area",
        name="Land-cover change candidate area",
        unit="ha",
        calculator="environmental.land_cover_change_area",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.PRIMARY,
        display_format={"decimal_places": 2},
        status_policy={},
        description="Candidate area from a validated aligned land-cover comparison.",
        sort_order=40,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="reforestation_cover",
        name="Reviewed reforestation cover",
        unit="%",
        calculator="environmental.reforestation_cover",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.PRIMARY,
        display_format={"decimal_places": 1},
        status_policy={},
        description="Cover monitoring for an explicit restoration/reforestation asset.",
        sort_order=50,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="reforestation_change",
        name="Reforestation-cover change",
        unit="percentage points",
        calculator="environmental.reforestation_change",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.SECONDARY,
        display_format={"decimal_places": 1, "positive_prefix": "+"},
        status_policy={},
        sort_order=60,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="thermal_hotspot_count",
        name="Thermal candidates requiring review",
        unit="count",
        calculator="environmental.thermal_hotspot_count",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.SECONDARY,
        display_format={"decimal_places": 0},
        status_policy={
            "mode": "lower_is_better",
            "good_max": 0,
            "watch_max": 1,
            "warning_max": 3,
            "minimum_confidence": 0.55,
        },
        description="Explicit thermal candidates; specialist review is required.",
        sort_order=70,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="terrain_change_area",
        name="Terrain-change candidate area",
        unit="ha",
        calculator="environmental.terrain_change_area",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.TECHNICAL,
        display_format={"decimal_places": 2},
        status_policy={},
        description="Terrain-change candidate from a valid paired surface; not confirmed erosion.",
        sort_order=100,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="ndvi_mean",
        name="Mean NDVI context",
        calculator="environmental.ndvi_mean",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.TECHNICAL,
        display_format={"decimal_places": 3},
        status_policy={},
        description="Reviewed vegetation-index context without ecological diagnosis.",
        sort_order=110,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="ndvi_change",
        name="NDVI change",
        calculator="environmental.ndvi_change",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.TECHNICAL,
        display_format={"decimal_places": 3, "positive_prefix": "+"},
        status_policy={},
        description="Change between compatible reviewed observations.",
        sort_order=120,
    ),
)


_CATALOG_REF = {
    "survey": "prod_env_environmental_survey",
    "reforestation": "prod_env_reforestation_monitoring",
    "drone": "prod_env_targeted_drone_verification",
    "sensor": "prod_env_sensor_installation",
    "monitoring": "prod_env_monitoring_plan",
    "review": "prod_env_specialist_review",
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
    availability = context.metadata.get("source_availability", {})
    if not isinstance(availability, Mapping):
        availability = {}

    supported_kinds = {
        "vegetation_change",
        "land_cover_change",
        "terrain_change",
        "reforestation_change",
        "thermal_hotspot",
    }
    for item in findings:
        if not isinstance(item, Mapping):
            continue
        kind = str(item.get("kind", "")).strip().lower()
        if kind not in supported_kinds:
            continue
        key = str(item.get("key", "candidate"))[:100]
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
            "vegetation_change": "VEGETATION_CHANGE_CANDIDATE",
            "land_cover_change": "LAND_COVER_CHANGE_CANDIDATE",
            "terrain_change": "TERRAIN_CHANGE_CANDIDATE",
            "reforestation_change": "REFORESTATION_CHANGE_CANDIDATE",
            "thermal_hotspot": "THERMAL_HOTSPOT_CANDIDATE",
        }[kind]
        observation_key = f"{kind}.{key}"
        observations.append(
            ObservationProposal(
                key=observation_key,
                observation_type=observation_type,
                severity=severity,
                detected_at=detected_at,
                source=str(item.get("source") or "environmental.validated_analysis")[
                    :160
                ],
                algorithm_key="environmental.review_candidates",
                algorithm_version=ALGORITHM_VERSION,
                confidence=confidence,
                value={
                    "candidate_label": str(
                        item.get("label") or "Mapped change candidate"
                    )[:200],
                    "affected_area_ha": item.get("area_ha"),
                    "cause": None,
                    "diagnosis": None,
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

        source_kind = str(item.get("source_kind", "")).lower()
        if (
            kind in {"vegetation_change", "land_cover_change"}
            and source_kind == "satellite"
            and not availability.get("current_drone_verification")
        ):
            catalog_key = "drone"
            title = "Verify the satellite change candidate by drone"
            description = (
                "Acquire targeted higher-resolution evidence for the mapped candidate before "
                "assigning a cause, impact, or remediation decision."
            )
        elif kind == "reforestation_change":
            catalog_key = "reforestation"
            title = "Review the reforestation monitoring change"
            description = (
                "Continue the reforestation monitoring series and obtain specialist or field "
                "validation before interpreting survival, loss, or cause."
            )
        else:
            catalog_key = "review"
            title = "Review the environmental change candidate"
            description = (
                "Have an authorized specialist inspect the source evidence before making an "
                "environmental, safety, compliance, or remediation decision."
            )
        actions.append(
            ActionRecommendation(
                key=f"review.{observation_key}",
                priority=(
                    "HIGH"
                    if severity
                    in {ObservationSeverity.WARNING, ObservationSeverity.CRITICAL}
                    else "MEDIUM"
                ),
                title=title,
                description=description,
                source_observation_key=observation_key,
                due_date=context.measured_at + timedelta(days=3),
                recommended_catalog_item_id=_CATALOG_REF[catalog_key],
                recommendation_refs=_catalog_reference(catalog_key),
            )
        )

    if not availability.get("satellite"):
        actions.append(
            ActionRecommendation(
                key="acquire.environmental_baseline",
                priority="MEDIUM",
                title="Establish an environmental survey baseline",
                description=(
                    "Acquire current, reviewable environmental evidence before reporting change."
                ),
                recommended_catalog_item_id=_CATALOG_REF["survey"],
                recommendation_refs=_catalog_reference("survey"),
            )
        )
    if not availability.get("historical_comparison"):
        actions.append(
            ActionRecommendation(
                key="establish.monitoring_history",
                priority="LOW",
                title="Establish repeatable environmental monitoring",
                description=(
                    "Plan compatible repeat acquisitions so later change can be measured against "
                    "a traceable baseline."
                ),
                recommended_catalog_item_id=_CATALOG_REF["monitoring"],
                recommendation_refs=_catalog_reference("monitoring"),
            )
        )
    if not availability.get("iot"):
        actions.append(
            ActionRecommendation(
                key="assess.sensor_installation",
                priority="LOW",
                title="Assess continuous sensor coverage",
                description=(
                    "Ask GeoVision to determine whether calibrated field sensors would close "
                    "the current environmental context gaps."
                ),
                recommended_catalog_item_id=_CATALOG_REF["sensor"],
                recommendation_refs=_catalog_reference("sensor"),
            )
        )

    return RuleOutcome(tuple(observations), tuple(actions))


_CALCULATORS = {
    "affected_area": lambda context: _calculation(
        context, "affected_area", status=KpiStatus.UNKNOWN
    ),
    "vegetation_cover": lambda context: _calculation(
        context, "vegetation_cover", status=KpiStatus.UNKNOWN
    ),
    "vegetation_cover_change": lambda context: _calculation(
        context, "vegetation_cover_change", status=KpiStatus.UNKNOWN
    ),
    "land_cover_change_area": lambda context: _calculation(
        context, "land_cover_change_area", status=KpiStatus.UNKNOWN
    ),
    "reforestation_cover": lambda context: _calculation(
        context, "reforestation_cover", status=KpiStatus.UNKNOWN
    ),
    "reforestation_change": lambda context: _calculation(
        context, "reforestation_change", status=KpiStatus.UNKNOWN
    ),
    "thermal_hotspot_count": lambda context: _calculation(
        context, "thermal_hotspot_count"
    ),
    "terrain_change_area": lambda context: _calculation(
        context, "terrain_change_area", status=KpiStatus.UNKNOWN
    ),
    "ndvi_mean": lambda context: _calculation(
        context, "ndvi_mean", status=KpiStatus.UNKNOWN
    ),
    "ndvi_change": lambda context: _calculation(
        context, "ndvi_change", status=KpiStatus.UNKNOWN
    ),
}


def register_environmental(
    *,
    calculators: CalculatorRegistry = calculator_registry,
    rules: RuleRegistry = rule_registry,
) -> None:
    """Idempotently activate Environmental in the shared intelligence engine."""

    for definition in KPI_DEFINITIONS:
        calculators.register(definition, _CALCULATORS[definition.key], replace=True)
    rules.register(
        sector=SECTOR,
        key="environmental.change_review",
        version=ALGORITHM_VERSION,
        evaluate=_finding_rule,
        replace=True,
    )


__all__ = [
    "ALGORITHM_VERSION",
    "EnvironmentalError",
    "EnvironmentalSourceContext",
    "KPI_DEFINITIONS",
    "SECTOR",
    "SUPPORTED_ASSET_TYPES",
    "SUPPORTED_DATASET_TYPES",
    "register_environmental",
]
