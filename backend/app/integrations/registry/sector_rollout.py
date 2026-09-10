"""Composition-layer rollout gates for optional sector HTTP modules."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.identity.domain import AuthorizationContext
from app.modules.integration_registry.domain import (
    FeatureFlagEvaluator,
    IntegrationRegistryError,
    normalize_identifier,
)
from app.modules.integration_registry.services import resolve_feature_flag


_SECTOR_FLAG_NAMES = {
    "agriculture": "agriculture",
    "environmental": "environmental",
    "infrastructure": "infrastructure",
    "mining": "mining",
    "industry": "industry_energy_utilities",
    "industry_energy_utilities": "industry_energy_utilities",
    "ports": "ports",
    "ports_industrial": "ports",
    # Keep the deployed flag key while the public taxonomy uses ports_logistics.
    "ports_logistics": "ports",
}


def sector_rollout_enabled(
    db: Session,
    *,
    context: AuthorizationContext,
    sector: str,
    evaluator: FeatureFlagEvaluator,
    provider_configured: bool | None = None,
) -> bool:
    """Resolve the member/workspace rollout without replacing sector entitlements.

    Sector packages predate the external rollout service and are enabled by their
    workspace module configuration. In local installations with no rollout
    provider or explicit override, that established configuration remains the
    baseline. Once a provider is configured, an unavailable/missing decision is
    fail-closed.
    """

    normalized_sector = normalize_identifier(sector, field="sector")
    flag_sector = _SECTOR_FLAG_NAMES.get(normalized_sector)
    if flag_sector is None:
        return False
    if not context.active_organization_id or not context.active_workspace_id:
        return False
    try:
        resolution = resolve_feature_flag(
            db,
            flag_key=f"geovision.sectors.{flag_sector}",
            organization_id=context.active_organization_id,
            workspace_id=context.active_workspace_id,
            member_user_id=context.user_id,
            authorized=True,
            # The sector's existing workspace/module gate remains the entitlement
            # authority. This rollout gate can deny it, but cannot grant around it.
            entitled=True,
            evaluator=evaluator,
        )
    except IntegrationRegistryError:
        return False
    configured = (
        bool(settings.azure_app_configuration_endpoint)
        if provider_configured is None
        else provider_configured
    )
    if resolution.source == "fail_closed" and not configured:
        return True
    return resolution.enabled


__all__ = ["sector_rollout_enabled"]
