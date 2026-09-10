"""Permission-checked Mining/Quarry survey intelligence APIs."""

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
from app.sectors.mining.domain import (
    ALGORITHM_VERSION,
    KPI_DEFINITIONS,
    SECTOR,
    SUPPORTED_ASSET_TYPES,
    SUPPORTED_DATASET_TYPES,
    MiningError,
)
from app.sectors.mining.schemas import (
    MiningCapabilitiesOut,
    MiningComparisonsOut,
    MiningEvaluationOut,
    MiningEvaluationRequest,
    MiningMapLayersOut,
    MiningReportContextOut,
)
from app.sectors.mining.services import (
    ANALYSIS_SCHEMA,
    evaluate_mining,
    mining_comparisons,
    mining_enabled_for_context,
    mining_map_layers,
    mining_report_context,
)


router = APIRouter(tags=["mining"])


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
        raise HTTPException(status_code=403, detail="Mining rollout is disabled")
    return asset


def _mining_error(exc: MiningError) -> HTTPException:
    return HTTPException(
        status_code=403 if exc.code == "feature_disabled" else 409,
        detail=str(exc),
    )


@router.get("/sectors/mining/capabilities", response_model=MiningCapabilitiesOut)
def mining_capabilities(
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    return {
        "sector": SECTOR,
        "enabled": mining_enabled_for_context(db, context=context)
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
        "comparison_kinds": ["SURVEY_2D", "SURFACE_3D"],
        "evidence_guardrails": [
            "Only validated, versioned analysis on PASSED datasets becomes a KPI.",
            "Precise volumes require reviewed project tolerances and measured accuracy evidence.",
            "RTK/PPK photogrammetry can satisfy the volume gate without LiDAR.",
            "Change requires compatible tenant-owned surfaces, aligned references, and strict chronology.",
            "Slope and haul-road outputs remain review candidates, never automatic conclusions.",
            "No reserve, ore-grade, resource, geotechnical, safety, defect, or compliance claim is generated.",
        ],
    }


@router.post(
    "/assets/{asset_id}/mining/evaluate",
    response_model=MiningEvaluationOut,
)
def mining_evaluate(
    asset_id: str,
    payload: MiningEvaluationRequest,
    user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    asset = _asset(db, context, asset_id, write=True)
    try:
        evaluation = evaluate_mining(db, asset=asset, actor=user, as_of=payload.as_of)
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
    except MiningError as exc:
        db.rollback()
        raise _mining_error(exc) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/assets/{asset_id}/mining/comparisons",
    response_model=MiningComparisonsOut,
)
def mining_comparison_list(
    asset_id: str,
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    asset = _asset(db, context, asset_id, write=False)
    try:
        items = mining_comparisons(db, asset=asset)
        return {"asset_id": asset.id, "items": items, "total": len(items)}
    except MiningError as exc:
        raise _mining_error(exc) from exc


@router.get(
    "/assets/{asset_id}/mining/map-layers",
    response_model=MiningMapLayersOut,
)
def mining_layers(
    asset_id: str,
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    asset = _asset(db, context, asset_id, write=False)
    try:
        items = mining_map_layers(db, asset=asset)
        return {"asset_id": asset.id, "items": items, "total": len(items)}
    except MiningError as exc:
        raise _mining_error(exc) from exc


@router.get(
    "/assets/{asset_id}/mining/report-context",
    response_model=MiningReportContextOut,
)
def mining_context(
    asset_id: str,
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    asset = _asset(db, context, asset_id, write=False)
    try:
        return mining_report_context(db, asset=asset)
    except MiningError as exc:
        raise _mining_error(exc) from exc


__all__ = ["router"]
