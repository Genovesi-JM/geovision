from __future__ import annotations

from datetime import datetime
import json
import uuid

import pytest

from app.core.tokens import create_user_access_token
from app.integrations.storage.local import LocalObjectStorageProvider
from app.models import (
    Acquisition,
    Action,
    Asset,
    Dataset,
    KpiValue,
    Observation,
    Order,
    Report,
    User,
)
from app.modules.analytics.domain import (
    EvaluationContext,
    KpiImportance,
    calculator_registry,
    rule_registry,
)
from app.modules.catalog.services import sync_catalog_from_legacy
from app.modules.reports.ports import report_context_registry
from app.modules.reports.schemas import ReportGenerateRequest
from app.modules.reports.services import generate_report
from app.sectors.mining import definition
from app.sectors.mining.domain import (
    KPI_DEFINITIONS,
    SUPPORTED_ASSET_TYPES,
    SUPPORTED_DATASET_TYPES,
)
from app.sectors.mining.fixtures import (
    demo_mining_bundle,
    resolve_demo_dataset_references,
)
from app.sectors.mining.services import ANALYSIS_SCHEMA, build_source_context
from app.sectors.registry import SECTOR_MODULES
from app.services.cart import seed_shop_products
from app.services.storage import StorageService


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
    result = {"Authorization": f"Bearer {token}"}
    if workspace_id:
        result["X-Workspace-ID"] = workspace_id
    return result


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
    asset_type: str = "STOCKPILE_ZONE",
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
                "customer_type": "enterprise",
                "sector_focus": "mining",
                "modules_enabled": ["assets", "analytics", "reports"]
                + (["mining"] if enabled else []),
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
            "sector": "MINING",
            "asset_type": asset_type,
            "name": f"{prefix} asset",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [14.90, -12.80],
                        [14.94, -12.80],
                        [14.94, -12.76],
                        [14.90, -12.76],
                        [14.90, -12.80],
                    ]
                ],
            },
        },
    )
    assert asset.status_code == 201, asset.text
    seed_shop_products(db_session)
    sync_catalog_from_legacy(db_session)
    return owner, organization["id"], workspace_id, asset.json(), headers


def _analysis(**values) -> dict:
    return {
        "schema": ANALYSIS_SCHEMA,
        "validation_status": "VALIDATED",
        "algorithm": "geovision.mining.test",
        "algorithm_version": "1.0.0",
        "confidence": 0.9,
        "metrics": {},
        **values,
    }


def _surface_reference(reference: str, *, datum: str = "EVRF2019") -> dict:
    return {
        "reviewed": True,
        "surface_reference": reference,
        "crs": "EPSG:25830",
        "vertical_datum": datum,
        "method": "geovision.mining.normalized_surface",
        "method_version": "1.0.0",
    }


def _survey(reference: str) -> dict:
    return {
        "reviewed": True,
        "survey_reference": reference,
        "method": "geovision.mining.rtk_ppk_survey",
        "method_version": "1.0.0",
        "crs": "EPSG:25830",
    }


def _quality(control_dataset_id: str, *, horizontal_rmse_cm: float = 2.0) -> dict:
    return {
        "reviewed": True,
        "project_tolerance_approved": True,
        "tolerance_reference": "project-tolerance-v1",
        "method": "geovision.mining.rtk_ppk_photogrammetry",
        "method_version": "1.0.0",
        "acquisition_method": "RTK_PPK_PHOTOGRAMMETRY",
        "horizontal_rmse_cm": horizontal_rmse_cm,
        "vertical_rmse_cm": 4.0,
        "ground_sample_distance_cm": 2.0,
        "control_point_count": 6,
        "checkpoint_count": 5,
        "control_dataset_id": control_dataset_id,
        "crs": "EPSG:25830",
        "vertical_datum": "EVRF2019",
        "project_tolerances": {
            "max_horizontal_rmse_cm": 5.0,
            "max_vertical_rmse_cm": 8.0,
            "max_ground_sample_distance_cm": 3.0,
            "min_control_point_count": 4,
            "min_checkpoint_count": 4,
        },
    }


