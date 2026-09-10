from __future__ import annotations

from datetime import datetime
import json
import uuid

from app.core.tokens import create_user_access_token
from app.integrations.storage.local import LocalObjectStorageProvider
from app.models import Acquisition, Action, Asset, Dataset, KpiValue, Observation, Order, Report, User
from app.modules.analytics.domain import EvaluationContext, KpiImportance, calculator_registry, rule_registry
from app.modules.catalog.services import sync_catalog_from_legacy
from app.modules.reports.ports import report_context_registry
from app.modules.reports.schemas import ReportGenerateRequest
from app.modules.reports.services import generate_report
from app.sectors.infrastructure import definition
from app.sectors.infrastructure.domain import (
    KPI_DEFINITIONS,
    SUPPORTED_ASSET_TYPES,
    SUPPORTED_DATASET_TYPES,
)
from app.sectors.infrastructure.fixtures import (
    demo_infrastructure_bundle,
    resolve_demo_dataset_references,
)
from app.sectors.infrastructure.services import ANALYSIS_SCHEMA, build_source_context
from app.services.storage import StorageService
from app.services.cart import seed_shop_products


def _user(db_session, prefix: str, *, role: str = "cliente") -> User:
    row = User(
        email=f"{prefix}-{uuid.uuid4().hex}@example.com",
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


def _admin_headers(client) -> dict[str, str]:
    response = client.post(
        "/auth/login", json={"email": "teste@admin.com", "password": "123456"}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _workspace_asset(
    client,
    db_session,
    *,
    prefix: str,
    enabled: bool = True,
    sector: str = "INFRASTRUCTURE",
    asset_type: str = "ROAD",
):
    owner = _user(db_session, f"{prefix}-owner")
    created = client.post(
        "/organizations",
        headers=_headers(owner),
        json={
            "name": f"{prefix}-{uuid.uuid4().hex[:8]}",
            "country": "Angola",
            "timezone": "Africa/Luanda",
            "workspace": {
                "name": f"{prefix} workspace",
                "customer_type": "business",
                "sector_focus": "infrastructure",
                "modules_enabled": ["assets", "analytics", "reports"]
                + (["infrastructure"] if enabled else []),
            },
        },
    )
    assert created.status_code == 201, created.text
    organization = created.json()
    workspace_id = organization["workspaces"][0]["id"]
    headers = _headers(owner, workspace_id)
    asset = client.post(
        "/assets",
        headers=headers,
        json={
            "sector": sector,
            "asset_type": asset_type,
            "name": f"{prefix} asset",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [13.10, -8.90],
                        [13.14, -8.90],
                        [13.14, -8.86],
                        [13.10, -8.86],
                        [13.10, -8.90],
                    ]
                ],
            },
        },
    )
    assert asset.status_code == 201, asset.text
    seed_shop_products(db_session)
    sync_catalog_from_legacy(db_session)
    return owner, organization["id"], workspace_id, asset.json(), headers


def _materialize_bundle(db_session, *, asset: Asset, bundle: dict) -> dict[str, Dataset]:
    datasets: dict[str, Dataset] = {}
    for item in bundle["datasets"]:
        row = Dataset(
            id=str(uuid.uuid4()),
            company_id=asset.organization_id,
            workspace_id=asset.workspace_id,
            asset_id=asset.id,
            name=item["name"],
            data_type=item["dataset_type"],
            dataset_type=item["dataset_type"],
            source="demo_fixture",
            provider_code="geovision",
            storage_provider="local",
            processing_level=item["processing_level"],
            quality_status="PASSED",
            status="ready",
            sector="INFRASTRUCTURE",
            capture_date=item["capture_date"],
            crs=item["crs"],
            resolution=5.0,
            resolution_unit="cm",
            metadata_json="{}",
            provenance_json=json.dumps(
                {
                    "processor": "geovision-infrastructure",
                    "processor_version": "1.0.0",
                    "fixture": True,
                }
            ),
            created_at=item["capture_date"],
            updated_at=item["capture_date"],
            processed_at=item["capture_date"],
        )
        db_session.add(row)
        datasets[item["name"]] = row
    db_session.flush()
    resolved = resolve_demo_dataset_references(
        bundle,
        {name: row.id for name, row in datasets.items()},
    )
    for item in resolved["datasets"]:
        datasets[item["name"]].metadata_json = json.dumps(item["metadata"])
    db_session.commit()
    return datasets


