"""Agriculture KPI definitions, calculators, and cautious operational rules."""

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
    ObservationProposal,
    ObservationSeverity,
    RuleOutcome,
    RuleRegistry,
    ValidationStatus,
    calculator_registry,
    rule_registry,
)


SECTOR = "AGRICULTURE"
ALGORITHM_VERSION = "1.0.0"

# Sector vocabulary belongs here rather than in the common Asset/Dataset schema.
SUPPORTED_ASSET_TYPES = frozenset(
    {
        "FARM",
        "FIELD",
        "GREENHOUSE",
        "IRRIGATION_ZONE",
        "ORCHARD",
        "PASTURE",
        "SITE",
        "VINEYARD",
    }
)
SUPPORTED_DATASET_TYPES = frozenset(
    {
        "GNDVI",
        "MULTISPECTRAL_IMAGES",
        "NDRE",
        "NDVI",
        "ORTHOMOSAIC",
        "SATELLITE_IMAGE",
        "TELEMETRY",
        "THERMAL_IMAGES",
        "WEATHER_DATA",
    }
)


class AgricultureError(ValueError):
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
class AgricultureSourceContext:
    evaluation: EvaluationContext
    availability: Mapping[str, Any]
    evidence: Mapping[str, Any]


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _measurement(context: EvaluationContext, key: str) -> Measurement | None:
    number = _finite_number(context.measurements.get(key))
    if number is None:
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
        value=number,
        source=str(detail.get("source") or "agriculture.source_fusion")[:160],
        confidence=max(0.0, min(1.0, confidence if confidence is not None else 0.5)),
        measured_at=measured_at,
        dataset_id=(str(detail["dataset_id"]) if detail.get("dataset_id") else None),
        mission_id=(str(detail["mission_id"]) if detail.get("mission_id") else None),
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
    value_transform=None,
    extra_provenance: Mapping[str, Any] | None = None,
) -> KpiCalculation | None:
    measurement = _measurement(context, key)
    if measurement is None:
        return None
    value = value_transform(measurement.value) if value_transform else measurement.value
    return KpiCalculation(
        value=value,
        measured_at=measurement.measured_at,
        source=measurement.source,
        confidence=measurement.confidence,
        provenance={
            **dict(measurement.provenance or {}),
            **dict(extra_provenance or {}),
            "sector": SECTOR,
            "measurement_key": key,
        },
        mission_id=measurement.mission_id,
        dataset_id=measurement.dataset_id,
    )


def _crop_condition(context: EvaluationContext) -> KpiCalculation | None:
    explicit = _calculation(context, "crop_condition_percent")
    if explicit is not None:
        return explicit
    ndvi = _measurement(context, "ndvi_mean")
    if ndvi is None:
        return None
    # This is a transparent vegetation-vigour proxy, not a crop diagnosis.
    return KpiCalculation(
        value=max(0.0, min(100.0, ndvi.value * 100.0)),
        measured_at=ndvi.measured_at,
        source=ndvi.source,
        confidence=max(0.0, ndvi.confidence * 0.85),
        provenance={
            **dict(ndvi.provenance or {}),
            "sector": SECTOR,
            "proxy": "ndvi_mean_times_100",
            "scientific_caution": "vegetation vigour proxy; not disease or yield diagnosis",
        },
        mission_id=ndvi.mission_id,
        dataset_id=ndvi.dataset_id,
    )