def _pair(current_id: str, previous_id: str) -> dict:
    return {
        "reviewed": True,
        "current_dataset_id": current_id,
        "previous_dataset_id": previous_id,
        "aligned": True,
        "same_crs": True,
        "same_vertical_datum": True,
        "vertical_datum": "EVRF2019",
        "method": "geovision.mining.surface_difference",
        "method_version": "1.0.0",
    }


def _dataset(
    db_session,
    *,
    asset: Asset,
    name: str,
    dataset_type: str,
    captured_at: datetime,
    metadata: dict | None = None,
    quality_status: str = "PASSED",
    status: str = "ready",
) -> Dataset:
    row = Dataset(
        id=str(uuid.uuid4()),
        company_id=asset.organization_id,
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        name=name,
        data_type=dataset_type,
        dataset_type=dataset_type,
        source="test",
        provider_code="geovision",
        storage_provider="local",
        processing_level="DERIVED",
        quality_status=quality_status,
        status=status,
        sector="MINING",
        capture_date=captured_at,
        crs="EPSG:25830",
        metadata_json=json.dumps(metadata or {}),
        provenance_json="{}",
        created_at=captured_at,
        updated_at=captured_at,
        processed_at=captured_at,
    )
    db_session.add(row)
    db_session.flush()
    return row


def _materialize_bundle(
    db_session, *, asset: Asset, bundle: dict
) -> dict[str, Dataset]:
    rows: dict[str, Dataset] = {}
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
            sector="MINING",
            capture_date=item["capture_date"],
            crs=item["crs"],
            resolution=2.0,
            resolution_unit="cm",
            metadata_json="{}",
            provenance_json=json.dumps(item["provenance"]),
            created_at=item["capture_date"],
            updated_at=item["capture_date"],
            processed_at=item["capture_date"],
        )
        db_session.add(row)
        rows[item["name"]] = row
    db_session.flush()
    resolved = resolve_demo_dataset_references(
        bundle, {name: row.id for name, row in rows.items()}
    )
    for item in resolved["datasets"]:
        rows[item["name"]].metadata_json = json.dumps(item["metadata"])
    db_session.commit()
    return rows


def test_mining_registers_as_an_independent_common_core_extension():
    assert definition.enabled_by_default is True
    assert definition.activation_phase == 30
    assert definition.routes[0].key == "sector.mining"
    assert definition.routes[0].order == 71
    legacy_owners = {
        identifier: [
            sector.name
            for sector in SECTOR_MODULES
            if identifier in sector.legacy_identifiers
        ]
        for identifier in {
            item for sector in SECTOR_MODULES for item in sector.legacy_identifiers
        }
    }
    assert all(len(owners) == 1 for owners in legacy_owners.values())
    assert legacy_owners["industry"] == ["industry_energy_utilities"]
    assert legacy_owners["quarry"] == ["mining"]
    assert SUPPORTED_ASSET_TYPES == {
        "MINE_SITE",
        "QUARRY",
        "PIT",
        "STOCKPILE_ZONE",
        "HAUL_ROAD",
        "SLOPE",
        "TALUS",
        "ENVIRONMENTAL_MONITORING_ZONE",
    }
    assert SUPPORTED_DATASET_TYPES == {
        "RGB_IMAGES",
        "ORTHOMOSAIC",
        "POINT_CLOUD",
        "DSM",
        "DTM",
        "MESH_3D",
        "RTK_OBSERVATIONS",
        "LIDAR_POINT_CLOUD",
    }
    registrations = calculator_registry.registrations("MINING")
    assert len(registrations) == len(KPI_DEFINITIONS)
    assert {item.definition.importance for item in registrations} == {
        KpiImportance.PRIMARY,
        KpiImportance.SECONDARY,
    }
    rule = rule_registry.registrations("MINING")[0]
    assert rule.version == "1.0.0"
    assert "MINING" in report_context_registry.sectors()
    empty = EvaluationContext(
        asset_id="asset",
        sector="MINING",
        measured_at=datetime(2026, 9, 10, 8),
    )
    assert all(item.calculate(empty) is None for item in registrations)
    stockpile_actions = rule.evaluate(
        EvaluationContext(
            asset_id="stockpile",
            sector="MINING",
            measured_at=datetime(2026, 9, 10, 8),
            metadata={"asset_type": "STOCKPILE_ZONE", "source_availability": {}},
        ),
        {},
    ).actions
    environmental_actions = rule.evaluate(
        EvaluationContext(
            asset_id="environmental-zone",
            sector="MINING",
            measured_at=datetime(2026, 9, 10, 8),
            metadata={
                "asset_type": "ENVIRONMENTAL_MONITORING_ZONE",
                "source_availability": {},
            },
        ),
        {},
    ).actions
    assert {
        item.recommended_catalog_item_id
        for item in (*stockpile_actions, *environmental_actions)
    } == {
        "prod_mining_volumetry_survey",
        "prod_mining_site_progress_survey",
        "prod_mining_environmental_monitoring",
        "prod_mining_repeat_monitoring_plan",
    }


