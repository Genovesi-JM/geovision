"""Ports/industrial KPI definitions with fail-closed inspection semantics."""

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


SECTOR = "PORTS_INDUSTRIAL"
ALGORITHM_VERSION = "1.0.0"

SUPPORTED_ASSET_TYPES = frozenset(
    {
        "BERTH",
        "CRANE",
        "EQUIPMENT",
        "GANTRY",
        "INSPECTION_ZONE",
        "LOADING_AREA",
        "PORT",
        "QUAY",
        "ROOF",
        "STRUCTURE",
        "TANK",
        "TERMINAL",
        "WAREHOUSE",
    }
)
SUPPORTED_DATASET_TYPES = frozenset(
    {
        "AIS_DATA",
        "DSM",
        "DTM",
        "MESH_3D",
        "ORTHOMOSAIC",
        "POINT_CLOUD",
        "RGB_IMAGES",
        "THERMAL_IMAGES",
        "WEATHER_DATA",
    }
)


class PortsError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class PortsSourceContext:
    evaluation: EvaluationContext
    availability: Mapping[str, Any]
    evidence: Mapping[str, Any]


def _value(context: EvaluationContext, key: str) -> float | int | str | None:
    value = context.measurements.get(key)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (float, int)):
        return value if math.isfinite(float(value)) else None
    rendered = str(value).strip()
    return rendered[:500] if rendered else None


def _calculation(
    context: EvaluationContext,
    key: str,
    *,
    default_status: KpiStatus | None = None,
) -> KpiCalculation | None:
    value = _value(context, key)
    if value is None:
        return None
    details = context.metadata.get("measurement_details", {})
    detail = details.get(key, {}) if isinstance(details, Mapping) else {}
    if not isinstance(detail, Mapping):
        detail = {}
    measured_at = detail.get("measured_at", context.measured_at)
    if not isinstance(measured_at, datetime):
        measured_at = context.measured_at
    confidence = detail.get("confidence", 0.5)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))
    status = default_status
    explicit_status = str(detail.get("status", "")).upper()
    if explicit_status in {item.value for item in KpiStatus}:
        status = KpiStatus(explicit_status)
    return KpiCalculation(
        value=value,
        measured_at=measured_at,
        source=str(detail.get("source") or "ports.validated_evidence")[:160],
        confidence=confidence,
        provenance={
            **(
                dict(detail.get("provenance", {}))
                if isinstance(detail.get("provenance"), Mapping)
                else {}
            ),
            "sector": SECTOR,
            "measurement_key": key,
            "interpretation_limit": (
                "inspection indicator only; not a defect, structural-integrity, "
                "safety, navigation, environmental-compliance, or engineering conclusion"
            ),
        },
        status=status,
        mission_id=str(detail["mission_id"]) if detail.get("mission_id") else None,
        dataset_id=str(detail["dataset_id"]) if detail.get("dataset_id") else None,
    )


KPI_DEFINITIONS = (
    KpiDefinitionSpec(
        sector=SECTOR,
        key="inspection_status",
        name="Inspection evidence status",
        unit=None,
        calculator="ports.inspection_status",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.PRIMARY,
        status_policy={},
        description="Status of the latest explicitly reviewed inspection evidence.",
        sort_order=10,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="inspection_freshness_days",
        name="Inspection age",
        unit="days",
        calculator="ports.inspection_freshness_days",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.PRIMARY,
        display_format={"decimal_places": 1},
        status_policy={
            "mode": "lower_is_better",
            "good_max": 30,
            "watch_max": 90,
            "warning_max": 180,
            "minimum_confidence": 0.7,
        },
        sort_order=20,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="condition_summary",
        name="Specialist-validated condition summary",
        unit=None,
        calculator="ports.condition_summary",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.PRIMARY,
        status_policy={},
        description="A bounded condition code available only after authorized specialist validation.",
        sort_order=30,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="reinspection_state",
        name="Reinspection state",
        unit=None,
        calculator="ports.reinspection_state",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.PRIMARY,
        status_policy={},
        description="Due state calculated only when a cadence and reviewed inspection exist.",
        sort_order=40,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="new_visual_candidate_count",
        name="New visual review candidates",
        unit="count",
        calculator="ports.new_visual_candidate_count",
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
        key="new_thermal_candidate_count",
        name="New thermal review candidates",
        unit="count",
        calculator="ports.new_thermal_candidate_count",
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
        key="environmental_alert_count",
        name="Sourced environmental alerts",
        unit="count",
        calculator="ports.environmental_alert_count",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.SECONDARY,
        display_format={"decimal_places": 0},
        status_policy={
            "mode": "lower_is_better",
            "good_max": 0,
            "watch_max": 1,
            "warning_max": 3,
            "minimum_confidence": 0.7,
        },
        sort_order=70,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="operational_alert_count",
        name="Sourced operational alerts",
        unit="count",
        calculator="ports.operational_alert_count",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.SECONDARY,
        display_format={"decimal_places": 0},
        status_policy={
            "mode": "lower_is_better",
            "good_max": 0,
            "watch_max": 1,
            "warning_max": 3,
            "minimum_confidence": 0.7,
        },
        sort_order=80,
    ),
    KpiDefinitionSpec(
        sector=SECTOR,
        key="assigned_sensor_freshness_minutes",
        name="Assigned sensor age",
        unit="minutes",
        calculator="ports.assigned_sensor_freshness_minutes",
        version=ALGORITHM_VERSION,
        importance=KpiImportance.TECHNICAL,
        display_format={"decimal_places": 1},
        status_policy={
            "mode": "lower_is_better",
            "good_max": 15,
            "watch_max": 60,
            "warning_max": 240,
            "minimum_confidence": 0.7,
        },
        sort_order=100,
    ),
)


