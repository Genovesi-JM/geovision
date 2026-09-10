"""Permission-checked Agriculture evaluation and evidence APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.deps import get_authorization_context, get_current_user
from app.models import Asset, User
from app.modules.analytics.services import asset_kpi_payloads
from app.modules.assets.services import AssetAccessError, get_asset
from app.modules.identity.domain import AuthorizationContext
from app.sectors.agriculture.domain import (
    ALGORITHM_VERSION,
    AgricultureError,
    KPI_DEFINITIONS,
    SECTOR,
    SUPPORTED_ASSET_TYPES,
    SUPPORTED_DATASET_TYPES,
)
from app.sectors.agriculture.schemas import (
    AgricultureCapabilitiesOut,
    AgricultureEvaluationOut,
    AgricultureEvaluationRequest,
    AgricultureMapLayersOut,
    AgricultureReportContextOut,
)
from app.sectors.agriculture.services import (
    ANALYSIS_SCHEMA,
    agriculture_map_layers,
    agriculture_report_context,
    evaluate_agriculture,
)


router = APIRouter(tags=["agriculture"])


def _asset(
    db: Session,
    context: AuthorizationContext,
    asset_id: str,
    *,
    write: bool,
) -> Asset:
    try:
        return get_asset(
            db,
            context=context,
            asset_id=asset_id,
            permission="asset:update" if write else "asset:read",
        )
    except AssetAccessError as exc:
        status = 404 if exc.code == "asset_not_found" else 403
        raise HTTPException(status_code=status, detail=str(exc)) from exc


def _agriculture_error(exc: AgricultureError) -> HTTPException:
    return HTTPException(
        status_code=409 if exc.code in {"sector_mismatch", "asset_type_unsupported"} else 400,
        detail=str(exc),
    )


@router.get(
    "/sectors/agriculture/capabilities",
    response_model=AgricultureCapabilitiesOut,
)
def agriculture_capabilities(
    _context: AuthorizationContext = Depends(get_authorization_context),
):
    return {
        "sector": SECTOR,
        "enabled": True,
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
            "ORTHOMOSAIC",
            "NDVI",
            "NDRE",
            "GNDVI",
            "THERMAL_IMAGES",
            "SATELLITE_IMAGE",
            "SENSOR_POINT",
            "OBSERVATION_ZONE",
        ],
        "scientific_guardrails": [
            "Only explicit validated index values are evaluated.",
            "Weather or band availability alone never becomes a crop diagnosis.",
            "Mapped findings require field or specialist validation before treatment.",
        ],
    }


@router.post(
    "/assets/{asset_id}/agriculture/evaluate",
    response_model=AgricultureEvaluationOut,
)
def agriculture_evaluate(
    asset_id: str,
    payload: AgricultureEvaluationRequest,
    user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    asset = _asset(db, context, asset_id, write=True)
    try:
        evaluation = evaluate_agriculture(
            db,
            asset=asset,
            actor=user,
            as_of=payload.as_of,
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
    except AgricultureError as exc:
        db.rollback()
        raise _agriculture_error(exc) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/assets/{asset_id}/agriculture/map-layers",
    response_model=AgricultureMapLayersOut,
)
def agriculture_layers(
    asset_id: str,
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    asset = _asset(db, context, asset_id, write=False)
    try:
        items = agriculture_map_layers(db, asset=asset)
        return {"asset_id": asset.id, "items": items, "total": len(items)}
    except AgricultureError as exc:
        raise _agriculture_error(exc) from exc


@router.get(
    "/assets/{asset_id}/agriculture/report-context",
    response_model=AgricultureReportContextOut,
)
def agriculture_context(
    asset_id: str,
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    asset = _asset(db, context, asset_id, write=False)
    try:
        return agriculture_report_context(db, asset=asset)
    except AgricultureError as exc:
        raise _agriculture_error(exc) from exc


__all__ = ["router"]
