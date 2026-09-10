"""Permission-checked Industry, Energy and Utilities capability API."""

import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.deps import get_authorization_context
from app.integrations.registry import get_feature_flag_evaluator
from app.integrations.registry.sector_rollout import sector_rollout_enabled
from app.models import Account
from app.modules.identity.domain import AuthorizationContext
from app.sectors.industry.domain import (
    CAPABILITY_VERSION,
    EVIDENCE_GUARDRAILS,
    OPERATIONAL_KPIS,
    SECTOR,
    SUPPORTED_ASSET_TYPES,
    SUPPORTED_DATASET_TYPES,
)
from app.sectors.industry.schemas import IndustryCapabilitiesOut


router = APIRouter(tags=["industry-energy-utilities"])

_MODULE_KEYS = frozenset(
    {
        "industry_energy_utilities",
        "industry",
        "industrial",
        "energy",
        "utilities",
        "solar",
    }
)


def _workspace_enabled(db: Session, context: AuthorizationContext) -> bool:
    if not context.active_workspace_id or not context.active_organization_id:
        return False
    workspace = db.get(Account, context.active_workspace_id)
    if not workspace or workspace.organization_id != context.active_organization_id:
        return False
    try:
        modules = json.loads(workspace.modules_enabled or "[]")
    except (TypeError, ValueError):
        return False
    return workspace.status == "active" and bool(
        {str(item).casefold() for item in modules} & _MODULE_KEYS
    )


@router.get(
    "/sectors/industry/capabilities",
    response_model=IndustryCapabilitiesOut,
    include_in_schema=False,
)
@router.get(
    "/sectors/industry-energy-utilities/capabilities",
    response_model=IndustryCapabilitiesOut,
)
def industry_capabilities(
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    enabled = _workspace_enabled(db, context) and sector_rollout_enabled(
        db,
        context=context,
        sector=SECTOR,
        evaluator=get_feature_flag_evaluator(),
    )
    return {
        "sector": SECTOR,
        "public_sector": "industry_energy_utilities",
        "enabled": enabled,
        "maturity": "expansion",
        "capability_version": CAPABILITY_VERSION,
        "asset_types": sorted(SUPPORTED_ASSET_TYPES),
        "dataset_types": sorted(SUPPORTED_DATASET_TYPES),
        "kpis": list(OPERATIONAL_KPIS),
        "evidence_guardrails": list(EVIDENCE_GUARDRAILS),
    }


__all__ = ["router"]