def test_infrastructure_registers_as_a_common_core_extension():
    assert definition.enabled_by_default is True
    assert definition.routes[0].key == "sector.infrastructure"
    assert definition.activation_phase == 28
    assert {
        "ROAD",
        "BRIDGE",
        "RAILWAY",
        "PIPELINE",
        "BUILDING",
        "STRUCTURE",
    }.issubset(SUPPORTED_ASSET_TYPES)
    assert {
        "RGB_IMAGES",
        "RTK_OBSERVATIONS",
        "ORTHOMOSAIC",
        "POINT_CLOUD",
        "MESH_3D",
        "DSM",
        "DTM",
        "THERMAL_IMAGES",
        "LIDAR_POINT_CLOUD",
        "BIM_MODEL",
        "PROJECT_REFERENCE",
    } == SUPPORTED_DATASET_TYPES
    registrations = calculator_registry.registrations("INFRASTRUCTURE")
    assert len(registrations) == len(KPI_DEFINITIONS)
    assert {item.definition.importance for item in registrations} == {
        KpiImportance.PRIMARY,
        KpiImportance.SECONDARY,
        KpiImportance.TECHNICAL,
    }
    assert rule_registry.registrations("INFRASTRUCTURE")[0].version == "1.0.0"
    assert "INFRASTRUCTURE" in report_context_registry.sectors()
    empty = EvaluationContext(
        asset_id="asset",
        sector="INFRASTRUCTURE",
        measured_at=datetime(2026, 9, 10, 8),
    )
    assert all(item.calculate(empty) is None for item in registrations)


def test_unvalidated_or_unpaired_claims_never_become_infrastructure_facts(
    client, db_session
):
    _, _, _, asset_payload, headers = _workspace_asset(
        client, db_session, prefix="infra-untrusted"
    )
    asset = db_session.get(Asset, asset_payload["id"])
    untrusted = {
        "schema": ANALYSIS_SCHEMA,
        "validation_status": "UNVALIDATED",
        "algorithm": "vendor.blackbox",
        "algorithm_version": "9.9.9",
        "metrics": {
            "overall_progress": 99,
            "schedule_variance": -20,
            "volume_change": 999999,
            "cut_volume": 100,
            "fill_volume": 100,
        },
        "progress_evidence": {
            "reviewed": True,
            "basis": "VALIDATED_SURVEY_CLASSIFICATION",
            "source_reference": "untrusted-claim",
            "reference_version": "fake",
        },
        "anomalies": [
            {"id": "fake-defect", "kind": "visual", "new": True, "label": "Defect"}
        ],
    }
    invalid_pairs = {
        "schema": ANALYSIS_SCHEMA,
        "validation_status": "VALIDATED",
        "algorithm": "geovision.infrastructure.claims",
        "algorithm_version": "1.0.0",
        "metrics": {
            "area_change": 900,
            "volume_change": 1200,
            "cut_volume": 300,
            "fill_volume": 1500,
            "schedule_variance": 17,
        },
        "comparison_evidence": {
            "current_dataset_id": "wrong-current",
            "previous_dataset_id": "outside-scope",
            "aligned": True,
            "same_crs": True,
            "method": "vendor.change",
            "method_version": "1.0.0",
        },
        "surface_evidence": {
            "current_dataset_id": "wrong-current",
            "previous_dataset_id": "outside-scope",
            "aligned": True,
            "same_crs": True,
            "vertical_datum": "unknown",
            "method": "vendor.surface",
            "method_version": "1.0.0",
        },
        "schedule_evidence": {
            "trusted": True,
            "kind": "SIGNED_BASELINE",
            "source_system": "UNTRUSTED_SPREADSHEET",
            "source_reference": "not-valid-on-imagery",
            "baseline_version": "1",
        },
    }
    db_session.add_all(
        [
            Dataset(
                company_id=asset.organization_id,
                workspace_id=asset.workspace_id,
                asset_id=asset.id,
                name="Unvalidated claims",
                dataset_type="ORTHOMOSAIC",
                status="ready",
                quality_status="PASSED",
                processing_level="DERIVED",
                capture_date=datetime(2026, 9, 10, 8),
                crs="EPSG:32733",
                metadata_json=json.dumps({"infrastructure_analysis": untrusted}),
            ),
            Dataset(
                company_id=asset.organization_id,
                workspace_id=asset.workspace_id,
                asset_id=asset.id,
                name="Invalid pair claims",
                dataset_type="ORTHOMOSAIC",
                status="ready",
                quality_status="PASSED",
                processing_level="DERIVED",
                capture_date=datetime(2026, 9, 10, 9),
                crs="EPSG:32733",
                metadata_json=json.dumps({"infrastructure_analysis": invalid_pairs}),
            ),
            Dataset(
                company_id=asset.organization_id,
                workspace_id=asset.workspace_id,
                asset_id=asset.id,
                name="Untrusted schedule source",
                dataset_type="PROJECT_REFERENCE",
                status="ready",
                quality_status="PASSED",
                processing_level="DERIVED",
                capture_date=datetime(2026, 9, 10, 9, 30),
                crs="EPSG:32733",
                metadata_json=json.dumps(
                    {
                        "infrastructure_analysis": {
                            **invalid_pairs,
                            "metrics": {"schedule_variance": 17},
                            "schedule_evidence": {
                                **invalid_pairs["schedule_evidence"],
                                "source_system": "UNTRUSTED_SPREADSHEET",
                            },
                        }
                    }
                ),
            ),
        ]
    )
    db_session.commit()

    context = build_source_context(
        db_session,
        asset=asset,
        as_of=datetime(2026, 9, 10, 10),
    )
    assert context.evaluation.measurements == {}
    assert context.evaluation.metadata["findings"] == ()
    assert context.availability["validated_analysis_count"] == 2
    assert context.availability["validated_progress"] is False
    assert context.availability["paired_surface"] is False
    assert context.availability["trusted_schedule"] is False

    evaluated = client.post(
        f"/assets/{asset.id}/infrastructure/evaluate",
        headers=headers,
        json={"as_of": "2026-09-10T10:00:00"},
    )
    assert evaluated.status_code == 200, evaluated.text
    assert evaluated.json()["kpi_value_ids"] == []
    assert all(item["availability"] == "NO_DATA" for item in evaluated.json()["kpis"])
    assert all(item["status"] == "UNKNOWN" for item in evaluated.json()["kpis"])
    assert db_session.query(Observation).filter(Observation.asset_id == asset.id).count() == 0
    action_text = " ".join(
        f"{row.title} {row.description}"
        for row in db_session.query(Action).filter(Action.asset_id == asset.id).all()
    ).lower()
    assert "before reporting overall progress" in action_text
    assert not any(term in action_text for term in ("certified", "structurally safe", "defect confirmed"))


