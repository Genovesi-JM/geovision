from __future__ import annotations

import json
import uuid

from app.core.time import utc_now
from app.core.tokens import create_user_access_token
from app.models import (
    AccountMember,
    Action,
    Asset,
    CatalogItem,
    Company,
    CompanyUser,
    Integration,
    IotDevice,
    KpiDefinition,
    KpiValue,
    Observation,
    Report,
    Site,
    User,
)


def _user(db_session, prefix: str, *, role: str = "cliente") -> User:
    user = User(
        email=f"{prefix}-{uuid.uuid4().hex}@example.com",
        password_hash=None,
        role=role,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _headers(user: User, workspace_id: str | None = None) -> dict[str, str]:
    token = create_user_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        auth_generation=user.auth_generation,
    )
    result = {"Authorization": f"Bearer {token}"}
    if workspace_id:
        result["X-Workspace-ID"] = workspace_id
    return result


def _organization(
    client,
    owner: User,
    name: str,
    *,
    modules: list[str],
) -> tuple[str, str]:
    response = client.post(
        "/organizations",
        headers=_headers(owner),
        json={
            "name": name,
            "country": "Angola",
            "timezone": "Africa/Luanda",
            "workspace": {
                "name": f"{name} North",
                "customer_type": "business",
                "sector_focus": "agro",
                "modules_enabled": modules,
            },
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body["id"], body["workspaces"][0]["id"]


def _add_workspace(
    client,
    owner: User,
    organization_id: str,
    active_workspace_id: str,
    *,
    name: str,
    modules: list[str],
) -> str:
    response = client.post(
        f"/organizations/{organization_id}/workspaces",
        headers=_headers(owner, active_workspace_id),
        json={
            "name": name,
            "customer_type": "business",
            "sector_focus": "infrastructure",
            "modules_enabled": modules,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _asset(
    client,
    owner: User,
    workspace_id: str,
    name: str,
    *,
    parent_asset_id: str | None = None,
    sector: str = "AGRICULTURE",
) -> dict:
    response = client.post(
        "/assets",
        headers=_headers(owner, workspace_id),
        json={
            "parent_asset_id": parent_asset_id,
            "sector": sector,
            "asset_type": "FIELD" if parent_asset_id else "SITE",
            "name": name,
            "location_label": "Huambo, Angola",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [15.0, -12.0],
                        [15.2, -12.0],
                        [15.2, -11.8],
                        [15.0, -12.0],
                    ]
                ],
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _seed_intelligence(
    db_session,
    *,
    organization_id: str,
    workspace_id: str,
    asset_id: str,
) -> tuple[KpiDefinition, KpiDefinition, KpiDefinition, Observation]:
    definitions = [
        KpiDefinition(
            sector="AGRICULTURE",
            key="yield_risk",
            label="Yield risk",
            name="Yield risk",
            unit="%",
            calculator="test",
            calculator_version="1.0.0",
            importance="PRIMARY",
            sort_order=1,
        ),
        KpiDefinition(
            sector="AGRICULTURE",
            key="soil_condition",
            label="Soil condition",
            name="Soil condition",
            unit="%",
            calculator="test",
            calculator_version="1.0.0",
            importance="SECONDARY",
            sort_order=2,
        ),
        KpiDefinition(
            sector="AGRICULTURE",
            key="spectral_noise",
            label="Spectral noise",
            name="Spectral noise",
            unit=None,
            calculator="test",
            calculator_version="1.0.0",
            importance="TECHNICAL",
            sort_order=3,
        ),
    ]
    db_session.add_all(definitions)
    db_session.flush()
    now = utc_now()
    db_session.add_all(
        [
            KpiValue(
                kpi_definition_id=definition.id,
                account_id=workspace_id,
                organization_id=organization_id,
                workspace_id=workspace_id,
                asset_id=asset_id,
                value=str(value),
                numeric_value=value,
                status=status,
                confidence=0.9,
                measured_at=now,
                source="validated-test",
                algorithm_version="1.0.0",
            )
            for definition, value, status in zip(
                definitions,
                (72.0, 61.0, 0.3),
                ("WARNING", "WATCH", "GOOD"),
                strict=True,
            )
        ]
    )
    validated = Observation(
        organization_id=organization_id,
        workspace_id=workspace_id,
        asset_id=asset_id,
        observation_type="WATER_STRESS",
        severity="WARNING",
        geometry_geojson=json.dumps(
            {"type": "Point", "coordinates": [15.1, -11.9]}
        ),
        value_json="{}",
        metadata_json="{}",
        confidence=0.88,
        source="validated-test",
        algorithm_key="water-stress",
        algorithm_version="1.0.0",
        provenance_json="{}",
        validation_status="VALIDATED",
        detected_at=now,
    )
    hidden = Observation(
        organization_id=organization_id,
        workspace_id=workspace_id,
        asset_id=asset_id,
        observation_type="UNREVIEWED_ANOMALY",
        severity="CRITICAL",
        geometry_geojson=json.dumps(
            {"type": "Point", "coordinates": [15.15, -11.95]}
        ),
        value_json="{}",
        metadata_json="{}",
        confidence=0.4,
        source="unreviewed-test",
        algorithm_key="unreviewed",
        algorithm_version="1.0.0",
        provenance_json="{}",
        validation_status="NEEDS_REVIEW",
        detected_at=now,
    )
    db_session.add_all([validated, hidden])
    db_session.commit()
    return definitions[0], definitions[1], definitions[2], validated


def test_portal_experience_filters_navigation_and_exposes_typed_context(
    client,
    db_session,
):
    owner = _user(db_session, "portal-owner")
    organization_id, workspace_id = _organization(
        client,
        owner,
        "Portal Farm",
        modules=["projects", "alerts", "store", "kpi", "map"],
    )
    second_workspace = _add_workspace(
        client,
        owner,
        organization_id,
        workspace_id,
        name="Portal Infrastructure",
        modules=["projects"],
    )
    root = _asset(client, owner, workspace_id, "Farm portfolio")
    child = _asset(
        client,
        owner,
        workspace_id,
        "North field",
        parent_asset_id=root["id"],
    )
    db_session.add(
        CatalogItem(
            code=f"PORTAL-{uuid.uuid4().hex}",
            slug=f"portal-{uuid.uuid4().hex}",
            item_type="SERVICE",
            name="GeoVision crop inspection",
            status="PUBLISHED",
        )
    )
    organization = db_session.get(Company, organization_id)
    organization.subscription_plan = "enterprise"
    db_session.add(
        Integration(
            company_id=organization_id,
            connector_type="legacy-org-wide",
            name="Must not enable a workspace",
            is_active=True,
        )
    )
    db_session.commit()

    response = client.get(
        "/portal/experience", headers=_headers(owner, workspace_id)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["active_workspace_id"] == workspace_id
    assert body["active_organization_id"] == organization_id
    assert {row["id"] for row in body["workspaces"]} == {
        workspace_id,
        second_workspace,
    }
    assert body["active_workspace"]["modules_enabled"] == [
        "projects",
        "alerts",
        "store",
        "kpi",
        "map",
    ]
    assert {"overview", "assets", "actions", "services", "map", "analytics"}.issubset(
        body["capabilities"]
    )
    assert "monitoring" not in body["capabilities"]
    assert "integrations" not in body["capabilities"]
    assert body["feature_flags"]["monitoring"] is False
    assert body["asset_tree"][0]["id"] == root["id"]
    assert body["asset_tree"][0]["children"][0]["id"] == child["id"]
    assert [group["key"] for group in body["navigation"]] == [
        "overview",
        "operations",
        "intelligence",
        "commercial",
        "management",
    ]
    serialized = json.dumps(body).casefold()
    assert "operations/contractors" not in serialized
    assert "supplier" not in serialized
    assert "provider_id" not in serialized
    assert "internal_role" not in serialized
    assert {
        rule["target_type"] for rule in body["deep_link_contract"]["destinations"]
    } == {"WORKSPACE", "ASSET", "ACTION", "SERVICE", "SERVICE_RESULT", "ORDER", "REPORT"}


def test_portal_hides_irrelevant_and_management_modules_from_small_viewer(
    client,
    db_session,
):
    owner = _user(db_session, "portal-small-owner")
    organization_id, workspace_id = _organization(
        client,
        owner,
        "Small Portal",
        modules=[],
    )
    viewer = _user(db_session, "portal-small-viewer")
    added = client.post(
        f"/organizations/{organization_id}/members",
        headers=_headers(owner, workspace_id),
        json={"email": viewer.email, "user_id": viewer.id, "role": "viewer"},
    )
    assert added.status_code == 201, added.text

    response = client.get(
        "/portal/experience", headers=_headers(viewer, workspace_id)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["capabilities"] == ["overview"]
    assert [group["key"] for group in body["navigation"]] == ["overview"]
    assert body["deep_link_contract"]["destinations"] == [
        {
            "target_type": "WORKSPACE",
            "route_template": "/dashboard.html?view=overview&workspace_id={workspace_id}",
            "capability": "overview",
        }
    ]


def test_portal_asset_summary_prioritizes_decision_kpis_and_isolates_workspaces(
    client,
    db_session,
):
    owner = _user(db_session, "portal-summary-owner")
    organization_id, workspace_a = _organization(
        client,
        owner,
        "Portal Summary",
        modules=["projects", "kpi", "reports"],
    )
    workspace_b = _add_workspace(
        client,
        owner,
        organization_id,
        workspace_a,
        name="Portal Summary South",
        modules=["projects", "kpi"],
    )
    asset_a = _asset(client, owner, workspace_a, "Visible farm")
    asset_b = _asset(
        client,
        owner,
        workspace_b,
        "Hidden infrastructure",
        sector="INFRASTRUCTURE",
    )
    db_session.add(
        Asset(
            organization_id=organization_id,
            workspace_id=None,
            sector="AGRICULTURE",
            asset_type="SITE",
            name="Ambiguous legacy asset",
            status="active",
        )
    )
    _seed_intelligence(
        db_session,
        organization_id=organization_id,
        workspace_id=workspace_a,
        asset_id=asset_a["id"],
    )
    db_session.add(
        Action(
            organization_id=organization_id,
            workspace_id=workspace_a,
            asset_id=asset_a["id"],
            source_rule_key="portal.action",
            source_rule_version="1.0.0",
            priority="HIGH",
            title="Inspect irrigation",
            description="Customer-visible action",
            status="OPEN",
            deduplication_key=f"portal-{uuid.uuid4().hex}",
        )
    )
    db_session.add(
        Report(
            organization_id=organization_id,
            workspace_id=workspace_a,
            asset_id=asset_a["id"],
            report_type="AGRICULTURE",
            title="Published field report",
            template_version="1.0.0",
            status="PUBLISHED",
            qa_level="HUMAN_REVIEW",
            context_schema_version="geovision.report-context.v1",
            context_json="{}",
            context_sha256="a" * 64,
            narrative_provider="deterministic",
            narrative_schema_version="geovision.report-narrative.v1",
            narrative_json="{}",
            qa_result_json="{}",
            generation_key=f"portal-{uuid.uuid4().hex}",
            published_at=utc_now(),
        )
    )
    db_session.commit()

    response = client.get(
        "/portal/assets/summary", headers=_headers(owner, workspace_a)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["workspace_id"] == workspace_a
    assert body["totals"] == {
        "assets": 1,
        "active": 1,
        "attention": 1,
        "open_actions": 1,
        "published_reports": 1,
        "offline_devices": 0,
    }
    item = body["items"][0]
    assert item["id"] == asset_a["id"]
    assert item["decision_status"] == "WARNING"
    assert [kpi["key"] for kpi in item["primary_kpis"]] == ["yield_risk"]
    assert [kpi["key"] for kpi in item["secondary_kpis"]] == ["soil_condition"]
    assert item["technical_metric_count"] == 1
    assert "spectral_noise" not in json.dumps(item)
    assert item["technical_metrics_path"].endswith("importance=TECHNICAL")
    assert asset_b["id"] not in {row["id"] for row in body["items"]}
    assert (
        client.get(
            f"/portal/assets/summary?asset_id={asset_b['id']}",
            headers=_headers(owner, workspace_a),
        ).status_code
        == 404
    )


def test_portal_map_layers_are_validated_typed_and_workspace_scoped(
    client,
    db_session,
):
    owner = _user(db_session, "portal-map-owner")
    organization_id, workspace_a = _organization(
        client,
        owner,
        "Portal Map",
        modules=["projects", "map", "iot"],
    )
    workspace_b = _add_workspace(
        client,
        owner,
        organization_id,
        workspace_a,
        name="Portal Map Other",
        modules=["projects", "map"],
    )
    asset_a = _asset(client, owner, workspace_a, "Mapped farm")
    asset_b = _asset(client, owner, workspace_b, "Other map")
    _, _, _, validated = _seed_intelligence(
        db_session,
        organization_id=organization_id,
        workspace_id=workspace_a,
        asset_id=asset_a["id"],
    )
    db_session.add_all(
        [
            Site(
                id="portal-site",
                company_id=organization_id,
                name="Portal device site",
            ),
            Site(
                id="portal-site-invalid",
                company_id=organization_id,
                name="Portal legacy device site",
            ),
        ]
    )
    db_session.flush()
    db_session.add(
        IotDevice(
            public_id=f"gv-portal-{uuid.uuid4().hex}",
            company_id=organization_id,
            site_id="portal-site",
            core_asset_id=asset_a["id"],
            name="Field gateway",
            token_hash="portal-token-hash",
            secret_encrypted="portal-encrypted-secret",
            last_latitude=-11.9,
            last_longitude=15.1,
            connectivity_status="online",
        )
    )
    db_session.add(
        IotDevice(
            public_id=f"gv-portal-invalid-{uuid.uuid4().hex}",
            company_id=organization_id,
            site_id="portal-site-invalid",
            core_asset_id=asset_a["id"],
            name="Legacy invalid coordinate",
            token_hash="portal-invalid-token-hash",
            secret_encrypted="portal-invalid-encrypted-secret",
            last_latitude=999.0,
            last_longitude=15.1,
            connectivity_status="online",
        )
    )
    db_session.commit()

    response = client.get(
        "/portal/map-layers", headers=_headers(owner, workspace_a)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["workspace_id"] == workspace_a
    assert len(body["bounds"]) == 4
    layers = {layer["id"]: layer for layer in body["layers"]}
    assert set(layers) == {"assets", "observations", "devices"}
    assert layers["assets"]["feature_collection"]["type"] == "FeatureCollection"
    assert {
        row["id"] for row in layers["assets"]["feature_collection"]["features"]
    } == {asset_a["id"]}
    observations = layers["observations"]["feature_collection"]["features"]
    assert {row["id"] for row in observations} == {validated.id}
    assert observations[0]["properties"]["target_type"] == "ASSET"
    assert observations[0]["properties"]["target_id"] == asset_a["id"]
    devices = layers["devices"]["feature_collection"]["features"]
    assert len(devices) == 1
    assert devices[0]["properties"]["target_id"] == asset_a["id"]
    assert asset_b["id"] not in json.dumps(body)
    serialized = json.dumps(body).casefold()
    assert "provider_code" not in serialized
    assert "provider_device_id" not in serialized
    assert "secret" not in serialized


def test_portal_rejects_other_tenants_and_platform_only_staff(
    client,
    db_session,
):
    owner = _user(db_session, "portal-boundary-owner")
    _, workspace_id = _organization(
        client,
        owner,
        "Portal Boundary",
        modules=["projects"],
    )
    outsider = _user(db_session, "portal-boundary-outsider")
    assert (
        client.get(
            "/portal/experience", headers=_headers(outsider, workspace_id)
        ).status_code
        == 403
    )
    staff = _user(db_session, "portal-boundary-staff", role="admin")
    assert (
        client.get(
            "/portal/experience", headers=_headers(staff, workspace_id)
        ).status_code
        == 403
    )


def test_portal_workspace_selector_omits_stale_revoked_organization_access(
    client,
    db_session,
):
    owner_a = _user(db_session, "portal-selector-owner-a")
    organization_a, workspace_a = _organization(
        client,
        owner_a,
        "Portal Selector A",
        modules=["projects"],
    )
    owner_b = _user(db_session, "portal-selector-owner-b")
    organization_b, workspace_b = _organization(
        client,
        owner_b,
        "Portal Selector B",
        modules=["projects"],
    )
    member = _user(db_session, "portal-selector-member")
    for owner, organization_id, workspace_id in (
        (owner_a, organization_a, workspace_a),
        (owner_b, organization_b, workspace_b),
    ):
        added = client.post(
            f"/organizations/{organization_id}/members",
            headers=_headers(owner, workspace_id),
            json={"email": member.email, "user_id": member.id, "role": "viewer"},
        )
        assert added.status_code == 201, added.text

    stale_org_membership = (
        db_session.query(CompanyUser)
        .filter(
            CompanyUser.company_id == organization_b,
            CompanyUser.user_id == member.id,
        )
        .one()
    )
    stale_org_membership.status = "revoked"
    stale_org_membership.is_active = False
    # Simulate an incomplete historical revocation: the lower-level workspace
    # row remains active and must not re-enable selector metadata.
    stale_workspace_membership = (
        db_session.query(AccountMember)
        .filter(
            AccountMember.account_id == workspace_b,
            AccountMember.user_id == member.id,
        )
        .one()
    )
    stale_workspace_membership.status = "active"
    db_session.commit()

    response = client.get(
        "/portal/experience", headers=_headers(member, workspace_a)
    )
    assert response.status_code == 200, response.text
    assert {item["id"] for item in response.json()["workspaces"]} == {workspace_a}


def test_portal_openapi_uses_explicit_response_contracts(client):
    paths = client.app.openapi()["paths"]
    assert paths["/portal/experience"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["$ref"].endswith("/PortalExperienceOut")
    assert paths["/portal/assets/summary"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["$ref"].endswith("/PortalAssetSummaryOut")
    assert paths["/portal/map-layers"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["$ref"].endswith("/PortalMapLayersOut")