def test_precise_volume_fails_closed_but_reviewed_surface_area_remains_available(
    client, db_session
):
    _, _, _, asset_payload, _ = _workspace_asset(
        client, db_session, prefix="mining-quality"
    )
    asset = db_session.get(Asset, asset_payload["id"])
    previous = _dataset(
        db_session,
        asset=asset,
        name="Previous surface",
        dataset_type="POINT_CLOUD",
        captured_at=datetime(2026, 8, 1, 8),
        metadata={
            "mining_analysis": _analysis(
                surface_reference_evidence=_surface_reference("previous-surface"),
                review_candidates=[],
            )
        },
    )
    control = _dataset(
        db_session,
        asset=asset,
        name="Current controls",
        dataset_type="RTK_OBSERVATIONS",
        captured_at=datetime(2026, 9, 1, 7),
    )
    current = _dataset(
        db_session,
        asset=asset,
        name="Current failed-tolerance surface",
        dataset_type="POINT_CLOUD",
        captured_at=datetime(2026, 9, 1, 8),
    )
    current.metadata_json = json.dumps(
        {
            "mining_analysis": _analysis(
                metrics={
                    "stockpile_volume": 999999.123,
                    "terrain_volume_change": 999999.123,
                    "surface_change_area": 50.0,
                },
                survey_evidence=_survey("current-survey"),
                surface_reference_evidence=_surface_reference("current-surface"),
                volume_quality_evidence=_quality(control.id, horizontal_rmse_cm=7.0),
                surface_comparison_evidence=_pair(current.id, previous.id),
                review_candidates=[],
            )
        }
    )
    failed_dataset = _dataset(
        db_session,
        asset=asset,
        name="Failed dataset with forged perfect result",
        dataset_type="POINT_CLOUD",
        captured_at=datetime(2026, 9, 2, 8),
        metadata={
            "mining_analysis": _analysis(
                metrics={"stockpile_volume": 888888.0},
                survey_evidence=_survey("failed-survey"),
                surface_reference_evidence=_surface_reference("failed-surface"),
                volume_quality_evidence=_quality(control.id),
            )
        },
        quality_status="FAILED",
    )
    db_session.commit()

    context = build_source_context(
        db_session, asset=asset, as_of=datetime(2026, 9, 10, 8)
    )
    assert context.evaluation.measurements["surface_change_area"] == 50.0
    assert "stockpile_volume" not in context.evaluation.measurements
    assert "terrain_volume_change" not in context.evaluation.measurements
    assert context.availability["precise_volume"] is False
    assert context.availability["rtk_ppk_photogrammetry"] is False
    assert failed_dataset.id not in {item["id"] for item in context.evaluation.datasets}


