"""
Risk Assessment Router

Endpoints for risk assessment using rule-based engine.
Sectors: Mining, Infrastructure, Construction, Agriculture, Demining
"""
import logging
import uuid as _uuid
from typing import Optional, List
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db

from app.services.risk_engine import (
    get_risk_engine,
    SectorType,
    RiskAssessmentRequest,
    RiskAssessmentResponse,
    RiskAlertSchema,
    RuleResultSchema,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/risk", tags=["risk"], dependencies=[Depends(get_current_user)])


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

@router.post("/assess", response_model=RiskAssessmentResponse)
async def assess_risk(request: RiskAssessmentRequest, db: Session = Depends(get_db)):
    engine = get_risk_engine()
    result = engine.assess(site_id=request.site_id, sector=request.sector, data=request.data)

    # Persist to DB
    from app.models import RiskAssessment as RAModel
    import json as _json
    ra = RAModel(
        id=result.assessment_id, site_id=result.site_id,
        sector=result.sector.value, risk_score=result.risk_score,
        risk_level=result.risk_level.value,
        triggered_count=len(result.triggered_rules),
        details_json=_json.dumps({
            "triggered_rules": [r.rule_id for r in result.triggered_rules],
            "recommendations": result.recommendations,
        }),
    )
    db.add(ra); db.commit()

    logger.info(f"Risk assessment for site {request.site_id}: score={result.risk_score}, level={result.risk_level.value}")

    return RiskAssessmentResponse(
        assessment_id=result.assessment_id,
        site_id=result.site_id,
        sector=result.sector.value,
        risk_score=result.risk_score,
        risk_level=result.risk_level.value,
        triggered_rules=[
            RuleResultSchema(rule_id=r.rule_id, rule_name=r.rule_name, triggered=r.triggered,
                             score_contribution=r.score_contribution, message=r.message,
                             severity=r.severity.value, data=r.data)
            for r in result.triggered_rules
        ],
        alerts=[
            RiskAlertSchema(id=a.id, title=a.title, message=a.message, severity=a.severity.value,
                            sector=a.sector.value, source=a.source, metric_name=a.metric_name,
                            metric_value=a.metric_value, threshold=a.threshold,
                            recommendation=a.recommendation, created_at=a.created_at)
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
    db: Session = Depends(get_db),
):
    from app.models import RiskAssessment as RAModel
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = (db.query(RAModel)
            .filter(RAModel.site_id == site_id, RAModel.created_at >= cutoff)
            .order_by(RAModel.created_at.asc()).all())

    if not rows:
        return RiskHistoryResponse(site_id=site_id, sector=sector.value,
                                   assessments=[], trend="stable", avg_score_7d=0, avg_score_30d=0)

    cutoff_7d = datetime.utcnow() - timedelta(days=7)
    scores_7d = [r.risk_score for r in rows if r.created_at >= cutoff_7d]
    scores_30d = [r.risk_score for r in rows]

    avg_7d = sum(scores_7d) / len(scores_7d) if scores_7d else 0
    avg_30d = sum(scores_30d) / len(scores_30d) if scores_30d else 0

    if len(scores_7d) >= 2:
        recent_avg = sum(scores_7d[-3:]) / min(3, len(scores_7d))
        earlier_avg = sum(scores_7d[:3]) / min(3, len(scores_7d))
        trend = "improving" if recent_avg < earlier_avg - 5 else ("worsening" if recent_avg > earlier_avg + 5 else "stable")
    else:
        trend = "stable"

    return RiskHistoryResponse(
        site_id=site_id, sector=sector.value,
        assessments=[
            RiskHistoryItem(assessment_id=r.id, risk_score=r.risk_score, risk_level=r.risk_level,
                            triggered_count=r.triggered_count or 0, assessed_at=r.created_at)
            for r in rows
        ],
        trend=trend, avg_score_7d=round(avg_7d, 1), avg_score_30d=round(avg_30d, 1),
    )


@router.get("/thresholds/{sector}")
async def get_sector_thresholds(sector: SectorType):
    """
    Get risk threshold definitions for a sector.
    
    Useful for configuring monitoring dashboards.
    """
    thresholds = {
        SectorType.MINING: {
            "tailings_level_pct": {"warning": 80, "critical": 90, "unit": "%"},
            "terrain_displacement_mm": {"warning": 20, "critical": 50, "unit": "mm"},
            "esg_score": {"warning": 75, "critical": 60, "unit": "%", "inverse": True},
            "dust_concentration_ppm": {"warning": 50, "critical": 100, "unit": "PPM"},
            "water_quality_index": {"warning": 70, "critical": 50, "unit": "index", "inverse": True},
            "extraction_efficiency_pct": {"warning": 80, "critical": 70, "unit": "%", "inverse": True},
        },
        SectorType.INFRASTRUCTURE: {
            "structural_health_index": {"warning": 80, "critical": 60, "unit": "index", "inverse": True},
            "timeline_delay_days": {"warning": 7, "critical": 30, "unit": "days"},
            "budget_overrun_pct": {"warning": 10, "critical": 20, "unit": "%"},
            "safety_incidents_30d": {"warning": 1, "critical": 3, "unit": "count"},
            "material_quality_pass_rate": {"warning": 95, "critical": 90, "unit": "%", "inverse": True},
        },
        SectorType.CONSTRUCTION: {
            "safety_score": {"warning": 80, "critical": 60, "unit": "%", "inverse": True},
            "progress_variance_pct": {"warning": 10, "critical": 20, "unit": "%"},
            "quality_defects_per_1000": {"warning": 5, "critical": 15, "unit": "per 1000"},
            "equipment_downtime_pct": {"warning": 10, "critical": 25, "unit": "%"},
        },
        SectorType.AGRO: {
            "ndvi_avg": {"warning": 0.4, "critical": 0.25, "unit": "index", "inverse": True},
            "soil_moisture_pct": {"warning": 30, "critical": 20, "unit": "%", "inverse": True},
            "pest_detection_count": {"warning": 5, "critical": 15, "unit": "count"},
            "irrigation_efficiency_pct": {"warning": 70, "critical": 50, "unit": "%", "inverse": True},
        },
        SectorType.DEMINING: {
            "clearance_progress_pct": {"warning": None, "critical": None, "unit": "%"},
            "safety_protocol_compliance": {"warning": 95, "critical": 90, "unit": "%", "inverse": True},
            "terrain_hazard_score": {"warning": 60, "critical": 80, "unit": "score"},
            "equipment_calibration_days": {"warning": 7, "critical": 14, "unit": "days since"},
        },
    }
    
    if sector not in thresholds:
        return {
            "sector": sector.value,
            "thresholds": {},
            "message": f"Thresholds for {sector.value} not configured yet"
        }
    
    return {
        "sector": sector.value,
        "thresholds": thresholds[sector],
        "risk_levels": {
            "low": "score < 25",
            "medium": "25 <= score < 50",
            "high": "50 <= score < 75",
            "critical": "score >= 75"
        }
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
        SectorType.INFRASTRUCTURE: {
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
            detail=f"Simulation not available for sector: {sector.value}"
        )
    
    data = scenarios[sector][scenario]
    
    engine = get_risk_engine()
    result = engine.assess(
        site_id=f"simulation-{uuid.uuid4().hex[:8]}",
        sector=sector,
        data=data
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
        }
    }
