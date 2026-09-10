"""Cross-sector rollout gates for workspace and member scoped flags."""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi import HTTPException

from app.integrations.registry import NullFeatureFlagEvaluator
from app.integrations.registry import DeterministicFeatureFlagEvaluator
from app.integrations.registry.sector_rollout import sector_rollout_enabled
from app.models import (
    Account,
    AccountMember,
    Asset,
    Company,
    FeatureFlagOverride,
    InternalRoleAssignment,
    User,
)
from app.core.tokens import create_user_access_token
from app.modules.identity.domain import AuthorizationContext
from app.sectors.agriculture.router import _asset as agriculture_asset


SECTORS = ("agriculture", "infrastructure", "environmental", "mining", "ports")
ASSET_KINDS = {
    "agriculture": ("AGRICULTURE", "FARM"),
    "infrastructure": ("INFRASTRUCTURE", "ROAD"),
    "environmental": ("ENVIRONMENTAL", "ENVIRONMENTAL_SITE"),
    "mining": ("MINING", "QUARRY"),
    "ports": ("PORTS_INDUSTRIAL", "QUAY"),
}


def _fixture(db_session):
    suffix = uuid.uuid4().hex
    owner = User(
        email=f"sector-owner-{suffix}@example.com",
        role="cliente",
        is_active=True,
    )
    colleague = User(
        email=f"sector-colleague-{suffix}@example.com",
        role="cliente",
        is_active=True,
    )
    organization = Company(
        name=f"Sector rollout {suffix}",
        email=f"sector-org-{suffix}@example.com",
        country="Angola",
        status="active",
        subscription_plan="enterprise",
    )
    db_session.add_all([owner, colleague, organization])
    db_session.flush()
    db_session.add(
        InternalRoleAssignment(
            user_id=owner.id,
            role="GV_ANALYST",
            assigned_by_user_id=owner.id,
        )
    )
    workspace = Account(
        organization_id=organization.id,
        name="Five-sector workspace",
        sector_focus="agriculture,infrastructure,environmental,mining,ports",
        entity_type="company",
        customer_type="multi_sector",
        dashboard_profile="operations",
        modules_enabled=json.dumps(list(SECTORS)),
        status="active",
    )
    db_session.add(workspace)
    db_session.flush()
    db_session.add_all(
        [
            AccountMember(
                account_id=workspace.id,
                user_id=user.id,
                role="owner" if user is owner else "member",
                status="active",
            )
            for user in (owner, colleague)
        ]
    )
    db_session.commit()
    return organization, workspace, owner, colleague


def _headers(user: User, workspace_id: str) -> dict[str, str]:
    token = create_user_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        auth_generation=user.auth_generation,
    )
    return {
        "Authorization": f"Bearer {token}",
        "X-Workspace-ID": workspace_id,
    }


def _context(organization: Company, workspace: Account, user: User):
    return AuthorizationContext(
        user_id=user.id,
        identity_subject=f"internal:{user.id}",
        active_workspace_id=workspace.id,
        active_organization_id=organization.id,
        workspace_role="owner",
        organization_role="owner",
        permissions=frozenset({"organization:read", "asset:read", "asset:update"}),
    )


