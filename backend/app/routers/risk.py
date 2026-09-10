"""
Risk Assessment Router

Endpoints for risk assessment using rule-based engine.
Public sectors use GeoVision's canonical six-sector taxonomy. Rule packs are
currently configured only where explicit threshold evidence exists.
"""

import logging
from typing import List
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.deps import get_authorization_context, get_db
from app.core.time import utc_now
from app.models import RiskAssessment as RiskAssessmentModel, Site
from app.modules.identity.domain import AuthorizationContext
from app.modules.organizations.domain import permission_granted

from app.services.risk_engine import (
    RISK_RULE_THRESHOLDS,
    RiskAssessmentRequest,
    RiskAssessmentResponse,
    RiskAlertSchema,
    RiskEngineNotConfiguredError,
    RiskEvidenceError,
    RuleResultSchema,
    SectorType,
    get_risk_engine,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/risk",
    tags=["risk"],
    dependencies=[Depends(get_authorization_context)],
)


# ============ SCHEMAS ============


class RiskHistoryItem(BaseModel):
    assessment_id: str
    risk_score: float
    risk_level: str
    triggered_count: int
    assessed_at: datetime


class RiskHistoryResponse(BaseModel):
    site_id: str
    sector: str
    assessments: List[RiskHistoryItem]
    trend: str  # improving, stable, worsening
    avg_score_7d: float
    avg_score_30d: float


# ============ DB-backed (no more in-memory store) ============


# ============ ENDPOINTS ============


def _authorized_site(
    db: Session,
    *,
    context: AuthorizationContext,
    site_id: str,
    permission: str,
) -> Site:
    if (
        not context.active_organization_id
        or not context.active_workspace_id
        or not permission_granted(context.permissions, permission)
    ):
        raise HTTPException(status_code=403, detail="Workspace access denied")
    site = (
        db.query(Site)
        .filter(
            Site.id == site_id,
            Site.company_id == context.active_organization_id,
            Site.is_active.is_(True),
        )
        .one_or_none()
    )
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found")
    return site


def _require_site_sector(site: Site, requested_sector: SectorType) -> None:
    try:
        site_sector = SectorType(site.sector)
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail="Site sector is outside the supported taxonomy",
        ) from exc
    if requested_sector is not site_sector:
        raise HTTPException(
            status_code=409,
            detail="Requested risk sector does not match the site sector",
        )