KPI_DEFINITIONS = (
    KpiDefinitionSpec(
        sector=SECTOR,
        key="crop_condition",
        name="Crop condition",
        unit="%",
        calculator="agriculture.crop_condition",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.PRIMARY,
        display_format={"decimal_places": 1},
        status_policy={
            "mode": "higher_is_better",
            "good_min": 70,
            "watch_min": 55,
            "warning_min": 40,
            "minimum_confidence": 0.45,
        },
        description="Evidence-based crop-condition indicator; never a disease diagnosis.",
        sort_order=10,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="area_needing_attention",
        name="Area needing attention",
        unit="ha",
        calculator="agriculture.area_needing_attention",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.PRIMARY,
        display_format={"decimal_places": 2},
        status_policy={
            "mode": "lower_is_better",
            "good_max": 0.5,
            "watch_max": 2,
            "warning_max": 5,
            "minimum_confidence": 0.5,
            "policy_note": "initial operations threshold; validate per crop and season",
        },
        sort_order=20,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="water_stress",
        name="Water-stress indicator",
        unit="%",
        calculator="agriculture.water_stress",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.PRIMARY,
        display_format={"decimal_places": 1},
        status_policy={
            "mode": "lower_is_better",
            "good_max": 15,
            "watch_max": 30,
            "warning_max": 50,
            "minimum_confidence": 0.55,
            "policy_note": "indicator only; field verification required",
        },
        sort_order=30,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="ndvi_mean",
        name="Mean NDVI",
        calculator="agriculture.ndvi_mean",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.SECONDARY,
        display_format={"decimal_places": 3},
        status_policy={
            "mode": "higher_is_better",
            "good_min": 0.65,
            "watch_min": 0.5,
            "warning_min": 0.35,
            "minimum_confidence": 0.5,
            "policy_note": "interpret by crop, growth stage, soil, and acquisition conditions",
        },
        sort_order=40,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="ndvi_change",
        name="NDVI change since previous observation",
        calculator="agriculture.ndvi_change",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.SECONDARY,
        display_format={"decimal_places": 3, "positive_prefix": "+"},
        status_policy={
            "mode": "higher_is_better",
            "good_min": 0.02,
            "watch_min": -0.02,
            "warning_min": -0.08,
            "minimum_confidence": 0.5,
        },
        sort_order=50,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="soil_moisture",
        name="Soil moisture",
        unit="%",
        calculator="agriculture.soil_moisture",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.SECONDARY,
        display_format={"decimal_places": 1},
        status_policy={
            "mode": "target_range",
            "good_min": 25,
            "good_max": 45,
            "watch_min": 18,
            "watch_max": 55,
            "warning_min": 12,
            "warning_max": 65,
            "minimum_confidence": 0.5,
            "policy_note": "generic volumetric range; calibrate for sensor and soil type",
        },
        sort_order=60,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="affected_area",
        name="Affected area",
        unit="ha",
        calculator="agriculture.affected_area",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.SECONDARY,
        display_format={"decimal_places": 2},
        status_policy={
            "mode": "lower_is_better",
            "good_max": 0.5,
            "watch_max": 2,
            "warning_max": 5,
            "minimum_confidence": 0.5,
        },
        sort_order=70,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="vegetation_coverage",
        name="Vegetation coverage",
        unit="%",
        calculator="agriculture.vegetation_coverage",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.SECONDARY,
        display_format={"decimal_places": 1},
        status_policy={
            "mode": "higher_is_better",
            "good_min": 80,
            "watch_min": 65,
            "warning_min": 45,
            "minimum_confidence": 0.5,
        },
        sort_order=80,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="ndre_mean",
        name="Mean NDRE",
        calculator="agriculture.ndre_mean",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.TECHNICAL,
        display_format={"decimal_places": 3},
        status_policy={},
        sort_order=100,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="gndvi_mean",
        name="Mean GNDVI",
        calculator="agriculture.gndvi_mean",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.TECHNICAL,
        display_format={"decimal_places": 3},
        status_policy={},
        sort_order=110,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="rainfall_24h",
        name="Rainfall (24 hours)",
        unit="mm",
        calculator="agriculture.rainfall_24h",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.TECHNICAL,
        display_format={"decimal_places": 1},
        status_policy={},
        sort_order=120,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="air_temperature",
        name="Air temperature",
        unit="°C",
        calculator="agriculture.air_temperature",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.TECHNICAL,
        display_format={"decimal_places": 1},
        status_policy={},
        sort_order=130,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="relative_humidity",
        name="Relative humidity",
        unit="%",
        calculator="agriculture.relative_humidity",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.TECHNICAL,
        display_format={"decimal_places": 1},
        status_policy={},
        sort_order=140,
    ),
)


