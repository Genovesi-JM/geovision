from __future__ import annotations

from datetime import datetime
import json
import uuid

from app.core.tokens import create_user_access_token
from app.models import (
    Action,
    Asset,
    Dataset,
    IntelligenceAcquisition,
    IotDevice,
    KpiValue,
    Observation,
    SatelliteScene,
    Site,
    TelemetryReading,
    User,
    WeatherObservation,
)
from app.modules.analytics.domain import (
    EvaluationContext,
    KpiImportance,
    calculator_registry,
    rule_registry,
)
from app.sectors.agriculture.domain import (
    KPI_DEFINITIONS,
    SUPPORTED_ASSET_TYPES,
    SUPPORTED_DATASET_TYPES,
)
from app.sectors.agriculture.fixtures import demo_fusion_bundle
from app.sectors.agriculture.services import ANALYSIS_SCHEMA, build_source_context


def _user(db_session, prefix: str) -> User:
    row = User(
        email=f"{prefix}-{uuid.uuid4().hex}@example.com",
        role="cliente",
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


def _workspace_asset(
    client,
    db_session,
    *,
    prefix: str,
    sector: str = "AGRICULTURE",
    asset_type: str = "FIELD",
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
                "sector_focus": "agro",
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
                        [13.13, -8.90],
                        [13.13, -8.87],
                        [13.10, -8.87],
                        [13.10, -8.90],
                    ]
                ],
            },
        },
    )
    assert asset.status_code == 201, asset.text
    return owner, organization["id"], workspace_id, asset.json(), headers


