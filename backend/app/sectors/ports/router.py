"""Permission-checked Ports and Logistics intelligence APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.deps import get_authorization_context, get_current_user
from app.integrations.registry import get_feature_flag_evaluator
from app.integrations.registry.sector_rollout import sector_rollout_enabled
from app.models import Asset, User
from app.modules.analytics.services import asset_kpi_payloads
from app.modules.assets.services import AssetAccessError, get_asset
from app.modules.identity.domain import AuthorizationContext
from app.sectors.ports.domain import (
    ALGORITHM_VERSION,
    KPI_DEFINITIONS,
    SECTOR,
    SUPPORTED_ASSET_TYPES,
    SUPPORTED_DATASET_TYPES,
    PortsError,
)
from app.sectors.ports.schemas import (
    PortsCapabilitiesOut,
    PortsComparisonsOut,
    PortsEvaluationOut,
    PortsEvaluationRequest,
    PortsInspectionHistoryOut,
    PortsMapLayersOut,
    PortsReportContextOut,
)
from app.sectors.ports.services import (
    ANALYSIS_SCHEMA,
    evaluate_ports,
    ports_comparisons,
    ports_enabled_for_context,
    ports_inspection_history,
    ports_map_layers,
    ports_report_context,
)


router = APIRouter(tags=["ports-logistics"])


def _rollout_enabled(db: Session, context: AuthorizationContext) -> bool:
    return sector_rollout_enabled(
        db,
        context=context,
        sector=SECTOR,
        evaluator=get_feature_flag_evaluator(),
    )


def _asset(
    db: Session,
    context: AuthorizationContext,
    asset_id: str,
    *,
    write: bool,
) -> Asset:
    try:
        asset = get_asset(
            db,
            context=context,
            asset_id=asset_id,
            permission="asset:update" if write else "asset:read",
        )
    except AssetAccessError as exc:
        status = 404 if exc.code == "asset_not_found" else 403
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    if not _rollout_enabled(db, context):
        raise HTTPException(status_code=403, detail="Ports rollout is disabled")
    return asset


def _ports_error(exc: PortsError) -> HTTPException:
    return HTTPException(
        status_code=403 if exc.code == "feature_disabled" else 409,
        detail=str(exc),
    )


@router.get(
    "/sectors/ports/capabilities",
    response_model=PortsCapabilitiesOut,
    include_in_schema=False,
)
@router.get(
    "/sectors/ports-logistics/capabilities",
    response_model=PortsCapabilitiesOut,
)
def ports_capabilities(
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    return {
        "sector": SECTOR,
        "public_sector": "ports_logistics",
        "maturity": "expansion",
        "enabled": ports_enabled_for_context(db, context=context)
        and _rollout_enabled(db, context),
        "algorithm_bundle_version": ALGORITHM_VERSION,
        "analysis_schema": ANALYSIS_SCHEMA,
        "asset_types": sorted(SUPPORTED_ASSET_TYPES),
        "dataset_types": sorted(SUPPORTED_DATASET_TYPES),
        "kpis": [
            {
                "key": item.key,
                "name": item.name,
                "unit": item.unit,
                "importance": item.importance.value,
                "calculator": item.calculator,
                "version": item.version,
            }
            for item in KPI_DEFINITIONS
        ],
        "map_layer_kinds": [
            "ASSET_BOUNDARY",
            "OBSERVATION_ZONE",
            *sorted(SUPPORTED_DATASET_TYPES),
        ],
        "comparison_kinds": ["VISUAL_2D", "THERMAL_2D", "REALITY_3D"],
        "evidence_guardrails": [
            "Only PASSED, versioned, validated analysis with exact asset identity is promoted.",
            "New candidates require a registered chronological same-asset comparison.",
            "Thermal candidates require reviewed calibration and environmental context.",
            "Condition summaries require an authorized specialist review reference.",
            "Sensor context uses auditable assignments and asset snapshots; offline/replayed data is excluded.",
            "Missing evidence and cadence remain UNKNOWN or NOT_CONFIGURED, never healthy by default.",
            "No automatic defect, structural, safety, navigation, or compliance conclusion is generated.",
        ],
    }


@router.post(
    "/assets/{asset_id}/ports/evaluate",
    response_model=PortsEvaluationOut,
    include_in_schema=False,
)
@router.post(
    "/assets/{asset_id}/ports-logistics/evaluate",
    response_model=PortsEvaluationOut,
)
def ports_evaluate(
    asset_id: str,
    payload: PortsEvaluationRequest,
    user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    asset = _asset(db, context, asset_id, write=True)
    try:
        evaluation = evaluate_ports(db, asset=asset, actor=user, as_of=payload.as_of)
        db.commit()
        return {
            "asset_id": asset.id,
            "evaluated_at": evaluation.sources.evaluation.measured_at,
            "source_availability": dict(evaluation.sources.availability),
            "evidence": dict(evaluation.sources.evidence),
            "kpi_value_ids": [row.id for row in evaluation.result.kpi_values],
            "observation_ids": [row.id for row in evaluation.result.observations],
            "action_ids": [row.id for row in evaluation.actions],
            "kpis": asset_kpi_payloads(db, asset),
        }
    except PortsError as exc:
        db.rollback()
        raise _ports_error(exc) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/assets/{asset_id}/ports/inspection-history",
    response_model=PortsInspectionHistoryOut,
    include_in_schema=False,
)
@router.get(
    "/assets/{asset_id}/ports-logistics/inspection-history",
    response_model=PortsInspectionHistoryOut,
)
def ports_history(
    asset_id: str,
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    asset = _asset(db, context, asset_id, write=False)
    try:
        items = ports_inspection_history(db, asset=asset)
        return {"asset_id": asset.id, "items": items, "total": len(items)}
    except PortsError as exc:
        raise _ports_error(exc) from exc


@router.get(
    "/assets/{asset_id}/ports/comparisons",
    response_model=PortsComparisonsOut,
    include_in_schema=False,
)
@router.get(
    "/assets/{asset_id}/ports-logistics/comparisons",
    response_model=PortsComparisonsOut,
)
def ports_comparison_list(
    asset_id: str,
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    asset = _asset(db, context, asset_id, write=False)
    try:
        items = ports_comparisons(db, asset=asset)
        return {"asset_id": asset.id, "items": items, "total": len(items)}
    except PortsError as exc:
        raise _ports_error(exc) from exc


@router.get(
    "/assets/{asset_id}/ports/map-layers",
    response_model=PortsMapLayersOut,
    include_in_schema=False,
)
@router.get(
    "/assets/{asset_id}/ports-logistics/map-layers",
    response_model=PortsMapLayersOut,
)
def ports_layers(
    asset_id: str,
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    asset = _asset(db, context, asset_id, write=False)
    try:
        items = ports_map_layers(db, asset=asset)
        return {"asset_id": asset.id, "items": items, "total": len(items)}
    except PortsError as exc:
        raise _ports_error(exc) from exc


@router.get(
    "/assets/{asset_id}/ports/report-context",
    response_model=PortsReportContextOut,
    include_in_schema=False,
)
@router.get(
    "/assets/{asset_id}/ports-logistics/report-context",
    response_model=PortsReportContextOut,
)
def ports_context(
    asset_id: str,
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    asset = _asset(db, context, asset_id, write=False)
    try:
        return ports_report_context(db, asset=asset)
    except PortsError as exc:
        raise _ports_error(exc) from exc


__all__ = ["router"]
