"""High-value authorization and privacy gates for a production release."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

import pytest
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from app.core.tokens import create_user_access_token
from app.models import (
    Account,
    AccountMember,
    Asset,
    Company,
    CompanyUser,
    InternalRoleAssignment,
    Invitation,
    RiskAssessment,
    Site,
    User,
)


pytestmark = pytest.mark.security_regression


def _user(db_session, label: str, *, role: str = "client") -> User:
    row = User(
        email=f"security-{label}-{uuid.uuid4().hex}@example.com",
        role=role,
        is_active=True,
    )
    db_session.add(row)
    db_session.commit()
    return row


def _headers(user: User, workspace_id: str | None = None) -> dict[str, str]:
    token = create_user_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        auth_generation=user.auth_generation,
    )
    headers = {"Authorization": f"Bearer {token}"}
    if workspace_id:
        headers["X-Workspace-ID"] = workspace_id
    return headers


def _scope(
    db_session,
    actor: User,
    label: str,
    *,
    role: str = "owner",
    sector: str = "agriculture",
) -> tuple[Company, Account, Site]:
    suffix = uuid.uuid4().hex[:10]
    organization = Company(
        name=f"Security {label} {suffix}",
        email=f"security-org-{label}-{suffix}@example.test",
        status="active",
    )
    db_session.add(organization)
    db_session.flush()
    workspace = Account(
        organization_id=organization.id,
        name=f"Security workspace {label} {suffix}",
        sector_focus=sector,
        entity_type="organization",
        customer_type="farm",
        dashboard_profile="farm",
        modules_enabled='["assets","analytics"]',
        status="active",
    )
    db_session.add(workspace)
    db_session.flush()
    db_session.add_all(
        [
            CompanyUser(
                company_id=organization.id,
                user_id=actor.id,
                email=actor.email,
                role=role,
                is_active=True,
                status="active",
            ),
            AccountMember(
                account_id=workspace.id,
                user_id=actor.id,
                role=role,
                status="active",
            ),
        ]
    )
    site = Site(
        company_id=organization.id,
        name=f"Security site {label}",
        sector=sector,
        is_active=True,
    )
    db_session.add(site)
    db_session.commit()
    return organization, workspace, site


def _add_member(
    db_session,
    *,
    user: User,
    organization: Company,
    workspace: Account,
    role: str,
) -> None:
    db_session.add_all(
        [
            CompanyUser(
                company_id=organization.id,
                user_id=user.id,
                email=user.email,
                role=role,
                is_active=True,
                status="active",
            ),
            AccountMember(
                account_id=workspace.id,
                user_id=user.id,
                role=role,
                status="active",
            ),
        ]
    )
    db_session.commit()


def _dependency_names(dependant: Dependant) -> set[str]:
    names: set[str] = set()
    pending = list(dependant.dependencies)
    visited: set[int] = set()
    while pending:
        dependency = pending.pop()
        if id(dependency) in visited:
            continue
        visited.add(id(dependency))
        call = dependency.call
        name = getattr(call, "__name__", None)
        if name:
            names.add(name)
        pending.extend(dependency.dependencies)
    return names


def _routes(application) -> list[APIRoute]:
    return [route for route in application.routes if isinstance(route, APIRoute)]


def test_obsolete_unscoped_account_and_project_routes_are_not_mounted(client):
    paths = {route.path for route in _routes(client.app)}
    for obsolete_prefix in (
        "/projects",
        "/accounts/customers",
        "/accounts/employees",
    ):
        assert not any(
            path == obsolete_prefix or path.startswith(f"{obsolete_prefix}/")
            for path in paths
        )


def test_internal_route_families_keep_canonical_authorization_dependencies(client):
    checked: set[tuple[str, str]] = set()
    for route in _routes(client.app):
        names = _dependency_names(route.dependant)
        methods = route.methods - {"HEAD", "OPTIONS"}
        required: str | None = None

        if route.path.startswith("/admin") or route.path.startswith("/shop/admin"):
            required = "require_admin"
        elif route.path.startswith("/payments/admin"):
            required = "require_billing_staff"
        elif route.path.startswith("/catalog/internal"):
            required = "require_catalog_staff"
        elif route.path.startswith("/orders/internal"):
            required = "require_order_staff"
        elif route.path.startswith("/missions/internal"):
            required = "require_mission_staff"
        elif route.path.startswith("/processing/jobs"):
            required = "require_operations_staff"
        elif route.path.startswith("/internal/economics"):
            required = (
                "require_economics_recorder"
                if "POST" in methods
                else "require_economics_viewer"
            )
        elif route.path in {
            "/operations/experience",
            "/operations/dashboard",
            "/operations/queues",
        }:
            required = "require_internal_actor"
        elif route.path.startswith("/operations/contractor/me"):
            required = "get_current_user"
        elif route.path.startswith("/operations/") and route.path != (
            "/operations/contractor/uploads/local"
        ):
            required = "require_operations_staff"
        elif route.path.startswith("/integrations/events/") and route.path != (
            "/integrations/events/azure/blob-created"
        ):
            required = "require_admin"
        elif route.path in {
            "/integrations/erp/sync",
            "/integrations/erp/outbox",
            "/integrations/erp/outbox/{outbox_id}/requeue",
        }:
            required = "require_admin"

        if required:
            assert required in names, f"{sorted(methods)} {route.path} lacks {required}"
            checked.update((method, route.path) for method in methods)

    # This lower bound makes accidental predicate narrowing visible during review.
    assert len(checked) >= 80

    signed_upload = next(
        route
        for route in _routes(client.app)
        if route.path == "/operations/contractor/uploads/local"
    )
    assert "get_current_user" not in _dependency_names(signed_upload.dependant)
    assert {parameter.name for parameter in signed_upload.dependant.query_params} == {
        "key",
        "expires",
        "upload",
        "signature",
    }

    for route in _routes(client.app):
        if route.path.startswith("/risk"):
            assert "get_authorization_context" in _dependency_names(route.dependant)


def test_legacy_superadmin_name_cannot_bypass_canonical_internal_roles(
    client,
    db_session,
    monkeypatch,
):
    from app.routers import integrations as integrations_router

    monkeypatch.setattr(
        integrations_router,
        "process_pending",
        lambda db: {"processed": 0, "failed": 0},
    )
    legacy_superadmin = _user(db_session, "legacy-superadmin", role="superadmin")
    legacy_admin = _user(db_session, "legacy-admin", role="admin")
    canonical_admin = _user(db_session, "canonical-admin")
    db_session.add(
        InternalRoleAssignment(
            user_id=canonical_admin.id,
            role="GV_SUPER_ADMIN",
            is_active=True,
        )
    )
    db_session.commit()

    protected_paths = (
        ("get", "/integrations/events/outbox/status"),
        ("post", "/integrations/erp/sync"),
    )
    for method, path in protected_paths:
        rejected = getattr(client, method)(path, headers=_headers(legacy_superadmin))
        assert rejected.status_code == 403, rejected.text
        for admitted in (legacy_admin, canonical_admin):
            response = getattr(client, method)(path, headers=_headers(admitted))
            assert response.status_code == 200, response.text


def test_risk_assessments_are_site_owned_permissioned_and_tenant_scoped(
    client,
    db_session,
):
    owner = _user(db_session, "risk-owner")
    organization_a, workspace_a, site_a = _scope(
        db_session, owner, "risk-a", sector="mining"
    )
    organization_b, workspace_b, site_b = _scope(
        db_session, owner, "risk-b", sector="mining"
    )
    viewer = _user(db_session, "risk-viewer")
    _add_member(
        db_session,
        user=viewer,
        organization=organization_a,
        workspace=workspace_a,
        role="viewer",
    )
    payload_a = {
        "site_id": site_a.id,
        "sector": "mining",
        "data": {
            "tailings_level_pct": 92,
            "terrain_displacement_mm": 52,
            "esg_score": 55,
            "dust_concentration_ppm": 120,
            "water_quality_index": 45,
            "extraction_efficiency_pct": 65,
        },
    }

    denied_role = client.post(
        "/risk/assess",
        headers=_headers(viewer, workspace_a.id),
        json=payload_a,
    )
    assert denied_role.status_code == 403, denied_role.text

    before = db_session.query(RiskAssessment).count()
    cross_tenant = client.post(
        "/risk/assess",
        headers=_headers(owner, workspace_a.id),
        json={**payload_a, "site_id": site_b.id},
    )
    assert cross_tenant.status_code == 404, cross_tenant.text
    db_session.expire_all()
    assert db_session.query(RiskAssessment).count() == before

    incomplete = client.post(
        "/risk/assess",
        headers=_headers(owner, workspace_a.id),
        json={**payload_a, "data": {}},
    )
    assert incomplete.status_code == 422
    db_session.expire_all()
    assert db_session.query(RiskAssessment).count() == before

    own = client.post(
        "/risk/assess",
        headers=_headers(owner, workspace_a.id),
        json=payload_a,
    )
    assert own.status_code == 200, own.text
    assert own.json()["site_id"] == site_a.id

    other_context = client.post(
        "/risk/assess",
        headers=_headers(owner, workspace_b.id),
        json={**payload_a, "site_id": site_b.id},
    )
    assert other_context.status_code == 200, other_context.text
    assert other_context.json()["site_id"] == site_b.id

    hidden_history = client.get(
        f"/risk/history/{site_b.id}?sector=mining",
        headers=_headers(owner, workspace_a.id),
    )
    assert hidden_history.status_code == 404, hidden_history.text
    own_history = client.get(
        f"/risk/history/{site_a.id}?sector=mining",
        headers=_headers(viewer, workspace_a.id),
    )
    assert own_history.status_code == 200, own_history.text
    assert [row["assessment_id"] for row in own_history.json()["assessments"]] == [
        own.json()["assessment_id"]
    ]
    wrong_sector = client.get(
        f"/risk/history/{site_a.id}?sector=environment",
        headers=_headers(viewer, workspace_a.id),
    )
    assert wrong_sector.status_code == 409

    mismatched_assessment = client.post(
        "/risk/assess",
        headers=_headers(owner, workspace_a.id),
        json={**payload_a, "sector": "environment"},
    )
    assert mismatched_assessment.status_code == 409

    unsupported_site = Site(
        company_id=organization_a.id,
        name="Agriculture risk engine unavailable",
        sector="agriculture",
        is_active=True,
    )
    db_session.add(unsupported_site)
    db_session.commit()
    before_unsupported = db_session.query(RiskAssessment).count()
    unsupported = client.post(
        "/risk/assess",
        headers=_headers(owner, workspace_a.id),
        json={
            "site_id": unsupported_site.id,
            "sector": "agriculture",
            "data": {"ndvi_avg": 0.2},
        },
    )
    assert unsupported.status_code == 409
    db_session.expire_all()
    assert db_session.query(RiskAssessment).count() == before_unsupported
    no_history = client.get(
        f"/risk/history/{unsupported_site.id}?sector=agriculture",
        headers=_headers(viewer, workspace_a.id),
    )
    assert no_history.status_code == 404
    assert organization_a.id != organization_b.id


def test_invitation_scope_cannot_mix_authorized_organizations_workspaces_or_targets(
    client,
    db_session,
):
    owner = _user(db_session, "invitation-owner")
    organization_a, workspace_a, _ = _scope(db_session, owner, "invitation-a")
    organization_b, workspace_b, _ = _scope(db_session, owner, "invitation-b")
    recipient = _user(db_session, "invitation-recipient")
    target_b = Asset(
        organization_id=organization_b.id,
        workspace_id=workspace_b.id,
        sector="ENVIRONMENTAL",
        asset_type="MONITORING_SITE",
        name="Tenant B invitation target",
        status="active",
    )
    db_session.add(target_b)
    db_session.commit()
    invitation_count = db_session.query(Invitation).count()
    membership_count = db_session.query(CompanyUser).count()

    attempts = (
        {
            "organization_id": organization_a.id,
            "workspace_id": workspace_b.id,
            "target_email": recipient.email,
            "intended_role": "member",
            "target_type": "workspace",
        },
        {
            "organization_id": organization_a.id,
            "workspace_id": workspace_a.id,
            "target_email": recipient.email,
            "intended_role": "member",
            "target_type": "asset",
            "target_id": target_b.id,
        },
    )
    for payload in attempts:
        response = client.post(
            "/invitations",
            headers=_headers(owner, workspace_a.id),
            json=payload,
        )
        assert response.status_code == 404, response.text

    db_session.expire_all()
    assert db_session.query(Invitation).count() == invitation_count
    assert db_session.query(CompanyUser).count() == membership_count


def _schema_property_names(
    schema: Any,
    *,
    components: dict[str, Any],
    seen_refs: set[str] | None = None,
) -> set[str]:
    if not isinstance(schema, dict):
        return set()
    seen = seen_refs or set()
    reference = schema.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/components/schemas/"):
        name = reference.rsplit("/", 1)[-1]
        if name in seen:
            return set()
        return _schema_property_names(
            components.get(name, {}),
            components=components,
            seen_refs={*seen, name},
        )
    properties = schema.get("properties", {})
    names = set(properties) if isinstance(properties, dict) else set()
    children: list[Any] = []
    if isinstance(properties, dict):
        children.extend(properties.values())
    children.extend(schema.get(key, []) for key in ("allOf", "anyOf", "oneOf"))
    children.append(schema.get("items"))
    additional = schema.get("additionalProperties")
    if isinstance(additional, dict):
        children.append(additional)
    for child in children:
        if isinstance(child, list):
            for nested in child:
                names.update(
                    _schema_property_names(
                        nested,
                        components=components,
                        seen_refs=seen,
                    )
                )
        else:
            names.update(
                _schema_property_names(
                    child,
                    components=components,
                    seen_refs=seen,
                )
            )
    return names


def _is_customer_response_path(path: str) -> bool:
    internal_prefixes: Iterable[str] = (
        "/admin",
        "/catalog/internal",
        "/integrations/events",
        "/internal",
        "/missions/internal",
        "/operations/capabilities",
        "/operations/contractors",
        "/operations/assignments",
        "/operations/jobs",
        "/operations/experience",
        "/operations/dashboard",
        "/operations/queues",
        "/orders/internal",
        "/payments/admin",
        "/processing",
        "/shop/admin",
    )
    return not any(
        path == prefix or path.startswith(f"{prefix}/") for prefix in internal_prefixes
    )


def test_customer_response_contracts_never_reference_internal_economics_fields(client):
    specification = client.app.openapi()
    components = specification.get("components", {}).get("schemas", {})
    forbidden = {
        "agreed_cost_amount",
        "cost_reference",
        "cost_currency",
        "direct_cost",
        "direct_cost_amount",
        "gross_contribution",
        "gross_margin",
        "gross_margin_percent",
        "internal_cost",
        "internal_notes",
        "provider_cost",
        "provider_usage",
    }
    checked = 0
    for path, path_item in specification["paths"].items():
        if not _is_customer_response_path(path):
            continue
        for method, operation in path_item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            for response in operation.get("responses", {}).values():
                for media in response.get("content", {}).values():
                    properties = _schema_property_names(
                        media.get("schema", {}),
                        components=components,
                    )
                    assert not properties.intersection(forbidden), (
                        f"{method.upper()} {path} exposes internal economics fields: "
                        f"{sorted(properties.intersection(forbidden))}"
                    )
                    checked += 1
    assert checked >= 200