def test_surface_pair_rejects_forged_datum_foreign_asset_and_invalid_prior_analysis(
    client, db_session
):
    _, _, _, asset_payload, headers = _workspace_asset(
        client, db_session, prefix="mining-pair-gates"
    )
    asset = db_session.get(Asset, asset_payload["id"])
    foreign_payload = client.post(
        "/assets",
        headers=headers,
        json={
            "sector": "MINING",
            "asset_type": "STOCKPILE_ZONE",
            "name": "Foreign stockpile in same workspace",
        },
    )
    assert foreign_payload.status_code == 201, foreign_payload.text
    foreign = db_session.get(Asset, foreign_payload.json()["id"])
    foreign_previous = _dataset(
        db_session,
        asset=foreign,
        name="Foreign previous surface",
        dataset_type="POINT_CLOUD",
        captured_at=datetime(2026, 8, 1, 8),
        metadata={
            "mining_analysis": _analysis(
                surface_reference_evidence=_surface_reference("foreign-surface")
            )
        },
    )
    wrong_datum = _dataset(
        db_session,
        asset=asset,
        name="Prior local-datum surface",
        dataset_type="POINT_CLOUD",
        captured_at=datetime(2026, 8, 2, 8),
        metadata={
            "mining_analysis": _analysis(
                surface_reference_evidence=_surface_reference(
                    "local-datum-surface", datum="LOCAL_DATUM"
                )
            )
        },
    )
    invalid_prior = _dataset(
        db_session,
        asset=asset,
        name="Prior surface with invalid analysis version",
        dataset_type="POINT_CLOUD",
        captured_at=datetime(2026, 8, 3, 8),
        metadata={
            "mining_analysis": {
                **_analysis(
                    surface_reference_evidence=_surface_reference("invalid-prior")
                ),
                "algorithm_version": "invalid version",
            }
        },
    )
    for index, previous in enumerate(
        (foreign_previous, wrong_datum, invalid_prior), start=1
    ):
        current = _dataset(
            db_session,
            asset=asset,
            name=f"Forged comparison {index}",
            dataset_type="POINT_CLOUD",
            captured_at=datetime(2026, 9, index, 8),
        )
        current.metadata_json = json.dumps(
            {
                "mining_analysis": _analysis(
                    metrics={"surface_change_area": 1000.0 + index},
                    surface_reference_evidence=_surface_reference(
                        f"forged-current-{index}"
                    ),
                    surface_comparison_evidence=_pair(current.id, previous.id),
                    review_candidates=[],
                )
            }
        )
    db_session.commit()

    context = build_source_context(
        db_session, asset=asset, as_of=datetime(2026, 9, 10, 8)
    )
    assert "surface_change_area" not in context.evaluation.measurements
    assert context.availability["paired_surface"] is False
    assert foreign_previous.id not in context.evidence["dataset_ids"]