def test_validated_infrastructure_flow_uses_common_asset_action_and_report_core(
    client, db_session, tmp_path
):
    owner, organization_id, workspace_id, asset_payload, headers = _workspace_asset(
        client, db_session, prefix="infra-full"
    )
    asset = db_session.get(Asset, asset_payload["id"])
    order = Order(
        user_id=owner.id,
        company_id=organization_id,
        organization_id=organization_id,
        workspace_id=workspace_id,
        order_number=f"GV-P28-{uuid.uuid4().hex[:10].upper()}",
        order_type="SERVICE",
        status="confirmed",
        fulfilment_status="CONFIRMED",
        payment_status="PENDING",
        currency="AOA",
        subtotal=1000,
        total=1000,
    )
    db_session.add(order)
    db_session.commit()
    mission = client.post(
        "/missions/internal",
        headers=_admin_headers(client),
        json={
            "asset_id": asset.id,
            "order_id": order.id,
            "acquisition_type": "DRONE",
            "title": "Infrastructure progress survey",
            "drone_details": {
                "payload_reference": "RGB-RTK",
                "mission_requirements": {"orthomosaic": True, "rtk": True},
                "flight_metadata": {},
            },
        },
    )
    assert mission.status_code == 201, mission.text
    acquisition = db_session.get(Acquisition, mission.json()["id"])
    assert acquisition.order_id == order.id
    assert acquisition.asset_id == asset.id
    datasets = _materialize_bundle(
        db_session,
        asset=asset,
        bundle=demo_infrastructure_bundle(),
    )
    current_survey = datasets["Current reviewed orthomosaic"]
    current_survey.mission_id = acquisition.id
    db_session.commit()
    assert current_survey.mission_id == acquisition.id
    visible_orders = client.get("/orders", headers=headers)
    assert visible_orders.status_code == 200, visible_orders.text
    assert order.id in {item["id"] for item in visible_orders.json()}
    mission_history = client.get(
        f"/missions/assets/{asset.id}/history", headers=headers
    )
    assert mission_history.status_code == 200, mission_history.text
    assert acquisition.id in {item["id"] for item in mission_history.json()}

    capabilities = client.get("/sectors/infrastructure/capabilities", headers=headers)
    assert capabilities.status_code == 200, capabilities.text
    assert capabilities.json()["enabled"] is True
    assert capabilities.json()["analysis_schema"] == ANALYSIS_SCHEMA

    evaluated = client.post(
        f"/assets/{asset.id}/infrastructure/evaluate",
        headers=headers,
        json={"as_of": "2026-09-10T08:00:00"},
    )
    assert evaluated.status_code == 200, evaluated.text
    body = evaluated.json()
    assert body["source_availability"] | {
        "validated_progress": True,
        "historical_comparison": True,
        "paired_2d_change": True,
        "paired_surface": True,
        "trusted_schedule": True,
    } == body["source_availability"]
    kpis = {item["definition"]["key"]: item for item in body["kpis"]}
    assert kpis["overall_progress"]["current"] == 57
    assert kpis["overall_progress"]["status"] == "UNKNOWN"
    assert kpis["progress_change"]["current"] == 15
    assert kpis["area_change"]["current"] == 1200
    assert kpis["volume_change"]["current"] == 2250
    assert kpis["cut_volume"]["current"] == 180
    assert kpis["fill_volume"]["current"] == 2430
    assert kpis["schedule_variance"]["current"] == 5
    assert kpis["schedule_variance"]["status"] == "WARNING"
    assert kpis["visual_anomaly_count"]["current"] == 1
    assert kpis["thermal_anomaly_count"]["current"] == 1
    assert kpis["review_area_count"]["current"] == 1
    assert kpis["overall_progress"]["dataset_id"] == datasets[
        "Current reviewed orthomosaic"
    ].id
    assert len(body["observation_ids"]) == 3
    assert len(body["action_ids"]) == 3

    counts = (
        db_session.query(KpiValue).filter(KpiValue.asset_id == asset.id).count(),
        db_session.query(Observation).filter(Observation.asset_id == asset.id).count(),
        db_session.query(Action).filter(Action.asset_id == asset.id).count(),
    )
    replayed = client.post(
        f"/assets/{asset.id}/infrastructure/evaluate",
        headers=headers,
        json={"as_of": "2026-09-10T08:00:00"},
    )
    assert replayed.status_code == 200, replayed.text
    assert counts == (
        db_session.query(KpiValue).filter(KpiValue.asset_id == asset.id).count(),
        db_session.query(Observation).filter(Observation.asset_id == asset.id).count(),
        db_session.query(Action).filter(Action.asset_id == asset.id).count(),
    )

    summary = client.get(f"/assets/{asset.id}/summary", headers=headers)
    assert summary.status_code == 200, summary.text
    assert summary.json()["status"] == "WARNING"
    observations = client.get(
        f"/assets/{asset.id}/observations", headers=headers
    ).json()["items"]
    assert len(observations) == 3
    assert all(item["validation_status"] == "NEEDS_REVIEW" for item in observations)
    assert all(item["value"]["engineering_conclusion"] is None for item in observations)
    actions = client.get(f"/assets/{asset.id}/actions", headers=headers).json()["items"]
    refs = {
        reference["id"]
        for item in actions
        for reference in item["recommendation_refs"]
    }
    assert refs == {
        "prod_infra_technical_inspection",
        "prod_infra_thermal_inspection",
        "prod_infra_specialist_review",
    }
    assert {item["recommended_catalog_item_id"] for item in actions} == refs

    comparisons = client.get(
        f"/assets/{asset.id}/infrastructure/comparisons", headers=headers
    )
    assert comparisons.status_code == 200, comparisons.text
    comparison_items = {item["kind"]: item for item in comparisons.json()["items"]}
    assert comparison_items["SURVEY_2D"]["availability"] == "AVAILABLE"
    assert comparison_items["SURFACE_3D"]["availability"] == "AVAILABLE"
    assert comparison_items["THERMAL_2D"]["availability"] == "NO_DATA"
    assert all(
        item["interpretation"] == "visual comparison only; no engineering conclusion"
        for item in comparison_items.values()
    )

    layers = client.get(
        f"/assets/{asset.id}/infrastructure/map-layers", headers=headers
    )
    assert layers.status_code == 200, layers.text
    layer_items = layers.json()["items"]
    assert {
        "ASSET_BOUNDARY",
        "ORTHOMOSAIC",
        "DSM",
        "THERMAL_IMAGES",
        "POINT_CLOUD",
        "MESH_3D",
        "BIM_MODEL",
        "OBSERVATION_ZONE",
    }.issubset({item["kind"] for item in layer_items})
    assert all(not str(item.get("data_ref", "")).startswith("http") for item in layer_items)
    assert all("provider" not in item["provenance"] for item in layer_items)
    assert all(
        item["availability"] == "UNKNOWN"
        for item in layer_items
        if item["kind"] == "OBSERVATION_ZONE"
    )

    context = client.get(
        f"/assets/{asset.id}/infrastructure/report-context", headers=headers
    )
    assert context.status_code == 200, context.text
    assert context.json()["schema"] == "geovision.infrastructure.report-context.v1"
    assert any("No structural" in item for item in context.json()["limitations"])
    assert context.json()["comparisons"][0]["kind"] == "SURVEY_2D"

    storage = StorageService(
        LocalObjectStorageProvider(
            root=tmp_path,
            public_base_url="http://testserver",
            signing_secret="test-infrastructure-report-signing-key",
        )
    )
    report_row, created = generate_report(
        db_session,
        actor=owner,
        asset=asset,
        data=ReportGenerateRequest(
            report_type="INFRASTRUCTURE_INTELLIGENCE",
            acquisition_id=acquisition.id,
            idempotency_key=f"infra-report-{uuid.uuid4()}",
        ),
        storage=storage,
    )
    db_session.commit()
    assert created is True
    assert report_row.asset_id == asset.id
    assert report_row.acquisition_id == acquisition.id
    report_context = json.loads(report_row.context_json)
    assert report_context["asset"]["sector"] == "INFRASTRUCTURE"
    assert any(
        "No structural" in item for item in report_context["limitations"]
    )
    assert db_session.query(Report).filter(Report.asset_id == asset.id).count() == 1
    assert owner.id


