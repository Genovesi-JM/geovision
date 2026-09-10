"""Conservative Industry, Energy and Utilities capability metadata."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
import math
from typing import Any

from app.modules.analytics.domain import (
    CalculatorRegistry,
    EvaluationContext,
    KpiCalculation,
    KpiDefinitionSpec,
    KpiImportance,
    calculator_registry,
)

SECTOR = "INDUSTRY_ENERGY_UTILITIES"
CAPABILITY_VERSION = "1.0.0"

SUPPORTED_ASSET_TYPES = frozenset(
    {
        "BUILDING",
        "EQUIPMENT",
        "FACILITY",
        "PIPELINE",
        "SITE",
        "SOLAR_ARRAY",
        "STRUCTURE",
        "TANK",
        "WAREHOUSE",
    }
)

SUPPORTED_DATASET_TYPES = frozenset(
    {
        "INSPECTION_RECORD",
        "IOT_TELEMETRY",
        "RGB_IMAGES",
        "THERMAL_IMAGES",
    }
)

OPERATIONAL_KPIS = (
    {
        "key": "data_freshness",
        "name": "Data freshness",
        "source_requirement": "timestamped configured source",
    },
    {
        "key": "asset_health",
        "name": "Asset health",
        "source_requirement": "validated asset observation",
    },
    {
        "key": "maintenance_due",
        "name": "Maintenance due",
        "source_requirement": "recorded maintenance schedule",
    },
    {
        "key": "open_incidents",
        "name": "Open incidents",
        "source_requirement": "authorized incident records",
    },
)

KPI_DEFINITIONS = (
    KpiDefinitionSpec(
        sector=SECTOR,
        key="equipment_attention_count",
        name="Equipment observations requiring attention",
        unit="count",
        calculator="industry.equipment_attention_count",
        version=CAPABILITY_VERSION,
        importance=KpiImportance.PRIMARY,
        display_format={"decimal_places": 0},
        status_policy={
            "mode": "lower_is_better",
            "good_max": 0,
            "watch_max": 2,
            "warning_max": 5,
            "minimum_confidence": 0.7,
        },
        description=(
            "Count from explicitly recorded observations; it is not an equipment, "
            "energy, engineering, or safety conclusion."
        ),
        sort_order=10,
    ),
)


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _equipment_attention_count(
    context: EvaluationContext,
) -> KpiCalculation | None:
    """Count only explicit, traceable equipment-observation records."""

    raw_observations = context.metadata.get("equipment_observations")
    if (
        not isinstance(raw_observations, Sequence)
        or isinstance(raw_observations, (str, bytes))
        or not raw_observations
    ):
        return None

    observation_ids: list[str] = []
    source_references: list[str] = []
    measured_at_values: list[datetime] = []
    confidence_values: list[float] = []
    attention_count = 0
    for item in raw_observations:
        if not isinstance(item, Mapping):
            return None
        observation_id = str(item.get("observation_id") or "").strip()
        source_reference = str(item.get("source_reference") or "").strip()
        requires_attention = item.get("requires_attention")
        recorded_at = item.get("recorded_at")
        confidence = _number(item.get("confidence"))
        if (
            not observation_id
            or observation_id in observation_ids
            or not source_reference
            or not isinstance(requires_attention, bool)
            or not isinstance(recorded_at, datetime)
            or confidence is None
            or not 0 <= confidence <= 1
        ):
            return None
        observation_ids.append(observation_id)
        source_references.append(source_reference)
        measured_at_values.append(recorded_at)
        confidence_values.append(confidence)
        if requires_attention:
            attention_count += 1

    return KpiCalculation(
        value=attention_count,
        measured_at=max(measured_at_values),
        source="industry.recorded_equipment_observations",
        confidence=min(confidence_values),
        provenance={
            "sector": SECTOR,
            "evidence_type": "explicit_equipment_observations",
            "observation_ids": observation_ids,
            "source_references": source_references,
            "observation_count": len(observation_ids),
        },
    )


_CALCULATORS = {
    "equipment_attention_count": _equipment_attention_count,
}


def register_industry(
    *,
    calculators: CalculatorRegistry = calculator_registry,
) -> None:
    """Idempotently activate Industry/Energy/Utilities KPI calculators."""

    for definition in KPI_DEFINITIONS:
        calculators.register(definition, _CALCULATORS[definition.key], replace=True)


EVIDENCE_GUARDRAILS = (
    "KPIs remain unavailable until their named source is connected and current.",
    "No equipment, energy, safety, engineering, or compliance state is inferred from missing data.",
    "Automated observations remain review candidates until an accountable operator validates them.",
    "Control actions require explicit authorization and a separately validated integration.",
)

__all__ = [
    "CAPABILITY_VERSION",
    "EVIDENCE_GUARDRAILS",
    "KPI_DEFINITIONS",
    "OPERATIONAL_KPIS",
    "SECTOR",
    "SUPPORTED_ASSET_TYPES",
    "SUPPORTED_DATASET_TYPES",
    "register_industry",
]
