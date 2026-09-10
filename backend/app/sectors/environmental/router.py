"""Permission-checked Environmental evaluation and evidence APIs."""

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
from app.sectors.environmental.domain import (
    ALGORITHM_VERSION,
    EnvironmentalError,
    KPI_DEFINITIONS,
    SECTOR,
    SUPPORTED_ASSET_TYPES,
    SUPPORTED_DATASET_TYPES,
)
from app.sectors.environmental.schemas import (
    EnvironmentalCapabilitiesOut,
    EnvironmentalComparisonsOut,
    EnvironmentalEvaluationOut,
    EnvironmentalEvaluationRequest,
    EnvironmentalMapLayersOut,
    EnvironmentalReportContextOut,
)
from app.sectors.environmental.services import (
    ANALYSIS_SCHEMA,
    environmental_comparisons,
    environmental_enabled_for_context,
    environmental_map_layers,
    environmental_report_context,
    evaluate_environmental,
)


router = APIRouter(tags=["environmental"])


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
        raise HTTPException(status_code=403, detail="Environmental rollout is disabled")
    return asset


def _environmental_error(exc: EnvironmentalError) -> HTTPException:
    return HTTPException(
        status_code=403 if exc.code == "feature_disabled" else 409,
        detail=str(exc),
    )


@router.get(
    "/sectors/environmental/capabilities",
    response_model=EnvironmentalCapabilitiesOut,
)
def environmental_capabilities(
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    return {
        "sector": SECTOR,
        "enabled": environmental_enabled_for_context(db, context=context)
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
        "comparison_kinds": [
            "SATELLITE_2D",
            "DRONE_2D",
            "THERMAL_2D",
            "TERRAIN_3D",
        ],
        "evidence_guardrails": [
            "Only explicitly validated and versioned analysis becomes a KPI.",
            "Change metrics require a compatible, aligned, time-ordered dataset pair.",
            "Terrain-change candidates require a paired surface and vertical datum.",
            "Public GIS, weather, satellite, and sensor sources provide context, not causation.",
            "All detected candidates require authorized review before impact or remediation decisions.",
        ],
    }


@router.post(
    "/assets/{asset_id}/environmental/evaluate",
    response_model=EnvironmentalEvaluationOut,
)
def environmental_evaluate(
    asset_id: str,
    payload: EnvironmentalEvaluationRequest,
    user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    asset = _asset(db, context, asset_id, write=True)
    try:
        evaluation = evaluate_environmental(
            db, asset=asset, actor=user, as_of=payload.as_of
        )
        db.commit()
        return {
            "asset_id": asset.id,
            "evaluated_at": evaluation.sources.evaluation.measured_at,
            "source_availability": dict(evaluation.sources.availability),
            "evidence": dict(evaluation.sources.evidence),
            "environmental_context": dict(evaluation.sources.context),
            "kpi_value_ids": [row.id for row in evaluation.result.kpi_values],
            "observation_ids": [row.id for row in evaluation.result.observations],
            "action_ids": [row.id for row in evaluation.actions],
            "kpis": asset_kpi_payloads(db, asset),
        }
    except EnvironmentalError as exc:
        db.rollback()
        raise _environmental_error(exc) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/assets/{asset_id}/environmental/comparisons",
    response_model=EnvironmentalComparisonsOut,
)
def environmental_comparison_list(
    asset_id: str,
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    asset = _asset(db, context, asset_id, write=False)
    try:
        items = environmental_comparisons(db, asset=asset)
        return {"asset_id": asset.id, "items": items, "total": len(items)}
    except EnvironmentalError as exc:
        raise _environmental_error(exc) from exc


@router.get(
    "/assets/{asset_id}/environmental/map-layers",
    response_model=EnvironmentalMapLayersOut,
)
def environmental_layers(
    asset_id: str,
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    asset = _asset(db, context, asset_id, write=False)
    try:
        items = environmental_map_layers(db, asset=asset)
        return {"asset_id": asset.id, "items": items, "total": len(items)}
    except EnvironmentalError as exc:
        raise _environmental_error(exc) from exc


@router.get(
    "/assets/{asset_id}/environmental/report-context",
    response_model=EnvironmentalReportContextOut,
)
def environmental_context(
    asset_id: str,
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    asset = _asset(db, context, asset_id, write=False)
    try:
        return environmental_report_context(db, asset=asset)
    except EnvironmentalError as exc:
        raise _environmental_error(exc) from exc


__all__ = ["router"]