def test_permissions_tenant_boundaries_and_workspace_feature_flag_are_independent(
    client, db_session
):
    owner, organization_id, workspace_id, asset, headers = _workspace_asset(
        client, db_session, prefix="infra-isolation"
    )
    viewer = _user(db_session, "infra-viewer")
    membership = client.post(
        f"/organizations/{organization_id}/members",
        headers=headers,
        json={"email": viewer.email, "user_id": viewer.id, "role": "viewer"},
    )
    assert membership.status_code == 201, membership.text
    viewer_headers = _headers(viewer, workspace_id)
    assert (
        client.get(
            f"/assets/{asset['id']}/infrastructure/report-context",
            headers=viewer_headers,
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/assets/{asset['id']}/infrastructure/evaluate",
            headers=viewer_headers,
            json={},
        ).status_code
        == 403
    )

    second = client.post(
        f"/organizations/{organization_id}/workspaces",
        headers=headers,
        json={
            "name": "Infrastructure disabled workspace",
            "sector_focus": "infrastructure",
            "customer_type": "business",
            "modules_enabled": ["assets", "analytics", "reports"],
        },
    )
    assert second.status_code == 201, second.text
    disabled_workspace_id = second.json()["id"]
    disabled_headers = _headers(owner, disabled_workspace_id)
    disabled_asset = client.post(
        "/assets",
        headers=disabled_headers,
        json={
            "sector": "INFRASTRUCTURE",
            "asset_type": "BRIDGE",
            "name": "Disabled-workspace bridge",
        },
    )
    assert disabled_asset.status_code == 201, disabled_asset.text
    capabilities = client.get(
        "/sectors/infrastructure/capabilities", headers=disabled_headers
    )
    assert capabilities.status_code == 200
    assert capabilities.json()["enabled"] is False
    assert (
        client.get(
            f"/assets/{disabled_asset.json()['id']}/infrastructure/map-layers",
            headers=disabled_headers,
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/assets/{asset['id']}/infrastructure/report-context",
            headers=disabled_headers,
        ).status_code
        == 404
    )
    assert client.get("/sectors/infrastructure/capabilities", headers=headers).json()[
        "enabled"
    ] is True

    _, _, _, _, outsider_headers = _workspace_asset(
        client, db_session, prefix="infra-outsider"
    )
    hidden = client.get(
        f"/assets/{asset['id']}/infrastructure/report-context",
        headers=outsider_headers,
    )
    assert hidden.status_code == 404
