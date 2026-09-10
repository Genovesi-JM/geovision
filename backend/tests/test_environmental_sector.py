from __future__ import annotations

from datetime import datetime
import json
import uuid

from app.core.tokens import create_user_access_token
from app.integrations.storage.local import LocalObjectStorageProvider
from app.models import (
    Acquisition,
    Action,
    Asset,
    Dataset,
    IntelligenceAcquisition,
    IotDevice,
    KpiValue,
    Observation,
    Order,
    Report,
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
from app.modules.catalog.services import sync_catalog_from_legacy
from app.modules.reports.ports import report_context_registry
from app.modules.reports.schemas import ReportGenerateRequest
from app.modules.reports.services import generate_report
from app.sectors.environmental import definition
from app.sectors.environmental.domain import (
    KPI_DEFINITIONS,
    SUPPORTED_ASSET_TYPES,
    SUPPORTED_DATASET_TYPES,
)
from app.sectors.environmental.fixtures import (
    demo_environmental_bundle,
    resolve_demo_dataset_references,
)
from app.sectors.environmental.services import ANALYSIS_SCHEMA, build_source_context
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
    sector: str = "ENVIRONMENTAL",
    asset_type: str = "RESTORATION_SITE",
):
    owner = _user(db_session, f"{prefix}-owner")
    created = client.post(
        "/organizations",
        headers=_headers(owner),
        json={
            "name": f"{prefix}-{uuid.uuid4().hex[:8]}",
            "country": "Spain",
            "timezone": "Europe/Madrid",
            "workspace": {
                "name": f"{prefix} workspace",
                "customer_type": "business",
                "sector_focus": "environment",
                "modules_enabled": ["assets", "analytics", "reports"]
                + (["environmental"] if enabled else []),
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
                        [-3.72, 40.40],
                        [-3.68, 40.40],
                        [-3.68, 40.44],
                        [-3.72, 40.44],
                        [-3.72, 40.40],
                    ]
                ],
            },
        },
    )
    assert asset.status_code == 201, asset.text
    seed_shop_products(db_session)
    sync_catalog_from_legacy(db_session)
    return owner, organization["id"], workspace_id, asset.json(), headers


def _validated_analysis(**values) -> dict:
    return {
        "schema": ANALYSIS_SCHEMA,
        "validation_status": "VALIDATED",
        "algorithm": "geovision.environmental.test",
        "algorithm_version": "1.0.0",
        "confidence": 0.9,
        "metrics": {},
        **values,
    }


