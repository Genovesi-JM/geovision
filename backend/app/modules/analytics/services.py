"""Persistence and evaluation services for GeoVision's shared intelligence layer."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
import json
import uuid
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.event_names import EventNames
from app.core.time import utc_now
from app.models import Acquisition, Asset, Dataset, KpiDefinition, KpiValue, Observation
from app.modules.analytics.domain import (
    ActionRecommendation,
    CalculatorRegistry,
    EvaluationContext,
    HistoricalValue,
    KpiCalculation,
    KpiDefinitionSpec,
    KpiStatus,
    ObservationProposal,
    RuleRegistry,
    calculate_kpi_status,
    calculator_registry,
    format_kpi_value,
    historical_comparison,
    rule_registry,
    worst_kpi_status,
)
from app.modules.assets.domain import normalize_geometry
from app.modules.datasets.domain import reject_sensitive_metadata
from app.services.event_outbox import enqueue_domain_event


class IntelligenceError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _json(value: Any, *, field_name: str) -> str:
    reject_sensitive_metadata(value, field_name)
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise IntelligenceError("invalid_json", f"{field_name} must be JSON-compatible") from exc
    if len(encoded.encode("utf-8")) > 65_536:
        raise IntelligenceError("payload_too_large", f"{field_name} must not exceed 64 KiB")
    return encoded


def _object(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _value_text(value: float | int | str) -> str:
    if isinstance(value, str):
        rendered = value.strip()
    else:
        rendered = str(value)
    if not rendered or len(rendered) > 500:
        raise IntelligenceError("invalid_value", "KPI value must contain 1 to 500 characters")
    return rendered


def _workspace_for_asset(asset: Asset, workspace_id: str | None) -> str:
    selected = workspace_id or asset.workspace_id
    if not selected:
        raise IntelligenceError(
            "workspace_required", "A workspace is required to persist KPI history"
        )
    if asset.workspace_id and selected != asset.workspace_id:
        raise IntelligenceError("workspace_mismatch", "Asset does not belong to this workspace")
    return selected


def _validate_sources(
    db: Session,
    *,
    asset: Asset,
    mission_id: str | None,
    dataset_id: str | None,
) -> None:
    if mission_id:
        mission = db.get(Acquisition, mission_id)
        if (
            mission is None
            or mission.organization_id != asset.organization_id
            or mission.asset_id != asset.id
        ):
            raise IntelligenceError(
                "mission_not_found", "Source mission was not found for this asset"
            )
    if dataset_id:
        dataset = db.get(Dataset, dataset_id)
        if (
            dataset is None
            or dataset.company_id != asset.organization_id
            or dataset.asset_id != asset.id
        ):
            raise IntelligenceError(
                "dataset_not_found", "Source dataset was not found for this asset"
            )
        if mission_id and dataset.mission_id and dataset.mission_id != mission_id:
            raise IntelligenceError(
                "source_mismatch", "Dataset and mission provenance do not match"
            )


def ensure_kpi_definition(db: Session, spec: KpiDefinitionSpec) -> KpiDefinition:
    row = (
        db.query(KpiDefinition)
        .filter(
            KpiDefinition.sector == spec.sector,
            KpiDefinition.key == spec.key,
            KpiDefinition.calculator_version == spec.version,
        )
        .order_by(KpiDefinition.created_at)
        .first()
    )
    values = {
        "name": spec.name,
        "label": spec.name,
        "unit": spec.unit,
        "description": spec.description,
        "calculator": spec.calculator,
        "calculator_version": spec.version,
        "importance": spec.importance.value,
        "display_format_json": _json(spec.display_format, field_name="display_format"),
        "status_policy_json": _json(spec.status_policy, field_name="status_policy"),
        "sort_order": spec.sort_order,
        "is_active": True,
    }
    if row is None:
        row = KpiDefinition(
            id=str(uuid.uuid4()),
            sector=spec.sector,
            key=spec.key,
            created_at=utc_now(),
            **values,
        )
        db.add(row)
    else:
        for key, value in values.items():
            setattr(row, key, value)
        row.updated_at = utc_now()
    db.flush()
    return row


def record_kpi_value(
    db: Session,
    *,
    asset: Asset,
    definition: KpiDefinitionSpec,
    calculation: KpiCalculation,
    workspace_id: str | None = None,
    mission_id: str | None = None,
    dataset_id: str | None = None,
    is_baseline: bool = False,
) -> KpiValue:
    selected_workspace = _workspace_for_asset(asset, workspace_id)
    _validate_sources(
        db,
        asset=asset,
        mission_id=mission_id,
        dataset_id=dataset_id,
    )
    definition_row = ensure_kpi_definition(db, definition)
    status = calculation.status or calculate_kpi_status(
        calculation.numeric_value,
        definition.status_policy,
        confidence=calculation.confidence,
    )
    existing = (
        db.query(KpiValue)
        .filter(
            KpiValue.organization_id == asset.organization_id,
            KpiValue.workspace_id == selected_workspace,
            KpiValue.asset_id == asset.id,
            KpiValue.kpi_definition_id == definition_row.id,
            KpiValue.mission_id == mission_id,
            KpiValue.dataset_id == dataset_id,
            KpiValue.measured_at == calculation.measured_at,
            KpiValue.source == calculation.source.strip()[:160],
            KpiValue.algorithm_version == definition.version,
            KpiValue.is_baseline.is_(is_baseline),
        )
        .order_by(KpiValue.created_at)
        .first()
    )
    if existing is not None:
        return existing
    row = KpiValue(
        id=str(uuid.uuid4()),
        kpi_definition_id=definition_row.id,
        account_id=selected_workspace,
        organization_id=asset.organization_id,
        workspace_id=selected_workspace,
        asset_id=asset.id,
        site_id=asset.legacy_source_id if asset.legacy_source == "site" else None,
        dataset_id=dataset_id,
        mission_id=mission_id,
        value=_value_text(calculation.value),
        numeric_value=calculation.numeric_value,
        status=status.value,
        confidence=float(calculation.confidence),
        measured_at=calculation.measured_at,
        source=calculation.source.strip()[:160],
        algorithm_version=definition.version,
        provenance_json=_json(
            {
                **dict(calculation.provenance),
                "calculator": definition.calculator,
                "calculator_version": definition.version,
                "mission_id": mission_id,
                "dataset_id": dataset_id,
            },
            field_name="provenance",
        ),
        is_baseline=is_baseline,
        recorded_at=calculation.measured_at,
        created_at=utc_now(),
    )
    db.add(row)
    db.flush()
    enqueue_domain_event(
        db,
        name=EventNames.KPI_UPDATED,
        aggregate_type="kpi_value",
        aggregate_id=row.id,
        idempotency_key=f"kpi-value:{row.id}:recorded",
        correlation_id=dataset_id or mission_id or asset.id,
        payload={
            "kpi_value_id": row.id,
            "definition_id": definition_row.id,
            "key": definition.key,
            "status": row.status,
            "organization_id": asset.organization_id,
            "workspace_id": selected_workspace,
            "asset_id": asset.id,
            "mission_id": mission_id,
            "dataset_id": dataset_id,
            "measured_at": calculation.measured_at.isoformat(),
            "algorithm_version": definition.version,
        },
    )
    return row


def record_observation(
    db: Session,
    *,
    asset: Asset,
    proposal: ObservationProposal,
    workspace_id: str | None = None,
) -> Observation:
    selected_workspace = _workspace_for_asset(asset, workspace_id)
    _validate_sources(
        db,
        asset=asset,
        mission_id=proposal.mission_id,
        dataset_id=proposal.dataset_id,
    )
    geometry = normalize_geometry(proposal.geometry)
    candidates = (
        db.query(Observation)
        .filter(
            Observation.organization_id == asset.organization_id,
            Observation.workspace_id == selected_workspace,
            Observation.asset_id == asset.id,
            Observation.mission_id == proposal.mission_id,
            Observation.dataset_id == proposal.dataset_id,
            Observation.observation_type == proposal.observation_type,
            Observation.algorithm_key == proposal.algorithm_key,
            Observation.algorithm_version == proposal.algorithm_version,
            Observation.detected_at == proposal.detected_at,
        )
        .all()
    )
    for existing in candidates:
        if _object(existing.provenance_json).get("observation_key") == proposal.key:
            return existing
    row = Observation(
        id=str(uuid.uuid4()),
        organization_id=asset.organization_id,
        workspace_id=selected_workspace,
        asset_id=asset.id,
        mission_id=proposal.mission_id,
        dataset_id=proposal.dataset_id,
        observation_type=proposal.observation_type,
        severity=proposal.severity.value,
        geometry_geojson=(
            _json(geometry, field_name="geometry") if geometry is not None else None
        ),
        value_json=_json(proposal.value, field_name="value"),
        numeric_value=proposal.numeric_value,
        unit=proposal.unit,
        metadata_json=_json(proposal.metadata, field_name="metadata"),
        confidence=float(proposal.confidence),
        source=proposal.source.strip()[:160],
        algorithm_key=proposal.algorithm_key,
        algorithm_version=proposal.algorithm_version,
        provenance_json=_json(
            {
                **dict(proposal.provenance),
                "observation_key": proposal.key,
                "mission_id": proposal.mission_id,
                "dataset_id": proposal.dataset_id,
            },
            field_name="provenance",
        ),
        validation_status=proposal.validation_status.value,
        detected_at=proposal.detected_at,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db.add(row)
    db.flush()
    enqueue_domain_event(
        db,
        name=EventNames.OBSERVATION_CREATED,
        aggregate_type="observation",
        aggregate_id=row.id,
        idempotency_key=f"observation:{row.id}:created",
        correlation_id=proposal.dataset_id or proposal.mission_id or asset.id,
        payload={
            "observation_id": row.id,
            "organization_id": row.organization_id,
            "workspace_id": row.workspace_id,
            "asset_id": row.asset_id,
            "mission_id": row.mission_id,
            "dataset_id": row.dataset_id,
            "type": row.observation_type,
            "severity": row.severity,
            "validation_status": row.validation_status,
            "confidence": row.confidence,
            "algorithm_version": row.algorithm_version,
            "detected_at": row.detected_at.isoformat(),
        },
    )
    return row


def definition_payload(row: KpiDefinition) -> dict[str, Any]:
    return {
        "id": row.id,
        "sector": row.sector,
        "key": row.key,
        "name": row.name or row.label,
        "unit": row.unit,
        "description": row.description,
        "calculator": row.calculator,
        "calculator_version": row.calculator_version,
        "importance": row.importance,
        "display_format": _object(row.display_format_json),
        "status_policy": _object(row.status_policy_json),
    }


def _original_value(row: KpiValue | None) -> float | int | str | None:
    if row is None:
        return None
    if row.numeric_value is not None:
        return float(row.numeric_value)
    return row.value


def kpi_payload(
    definition: KpiDefinition,
    values: Sequence[KpiValue],
) -> dict[str, Any]:
    ordered = sorted(values, key=lambda item: item.measured_at, reverse=True)
    measurements = [item for item in ordered if not item.is_baseline]
    baselines = [item for item in ordered if item.is_baseline]
    current = measurements[0] if measurements else None
    previous = measurements[1] if len(measurements) > 1 else None
    baseline = baselines[0] if baselines else None
    comparison = historical_comparison(
        [
            HistoricalValue(
                numeric_value=(float(item.numeric_value) if item.numeric_value is not None else None),
                measured_at=item.measured_at,
                is_baseline=item.is_baseline,
            )
            for item in ordered
        ]
    )
    display_format = _object(definition.display_format_json)
    return {
        "definition": definition_payload(definition),
        "availability": "AVAILABLE" if current is not None else "NO_DATA",
        "current": _original_value(current),
        "previous": _original_value(previous),
        "baseline": _original_value(baseline),
        "change": comparison.change,
        "change_percent": comparison.change_percent,
        "baseline_change": comparison.baseline_change,
        "baseline_change_percent": comparison.baseline_change_percent,
        "display_value": format_kpi_value(
            _original_value(current), definition.unit, display_format
        ),
        "status": current.status if current else KpiStatus.UNKNOWN.value,
        "confidence": float(current.confidence) if current else None,
        "measured_at": current.measured_at if current else None,
        "previous_measured_at": previous.measured_at if previous else None,
        "baseline_measured_at": baseline.measured_at if baseline else None,
        "source": current.source if current else None,
        "mission_id": current.mission_id if current else None,
        "dataset_id": current.dataset_id if current else None,
        "provenance": _object(current.provenance_json) if current else {},
    }


def asset_kpi_payloads(db: Session, asset: Asset) -> list[dict[str, Any]]:
    rows = (
        db.query(KpiValue)
        .filter(
            KpiValue.organization_id == asset.organization_id,
            KpiValue.asset_id == asset.id,
        )
        .order_by(KpiValue.measured_at.desc())
        .all()
    )
    grouped: dict[str, list[KpiValue]] = defaultdict(list)
    for row in rows:
        grouped[row.kpi_definition_id].append(row)
    definitions = (
        db.query(KpiDefinition)
        .filter(
            KpiDefinition.is_active.is_(True),
            or_(
                KpiDefinition.sector == asset.sector,
                KpiDefinition.id.in_(tuple(grouped)) if grouped else False,
            ),
        )
        .all()
    )
    return [
        kpi_payload(definition, grouped.get(definition.id, ()))
        for definition in sorted(
            definitions,
            key=lambda item: (
                {"PRIMARY": 0, "SECONDARY": 1, "TECHNICAL": 2}.get(item.importance, 3),
                item.sort_order,
                item.key,
            ),
        )
    ]


def observation_payload(row: Observation) -> dict[str, Any]:
    return {
        "id": row.id,
        "organization_id": row.organization_id,
        "workspace_id": row.workspace_id,
        "asset_id": row.asset_id,
        "mission_id": row.mission_id,
        "dataset_id": row.dataset_id,
        "type": row.observation_type,
        "severity": row.severity,
        "geometry": _object(row.geometry_geojson) if row.geometry_geojson else None,
        "value": _object(row.value_json),
        "numeric_value": row.numeric_value,
        "unit": row.unit,
        "metadata": _object(row.metadata_json),
        "confidence": row.confidence,
        "source": row.source,
        "algorithm": row.algorithm_key,
        "algorithm_version": row.algorithm_version,
        "provenance": _object(row.provenance_json),
        "validation_status": row.validation_status,
        "validated_by_user_id": row.validated_by_user_id,
        "validated_at": row.validated_at,
        "detected_at": row.detected_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def list_asset_observations(
    db: Session,
    *,
    asset: Asset,
    severity: str | None = None,
    severities: Sequence[str] | None = None,
    validation_status: str | None = None,
    exclude_validation_statuses: Sequence[str] | None = None,
    since: datetime | None = None,
    limit: int = 100,
) -> list[Observation]:
    query = db.query(Observation).filter(
        Observation.organization_id == asset.organization_id,
        Observation.asset_id == asset.id,
    )
    if asset.workspace_id:
        query = query.filter(Observation.workspace_id == asset.workspace_id)
    if severity and severities:
        raise IntelligenceError(
            "invalid_observation_filter",
            "Use either severity or severities, not both",
        )
    if severity:
        query = query.filter(Observation.severity == severity.upper())
    elif severities:
        normalized_severities = tuple(value.upper() for value in severities)
        query = query.filter(Observation.severity.in_(normalized_severities))
    if validation_status:
        query = query.filter(Observation.validation_status == validation_status.upper())
    if exclude_validation_statuses:
        excluded = tuple(value.upper() for value in exclude_validation_statuses)
        query = query.filter(Observation.validation_status.notin_(excluded))
    if since:
        query = query.filter(Observation.detected_at >= since)
    return query.order_by(Observation.detected_at.desc(), Observation.id).limit(limit).all()


@dataclass(frozen=True, slots=True)
class PendingAction:
    rule_key: str
    rule_version: str
    recommendation: ActionRecommendation
    source_observation_id: str | None


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    kpi_values: tuple[KpiValue, ...]
    observations: tuple[Observation, ...]
    pending_actions: tuple[PendingAction, ...]


def evaluate_asset(
    db: Session,
    *,
    asset: Asset,
    context: EvaluationContext,
    workspace_id: str | None = None,
    calculators: CalculatorRegistry = calculator_registry,
    rules: RuleRegistry = rule_registry,
) -> EvaluationResult:
    """Run registered sector code while the core owns persistence/provenance."""

    if context.asset_id != asset.id or context.sector != asset.sector.upper():
        raise IntelligenceError("asset_context_mismatch", "Evaluation context does not match asset")

    calculations: dict[str, KpiCalculation] = {}
    value_rows: list[KpiValue] = []
    for registration in calculators.registrations(context.sector):
        calculation = registration.calculate(context)
        if calculation is None:
            continue
        calculations[registration.definition.key] = calculation
        value_rows.append(
            record_kpi_value(
                db,
                asset=asset,
                definition=registration.definition,
                calculation=calculation,
                workspace_id=workspace_id,
                mission_id=(
                    calculation.mission_id
                    or (
                        str(context.metadata["mission_id"])
                        if context.metadata.get("mission_id")
                        else None
                    )
                ),
                dataset_id=(
                    calculation.dataset_id
                    or (
                        str(context.metadata["dataset_id"])
                        if context.metadata.get("dataset_id")
                        else None
                    )
                ),
            )
        )

    observation_rows: list[Observation] = []
    pending: list[PendingAction] = []
    for registration in rules.registrations(context.sector):
        outcome = registration.evaluate(context, calculations)
        if outcome is None:
            continue
        by_key: dict[str, Observation] = {}
        for proposal in outcome.observations:
            row = record_observation(
                db,
                asset=asset,
                proposal=proposal,
                workspace_id=workspace_id,
            )
            observation_rows.append(row)
            by_key[proposal.key] = row
        for recommendation in outcome.actions:
            source = by_key.get(recommendation.source_observation_key or "")
            pending.append(
                PendingAction(
                    rule_key=registration.key,
                    rule_version=registration.version,
                    recommendation=recommendation,
                    source_observation_id=source.id if source else None,
                )
            )

    return EvaluationResult(tuple(value_rows), tuple(observation_rows), tuple(pending))


def summary_status(kpis: Sequence[Mapping[str, Any]]) -> KpiStatus:
    return worst_kpi_status([str(item.get("status", "UNKNOWN")) for item in kpis])


__all__ = [
    "EvaluationResult",
    "IntelligenceError",
    "PendingAction",
    "asset_kpi_payloads",
    "definition_payload",
    "ensure_kpi_definition",
    "evaluate_asset",
    "kpi_payload",
    "list_asset_observations",
    "observation_payload",
    "record_kpi_value",
    "record_observation",
    "summary_status",
]