def _materialize_fusion(db_session, *, asset: Asset, bundle: dict):
    site = Site(
        id=str(uuid.uuid4()),
        company_id=asset.organization_id,
        name="Fusion fixture site",
        country="Angola",
        sector="agriculture",
    )
    db_session.add(site)
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
            provider_code=(
                "copernicus"
                if item["dataset_type"] == "SATELLITE_IMAGE"
                else "geovision"
            ),
            storage_provider="local",
            processing_level=item["processing_level"],
            quality_status=item["quality_status"],
            status="ready",
            sector="AGRICULTURE",
            capture_date=item["capture_date"],
            crs="EPSG:4326",
            resolution=10.0,
            resolution_unit="m",
            metadata_json=json.dumps(item["metadata"]),
            provenance_json=json.dumps({"fixture": True}),
            created_at=item["capture_date"],
            updated_at=item["capture_date"],
        )
        db_session.add(row)
        datasets[item["name"]] = row
    db_session.flush()

    satellite_dataset = datasets["Sentinel-2 context scene"]
    satellite_run = IntelligenceAcquisition(
        id=str(uuid.uuid4()),
        organization_id=asset.organization_id,
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        kind="SATELLITE",
        provider_code="copernicus",
        request_fingerprint="a" * 64,
        request_json="{}",
        result_summary_json="{}",
        dataset_ids_json=json.dumps([satellite_dataset.id]),
        status="COMPLETED",
        idempotency_key=f"agriculture-demo-satellite:{asset.id}",
        completed_at=bundle["satellite_scene"]["acquired_at"],
    )
    db_session.add(satellite_run)
    db_session.flush()
    scene = bundle["satellite_scene"]
    db_session.add(
        SatelliteScene(
            id=str(uuid.uuid4()),
            organization_id=asset.organization_id,
            asset_id=asset.id,
            intelligence_acquisition_id=satellite_run.id,
            dataset_id=satellite_dataset.id,
            provider_code=scene["provider_code"],
            provider_reference=scene["provider_reference"],
            collection=scene["collection"],
            acquired_at=scene["acquired_at"],
            cloud_cover_percent=scene["cloud_cover_percent"],
            resolution_meters=scene["resolution_meters"],
            crs="EPSG:4326",
            bands_json=json.dumps(scene["bands"]),
            bbox_json=json.dumps([13.10, -8.90, 13.13, -8.87]),
            coverage_geojson=json.dumps(scene["coverage"]),
            assets_json="{}",
            provenance_json=json.dumps({"fixture": True}),
        )
    )

    weather_dataset = datasets["Nearby observed weather"]
    weather_run = IntelligenceAcquisition(
        id=str(uuid.uuid4()),
        organization_id=asset.organization_id,
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        kind="WEATHER",
        provider_code="fake_weather",
        request_fingerprint="b" * 64,
        request_json="{}",
        result_summary_json="{}",
        dataset_ids_json=json.dumps([weather_dataset.id]),
        status="COMPLETED",
        idempotency_key=f"agriculture-demo-weather:{asset.id}",
        completed_at=weather_dataset.capture_date,
    )
    db_session.add(weather_run)
    db_session.flush()
    for item in bundle["weather"]:
        db_session.add(
            WeatherObservation(
                id=str(uuid.uuid4()),
                organization_id=asset.organization_id,
                asset_id=asset.id,
                intelligence_acquisition_id=weather_run.id,
                dataset_id=weather_dataset.id,
                provider_code="fake_weather",
                source_reference="demo-station",
                source_name="GeoVision demo station",
                observed_at=weather_dataset.capture_date,
                metric=item["metric"],
                value=item["value"],
                unit=item["unit"],
                quality=item["quality"],
                latitude=-8.885,
                longitude=13.115,
                distance_km=1.2,
                provenance_json=json.dumps({"fixture": True}),
            )
        )

    device = IotDevice(
        id=str(uuid.uuid4()),
        public_id=f"field-node-{uuid.uuid4().hex[:10]}",
        company_id=asset.organization_id,
        site_id=site.id,
        core_asset_id=asset.id,
        provider_code="geovision",
        provider_device_id=f"demo-{uuid.uuid4().hex}",
        name="Calibrated field node",
        device_type="soil_weather_node",
        transport="mqtt",
        status="active",
        token_hash="0" * 64,
        secret_encrypted="fixture-ciphertext-not-a-secret",
        capabilities_json=json.dumps(["soil_moisture"]),
        configuration_json="{}",
        connectivity_status="online",
        health_status="healthy",
        last_latitude=-8.884,
        last_longitude=13.116,
        last_seen_at=bundle["telemetry"]["recorded_at"],
    )
    db_session.add(device)
    db_session.flush()
    telemetry = bundle["telemetry"]
    db_session.add(
        TelemetryReading(
            id=str(uuid.uuid4()),
            device_id=device.id,
            company_id=asset.organization_id,
            site_id=site.id,
            core_asset_id=asset.id,
            message_id=f"demo-{uuid.uuid4().hex}",
            source="edge_replay",
            channel=telemetry["channel"],
            numeric_value=telemetry["value"],
            unit=telemetry["unit"],
            quality=telemetry["quality"],
            recorded_at=telemetry["recorded_at"],
            metadata_json=json.dumps({"calibrated": True, "fixture": True}),
        )
    )
    db_session.commit()
    return datasets


def test_agriculture_registers_sector_local_capabilities_and_versioned_logic():
    assert {"FARM", "FIELD", "SITE", "PASTURE"}.issubset(SUPPORTED_ASSET_TYPES)
    assert {
        "MULTISPECTRAL_IMAGES",
        "ORTHOMOSAIC",
        "NDVI",
        "SATELLITE_IMAGE",
        "WEATHER_DATA",
        "TELEMETRY",
    }.issubset(SUPPORTED_DATASET_TYPES)
    registrations = calculator_registry.registrations("AGRICULTURE")
    assert len(registrations) == len(KPI_DEFINITIONS)
    assert {item.definition.importance for item in registrations} == {
        KpiImportance.PRIMARY,
        KpiImportance.SECONDARY,
        KpiImportance.TECHNICAL,
    }
    assert rule_registry.registrations("AGRICULTURE")[0].version == "1.0.0"