def test_all_sector_flags_honor_workspace_member_and_http_precedence(
    client, db_session
):
    organization, workspace, owner, colleague = _fixture(db_session)
    owner_context = _context(organization, workspace, owner)
    colleague_context = _context(organization, workspace, colleague)
    evaluator = NullFeatureFlagEvaluator()

    for sector in SECTORS:
        assert sector_rollout_enabled(
            db_session,
            context=owner_context,
            sector=sector,
            evaluator=evaluator,
            provider_configured=False,
        )
        db_session.add(
            FeatureFlagOverride(
                organization_id=organization.id,
                workspace_id=workspace.id,
                flag_key=f"geovision.sectors.{sector}",
                enabled=False,
                source="GEOVISION",
                created_by_user_id=owner.id,
                updated_by_user_id=owner.id,
            )
        )
        asset_sector, asset_type = ASSET_KINDS[sector]
        db_session.add(
            Asset(
                organization_id=organization.id,
                workspace_id=workspace.id,
                sector=asset_sector,
                asset_type=asset_type,
                name=f"Synthetic {sector} rollout asset",
                status="active",
                created_by_user_id=owner.id,
                updated_by_user_id=owner.id,
            )
        )
        db_session.add(
            FeatureFlagOverride(
                organization_id=organization.id,
                workspace_id=workspace.id,
                user_id=owner.id,
                flag_key=f"geovision.sectors.{sector}",
                enabled=True,
                source="GEOVISION",
                created_by_user_id=owner.id,
                updated_by_user_id=owner.id,
            )
        )
    db_session.commit()

    for sector in SECTORS:
        assert sector_rollout_enabled(
            db_session,
            context=owner_context,
            sector=sector,
            evaluator=evaluator,
            provider_configured=False,
        )
        assert not sector_rollout_enabled(
            db_session,
            context=colleague_context,
            sector=sector,
            evaluator=evaluator,
            provider_configured=False,
        )

    assets = {
        row.sector: row
        for row in db_session.query(Asset)
        .filter(Asset.organization_id == organization.id)
        .all()
    }
    path_sectors = {
        "AGRICULTURE": "agriculture",
        "INFRASTRUCTURE": "infrastructure",
        "ENVIRONMENTAL": "environmental",
        "MINING": "mining",
        "PORTS_INDUSTRIAL": "ports",
    }
    for asset_sector, path_sector in path_sectors.items():
        denied = client.get(
            f"/assets/{assets[asset_sector].id}/{path_sector}/report-context",
            headers=_headers(colleague, workspace.id),
        )
        assert denied.status_code == 403, denied.text
        assert "disabled" in denied.json()["detail"].lower()


def test_configured_rollout_provider_fails_closed_and_blocks_sector_operation(
    client,
    db_session,
):
    organization, workspace, owner, colleague = _fixture(db_session)
    owner_context = _context(organization, workspace, owner)
    colleague_context = _context(organization, workspace, colleague)
    evaluator = NullFeatureFlagEvaluator()

    assert not sector_rollout_enabled(
        db_session,
        context=owner_context,
        sector="agriculture",
        evaluator=evaluator,
        provider_configured=True,
    )

    db_session.add(
        FeatureFlagOverride(
            organization_id=organization.id,
            workspace_id=workspace.id,
            flag_key="geovision.sectors.agriculture",
            enabled=False,
            source="GEOVISION",
            created_by_user_id=owner.id,
            updated_by_user_id=owner.id,
        )
    )
    asset = Asset(
        organization_id=organization.id,
        workspace_id=workspace.id,
        sector="AGRICULTURE",
        asset_type="FARM",
        name="Synthetic rollout farm",
        status="active",
        created_by_user_id=owner.id,
        updated_by_user_id=owner.id,
    )
    db_session.add(asset)
    db_session.commit()

    with pytest.raises(HTTPException) as denied:
        agriculture_asset(
            db_session,
            colleague_context,
            asset.id,
            write=False,
        )
    assert denied.value.status_code == 403
    assert "disabled" in str(denied.value.detail).lower()

    report = client.post(
        f"/assets/{asset.id}/reports",
        headers=_headers(owner, workspace.id),
        json={"idempotency_key": f"rollout-report-{uuid.uuid4().hex}"},
    )
    assert report.status_code == 403, report.text
    assert report.json()["detail"] == (
        "Sector report generation is disabled for this workspace member"
    )


def test_configured_external_decisions_are_honored(db_session):
    organization, workspace, owner, _colleague = _fixture(db_session)
    context = _context(organization, workspace, owner)
    key = "geovision.sectors.agriculture"

    assert not sector_rollout_enabled(
        db_session,
        context=context,
        sector="agriculture",
        evaluator=DeterministicFeatureFlagEvaluator({key: False}),
        provider_configured=True,
    )
    assert sector_rollout_enabled(
        db_session,
        context=context,
        sector="agriculture",
        evaluator=DeterministicFeatureFlagEvaluator({key: True}),
        provider_configured=True,
    )


def test_unknown_sector_and_missing_scope_fail_closed(db_session):
    organization, workspace, owner, _colleague = _fixture(db_session)
    evaluator = NullFeatureFlagEvaluator()
    context = _context(organization, workspace, owner)

    assert not sector_rollout_enabled(
        db_session,
        context=context,
        sector="unknown",
        evaluator=evaluator,
        provider_configured=False,
    )
    assert not sector_rollout_enabled(
        db_session,
        context=AuthorizationContext(
            user_id=owner.id,
            identity_subject=f"internal:{owner.id}",
        ),
        sector="agriculture",
        evaluator=evaluator,
        provider_configured=False,
    )