def _attention_rule(
    context: EvaluationContext,
    values: Mapping[str, KpiCalculation],
) -> RuleOutcome:
    observations: list[ObservationProposal] = []
    actions: list[ActionRecommendation] = []
    attention = values.get("area_needing_attention") or values.get("affected_area")
    details = context.metadata.get("measurement_details", {})
    attention_detail = (
        details.get("area_needing_attention", {})
        if isinstance(details, Mapping)
        else {}
    )
    geometry = context.metadata.get("attention_zone_geometry")
    if attention is not None and float(attention.value) > 0:
        area = float(attention.value)
        severity = (
            ObservationSeverity.CRITICAL
            if area > 5
            else ObservationSeverity.WARNING
            if area > 2
            else ObservationSeverity.WATCH
        )
        observation = ObservationProposal(
            key="attention_zone",
            observation_type="CROP_ATTENTION_ZONE",
            severity=severity,
            detected_at=attention.measured_at,
            source=attention.source,
            algorithm_key="agriculture.attention_zone",
            algorithm_version=ALGORITHM_VERSION,
            confidence=attention.confidence,
            value={
                "affected_hectares": area,
                "interpretation": "zone requiring field verification",
            },
            numeric_value=area,
            unit="ha",
            geometry=geometry if isinstance(geometry, Mapping) else None,
            metadata={"diagnosis": None, "field_verification_required": True},
            provenance=dict(attention.provenance),
            validation_status=ValidationStatus.NEEDS_REVIEW,
            mission_id=attention.mission_id,
            dataset_id=attention.dataset_id,
        )
        observations.append(observation)
        actions.append(
            ActionRecommendation(
                key="inspect_attention_zone",
                priority="HIGH" if severity is not ObservationSeverity.WATCH else "MEDIUM",
                title="Inspect the mapped attention zone",
                description=(
                    "Verify the highlighted area in the field before treatment, irrigation, "
                    "or crop-protection decisions."
                ),
                source_observation_key="attention_zone",
                due_date=context.measured_at + timedelta(days=2),
                recommendation_refs=(
                    {"kind": "geovision_service", "code": "FIELD_ZONE_INSPECTION"},
                ),
            )
        )

    water_stress = values.get("water_stress")
    if water_stress is not None and float(water_stress.value) >= 30:
        observations.append(
            ObservationProposal(
                key="water_stress_indicator",
                observation_type="WATER_STRESS_INDICATOR",
                severity=(
                    ObservationSeverity.CRITICAL
                    if float(water_stress.value) >= 50
                    else ObservationSeverity.WARNING
                ),
                detected_at=water_stress.measured_at,
                source=water_stress.source,
                algorithm_key="agriculture.water_stress_indicator",
                algorithm_version=ALGORITHM_VERSION,
                confidence=water_stress.confidence,
                value={
                    "indicator_percent": float(water_stress.value),
                    "diagnosis": None,
                },
                numeric_value=float(water_stress.value),
                unit="%",
                metadata={"specialist_interpretation_required": True},
                provenance=dict(water_stress.provenance),
                validation_status=ValidationStatus.NEEDS_REVIEW,
                mission_id=water_stress.mission_id,
                dataset_id=water_stress.dataset_id,
            )
        )
        actions.append(
            ActionRecommendation(
                key="request_water_stress_assessment",
                priority="HIGH",
                title="Request a water-stress assessment",
                description=(
                    "Ask a GeoVision specialist to review imagery, sensor context, and field "
                    "conditions before changing irrigation."
                ),
                source_observation_key="water_stress_indicator",
                due_date=context.measured_at + timedelta(days=3),
                recommendation_refs=(
                    {"kind": "geovision_service", "code": "SPECIALIST_ASSESSMENT"},
                ),
            )
        )

    availability = context.metadata.get("source_availability", {})
    if isinstance(availability, Mapping):
        if not availability.get("drone") and not availability.get("satellite"):
            actions.append(
                ActionRecommendation(
                    key="request_detailed_survey",
                    priority="MEDIUM",
                    title="Request a detailed crop survey",
                    description=(
                        "Acquire current imagery before drawing conclusions about crop condition."
                    ),
                    recommendation_refs=(
                        {"kind": "geovision_service", "code": "DETAILED_CROP_SURVEY"},
                    ),
                )
            )
        if not availability.get("iot"):
            actions.append(
                ActionRecommendation(
                    key="consider_field_monitoring",
                    priority="LOW",
                    title="Consider continuous field monitoring",
                    description=(
                        "Ask GeoVision to assess whether calibrated soil and weather sensors "
                        "would close current monitoring gaps."
                    ),
                    recommendation_refs=(
                        {"kind": "geovision_service", "code": "MONITORING_ASSESSMENT"},
                    ),
                )
            )

    return RuleOutcome(tuple(observations), tuple(actions))


_CALCULATORS = {
    "crop_condition": _crop_condition,
    "area_needing_attention": lambda context: _calculation(
        context, "area_needing_attention"
    ),
    "water_stress": lambda context: _calculation(context, "water_stress"),
    "ndvi_mean": lambda context: _calculation(context, "ndvi_mean"),
    "ndvi_change": lambda context: _calculation(context, "ndvi_change"),
    "soil_moisture": lambda context: _calculation(context, "soil_moisture"),
    "affected_area": lambda context: _calculation(context, "affected_area"),
    "vegetation_coverage": lambda context: _calculation(
        context, "vegetation_coverage"
    ),
    "ndre_mean": lambda context: _calculation(context, "ndre_mean"),
    "gndvi_mean": lambda context: _calculation(context, "gndvi_mean"),
    "rainfall_24h": lambda context: _calculation(context, "rainfall_24h"),
    "air_temperature": lambda context: _calculation(context, "air_temperature"),
    "relative_humidity": lambda context: _calculation(context, "relative_humidity"),
}


def register_agriculture(
    *,
    calculators: CalculatorRegistry = calculator_registry,
    rules: RuleRegistry = rule_registry,
) -> None:
    """Idempotently activate Agriculture in the shared intelligence engine."""

    for definition in KPI_DEFINITIONS:
        calculators.register(
            definition,
            _CALCULATORS[definition.key],
            replace=True,
        )
    rules.register(
        sector=SECTOR,
        key="agriculture.attention_and_monitoring",
        version=ALGORITHM_VERSION,
        evaluate=_attention_rule,
        replace=True,
    )


__all__ = [
    "ALGORITHM_VERSION",
    "AgricultureError",
    "AgricultureSourceContext",
    "KPI_DEFINITIONS",
    "SECTOR",
    "SUPPORTED_ASSET_TYPES",
    "SUPPORTED_DATASET_TYPES",
    "register_agriculture",
]