def test_calculators_degrade_cleanly_and_do_not_invent_missing_indices():
    context = EvaluationContext(
        asset_id="asset",
        sector="AGRICULTURE",
        measured_at=datetime(2026, 9, 10, 8),
        measurements={"ndvi_mean": 0.62},
        metadata={
            "measurement_details": {
                "ndvi_mean": {
                    "source": "satellite:derived_ndvi",
                    "confidence": 0.8,
                    "measured_at": datetime(2026, 9, 10, 7),
                    "dataset_id": "dataset-ndvi",
                }
            }
        },
    )
    results = {
        item.definition.key: item.calculate(context)
        for item in calculator_registry.registrations("AGRICULTURE")
    }
    assert results["ndvi_mean"].value == 0.62
    assert results["crop_condition"].value == 62
    assert results["crop_condition"].confidence == 0.68
    assert results["ndre_mean"] is None
    assert results["gndvi_mean"] is None
    assert results["water_stress"] is None
    assert "not disease" in results["crop_condition"].provenance["scientific_caution"]


def test_unrecognized_or_out_of_range_dataset_analysis_is_not_treated_as_fact(
    client, db_session
):
    _, _, _, payload, _ = _workspace_asset(
        client, db_session, prefix="agriculture-invalid"
    )
    asset = db_session.get(Asset, payload["id"])
    db_session.add_all(
        [
            Dataset(
                company_id=asset.organization_id,
                workspace_id=asset.workspace_id,
                asset_id=asset.id,
                name="Untrusted free-form metadata",
                dataset_type="NDVI",
                status="ready",
                quality_status="PASSED",
                processing_level="DERIVED",
                capture_date=datetime(2026, 9, 10, 8),
                metadata_json=json.dumps({"ndvi_mean": 0.99}),
            ),
            Dataset(
                company_id=asset.organization_id,
                workspace_id=asset.workspace_id,
                asset_id=asset.id,
                name="Invalid structured index",
                dataset_type="NDVI",
                status="ready",
                quality_status="PASSED",
                processing_level="DERIVED",
                capture_date=datetime(2026, 9, 10, 9),
                metadata_json=json.dumps(
                    {
                        "agriculture_analysis": {
                            "schema": ANALYSIS_SCHEMA,
                            "confidence": 0.9,
                            "metrics": {"ndvi_mean": 4.2},
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
    assert "ndvi_mean" not in context.evaluation.measurements
    assert context.availability["analysis_dataset_count"] == 1


def test_full_drone_satellite_weather_and_sensor_fusion_is_idempotent(
    client, db_session
):
    owner, organization_id, workspace_id, asset_payload, headers = _workspace_asset(
        client, db_session, prefix="agriculture-fusion"
    )
    asset = db_session.get(Asset, asset_payload["id"])
    bundle = demo_fusion_bundle()
    datasets = _materialize_fusion(db_session, asset=asset, bundle=bundle)

    capabilities = client.get("/sectors/agriculture/capabilities", headers=headers)
    assert capabilities.status_code == 200, capabilities.text
    assert capabilities.json()["enabled"] is True
    assert capabilities.json()["analysis_schema"] == ANALYSIS_SCHEMA

    evaluated = client.post(
        f"/assets/{asset.id}/agriculture/evaluate",
        headers=headers,
        json={"as_of": "2026-09-10T08:00:00"},
    )
    assert evaluated.status_code == 200, evaluated.text
    body = evaluated.json()
    assert body["source_availability"] | {
        "drone": True,
        "satellite": True,
        "iot": True,
        "weather": True,
    } == body["source_availability"]
    items = {item["definition"]["key"]: item for item in body["kpis"]}
    assert items["crop_condition"]["status"] == "WATCH"
    assert items["area_needing_attention"]["current"] == 3.4
    assert items["water_stress"]["status"] == "WARNING"
    assert items["soil_moisture"]["current"] == 21.5
    assert items["ndvi_change"]["current"] == -0.11
    assert items["ndvi_mean"]["dataset_id"] == datasets[
        "Current drone multispectral campaign"
    ].id
    assert items["soil_moisture"]["dataset_id"] is None
    assert items["ndre_mean"]["status"] == "UNKNOWN"
    assert len(body["observation_ids"]) == 2
    assert len(body["action_ids"]) == 2

    counts = (
        db_session.query(KpiValue).filter(KpiValue.asset_id == asset.id).count(),
        db_session.query(Observation).filter(Observation.asset_id == asset.id).count(),
        db_session.query(Action).filter(Action.asset_id == asset.id).count(),
    )
    replayed = client.post(
        f"/assets/{asset.id}/agriculture/evaluate",
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
    assert summary.status_code == 200
    assert summary.json()["status"] == "WARNING"
    observations = client.get(
        f"/assets/{asset.id}/observations", headers=headers
    ).json()["items"]
    assert any(item["geometry"] for item in observations)
    assert all(item["validation_status"] == "NEEDS_REVIEW" for item in observations)

    actions = client.get(f"/assets/{asset.id}/actions", headers=headers).json()["items"]
    combined = " ".join(
        f"{item['title']} {item['description']}" for item in actions
    ).lower()
    assert "before treatment" in combined
    assert not any(term in combined for term in ("pesticide", "herbicide", "disease diagnosis"))

    layers = client.get(
        f"/assets/{asset.id}/agriculture/map-layers", headers=headers
    )
    assert layers.status_code == 200, layers.text
    layer_items = layers.json()["items"]
    assert {"ASSET_BOUNDARY", "NDVI", "SATELLITE_IMAGE", "SENSOR_POINT", "OBSERVATION_ZONE"}.issubset(
        {item["kind"] for item in layer_items}
    )
    assert all(
        not str(item.get("data_ref", "")).startswith("http") for item in layer_items
    )

    report = client.get(
        f"/assets/{asset.id}/agriculture/report-context", headers=headers
    )
    assert report.status_code == 200, report.text
    assert report.json()["schema"] == "geovision.agriculture.report-context.v1"
    assert report.json()["algorithm_bundle_version"] == "1.0.0"
    assert any("No chemical" in item for item in report.json()["limitations"])

    viewer = _user(db_session, "agriculture-viewer")
    membership = client.post(
        f"/organizations/{organization_id}/members",
        headers=headers,
        json={"email": viewer.email, "user_id": viewer.id, "role": "viewer"},
    )
    assert membership.status_code == 201, membership.text
    viewer_headers = _headers(viewer, workspace_id)
    assert (
        client.get(
            f"/assets/{asset.id}/agriculture/report-context",
            headers=viewer_headers,
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/assets/{asset.id}/agriculture/evaluate",
            headers=viewer_headers,
            json={},
        ).status_code
        == 403
    )
    assert owner.id
    assert workspace_id == asset.workspace_id


def test_no_data_is_explicit_and_cross_sector_or_cross_tenant_access_is_blocked(
    client, db_session
):
    _, _, _, agriculture, headers = _workspace_asset(
        client, db_session, prefix="agriculture-empty"
    )
    response = client.post(
        f"/assets/{agriculture['id']}/agriculture/evaluate",
        headers=headers,
        json={},
    )
    assert response.status_code == 200, response.text
    assert response.json()["kpi_value_ids"] == []
    assert len(response.json()["action_ids"]) == 2
    assert all(item["availability"] == "NO_DATA" for item in response.json()["kpis"])
    assert all(item["status"] == "UNKNOWN" for item in response.json()["kpis"])

    _, _, _, infrastructure, infrastructure_headers = _workspace_asset(
        client,
        db_session,
        prefix="agriculture-wrong-sector",
        sector="INFRASTRUCTURE",
        asset_type="BRIDGE",
    )
    wrong_sector = client.post(
        f"/assets/{infrastructure['id']}/agriculture/evaluate",
        headers=infrastructure_headers,
        json={},
    )
    assert wrong_sector.status_code == 409

    outsider, _, outsider_workspace, _, outsider_headers = _workspace_asset(
        client, db_session, prefix="agriculture-outsider"
    )
    assert outsider.id and outsider_workspace
    hidden = client.get(
        f"/assets/{agriculture['id']}/agriculture/report-context",
        headers=outsider_headers,
    )
    assert hidden.status_code == 404