_CATALOG_REF = {
    "visual": "prod_ports_visual_inspection",
    "thermal": "prod_ports_thermal_inspection",
    "mapping": "prod_ports_3d_mapping",
    "sensor": "prod_ports_sensor_installation",
    "monitoring": "prod_ports_monitoring_plan",
    "review": "prod_ports_specialist_review",
}


def _catalog_reference(key: str) -> tuple[Mapping[str, Any], ...]:
    return ({"kind": "geovision_catalog_item", "id": _CATALOG_REF[key]},)


def _inspection_rule(
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
        if kind not in {
            "environmental_alert",
            "operational_alert",
            "thermal",
            "visual",
        }:
            continue
        detected_at = item.get("detected_at", context.measured_at)
        if not isinstance(detected_at, datetime):
            detected_at = context.measured_at
        confidence = item.get("confidence", 0.5)
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))
        declared_severity = str(item.get("severity", "WATCH")).upper()
        severity = (
            ObservationSeverity(declared_severity)
            if declared_severity in {member.value for member in ObservationSeverity}
            else ObservationSeverity.WATCH
        )
        key = str(item.get("key") or f"{kind}-candidate")[:100]
        observation_key = f"{kind}.{key}"
        observation_types = {
            "environmental_alert": "PORT_ENVIRONMENTAL_ALERT_CONTEXT",
            "operational_alert": "PORT_OPERATIONAL_ALERT_CONTEXT",
            "thermal": "PORT_THERMAL_ANOMALY_CANDIDATE",
            "visual": "PORT_VISUAL_ANOMALY_CANDIDATE",
        }
        observations.append(
            ObservationProposal(
                key=observation_key,
                observation_type=observation_types[kind],
                severity=severity,
                detected_at=detected_at,
                source=str(item.get("source") or "ports.validated_analysis")[:160],
                algorithm_key="ports.review_candidates",
                algorithm_version=ALGORITHM_VERSION,
                confidence=confidence,
                value={
                    "candidate_label": str(item.get("label") or "Review candidate")[
                        :200
                    ],
                    "candidate_kind": kind,
                    "cause": None,
                    "condition": None,
                    "defect": None,
                    "structural_integrity": None,
                    "safety_conclusion": None,
                    "navigation_conclusion": None,
                    "compliance_conclusion": None,
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
                    "Review the visual inspection candidate"
                    if kind == "visual"
                    else "Review the thermal inspection candidate"
                    if kind == "thermal"
                    else "Review the sourced port-context alert"
                ),
                description=(
                    "Have an authorized specialist review the source evidence before any "
                    "defect, structural, safety, navigation, or compliance decision."
                ),
                source_observation_key=observation_key,
                due_date=context.measured_at + timedelta(days=3),
                recommended_catalog_item_id=_CATALOG_REF["review"],
                recommendation_refs=_catalog_reference("review"),
            )
        )

    availability = context.metadata.get("source_availability", {})
    asset_type = str(context.metadata.get("asset_type", "")).upper()
    if isinstance(availability, Mapping):
        if availability.get("inspection_evidence") != "AVAILABLE":
            actions.append(
                ActionRecommendation(
                    key="acquire.reviewed_visual_inspection",
                    priority="MEDIUM",
                    title="Acquire a reviewed visual inspection",
                    description="Collect asset-specific RGB or zoom evidence for documented review.",
                    recommended_catalog_item_id=_CATALOG_REF["visual"],
                    recommendation_refs=_catalog_reference("visual"),
                )
            )
        if (
            asset_type in {"CRANE", "GANTRY", "ROOF", "TANK", "WAREHOUSE"}
            and availability.get("thermal_inventory") != "AVAILABLE"
        ):
            actions.append(
                ActionRecommendation(
                    key="acquire.calibrated_thermal_inspection",
                    priority="LOW",
                    title="Establish calibrated thermal inspection evidence",
                    description=(
                        "Acquire calibrated thermal evidence before surfacing temperature candidates."
                    ),
                    recommended_catalog_item_id=_CATALOG_REF["thermal"],
                    recommendation_refs=_catalog_reference("thermal"),
                )
            )
        if availability.get("comparison_3d") != "AVAILABLE":
            actions.append(
                ActionRecommendation(
                    key="acquire.registered_3d_baseline",
                    priority="LOW",
                    title="Create a registered 3D inspection baseline",
                    description="Capture compatible 3D evidence for later asset-centric comparison.",
                    recommended_catalog_item_id=_CATALOG_REF["mapping"],
                    recommendation_refs=_catalog_reference("mapping"),
                )
            )
        if availability.get("sensor_assignment") == "NOT_CONFIGURED":
            actions.append(
                ActionRecommendation(
                    key="configure.asset_sensor",
                    priority="LOW",
                    title="Assess an asset sensor installation",
                    description="Define and commission a suitable sensor before monitoring telemetry.",
                    recommended_catalog_item_id=_CATALOG_REF["sensor"],
                    recommendation_refs=_catalog_reference("sensor"),
                )
            )
        if availability.get("reinspection") in {"NOT_CONFIGURED", "OVERDUE"}:
            actions.append(
                ActionRecommendation(
                    key="establish.reinspection_plan",
                    priority=(
                        "HIGH"
                        if availability.get("reinspection") == "OVERDUE"
                        else "LOW"
                    ),
                    title="Establish the next inspection cycle",
                    description="Configure or perform the next evidence-based inspection cycle.",
                    recommended_catalog_item_id=_CATALOG_REF["monitoring"],
                    recommendation_refs=_catalog_reference("monitoring"),
                )
            )
        if availability.get("condition_summary") != "AVAILABLE" and findings:
            actions.append(
                ActionRecommendation(
                    key="request.specialist_condition_review",
                    priority="MEDIUM",
                    title="Request a specialist condition review",
                    description="Obtain a bounded specialist-reviewed summary for the candidate evidence.",
                    recommended_catalog_item_id=_CATALOG_REF["review"],
                    recommendation_refs=_catalog_reference("review"),
                )
            )

    return RuleOutcome(tuple(observations), tuple(actions))