@pytest.mark.parametrize(
    (
        "asset_type",
        "kind",
        "evidence_key",
        "scope",
        "metric_key",
        "observation_type",
        "catalog_id",
    ),
    [
        (
            "SLOPE",
            "slope",
            "slope_evidence",
            "SLOPE",
            "slope_review_candidate_count",
            "SLOPE_CHANGE_CANDIDATE",
            "prod_mining_lidar_specialist_survey",
        ),
        (
            "HAUL_ROAD",
            "haul_road",
            "haul_road_evidence",
            "HAUL_ROAD",
            "haul_road_review_candidate_count",
            "HAUL_ROAD_SURFACE_CHANGE_CANDIDATE",
            "prod_mining_site_progress_survey",
        ),
    ],
)
def test_slope_and_haul_road_candidates_require_explicit_reviewed_evidence(
    client,
    db_session,
    asset_type,
    kind,
    evidence_key,
    scope,
    metric_key,
    observation_type,
    catalog_id,
):
    _, _, _, asset_payload, headers = _workspace_asset(
        client,
        db_session,
        prefix=f"mining-{kind}",
        asset_type=asset_type,
    )
    asset = db_session.get(Asset, asset_payload["id"])
    previous = _dataset(
        db_session,
        asset=asset,
        name="Previous inspected surface",
        dataset_type="POINT_CLOUD",
        captured_at=datetime(2026, 8, 1, 8),
        metadata={
            "mining_analysis": _analysis(
                surface_reference_evidence=_surface_reference("previous-inspection")
            )
        },
    )
    current = _dataset(
        db_session,
        asset=asset,
        name="Current inspected surface",
        dataset_type="POINT_CLOUD",
        captured_at=datetime(2026, 9, 1, 8),
    )
    base = _analysis(
        surface_reference_evidence=_surface_reference("current-inspection"),
        surface_comparison_evidence=_pair(current.id, previous.id),
        review_candidates=[
            {
                "id": f"{kind}-candidate-1",
                "kind": kind,
                "new": True,
                "label": "Mapped geometric change candidate",
                "area_m2": 120.0,
                "severity": "WATCH",
                "confidence": 0.81,
            }
        ],
    )
    current.metadata_json = json.dumps({"mining_analysis": base})
    db_session.commit()
    ungated = build_source_context(
        db_session, asset=asset, as_of=datetime(2026, 9, 10, 8)
    )
    assert ungated.evaluation.metadata["findings"] == ()
    assert metric_key not in ungated.evaluation.measurements

    evidence = {
        "reviewed": True,
        "interpretation_scope": "GEOMETRIC_CHANGE_ONLY",
        "asset_scope": scope,
        "source_reference": f"{kind}-review-1",
        "method": "geovision.mining.geometric_change_review",
        "method_version": "1.0.0",
    }
    if kind == "slope":
        evidence.update(
            {
                "recommended_method": "LIDAR",
                "lidar_justification": (
                    "Occluded geometry requires a specialist to assess point-density needs."
                ),
            }
        )
    base[evidence_key] = evidence
    current.metadata_json = json.dumps({"mining_analysis": base})
    db_session.commit()

    evaluated = client.post(
        f"/assets/{asset.id}/mining/evaluate",
        headers=headers,
        json={"as_of": "2026-09-10T08:00:00"},
    )
    assert evaluated.status_code == 200, evaluated.text
    kpis = {item["definition"]["key"]: item for item in evaluated.json()["kpis"]}
    assert kpis[metric_key]["current"] == 1
    observations = client.get(
        f"/assets/{asset.id}/observations", headers=headers
    ).json()["items"]
    assert len(observations) == 1
    assert observations[0]["type"] == observation_type
    assert observations[0]["validation_status"] == "NEEDS_REVIEW"
    assert observations[0]["value"]["cause"] is None
    assert observations[0]["value"]["diagnosis"] is None
    assert observations[0]["value"]["geotechnical_conclusion"] is None
    actions = client.get(f"/assets/{asset.id}/actions", headers=headers).json()["items"]
    reviewed = [item for item in actions if item["source_observation_id"]]
    assert len(reviewed) == 1
    assert reviewed[0]["recommended_catalog_item_id"] == catalog_id


