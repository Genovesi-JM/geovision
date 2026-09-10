"""Permission-checked Infrastructure evaluation and evidence APIs."""

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
from app.sectors.infrastructure.domain import (
    ALGORITHM_VERSION,
    InfrastructureError,
    KPI_DEFINITIONS,
    SECTOR,
    SUPPORTED_ASSET_TYPES,
    SUPPORTED_DATASET_TYPES,
)
from app.sectors.infrastructure.schemas import (
    InfrastructureCapabilitiesOut,
    InfrastructureComparisonsOut,
    InfrastructureEvaluationOut,
    InfrastructureEvaluationRequest,
    InfrastructureMapLayersOut,
    InfrastructureReportContextOut,
)
from app.sectors.infrastructure.services import (
    ANALYSIS_SCHEMA,
    evaluate_infrastructure,
    infrastructure_comparisons,
    infrastructure_enabled_for_context,
    infrastructure_map_layers,
    infrastructure_report_context,
)


router = APIRouter(tags=["infrastructure"])


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
        raise HTTPException(
            status_code=403, detail="Infrastructure rollout is disabled"
        )
    return asset


def _infrastructure_error(exc: InfrastructureError) -> HTTPException:
    status = 403 if exc.code == "feature_disabled" else 409
    return HTTPException(status_code=status, detail=str(exc))


@router.get(
    "/sectors/infrastructure/capabilities",
    response_model=InfrastructureCapabilitiesOut,
)
def infrastructure_capabilities(
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    return {
        "sector": SECTOR,
        "enabled": infrastructure_enabled_for_context(db, context=context)
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
        "comparison_kinds": ["SURVEY_2D", "SURFACE_3D", "THERMAL_2D"],
        "evidence_guardrails": [
            "Only explicitly validated and versioned analysis is accepted.",
            "Progress requires reviewed survey, signed quantity, or trusted 4D evidence.",
            "Cut/fill requires a compatible, aligned surface pair and vertical datum.",
            "Schedule variance requires a trusted, versioned schedule source.",
            "Detected candidates require specialist review and are not engineering conclusions.",
        ],
    }


@router.post(
    "/assets/{asset_id}/infrastructure/evaluate",
    response_model=InfrastructureEvaluationOut,
)
def infrastructure_evaluate(
    asset_id: str,
    payload: InfrastructureEvaluationRequest,
    user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    asset = _asset(db, context, asset_id, write=True)
    try:
        evaluation = evaluate_infrastructure(
            db, asset=asset, actor=user, as_of=payload.as_of
        )
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
    except InfrastructureError as exc:
        db.rollback()
        raise _infrastructure_error(exc) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/assets/{asset_id}/infrastructure/comparisons",
    response_model=InfrastructureComparisonsOut,
)
def infrastructure_comparison_list(
    asset_id: str,
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    asset = _asset(db, context, asset_id, write=False)
    try:
        items = infrastructure_comparisons(db, asset=asset)
        return {"asset_id": asset.id, "items": items, "total": len(items)}
    except InfrastructureError as exc:
        raise _infrastructure_error(exc) from exc


@router.get(
    "/assets/{asset_id}/infrastructure/map-layers",
    response_model=InfrastructureMapLayersOut,
)
def infrastructure_layers(
    asset_id: str,
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    asset = _asset(db, context, asset_id, write=False)
    try:
        items = infrastructure_map_layers(db, asset=asset)
        return {"asset_id": asset.id, "items": items, "total": len(items)}
    except InfrastructureError as exc:
        raise _infrastructure_error(exc) from exc


@router.get(
    "/assets/{asset_id}/infrastructure/report-context",
    response_model=InfrastructureReportContextOut,
)
def infrastructure_context(
    asset_id: str,
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    asset = _asset(db, context, asset_id, write=False)
    try:
        return infrastructure_report_context(db, asset=asset)
    except InfrastructureError as exc:
        raise _infrastructure_error(exc) from exc


__all__ = ["router"]