@router.post("/assess", response_model=RiskAssessmentResponse)
async def assess_risk(
    request: RiskAssessmentRequest,
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    site = _authorized_site(
        db,
        context=context,
        site_id=request.site_id,
        permission="asset:update",
    )
    _require_site_sector(site, request.sector)
    engine = get_risk_engine()
    try:
        result = engine.assess(
            site_id=request.site_id, sector=request.sector, data=request.data
        )
    except RiskEngineNotConfiguredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RiskEvidenceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Persist to DB
    import json as _json

    ra = RiskAssessmentModel(
        id=result.assessment_id,
        site_id=result.site_id,
        sector=result.sector.value,
        risk_score=result.risk_score,
        risk_level=result.risk_level.value,
        triggered_count=len(result.triggered_rules),
        details_json=_json.dumps(
            {
                "triggered_rules": [r.rule_id for r in result.triggered_rules],
                "recommendations": result.recommendations,
            }
        ),
    )
    db.add(ra)
    db.commit()

    logger.info(
        f"Risk assessment for site {request.site_id}: score={result.risk_score}, level={result.risk_level.value}"
    )

    return RiskAssessmentResponse(
        assessment_id=result.assessment_id,
        site_id=result.site_id,
        sector=result.sector.value,
        risk_score=result.risk_score,
        risk_level=result.risk_level.value,
        triggered_rules=[
            RuleResultSchema(
                rule_id=r.rule_id,
                rule_name=r.rule_name,
                triggered=r.triggered,
                score_contribution=r.score_contribution,
                message=r.message,
                severity=r.severity.value,
                data=r.data,
            )
            for r in result.triggered_rules
        ],
        alerts=[
            RiskAlertSchema(
                id=a.id,
                title=a.title,
                message=a.message,
                severity=a.severity.value,
                sector=a.sector.value,
                source=a.source,
                metric_name=a.metric_name,
                metric_value=a.metric_value,
                threshold=a.threshold,
                recommendation=a.recommendation,
                created_at=a.created_at,
            )
            for a in result.alerts
        ],
        recommendations=result.recommendations,
        assessed_at=result.assessed_at,
    )


@router.get("/history/{site_id}", response_model=RiskHistoryResponse)
async def get_risk_history(
    site_id: str,
    sector: SectorType = Query(...),
    days: int = Query(30, ge=1, le=365),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    site = _authorized_site(
        db,
        context=context,
        site_id=site_id,
        permission="asset:read",
    )
    _require_site_sector(site, sector)
    cutoff = utc_now() - timedelta(days=days)
    rows = (
        db.query(RiskAssessmentModel)
        .filter(
            RiskAssessmentModel.site_id == site_id,
            RiskAssessmentModel.sector == sector.value,
            RiskAssessmentModel.created_at >= cutoff,
        )
        .order_by(RiskAssessmentModel.created_at.asc())
        .all()
    )

    if not rows:
        raise HTTPException(
            status_code=404,
            detail="No risk assessments found for this site and sector",
        )

    cutoff_7d = utc_now() - timedelta(days=7)
    scores_7d = [r.risk_score for r in rows if r.created_at >= cutoff_7d]
    scores_30d = [r.risk_score for r in rows]

    avg_7d = sum(scores_7d) / len(scores_7d) if scores_7d else 0
    avg_30d = sum(scores_30d) / len(scores_30d) if scores_30d else 0

    if len(scores_7d) >= 2:
        recent_avg = sum(scores_7d[-3:]) / min(3, len(scores_7d))
        earlier_avg = sum(scores_7d[:3]) / min(3, len(scores_7d))
        trend = (
            "improving"
            if recent_avg < earlier_avg - 5
            else ("worsening" if recent_avg > earlier_avg + 5 else "stable")
        )
    else:
        trend = "stable"

    return RiskHistoryResponse(
        site_id=site_id,
        sector=sector.value,
        assessments=[
            RiskHistoryItem(
                assessment_id=r.id,
                risk_score=r.risk_score,
                risk_level=r.risk_level,
                triggered_count=r.triggered_count or 0,
                assessed_at=r.created_at,
            )
            for r in rows
        ],
        trend=trend,
        avg_score_7d=round(avg_7d, 1),
        avg_score_30d=round(avg_30d, 1),
    )


@router.get("/thresholds/{sector}")
async def get_sector_thresholds(sector: SectorType):
    """
    Get risk threshold definitions for a sector.

    Useful for configuring monitoring dashboards.
    """
    if sector not in RISK_RULE_THRESHOLDS:
        raise HTTPException(
            status_code=409,
            detail=f"Risk rules are not configured for sector: {sector.value}",
        )

    return {
        "sector": sector.value,
        "thresholds": RISK_RULE_THRESHOLDS[sector],
        "risk_levels": {
            "low": "score < 25",
            "medium": "25 <= score < 50",
            "high": "50 <= score < 75",
            "critical": "score >= 75",
        },
    }


@router.post("/simulate")
async def simulate_assessment(
    sector: SectorType = Query(...),
    scenario: str = Query("normal", pattern="^(normal|warning|critical)$"),
):
    """
    Simulate a risk assessment with predefined scenarios.

    Useful for testing dashboard alerts and notifications.
    """
    import uuid

    scenarios = {
        SectorType.MINING: {
            "normal": {
                "tailings_level_pct": 65,
                "terrain_displacement_mm": 5,
                "esg_score": 88,
                "dust_concentration_ppm": 30,
                "water_quality_index": 92,
                "extraction_efficiency_pct": 91,
            },
            "warning": {
                "tailings_level_pct": 82,
                "terrain_displacement_mm": 25,
                "esg_score": 72,
                "dust_concentration_ppm": 60,
                "water_quality_index": 75,
                "extraction_efficiency_pct": 78,
            },
            "critical": {
                "tailings_level_pct": 93,
                "terrain_displacement_mm": 55,
                "esg_score": 55,
                "dust_concentration_ppm": 120,
                "water_quality_index": 45,
                "extraction_efficiency_pct": 65,
            },
        },
        SectorType.CONSTRUCTION_INFRASTRUCTURE: {
            "normal": {
                "structural_health_index": 95,
                "timeline_delay_days": 2,
                "budget_overrun_pct": 3,
                "safety_incidents_30d": 0,
                "material_quality_pass_rate": 99,
            },
            "warning": {
                "structural_health_index": 78,
                "timeline_delay_days": 12,
                "budget_overrun_pct": 12,
                "safety_incidents_30d": 1,
                "material_quality_pass_rate": 93,
            },
            "critical": {
                "structural_health_index": 55,
                "timeline_delay_days": 45,
                "budget_overrun_pct": 28,
                "safety_incidents_30d": 4,
                "material_quality_pass_rate": 85,
            },
        },
    }

    if sector not in scenarios:
        raise HTTPException(
            status_code=400,
            detail=f"Simulation not available for sector: {sector.value}",
        )

    data = scenarios[sector][scenario]

    engine = get_risk_engine()
    result = engine.assess(
        site_id=f"simulation-{uuid.uuid4().hex[:8]}", sector=sector, data=data
    )

    return {
        "scenario": scenario,
        "sector": sector.value,
        "input_data": data,
        "result": {
            "risk_score": result.risk_score,
            "risk_level": result.risk_level.value,
            "triggered_rules": len(result.triggered_rules),
            "alerts": len(result.alerts),
            "recommendations": result.recommendations,
        },
    }