def _dataset(
    db_session,
    *,
    asset: Asset,
    name: str,
    dataset_type: str,
    captured_at: datetime,
    metadata: dict | None = None,
    provider_code: str = "geovision",
    crs: str = "EPSG:4326",
) -> Dataset:
    row = Dataset(
        id=str(uuid.uuid4()),
        company_id=asset.organization_id,
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        name=name,
        data_type=dataset_type,
        dataset_type=dataset_type,
        provider_code=provider_code,
        storage_provider="local",
        processing_level="DERIVED",
        quality_status="PASSED",
        status="ready",
        sector="ENVIRONMENTAL",
        capture_date=captured_at,
        crs=crs,
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
            provider_code=item["provider_code"],
            storage_provider="local",
            processing_level=item["processing_level"],
            quality_status="PASSED",
            status="ready",
            sector="ENVIRONMENTAL",
            capture_date=item["capture_date"],
            crs=item["crs"],
            resolution=10.0,
            resolution_unit="m",
            metadata_json="{}",
            provenance_json=json.dumps(item["provenance"]),
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

    for index, scene in enumerate(bundle["satellite_scenes"], start=1):
        dataset = datasets[scene["dataset_name"]]
        run = IntelligenceAcquisition(
            id=str(uuid.uuid4()),
            organization_id=asset.organization_id,
            workspace_id=asset.workspace_id,
            asset_id=asset.id,
            kind="SATELLITE",
            provider_code="copernicus",
            request_fingerprint=f"{index:064x}",
            request_json="{}",
            result_summary_json="{}",
            dataset_ids_json=json.dumps([dataset.id]),
            status="COMPLETED",
            idempotency_key=f"environmental-demo-satellite:{asset.id}:{index}",
            completed_at=scene["acquired_at"],
        )
        db_session.add(run)
        db_session.flush()
        db_session.add(
            SatelliteScene(
                id=str(uuid.uuid4()),
                organization_id=asset.organization_id,
                asset_id=asset.id,
                intelligence_acquisition_id=run.id,
                dataset_id=dataset.id,
                provider_code=scene["provider_code"],
                provider_reference=scene["provider_reference"],
                collection=scene["collection"],
                acquired_at=scene["acquired_at"],
                cloud_cover_percent=scene["cloud_cover_percent"],
                resolution_meters=scene["resolution_meters"],
                crs="EPSG:4326",
                bands_json=json.dumps(["B02", "B03", "B04", "B08"]),
                bbox_json=json.dumps([-3.72, 40.40, -3.68, 40.44]),
                coverage_geojson=json.dumps(scene["coverage"]),
                assets_json="{}",
                provenance_json=json.dumps(
                    {"source_name": "Copernicus", "fixture": True}
                ),
            )
        )

    weather_dataset = datasets["AEMET observed weather context"]
    weather_run = IntelligenceAcquisition(
        id=str(uuid.uuid4()),
        organization_id=asset.organization_id,
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        kind="WEATHER",
        provider_code="aemet",
        request_fingerprint="f" * 64,
        request_json="{}",
        result_summary_json="{}",
        dataset_ids_json=json.dumps([weather_dataset.id]),
        status="COMPLETED",
        idempotency_key=f"environmental-demo-weather:{asset.id}",
        completed_at=weather_dataset.capture_date,
    )
    db_session.add(weather_run)
    db_session.flush()
    for index, item in enumerate(bundle["weather"]):
        db_session.add(
            WeatherObservation(
                id=str(uuid.uuid4()),
                organization_id=asset.organization_id,
                asset_id=asset.id,
                intelligence_acquisition_id=weather_run.id,
                dataset_id=weather_dataset.id,
                provider_code="aemet",
                source_reference=f"demo-station-{index}",
                source_name="AEMET demo station",
                observed_at=weather_dataset.capture_date,
                metric=item["metric"],
                value=item["value"],
                unit=item["unit"],
                quality="observed",
                latitude=40.42,
                longitude=-3.70,
                distance_km=3.0,
                provenance_json=json.dumps({"source_name": "AEMET", "fixture": True}),
            )
        )

    site = Site(
        id=str(uuid.uuid4()),
        company_id=asset.organization_id,
        name="Environmental demo site",
        country="Spain",
        sector="environment",
    )
    db_session.add(site)
    db_session.flush()
    device = IotDevice(
        id=str(uuid.uuid4()),
        public_id=f"env-node-{uuid.uuid4().hex[:12]}",
        company_id=asset.organization_id,
        site_id=site.id,
        core_asset_id=asset.id,
        provider_code="geovision",
        provider_device_id=f"fixture-{uuid.uuid4().hex}",
        name="Calibrated environmental node",
        device_type="environmental_node",
        transport="mqtt",
        status="active",
        token_hash="0" * 64,
        secret_encrypted="fixture-ciphertext-not-a-secret",
        capabilities_json=json.dumps(["air_temperature"]),
        configuration_json="{}",
        connectivity_status="online",
        health_status="healthy",
        last_seen_at=weather_dataset.capture_date,
    )
    db_session.add(device)
    db_session.flush()
    db_session.add(
        TelemetryReading(
            id=str(uuid.uuid4()),
            device_id=device.id,
            company_id=asset.organization_id,
            site_id=site.id,
            core_asset_id=asset.id,
            message_id=f"demo-{uuid.uuid4().hex}",
            source="edge_replay",
            channel="air_temperature_c",
            numeric_value=25.8,
            unit="°C",
            quality="good",
            recorded_at=weather_dataset.capture_date,
            metadata_json=json.dumps({"calibrated": True, "fixture": True}),
        )
    )
    db_session.commit()
    return datasets


def test_environmental_registers_as_a_common_core_extension():
    assert definition.enabled_by_default is True
    assert definition.activation_phase == 29
    assert definition.routes[0].key == "sector.environmental"
    assert {
        "LAND_PARCEL",
        "FOREST",
        "HABITAT",
        "WETLAND",
        "WATER_BODY",
        "COASTAL_AREA",
        "RESTORATION_SITE",
        "PROTECTED_AREA",
        "ENVIRONMENTAL_SITE",
        "SITE",
    } == SUPPORTED_ASSET_TYPES
    assert {
        "SATELLITE_IMAGE",
        "MULTISPECTRAL_IMAGES",
        "ORTHOMOSAIC",
        "LAND_COVER_CLASSIFICATION",
        "THERMAL_IMAGES",
        "DSM",
        "DTM",
        "ENVIRONMENTAL_REFERENCE",
        "WEATHER_DATA",
        "TELEMETRY",
    }.issubset(SUPPORTED_DATASET_TYPES)
    registrations = calculator_registry.registrations("ENVIRONMENTAL")
    assert len(registrations) == len(KPI_DEFINITIONS)
    assert {item.definition.importance for item in registrations} == {
        KpiImportance.PRIMARY,
        KpiImportance.SECONDARY,
        KpiImportance.TECHNICAL,
    }
    assert rule_registry.registrations("ENVIRONMENTAL")[0].version == "1.0.0"
    assert "ENVIRONMENTAL" in report_context_registry.sectors()
    empty = EvaluationContext(
        asset_id="asset",
        sector="ENVIRONMENTAL",
        measured_at=datetime(2026, 9, 10, 8),
    )
    assert all(item.calculate(empty) is None for item in registrations)


def test_context_sources_and_ungated_candidates_never_become_environmental_facts(
    client, db_session
):
    _, _, _, asset_payload, headers = _workspace_asset(
        client, db_session, prefix="environment-context-only"
    )
    asset = db_session.get(Asset, asset_payload["id"])
    previous_weather = _dataset(
        db_session,
        asset=asset,
        name="Previous context weather",
        dataset_type="WEATHER_DATA",
        captured_at=datetime(2026, 9, 1, 8),
        provider_code="aemet",
    )
    injected = _validated_analysis(
        metrics={
            "vegetation_cover": 99,
            "vegetation_cover_change": 90,
            "land_cover_change_area": 9999,
            "ndvi_mean": 0.99,
            "ndvi_change": 1.9,
        },
        classification_evidence={
            "reviewed": True,
            "basis": "VALIDATED_LAND_COVER_CLASSIFICATION",
            "source_reference": "injected",
            "reference_version": "1",
            "class_schema_version": "1.0.0",
        },
        comparison_evidence={
            "current_dataset_id": "placeholder",
            "previous_dataset_id": previous_weather.id,
            "aligned": True,
            "same_crs": True,
            "method": "vendor.injected_change",
            "method_version": "1.0.0",
        },
        change_candidates=[
            {
                "id": "injected-change",
                "kind": "land_cover_change",
                "new": True,
                "area_ha": 9999,
            }
        ],
    )
    weather = _dataset(
        db_session,
        asset=asset,
        name="Injected weather analysis",
        dataset_type="WEATHER_DATA",
        captured_at=datetime(2026, 9, 2, 8),
        metadata={"environmental_analysis": injected},
        provider_code="aemet",
    )
    injected["comparison_evidence"]["current_dataset_id"] = weather.id
    weather.metadata_json = json.dumps({"environmental_analysis": injected})
    _dataset(
        db_session,
        asset=asset,
        name="Injected official analysis",
        dataset_type="ENVIRONMENTAL_REFERENCE",
        captured_at=datetime(2026, 9, 3, 8),
        metadata={"environmental_analysis": injected},
        provider_code="miteco",
    )
    _dataset(
        db_session,
        asset=asset,
        name="Uncalibrated thermal candidates",
        dataset_type="THERMAL_IMAGES",
        captured_at=datetime(2026, 9, 4, 8),
        metadata={
            "environmental_analysis": _validated_analysis(
                thermal_hotspots=[
                    {"id": "fake-hotspot", "new": True, "confidence": 0.99}
                ]
            )
        },
    )
    db_session.commit()

    context = build_source_context(
        db_session, asset=asset, as_of=datetime(2026, 9, 10, 8)
    )
    assert context.evaluation.measurements == {}
    assert context.evaluation.metadata["findings"] == ()
    assert context.availability["official_environmental_context"] is True
    assert context.availability["validated_analysis_count"] == 1

    evaluated = client.post(
        f"/assets/{asset.id}/environmental/evaluate",
        headers=headers,
        json={"as_of": "2026-09-10T08:00:00"},
    )
    assert evaluated.status_code == 200, evaluated.text
    assert evaluated.json()["kpi_value_ids"] == []
    assert evaluated.json()["observation_ids"] == []
    assert all(item["availability"] == "NO_DATA" for item in evaluated.json()["kpis"])


def test_satellite_change_requires_linked_drone_verification_and_reviewed_area_inventory(
    client, db_session
):
    _, _, _, asset_payload, headers = _workspace_asset(
        client, db_session, prefix="environment-satellite-first", asset_type="FOREST"
    )
    asset = db_session.get(Asset, asset_payload["id"])
    baseline = _dataset(
        db_session,
        asset=asset,
        name="Satellite baseline",
        dataset_type="SATELLITE_IMAGE",
        provider_code="copernicus",
        captured_at=datetime(2026, 8, 1, 8),
    )
    current = _dataset(
        db_session,
        asset=asset,
        name="Satellite change",
        dataset_type="SATELLITE_IMAGE",
        provider_code="copernicus",
        captured_at=datetime(2026, 9, 1, 8),
    )
    current.metadata_json = json.dumps(
        {
            "environmental_analysis": _validated_analysis(
                metrics={"land_cover_change_area": 3.2},
                classification_evidence={
                    "reviewed": True,
                    "basis": "VALIDATED_LAND_COVER_CLASSIFICATION",
                    "source_reference": "satellite-review",
                    "reference_version": "2",
                    "class_schema_version": "1.0.0",
                },
                comparison_evidence={
                    "current_dataset_id": current.id,
                    "previous_dataset_id": baseline.id,
                    "aligned": True,
                    "same_crs": True,
                    "method": "geovision.environmental.satellite_change",
                    "method_version": "1.0.0",
                },
                change_candidates=[
                    {
                        "id": "satellite-zone-1",
                        "kind": "land_cover_change",
                        "new": True,
                        "area_ha": 3.2,
                        "severity": "WARNING",
                        "confidence": 0.83,
                    },
                    {
                        "id": "satellite-zone-2",
                        "kind": "land_cover_change",
                        "new": True,
                        "area_ha": 1.0,
                        "severity": "WATCH",
                        "confidence": 0.8,
                    },
                ],
                affected_area_evidence={
                    "reviewed": True,
                    "non_overlapping": False,
                    "inventory_reference": "overlapping-inventory",
                    "method": "geovision.environmental.area_inventory",
                    "method_version": "1.0.0",
                    "candidate_ids": ["satellite-zone-1", "satellite-zone-2"],
                },
            )
        }
    )
    _dataset(
        db_session,
        asset=asset,
        name="Later unrelated drone survey",
        dataset_type="ORTHOMOSAIC",
        captured_at=datetime(2026, 9, 2, 8),
        metadata={
            "environmental_analysis": _validated_analysis(
                classification_evidence={
                    "reviewed": True,
                    "basis": "VALIDATED_VEGETATION_CLASSIFICATION",
                    "source_reference": "unrelated-flight",
                    "reference_version": "1",
                    "class_schema_version": "1.0.0",
                }
            )
        },
    )
    db_session.commit()

    context = build_source_context(
        db_session, asset=asset, as_of=datetime(2026, 9, 10, 8)
    )
    assert context.availability["current_drone_verification"] is False
    assert context.evaluation.measurements["land_cover_change_area"] == 3.2
    assert "affected_area" not in context.evaluation.measurements

    evaluated = client.post(
        f"/assets/{asset.id}/environmental/evaluate",
        headers=headers,
        json={"as_of": "2026-09-10T08:00:00"},
    )
    assert evaluated.status_code == 200, evaluated.text
    actions = client.get(f"/assets/{asset.id}/actions", headers=headers).json()["items"]
    targeted = [
        item
        for item in actions
        if item["recommended_catalog_item_id"] == "prod_env_targeted_drone_verification"
    ]
    assert len(targeted) == 2
    assert all("before assigning a cause" in item["description"] for item in targeted)
    affected = {item["definition"]["key"]: item for item in evaluated.json()["kpis"]}[
        "affected_area"
    ]
    assert affected["availability"] == "NO_DATA"
    assert affected["status"] == "UNKNOWN"


def test_validated_environmental_flow_uses_common_lifecycle_and_retains_provenance(
    client, db_session, tmp_path
):
    owner, organization_id, workspace_id, asset_payload, headers = _workspace_asset(
        client, db_session, prefix="environment-full"
    )
    asset = db_session.get(Asset, asset_payload["id"])
    order = Order(
        user_id=owner.id,
        company_id=organization_id,
        organization_id=organization_id,
        workspace_id=workspace_id,
        order_number=f"GV-P29-{uuid.uuid4().hex[:10].upper()}",
        order_type="SERVICE",
        status="confirmed",
        fulfilment_status="CONFIRMED",
        payment_status="PENDING",
        currency="EUR",
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
            "title": "Targeted environmental verification",
            "drone_details": {
                "payload_reference": "RGB-MULTISPECTRAL-THERMAL",
                "mission_requirements": {"orthomosaic": True, "thermal": True},
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
        bundle=demo_environmental_bundle(),
    )
    current_drone = datasets["Current targeted drone orthomosaic"]
    current_drone.mission_id = acquisition.id
    db_session.commit()
    assert current_drone.mission_id == acquisition.id
    assert order.id in {
        item["id"] for item in client.get("/orders", headers=headers).json()
    }
    mission_history = client.get(
        f"/missions/assets/{asset.id}/history", headers=headers
    )
    assert mission_history.status_code == 200, mission_history.text
    assert acquisition.id in {item["id"] for item in mission_history.json()}

    capabilities = client.get("/sectors/environmental/capabilities", headers=headers)
    assert capabilities.status_code == 200, capabilities.text
    assert capabilities.json()["enabled"] is True
    assert capabilities.json()["analysis_schema"] == ANALYSIS_SCHEMA

    evaluated = client.post(
        f"/assets/{asset.id}/environmental/evaluate",
        headers=headers,
        json={"as_of": "2026-09-10T08:00:00"},
    )
    assert evaluated.status_code == 200, evaluated.text
    body = evaluated.json()
    assert (
        body["source_availability"]
        | {
            "satellite": True,
            "current_drone_verification": True,
            "weather": True,
            "iot": True,
            "official_environmental_context": True,
            "historical_comparison": True,
            "paired_change": True,
            "paired_surface": True,
        }
        == body["source_availability"]
    )
    kpis = {item["definition"]["key"]: item for item in body["kpis"]}
    assert kpis["affected_area"]["current"] == 4.2
    assert kpis["vegetation_cover"]["current"] == 64
    assert kpis["vegetation_cover_change"]["current"] == -9
    assert kpis["land_cover_change_area"]["current"] == 4.2
    assert kpis["reforestation_cover"]["current"] == 63
    assert kpis["reforestation_change"]["current"] == -9
    assert kpis["terrain_change_area"]["current"] == 0.7
    assert kpis["thermal_hotspot_count"]["current"] == 1
    assert kpis["thermal_hotspot_count"]["status"] == "WATCH"
    # The later RGB orthomosaic cannot masquerade as a vegetation-index product.
    assert kpis["ndvi_mean"]["current"] == 0.52
    assert kpis["ndvi_change"]["current"] == -0.09
    assert len(body["observation_ids"]) == 4
    assert len(body["action_ids"]) == 4

    counts = (
        db_session.query(KpiValue).filter(KpiValue.asset_id == asset.id).count(),
        db_session.query(Observation).filter(Observation.asset_id == asset.id).count(),
        db_session.query(Action).filter(Action.asset_id == asset.id).count(),
    )
    replayed = client.post(
        f"/assets/{asset.id}/environmental/evaluate",
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
    observations = client.get(
        f"/assets/{asset.id}/observations", headers=headers
    ).json()["items"]
    assert len(observations) == 4
    assert all(item["validation_status"] == "NEEDS_REVIEW" for item in observations)
    assert all(item["value"]["cause"] is None for item in observations)
    assert all(item["value"]["diagnosis"] is None for item in observations)
    assert {item["type"] for item in observations} == {
        "LAND_COVER_CHANGE_CANDIDATE",
        "REFORESTATION_CHANGE_CANDIDATE",
        "TERRAIN_CHANGE_CANDIDATE",
        "THERMAL_HOTSPOT_CANDIDATE",
    }
    assert not any("EROSION" in item["type"] for item in observations)
    actions = client.get(f"/assets/{asset.id}/actions", headers=headers).json()["items"]
    assert {item["recommended_catalog_item_id"] for item in actions} == {
        "prod_env_reforestation_monitoring",
        "prod_env_specialist_review",
    }
    assert not any(
        item["recommended_catalog_item_id"] == "prod_env_targeted_drone_verification"
        for item in actions
    )
    combined = " ".join(
        f"{item['title']} {item['description']}" for item in actions
    ).lower()
    assert not any(
        term in combined for term in ("confirmed erosion", "caused by", "wildfire")
    )

    comparisons = client.get(
        f"/assets/{asset.id}/environmental/comparisons", headers=headers
    )
    assert comparisons.status_code == 200, comparisons.text
    comparison_items = {item["kind"]: item for item in comparisons.json()["items"]}
    assert comparison_items["SATELLITE_2D"]["availability"] == "AVAILABLE"
    assert comparison_items["DRONE_2D"]["availability"] == "AVAILABLE"
    assert comparison_items["TERRAIN_3D"]["availability"] == "AVAILABLE"
    assert comparison_items["THERMAL_2D"]["availability"] == "NO_DATA"
    assert all(
        "no causal" in item["interpretation"] for item in comparison_items.values()
    )

    layers = client.get(f"/assets/{asset.id}/environmental/map-layers", headers=headers)
    assert layers.status_code == 200, layers.text
    layer_items = layers.json()["items"]
    assert {
        "ASSET_BOUNDARY",
        "SATELLITE_IMAGE",
        "ORTHOMOSAIC",
        "DTM",
        "THERMAL_IMAGES",
        "ENVIRONMENTAL_REFERENCE",
        "OBSERVATION_ZONE",
    }.issubset({item["kind"] for item in layer_items})
    assert all(
        not str(item.get("data_ref", "")).startswith("http") for item in layer_items
    )
    official = next(
        item for item in layer_items if item["kind"] == "ENVIRONMENTAL_REFERENCE"
    )
    assert official["provenance"]["official_source"] is True
    assert official["provenance"]["license_id"] == "MITECO-GENERAL-REUSE-CONDITIONS"
    assert official["provenance"]["reuse_notice_url"].endswith("/aviso-legal.html")
    assert official["provenance"]["no_endorsement"] is True
    assert official["provenance"]["context_only"] is True
    assert official["provenance"]["measurements_authoritative"] is False
    assert official["provenance"]["diagnostic_authority"] is False
    assert official["provenance"]["geographic_scope"] == "Spain"
    assert official["provenance"]["dataset_updated_at"] == "2026-08-01"
    assert "Ministerio" in official["provenance"]["attribution"]
    assert all(
        item["availability"] == "UNKNOWN"
        for item in layer_items
        if item["kind"] == "OBSERVATION_ZONE"
    )

    context = client.get(
        f"/assets/{asset.id}/environmental/report-context", headers=headers
    )
    assert context.status_code == 200, context.text
    assert context.json()["schema"] == "geovision.environmental.report-context.v1"
    official_context = context.json()["environmental_context"]["official_layers"][0]
    assert official_context["dataset_id"] == datasets["MITECO biodiversity context"].id
    assert official_context["provenance"]["official_source"] is True
    assert official_context["provenance"]["context_only"] is True
    assert official_context["provenance"]["diagnostic_authority"] is False
    assert any("No ecological" in item for item in context.json()["limitations"])

    storage = StorageService(
        LocalObjectStorageProvider(
            root=tmp_path,
            public_base_url="http://testserver",
            signing_secret="test-environmental-report-signing-key",
        )
    )
    report_row, created = generate_report(
        db_session,
        actor=owner,
        asset=asset,
        data=ReportGenerateRequest(
            report_type="ENVIRONMENTAL_INTELLIGENCE",
            acquisition_id=acquisition.id,
            idempotency_key=f"environment-report-{uuid.uuid4()}",
        ),
        storage=storage,
    )
    db_session.commit()
    assert created is True
    assert report_row.asset_id == asset.id
    assert report_row.acquisition_id == acquisition.id
    report_context = json.loads(report_row.context_json)
    assert report_context["asset"]["sector"] == "ENVIRONMENTAL"
    assert any("No ecological" in item for item in report_context["limitations"])
    assert db_session.query(Report).filter(Report.asset_id == asset.id).count() == 1


def test_permissions_tenant_boundaries_and_feature_flag_are_independent(
    client, db_session
):
    owner, organization_id, workspace_id, asset, headers = _workspace_asset(
        client, db_session, prefix="environment-isolation"
    )
    viewer = _user(db_session, "environment-viewer")
    membership = client.post(
        f"/organizations/{organization_id}/members",
        headers=headers,
        json={"email": viewer.email, "user_id": viewer.id, "role": "viewer"},
    )
    assert membership.status_code == 201, membership.text
    viewer_headers = _headers(viewer, workspace_id)
    assert (
        client.get(
            f"/assets/{asset['id']}/environmental/report-context",
            headers=viewer_headers,
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/assets/{asset['id']}/environmental/evaluate",
            headers=viewer_headers,
            json={},
        ).status_code
        == 403
    )

    second = client.post(
        f"/organizations/{organization_id}/workspaces",
        headers=headers,
        json={
            "name": "Environmental disabled workspace",
            "sector_focus": "environment",
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
            "sector": "ENVIRONMENTAL",
            "asset_type": "WETLAND",
            "name": "Disabled-workspace wetland",
        },
    )
    assert disabled_asset.status_code == 201, disabled_asset.text
    capabilities = client.get(
        "/sectors/environmental/capabilities", headers=disabled_headers
    )
    assert capabilities.status_code == 200
    assert capabilities.json()["enabled"] is False
    assert (
        client.get(
            f"/assets/{disabled_asset.json()['id']}/environmental/map-layers",
            headers=disabled_headers,
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/assets/{asset['id']}/environmental/report-context",
            headers=disabled_headers,
        ).status_code
        == 404
    )
    assert (
        client.get("/sectors/environmental/capabilities", headers=headers).json()[
            "enabled"
        ]
        is True
    )

    _, _, _, _, outsider_headers = _workspace_asset(
        client, db_session, prefix="environment-outsider"
    )
    hidden = client.get(
        f"/assets/{asset['id']}/environmental/report-context",
        headers=outsider_headers,
    )
    assert hidden.status_code == 404