def test_validated_rtk_photogrammetry_flow_uses_common_lifecycle_without_lidar(
    client, db_session, tmp_path
):
    owner, organization_id, workspace_id, asset_payload, headers = _workspace_asset(
        client, db_session, prefix="mining-full"
    )
    asset = db_session.get(Asset, asset_payload["id"])
    order = Order(
        user_id=owner.id,
        company_id=organization_id,
        organization_id=organization_id,
        workspace_id=workspace_id,
        order_number=f"GV-P30-{uuid.uuid4().hex[:10].upper()}",
        order_type="SERVICE",
        status="confirmed",
        fulfilment_status="CONFIRMED",
        payment_status="PENDING",
        currency="EUR",
        subtotal=1200,
        total=1200,
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
            "title": "RTK/PPK stockpile survey",
            "drone_details": {
                "payload_reference": "RGB-RTK-PHOTOGRAMMETRY",
                "mission_requirements": {
                    "orthomosaic": True,
                    "point_cloud": True,
                    "lidar": False,
                },
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
        bundle=demo_mining_bundle(),
    )
    current = datasets["Current stockpile point cloud"]
    current.mission_id = acquisition.id
    datasets["Current stockpile orthomosaic"].mission_id = acquisition.id
    db_session.commit()
    assert not any(row.dataset_type == "LIDAR_POINT_CLOUD" for row in datasets.values())
    assert order.id in {
        item["id"] for item in client.get("/orders", headers=headers).json()
    }
    history = client.get(f"/missions/assets/{asset.id}/history", headers=headers)
    assert history.status_code == 200, history.text
    assert acquisition.id in {item["id"] for item in history.json()}

    capabilities = client.get("/sectors/mining/capabilities", headers=headers)
    assert capabilities.status_code == 200, capabilities.text
    assert capabilities.json()["enabled"] is True
    assert capabilities.json()["analysis_schema"] == ANALYSIS_SCHEMA

    evaluated = client.post(
        f"/assets/{asset.id}/mining/evaluate",
        headers=headers,
        json={"as_of": "2026-09-10T08:00:00"},
    )
    assert evaluated.status_code == 200, evaluated.text
    body = evaluated.json()
    assert body["source_availability"]["precise_volume"] is True
    assert body["source_availability"]["paired_surface"] is True
    assert body["source_availability"]["historical_comparison"] is True
    assert body["source_availability"]["rtk_ppk_photogrammetry"] is True
    assert body["source_availability"]["lidar"] is False
    kpis = {item["definition"]["key"]: item for item in body["kpis"]}
    assert kpis["stockpile_volume"]["current"] == 13250
    assert kpis["terrain_volume_change"]["current"] == 1250
    assert kpis["surface_change_area"]["current"] == 860
    assert kpis["survey_freshness_days"]["current"] == 5
    quality = kpis["stockpile_volume"]["provenance"]["quality"]
    assert quality["acquisition_method"] == "RTK_PPK_PHOTOGRAMMETRY"
    assert quality["horizontal_rmse_cm"] == 2.4
    assert quality["vertical_rmse_cm"] == 4.1
    assert quality["ground_sample_distance_cm"] == 2
    assert quality["control_point_count"] == 6
    assert quality["checkpoint_count"] == 5
    assert quality["crs"] == "EPSG:25830"
    assert quality["vertical_datum"] == "EVRF2019"

    counts = (
        db_session.query(KpiValue).filter(KpiValue.asset_id == asset.id).count(),
        db_session.query(Observation).filter(Observation.asset_id == asset.id).count(),
        db_session.query(Action).filter(Action.asset_id == asset.id).count(),
    )
    replay = client.post(
        f"/assets/{asset.id}/mining/evaluate",
        headers=headers,
        json={"as_of": "2026-09-10T08:00:00"},
    )
    assert replay.status_code == 200, replay.text
    assert counts == (
        db_session.query(KpiValue).filter(KpiValue.asset_id == asset.id).count(),
        db_session.query(Observation).filter(Observation.asset_id == asset.id).count(),
        db_session.query(Action).filter(Action.asset_id == asset.id).count(),
    )

    observations = client.get(
        f"/assets/{asset.id}/observations", headers=headers
    ).json()["items"]
    assert len(observations) == 1
    assert observations[0]["type"] == "MINING_SURFACE_CHANGE_CANDIDATE"
    assert observations[0]["validation_status"] == "NEEDS_REVIEW"
    assert all(
        observations[0]["value"][key] is None
        for key in (
            "cause",
            "diagnosis",
            "defect",
            "geotechnical_conclusion",
            "safety_certification",
        )
    )
    actions = client.get(f"/assets/{asset.id}/actions", headers=headers).json()["items"]
    assert {item["recommended_catalog_item_id"] for item in actions} == {
        "prod_mining_site_progress_survey"
    }

    comparisons = client.get(f"/assets/{asset.id}/mining/comparisons", headers=headers)
    assert comparisons.status_code == 200, comparisons.text
    comparison_items = {item["kind"]: item for item in comparisons.json()["items"]}
    assert comparison_items["SURVEY_2D"]["availability"] == "AVAILABLE"
    assert comparison_items["SURFACE_3D"]["availability"] == "AVAILABLE"
    assert comparison_items["SURFACE_3D"]["vertical_datum"] == "EVRF2019"

    layers = client.get(f"/assets/{asset.id}/mining/map-layers", headers=headers)
    assert layers.status_code == 200, layers.text
    layer_items = layers.json()["items"]
    assert {
        "ASSET_BOUNDARY",
        "POINT_CLOUD",
        "ORTHOMOSAIC",
        "RTK_OBSERVATIONS",
        "OBSERVATION_ZONE",
    }.issubset({item["kind"] for item in layer_items})
    point_cloud = next(
        item
        for item in layer_items
        if item["dataset_id"] == current.id and item["kind"] == "POINT_CLOUD"
    )
    assert point_cloud["quality"]["volume_tolerance"] == "PASSED"
    assert all(
        item["availability"] == "UNKNOWN"
        for item in layer_items
        if item["kind"] == "OBSERVATION_ZONE"
    )

    context = client.get(f"/assets/{asset.id}/mining/report-context", headers=headers)
    assert context.status_code == 200, context.text
    context_body = context.json()
    assert context_body["schema"] == "geovision.mining.report-context.v1"
    combined = json.dumps(context_body).lower()
    assert "no reserve" in combined
    assert "ore-grade" in combined
    assert "safety" in combined
    assert not any(
        phrase in combined
        for phrase in (
            "confirmed reserve",
            "ore grade is",
            "slope is stable",
            "safe for operations",
            "defect confirmed",
        )
    )

    storage = StorageService(
        LocalObjectStorageProvider(
            root=tmp_path,
            public_base_url="http://testserver",
            signing_secret="test-mining-report-signing-key",
        )
    )
    report_row, created = generate_report(
        db_session,
        actor=owner,
        asset=asset,
        data=ReportGenerateRequest(
            report_type="MINING_VOLUMETRY",
            acquisition_id=acquisition.id,
            idempotency_key=f"mining-report-{uuid.uuid4()}",
        ),
        storage=storage,
    )
    db_session.commit()
    assert created is True
    assert report_row.asset_id == asset.id
    assert report_row.acquisition_id == acquisition.id
    report_context = json.loads(report_row.context_json)
    assert report_context["asset"]["sector"] == "MINING"
    assert report_context["source_availability"]["rtk_ppk_photogrammetry"] is True
    assert db_session.query(Report).filter(Report.asset_id == asset.id).count() == 1


def test_mining_permissions_tenant_boundaries_and_feature_flag_are_independent(
    client, db_session
):
    owner, organization_id, workspace_id, asset, headers = _workspace_asset(
        client, db_session, prefix="mining-isolation"
    )
    viewer = _user(db_session, "mining-viewer")
    membership = client.post(
        f"/organizations/{organization_id}/members",
        headers=headers,
        json={"email": viewer.email, "user_id": viewer.id, "role": "viewer"},
    )
    assert membership.status_code == 201, membership.text
    viewer_headers = _headers(viewer, workspace_id)
    assert (
        client.get(
            f"/assets/{asset['id']}/mining/report-context", headers=viewer_headers
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/assets/{asset['id']}/mining/evaluate",
            headers=viewer_headers,
            json={},
        ).status_code
        == 403
    )

    second = client.post(
        f"/organizations/{organization_id}/workspaces",
        headers=headers,
        json={
            "name": "Mining disabled workspace",
            "sector_focus": "mining",
            "customer_type": "enterprise",
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
            "sector": "MINING",
            "asset_type": "QUARRY",
            "name": "Disabled-workspace quarry",
        },
    )
    assert disabled_asset.status_code == 201, disabled_asset.text
    capabilities = client.get("/sectors/mining/capabilities", headers=disabled_headers)
    assert capabilities.status_code == 200
    assert capabilities.json()["enabled"] is False
    assert (
        client.get(
            f"/assets/{disabled_asset.json()['id']}/mining/map-layers",
            headers=disabled_headers,
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/assets/{asset['id']}/mining/report-context",
            headers=disabled_headers,
        ).status_code
        == 404
    )
    assert (
        client.get("/sectors/mining/capabilities", headers=headers).json()["enabled"]
        is True
    )

    _, _, _, _, outsider_headers = _workspace_asset(
        client, db_session, prefix="mining-outsider"
    )
    hidden = client.get(
        f"/assets/{asset['id']}/mining/report-context",
        headers=outsider_headers,
    )
    assert hidden.status_code == 404
