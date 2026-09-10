"""Tenant-scoped read APIs for normalized KPI and observation intelligence."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.deps import get_authorization_context
from app.models import Action
from app.modules.analytics.domain import KpiStatus, worst_kpi_status
from app.modules.analytics.schemas import (
    AssetIntelligenceSummaryOut,
    AssetKpiListOut,
    IntelligenceAlertListOut,
    ObservationListOut,
)
from app.modules.analytics.services import (
    asset_kpi_payloads,
    list_asset_observations,
    observation_payload,
)
from app.modules.assets.services import AssetAccessError, get_asset
from app.modules.identity.domain import AuthorizationContext


router = APIRouter(tags=["intelligence"])


def _asset(db: Session, context: AuthorizationContext, asset_id: str):
    try:
        return get_asset(db, context=context, asset_id=asset_id, permission="asset:read")
    except AssetAccessError as exc:
        status = 404 if exc.code == "asset_not_found" else 403
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.get("/assets/{asset_id}/kpis", response_model=AssetKpiListOut)
def asset_kpis(
    asset_id: str,
    importance: Literal["PRIMARY", "SECONDARY", "TECHNICAL"] | None = None,
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    asset = _asset(db, context, asset_id)
    items = asset_kpi_payloads(db, asset)
    if importance:
        items = [
            item for item in items if item["definition"]["importance"] == importance
        ]
    return {"asset_id": asset.id, "items": items, "total": len(items)}


@router.get("/assets/{asset_id}/observations", response_model=ObservationListOut)
def asset_observations(
    asset_id: str,
    severity: Literal["INFO", "WATCH", "WARNING", "CRITICAL"] | None = None,
    validation_status: Literal[
        "UNVALIDATED", "NEEDS_REVIEW", "VALIDATED", "REJECTED"
    ]
    | None = None,
    since: datetime | None = None,
    limit: int = Query(100, ge=1, le=500),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    asset = _asset(db, context, asset_id)
    rows = list_asset_observations(
        db,
        asset=asset,
        severity=severity,
        validation_status=validation_status,
        since=since,
        limit=limit,
    )
    return {
        "asset_id": asset.id,
        "items": [observation_payload(row) for row in rows],
        "total": len(rows),
    }


@router.get("/assets/{asset_id}/alerts", response_model=IntelligenceAlertListOut)
def asset_alerts(
    asset_id: str,
    include_rejected: bool = False,
    limit: int = Query(100, ge=1, le=500),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    asset = _asset(db, context, asset_id)
    rows = list_asset_observations(
        db,
        asset=asset,
        severities=("WARNING", "CRITICAL"),
        exclude_validation_statuses=(() if include_rejected else ("REJECTED",)),
        limit=limit,
    )
    items = [
        {
            "id": row.id,
            "asset_id": row.asset_id,
            "observation_type": row.observation_type,
            "severity": row.severity,
            "validation_status": row.validation_status,
            "confidence": row.confidence,
            "detected_at": row.detected_at,
            "source": row.source,
            "algorithm_version": row.algorithm_version,
        }
        for row in rows
    ]
    return {
        "asset_id": asset.id,
        "items": items,
        "total": len(items),
        "critical_count": sum(item["severity"] == "CRITICAL" for item in items),
        "warning_count": sum(item["severity"] == "WARNING" for item in items),
        "unvalidated_count": sum(
            item["validation_status"] in {"UNVALIDATED", "NEEDS_REVIEW"}
            for item in items
        ),
    }


@router.get("/assets/{asset_id}/summary", response_model=AssetIntelligenceSummaryOut)
def asset_intelligence_summary(
    asset_id: str,
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    asset = _asset(db, context, asset_id)
    kpis = asset_kpi_payloads(db, asset)
    observations = list_asset_observations(db, asset=asset, limit=500)
    primary = [item for item in kpis if item["definition"]["importance"] == "PRIMARY"]
    secondary = [
        item for item in kpis if item["definition"]["importance"] == "SECONDARY"
    ]
    status_inputs = primary or secondary or kpis
    status = (
        worst_kpi_status([item["status"] for item in status_inputs])
        if status_inputs
        else KpiStatus.UNKNOWN
    )
    confidence_values = [
        float(item["confidence"])
        for item in status_inputs
        if item["confidence"] is not None
    ]
    measured_values = [
        item["measured_at"] for item in status_inputs if item["measured_at"] is not None
    ]
    active_actions = (
        db.query(Action)
        .filter(
            Action.organization_id == asset.organization_id,
            Action.asset_id == asset.id,
            Action.status.in_(("OPEN", "IN_PROGRESS")),
        )
        .count()
    )
    relevant_observations = [
        row for row in observations if row.validation_status != "REJECTED"
    ]
    return {
        "asset_id": asset.id,
        "sector": asset.sector,
        "status": status.value,
        "confidence": (
            sum(confidence_values) / len(confidence_values)
            if confidence_values
            else None
        ),
        "measured_at": max(measured_values) if measured_values else None,
        "primary_kpis": primary,
        "secondary_kpis": secondary,
        "technical_kpi_count": sum(
            item["definition"]["importance"] == "TECHNICAL" for item in kpis
        ),
        "open_action_count": active_actions,
        "critical_observation_count": sum(
            row.severity == "CRITICAL" for row in relevant_observations
        ),
        "warning_observation_count": sum(
            row.severity == "WARNING" for row in relevant_observations
        ),
        "unvalidated_observation_count": sum(
            row.validation_status in {"UNVALIDATED", "NEEDS_REVIEW"}
            for row in relevant_observations
        ),
        "latest_observation_at": (
            max(row.detected_at for row in observations) if observations else None
        ),
    }


__all__ = ["router"]