_CALCULATORS = {
    "inspection_status": lambda context: _calculation(
        context, "inspection_status", default_status=KpiStatus.UNKNOWN
    ),
    "inspection_freshness_days": lambda context: _calculation(
        context, "inspection_freshness_days"
    ),
    "condition_summary": lambda context: _calculation(
        context, "condition_summary", default_status=KpiStatus.UNKNOWN
    ),
    "reinspection_state": lambda context: _calculation(
        context, "reinspection_state", default_status=KpiStatus.UNKNOWN
    ),
    "new_visual_candidate_count": lambda context: _calculation(
        context, "new_visual_candidate_count"
    ),
    "new_thermal_candidate_count": lambda context: _calculation(
        context, "new_thermal_candidate_count"
    ),
    "environmental_alert_count": lambda context: _calculation(
        context, "environmental_alert_count"
    ),
    "operational_alert_count": lambda context: _calculation(
        context, "operational_alert_count"
    ),
    "assigned_sensor_freshness_minutes": lambda context: _calculation(
        context, "assigned_sensor_freshness_minutes"
    ),
}


def register_ports(
    *,
    calculators: CalculatorRegistry = calculator_registry,
    rules: RuleRegistry = rule_registry,
) -> None:
    """Idempotently activate Ports/Industrial in the common intelligence engine."""

    for definition in KPI_DEFINITIONS:
        calculators.register(definition, _CALCULATORS[definition.key], replace=True)
    rules.register(
        sector=SECTOR,
        key="ports.inspection_review",
        version=ALGORITHM_VERSION,
        evaluate=_inspection_rule,
        replace=True,
    )


__all__ = [
    "ALGORITHM_VERSION",
    "KPI_DEFINITIONS",
    "PortsError",
    "PortsSourceContext",
    "SECTOR",
    "SUPPORTED_ASSET_TYPES",
    "SUPPORTED_DATASET_TYPES",
    "register_ports",
]
