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
    DeviceAssignment,
    IotAlert,
    IotAlertRule,
    IotDevice,
    KpiValue,
    Observation,
    Order,
    Report,
    Site,
    TelemetryReading,
    User,
)
from app.modules.analytics.domain import (
    EvaluationContext,
    calculator_registry,
    rule_registry,
)
from app.modules.assets.domain import ASSET_TYPE_REGISTRY
from app.modules.catalog.services import sync_catalog_from_legacy
from app.modules.reports.ports import report_context_registry
from app.modules.reports.schemas import ReportGenerateRequest
from app.modules.reports.services import generate_report
from app.sectors.ports import definition
from app.sectors.ports.domain import (
    KPI_DEFINITIONS,
    SUPPORTED_ASSET_TYPES,
    SUPPORTED_DATASET_TYPES,
)
from app.sectors.ports.fixtures import (
    demo_ports_bundle,
    resolve_demo_dataset_references,
)
from app.sectors.ports.services import (
    ANALYSIS_SCHEMA,
    _compatible_pair,
    build_source_context,
)
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


def _workspace(
    client,
    db_session,
    *,
    prefix: str,
    enabled: bool = True,
) -> tuple[User, str, str, dict[str, str]]:
    owner = _user(db_session, f"{prefix}-owner")
    created = client.post(
        "/organizations",
        headers=_headers(owner),
        json={
            "name": f"{prefix}-{uuid.uuid4().hex[:8]}",
            "country": "Portugal",
            "timezone": "Europe/Lisbon",
            "workspace": {
                "name": f"{prefix} workspace",
                "customer_type": "enterprise",
                "sector_focus": "industry",
                "modules_enabled": ["assets", "analytics", "reports"]
                + (["ports"] if enabled else []),
            },
        },
    )
    assert created.status_code == 201, created.text
    organization = created.json()
    workspace_id = organization["workspaces"][0]["id"]
    return owner, organization["id"], workspace_id, _headers(owner, workspace_id)


def _asset(
    client,
    *,
    headers: dict[str, str],
    name: str,
    asset_type: str,
    parent_asset_id: str | None = None,
    cadence_days: int | None = None,
) -> dict:
    metadata = {}
    if cadence_days is not None:
        metadata["inspection_cadence_days"] = cadence_days
    response = client.post(
        "/assets",
        headers=headers,
        json={
            "sector": "PORTS_LOGISTICS",
            "asset_type": asset_type,
            "name": name,
            "parent_asset_id": parent_asset_id,
            "metadata": metadata,
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-8.881, 37.952],
                        [-8.878, 37.952],
                        [-8.878, 37.955],
                        [-8.881, 37.955],
                        [-8.881, 37.952],
                    ]
                ],
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _inspection(
    asset_id: str,
    reference: str,
    *,
    modality: str = "RGB",
    registration_reference: str = "registration-v1",
) -> dict:
    return {
        "reviewed": True,
        "asset_id": asset_id,
        "inspection_reference": reference,
        "modality": modality,
        "capture_mode": modality,
        "crs": "EPSG:25830",
        "method": "geovision.ports.test_inspection",
        "method_version": "1.0.0",
        "registration_reference": registration_reference,
        "registration_method": "geovision.ports.test_registration",
        "registration_version": "1.0.0",
    }


def _analysis(
    asset_id: str,
    reference: str,
    *,
    modality: str = "RGB",
    **values,
) -> dict:
    return {
        "schema": ANALYSIS_SCHEMA,
        "validation_status": "VALIDATED",
        "algorithm": "geovision.ports.test",
        "algorithm_version": "1.0.0",
        "confidence": 0.9,
        "metrics": {},
        "inspection_evidence": _inspection(asset_id, reference, modality=modality),
        **values,
    }


def _pair(current: Dataset, previous: Dataset, *, crs: str = "EPSG:25830") -> dict:
    current_analysis = json.loads(current.metadata_json)["ports_analysis"]
    previous_analysis = json.loads(previous.metadata_json)["ports_analysis"]
    return {
        "reviewed": True,
        "current_dataset_id": current.id,
        "previous_dataset_id": previous.id,
        "current_inspection_reference": current_analysis["inspection_evidence"][
            "inspection_reference"
        ],
        "previous_inspection_reference": previous_analysis["inspection_evidence"][
            "inspection_reference"
        ],
        "aligned": True,
        "crs": crs,
        "registration_reference": "registration-v1",
        "method": "geovision.ports.test_comparison",
        "method_version": "1.0.0",
    }


def _inventory(asset_id: str, *, kind: str, candidates: list[dict]) -> dict:
    return {
        "reviewed": True,
        "complete_for_dataset": True,
        "asset_id": asset_id,
        "modality": kind.upper(),
        "inventory_reference": f"{kind}-inventory-{uuid.uuid4().hex[:8]}",
        "inventory_scope": "COMPARISON",
        "method": "geovision.ports.test_inventory",
        "method_version": "1.0.0",
        "candidates": candidates,
    }


def _dataset(
    db_session,
    *,
    asset: Asset,
    name: str,
    dataset_type: str,
    captured_at: datetime,
    analysis: dict | None = None,
    quality_status: str = "PASSED",
    status: str = "ready",
    crs: str = "EPSG:25830",
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
        sector="PORTS_LOGISTICS",
        capture_date=captured_at,
        crs=crs,
        metadata_json=json.dumps({"ports_analysis": analysis} if analysis else {}),
        provenance_json="{}",
        created_at=captured_at,
        updated_at=captured_at,
        processed_at=captured_at,
    )
    db_session.add(row)
    db_session.flush()
    return row


def _materialize_bundle(
    db_session,
    *,
    asset: Asset,
    bundle: dict,
    mission_ids: dict[str, str],
) -> dict[str, Dataset]:
    rows: dict[str, Dataset] = {}
    for item in bundle["datasets"]:
        row = Dataset(
            id=str(uuid.uuid4()),
            company_id=asset.organization_id,
            workspace_id=asset.workspace_id,
            asset_id=asset.id,
            mission_id=mission_ids[item["inspection"]],
            name=item["name"],
            data_type=item["dataset_type"],
            dataset_type=item["dataset_type"],
            source="demo_fixture",
            provider_code="geovision",
            storage_provider="local",
            processing_level=item["processing_level"],
            quality_status="PASSED",
            status="ready",
            sector="PORTS_LOGISTICS",
            capture_date=item["capture_date"],
            crs=item["crs"],
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


def test_ports_registers_independent_common_core_vocabulary_and_rules():
    assert definition.enabled_by_default is True
    assert definition.activation_phase == 31
    assert definition.routes[0].key == "sector.ports_logistics"
    assert definition.routes[0].order == 73
    assert SUPPORTED_ASSET_TYPES == {
        "BERTH",
        "CRANE",
        "EQUIPMENT",
        "GANTRY",
        "INSPECTION_ZONE",
        "LOADING_AREA",
        "PORT",
        "QUAY",
        "ROOF",
        "STRUCTURE",
        "TANK",
        "TERMINAL",
        "WAREHOUSE",
    }
    assert SUPPORTED_ASSET_TYPES.issubset(ASSET_TYPE_REGISTRY)
    assert SUPPORTED_DATASET_TYPES == {
        "AIS_DATA",
        "DSM",
        "DTM",
        "MESH_3D",
        "ORTHOMOSAIC",
        "POINT_CLOUD",
        "RGB_IMAGES",
        "THERMAL_IMAGES",
        "WEATHER_DATA",
    }
    owners = {
        identifier: [
            sector.name
            for sector in SECTOR_MODULES
            if identifier in sector.legacy_identifiers
        ]
        for identifier in {
            item for sector in SECTOR_MODULES for item in sector.legacy_identifiers
        }
    }
    assert all(len(value) == 1 for value in owners.values())
    assert owners["industry"] == ["industry_energy_utilities"]
    assert len(calculator_registry.registrations("PORTS_LOGISTICS")) == len(
        KPI_DEFINITIONS
    )
    assert "PORTS_LOGISTICS" in report_context_registry.sectors()
    empty = EvaluationContext(
        asset_id="asset",
        sector="PORTS_LOGISTICS",
        measured_at=datetime(2026, 9, 10, 8),
    )
    assert all(
        registration.calculate(empty) is None
        for registration in calculator_registry.registrations("PORTS_LOGISTICS")
    )
    rule = rule_registry.registrations("PORTS_LOGISTICS")[0]
    outcome = rule.evaluate(
        EvaluationContext(
            asset_id="tank",
            sector="PORTS_LOGISTICS",
            measured_at=datetime(2026, 9, 10, 8),
            metadata={
                "asset_type": "TANK",
                "source_availability": {
                    "inspection_evidence": "UNKNOWN",
                    "thermal_inventory": "UNKNOWN",
                    "comparison_3d": "NO_DATA",
                    "sensor_assignment": "NOT_CONFIGURED",
                    "reinspection": "NOT_CONFIGURED",
                    "condition_summary": "UNKNOWN",
                },
                "findings": ({"kind": "visual", "key": "candidate"},),
            },
        ),
        {},
    )
    assert {item.recommended_catalog_item_id for item in outcome.actions} == {
        "prod_ports_3d_mapping",
        "prod_ports_monitoring_plan",
        "prod_ports_sensor_installation",
        "prod_ports_specialist_review",
        "prod_ports_thermal_inspection",
        "prod_ports_visual_inspection",
    }


def test_ports_fail_closed_on_unversioned_unreviewed_or_unregistered_evidence(
    client, db_session
):
    _, _, _, headers = _workspace(client, db_session, prefix="ports-gates")
    payload = _asset(
        client,
        headers=headers,
        name="Gantry evidence gate",
        asset_type="GANTRY",
    )
    asset = db_session.get(Asset, payload["id"])
    previous = _dataset(
        db_session,
        asset=asset,
        name="Previous visual",
        dataset_type="RGB_IMAGES",
        captured_at=datetime(2026, 8, 1, 8),
        analysis=_analysis(asset.id, "previous"),
    )
    current = _dataset(
        db_session,
        asset=asset,
        name="Current forged visual",
        dataset_type="RGB_IMAGES",
        captured_at=datetime(2026, 9, 1, 8),
        analysis=_analysis(asset.id, "current"),
    )
    forged = json.loads(current.metadata_json)["ports_analysis"]
    forged["comparison_evidence"] = _pair(current, previous, crs="EPSG:4326")
    forged["candidate_inventory"] = _inventory(
        asset.id,
        kind="visual",
        candidates=[
            {
                "candidate_reference": "forged-new-candidate",
                "new": True,
                "label": "Must not be surfaced",
            }
        ],
    )
    forged["specialist_condition_evidence"] = {
        "specialist_validated": True,
        "review_authority": "UNVERIFIED_REVIEWER",
        "review_reference": "forged-review",
        "summary_code": "NO_MATERIAL_CHANGE_REPORTED",
        "method": "geovision.ports.condition",
        "method_version": "1.0.0",
    }
    current.metadata_json = json.dumps({"ports_analysis": forged})
    bad_thermal = _dataset(
        db_session,
        asset=asset,
        name="Uncalibrated thermal",
        dataset_type="THERMAL_IMAGES",
        captured_at=datetime(2026, 9, 2, 8),
        analysis={
            **_analysis(asset.id, "thermal", modality="THERMAL"),
            "candidate_inventory": _inventory(
                asset.id,
                kind="thermal",
                candidates=[
                    {
                        "candidate_reference": "ungated-hotspot",
                        "new": True,
                        "label": "Ungated thermal response",
                    }
                ],
            ),
        },
    )
    invalid_version = _dataset(
        db_session,
        asset=asset,
        name="Invalid algorithm version",
        dataset_type="RGB_IMAGES",
        captured_at=datetime(2026, 9, 3, 8),
        analysis={
            **_analysis(asset.id, "bad-version"),
            "algorithm_version": "bad version",
        },
    )
    failed = _dataset(
        db_session,
        asset=asset,
        name="Failed quality",
        dataset_type="RGB_IMAGES",
        captured_at=datetime(2026, 9, 4, 8),
        analysis=_analysis(asset.id, "failed"),
        quality_status="FAILED",
    )
    db_session.commit()

    context = build_source_context(
        db_session, asset=asset, as_of=datetime(2026, 9, 10, 8)
    )
    assert "new_visual_candidate_count" not in context.evaluation.measurements
    assert "new_thermal_candidate_count" not in context.evaluation.measurements
    assert "condition_summary" not in context.evaluation.measurements
    assert context.evaluation.metadata["findings"] == ()
    assert context.availability["condition_summary"] == "UNKNOWN"
    assert bad_thermal.id in context.evidence["validated_analysis_dataset_ids"]
    assert invalid_version.id not in context.evidence["validated_analysis_dataset_ids"]
    assert failed.id not in context.evidence["validated_analysis_dataset_ids"]


def test_latest_empty_candidate_inventory_replaces_older_candidate_batch(
    client, db_session
):
    _, _, _, headers = _workspace(client, db_session, prefix="ports-inventory")
    payload = _asset(
        client,
        headers=headers,
        name="Quay inspection zone",
        asset_type="INSPECTION_ZONE",
    )
    asset = db_session.get(Asset, payload["id"])
    previous = _dataset(
        db_session,
        asset=asset,
        name="Baseline",
        dataset_type="RGB_IMAGES",
        captured_at=datetime(2026, 7, 1, 8),
        analysis=_analysis(asset.id, "baseline"),
    )
    middle = _dataset(
        db_session,
        asset=asset,
        name="Middle inspection",
        dataset_type="RGB_IMAGES",
        captured_at=datetime(2026, 8, 1, 8),
        analysis=_analysis(asset.id, "middle"),
    )
    middle_analysis = json.loads(middle.metadata_json)["ports_analysis"]
    middle_analysis["comparison_evidence"] = _pair(middle, previous)
    middle_analysis["candidate_inventory"] = _inventory(
        asset.id,
        kind="visual",
        candidates=[
            {
                "candidate_reference": "old-new-area",
                "new": True,
                "label": "Older candidate",
                "confidence": 0.8,
            }
        ],
    )
    middle.metadata_json = json.dumps({"ports_analysis": middle_analysis})
    latest = _dataset(
        db_session,
        asset=asset,
        name="Latest inspection",
        dataset_type="RGB_IMAGES",
        captured_at=datetime(2026, 9, 1, 8),
        analysis=_analysis(asset.id, "latest"),
    )
    latest_analysis = json.loads(latest.metadata_json)["ports_analysis"]
    latest_analysis["comparison_evidence"] = _pair(latest, middle)
    latest_analysis["candidate_inventory"] = _inventory(
        asset.id, kind="visual", candidates=[]
    )
    latest.metadata_json = json.dumps({"ports_analysis": latest_analysis})
    db_session.commit()

    context = build_source_context(
        db_session, asset=asset, as_of=datetime(2026, 9, 10, 8)
    )
    assert context.evaluation.measurements["new_visual_candidate_count"] == 0
    assert context.evaluation.metadata["findings"] == ()


def test_ports_comparison_rejects_cross_scope_quality_modality_registration_and_time(
    client, db_session
):
    _, _, _, headers = _workspace(client, db_session, prefix="ports-pair-gates")
    asset_payload = _asset(
        client,
        headers=headers,
        name="Comparison gantry",
        asset_type="GANTRY",
    )
    asset = db_session.get(Asset, asset_payload["id"])

    def pair_rows(
        label: str,
        *,
        previous_type: str = "RGB_IMAGES",
        previous_modality: str = "RGB",
        previous_crs: str = "EPSG:25830",
        previous_registration: str = "registration-v1",
        previous_at: datetime = datetime(2026, 8, 1, 8),
        current_at: datetime = datetime(2026, 9, 1, 8),
    ) -> tuple[Dataset, Dataset, dict]:
        previous = _dataset(
            db_session,
            asset=asset,
            name=f"{label} previous",
            dataset_type=previous_type,
            captured_at=previous_at,
            crs=previous_crs,
            analysis={
                **_analysis(asset.id, f"{label}-previous", modality=previous_modality),
                "inspection_evidence": _inspection(
                    asset.id,
                    f"{label}-previous",
                    modality=previous_modality,
                    registration_reference=previous_registration,
                ),
            },
        )
        current = _dataset(
            db_session,
            asset=asset,
            name=f"{label} current",
            dataset_type="RGB_IMAGES",
            captured_at=current_at,
            analysis=_analysis(asset.id, f"{label}-current"),
        )
        analysis = json.loads(current.metadata_json)["ports_analysis"]
        analysis["comparison_evidence"] = _pair(current, previous)
        current.metadata_json = json.dumps({"ports_analysis": analysis})
        return previous, current, analysis

    previous, current, analysis = pair_rows("valid")
    assert (
        _compatible_pair(
            current, analysis, {previous.id: previous, current.id: current}
        )
        is previous
    )

    previous, current, analysis = pair_rows("failed-quality")
    previous.quality_status = "FAILED"
    assert (
        _compatible_pair(
            current, analysis, {previous.id: previous, current.id: current}
        )
        is None
    )

    previous, current, analysis = pair_rows("unversioned")
    previous_analysis = json.loads(previous.metadata_json)["ports_analysis"]
    previous_analysis["algorithm_version"] = "invalid version"
    previous.metadata_json = json.dumps({"ports_analysis": previous_analysis})
    assert (
        _compatible_pair(
            current, analysis, {previous.id: previous, current.id: current}
        )
        is None
    )

    previous, current, analysis = pair_rows(
        "wrong-modality",
        previous_type="THERMAL_IMAGES",
        previous_modality="THERMAL",
    )
    assert (
        _compatible_pair(
            current, analysis, {previous.id: previous, current.id: current}
        )
        is None
    )

    previous, current, analysis = pair_rows("wrong-crs", previous_crs="EPSG:4326")
    assert (
        _compatible_pair(
            current, analysis, {previous.id: previous, current.id: current}
        )
        is None
    )

    previous, current, analysis = pair_rows(
        "wrong-registration", previous_registration="different-registration"
    )
    assert (
        _compatible_pair(
            current, analysis, {previous.id: previous, current.id: current}
        )
        is None
    )

    previous, current, analysis = pair_rows(
        "nonchronological",
        previous_at=datetime(2026, 9, 2, 8),
        current_at=datetime(2026, 9, 1, 8),
    )
    assert (
        _compatible_pair(
            current, analysis, {previous.id: previous, current.id: current}
        )
        is None
    )

    previous, current, analysis = pair_rows("cross-asset")
    original_asset_id = previous.asset_id
    previous.asset_id = str(uuid.uuid4())
    assert (
        _compatible_pair(
            current, analysis, {previous.id: previous, current.id: current}
        )
        is None
    )
    previous.asset_id = original_asset_id

    previous, current, analysis = pair_rows("cross-workspace")
    original_workspace_id = previous.workspace_id
    previous.workspace_id = str(uuid.uuid4())
    assert (
        _compatible_pair(
            current, analysis, {previous.id: previous, current.id: current}
        )
        is None
    )
    previous.workspace_id = original_workspace_id

    previous, current, analysis = pair_rows("cross-tenant")
    original_company_id = previous.company_id
    previous.company_id = str(uuid.uuid4())
    assert (
        _compatible_pair(
            current, analysis, {previous.id: previous, current.id: current}
        )
        is None
    )
    previous.company_id = original_company_id
    db_session.rollback()


def test_ports_official_and_customer_context_alerts_are_context_only(
    client, db_session
):
    _, _, _, headers = _workspace(client, db_session, prefix="ports-context")
    payload = _asset(
        client,
        headers=headers,
        name="Port context asset",
        asset_type="PORT",
    )
    asset = db_session.get(Asset, payload["id"])

    def context_analysis(category: str, source_kind: str, label: str) -> dict:
        return {
            "schema": ANALYSIS_SCHEMA,
            "validation_status": "VALIDATED",
            "algorithm": "geovision.ports.context_normalization",
            "algorithm_version": "1.0.0",
            "confidence": 0.88,
            "metrics": {
                # These values are intentionally ignored by the context-only gate.
                "condition_summary": "HEALTHY",
                "new_visual_candidate_count": 0,
            },
            "context_evidence": {
                "reviewed": True,
                "source_kind": source_kind,
                "source_reference": f"{category}-source-v1",
                "terms_reference": f"{category}-terms-v1",
                "retrieved_at": "2026-09-10T07:00:00Z",
                "method": "geovision.ports.context_normalization",
                "method_version": "1.0.0",
            },
            "context_alerts": [
                {
                    "alert_reference": f"{category}-alert-1",
                    "category": category,
                    "status": "ACTIVE",
                    "event_at": "2026-09-10T06:00:00Z",
                    "label": label,
                    "severity": "WATCH",
                }
            ],
        }

    _dataset(
        db_session,
        asset=asset,
        name="Official environmental context",
        dataset_type="WEATHER_DATA",
        captured_at=datetime(2026, 9, 10, 7),
        analysis=context_analysis(
            "environmental", "OFFICIAL_ENVIRONMENTAL_FEED", "Wind context alert"
        ),
    )
    _dataset(
        db_session,
        asset=asset,
        name="Optional maritime context",
        dataset_type="AIS_DATA",
        captured_at=datetime(2026, 9, 10, 7),
        analysis=context_analysis(
            "operational", "OFFICIAL_MARITIME_FEED", "Traffic context alert"
        ),
    )
    db_session.commit()

    context = build_source_context(
        db_session, asset=asset, as_of=datetime(2026, 9, 10, 8)
    )
    assert context.evaluation.measurements["environmental_alert_count"] == 1
    assert context.evaluation.measurements["operational_alert_count"] == 1
    assert "condition_summary" not in context.evaluation.measurements
    assert "new_visual_candidate_count" not in context.evaluation.measurements
    assert {item["kind"] for item in context.evaluation.metadata["findings"]} == {
        "environmental_alert",
        "operational_alert",
    }
    assert all(
        item["provenance"]["context_only"] is True
        for item in context.evaluation.metadata["findings"]
    )


def test_ports_iot_context_uses_assignments_and_snapshot_history(client, db_session):
    _, organization_id, workspace_id, headers = _workspace(
        client, db_session, prefix="ports-iot"
    )
    terminal_payload = _asset(
        client, headers=headers, name="IoT terminal", asset_type="TERMINAL"
    )
    first_payload = _asset(
        client,
        headers=headers,
        name="First tank",
        asset_type="TANK",
        parent_asset_id=terminal_payload["id"],
    )
    second_payload = _asset(
        client,
        headers=headers,
        name="Second tank",
        asset_type="TANK",
        parent_asset_id=terminal_payload["id"],
    )
    first = db_session.get(Asset, first_payload["id"])
    second = db_session.get(Asset, second_payload["id"])
    site = Site(company_id=organization_id, name="Ports IoT compatibility site")
    db_session.add(site)
    db_session.flush()
    device = IotDevice(
        public_id=f"GV-PORT-{uuid.uuid4().hex[:10]}",
        company_id=organization_id,
        site_id=site.id,
        core_asset_id=second.id,
        provider_device_id="opaque-provider-device-must-not-leak",
        name="Reassigned tank sensor",
        device_type="multi_sensor",
        status="online",
        connectivity_status="online",
        health_status="healthy",
        token_hash="hash",
        secret_encrypted="encrypted",
        capabilities_json='["temperature"]',
        configuration_json="{}",
        last_seen_at=datetime(2026, 9, 10, 7, 58),
    )
    db_session.add(device)
    db_session.flush()
    rule = IotAlertRule(
        company_id=organization_id,
        device_id=device.id,
        site_id=site.id,
        name="Tank temperature context",
        channel="temperature",
        operator=">",
        threshold=30,
        severity="warning",
        enabled=True,
    )
    db_session.add(rule)
    db_session.flush()
    db_session.add_all(
        [
            DeviceAssignment(
                company_id=organization_id,
                device_id=device.id,
                asset_id=first.id,
                status="ended",
                reason="moved to second tank",
                assigned_at=datetime(2026, 8, 1, 8),
                ended_at=datetime(2026, 9, 1, 8),
            ),
            DeviceAssignment(
                company_id=organization_id,
                device_id=device.id,
                asset_id=second.id,
                status="active",
                reason="current assignment",
                assigned_at=datetime(2026, 9, 1, 8),
            ),
            TelemetryReading(
                device_id=device.id,
                company_id=organization_id,
                site_id=site.id,
                core_asset_id=first.id,
                message_id=f"old-{uuid.uuid4().hex}",
                channel="temperature",
                numeric_value=31.0,
                unit="C",
                quality="good",
                recorded_at=datetime(2026, 8, 15, 8),
                received_at=datetime(2026, 8, 15, 8),
                metadata_json="{}",
            ),
            TelemetryReading(
                device_id=device.id,
                company_id=organization_id,
                site_id=site.id,
                core_asset_id=second.id,
                message_id=f"new-{uuid.uuid4().hex}",
                channel="temperature",
                numeric_value=32.0,
                unit="C",
                quality="good",
                recorded_at=datetime(2026, 9, 10, 7, 58),
                received_at=datetime(2026, 9, 10, 7, 58),
                metadata_json="{}",
            ),
            TelemetryReading(
                device_id=device.id,
                company_id=organization_id,
                site_id=site.id,
                core_asset_id=second.id,
                message_id=f"replay-{uuid.uuid4().hex}",
                channel="temperature",
                numeric_value=99.0,
                unit="C",
                source="offline_replay",
                quality="good",
                recorded_at=datetime(2026, 9, 10, 7, 59),
                received_at=datetime(2026, 9, 10, 8),
                metadata_json='{"offline_replay":true}',
            ),
            IotAlert(
                company_id=organization_id,
                device_id=device.id,
                rule_id=rule.id,
                channel="temperature",
                value=32.0,
                severity="warning",
                message="Source alert requiring operational review",
                status="open",
                opened_at=datetime(2026, 9, 10, 7, 59),
            ),
        ]
    )
    db_session.commit()

    first_context = build_source_context(
        db_session, asset=first, as_of=datetime(2026, 9, 10, 8)
    )
    first_sensor = first_context.evidence["sensor_context"]
    assert first_sensor["status"] == "NOT_CONFIGURED"
    assert first_sensor["historical_reading_count"] == 1
    assert (
        "assigned_sensor_freshness_minutes" not in first_context.evaluation.measurements
    )

    second_context = build_source_context(
        db_session, asset=second, as_of=datetime(2026, 9, 10, 8)
    )
    second_sensor = second_context.evidence["sensor_context"]
    assert second_sensor["status"] == "AVAILABLE"
    assert second_sensor["historical_reading_count"] == 1
    assert (
        second_context.evaluation.measurements["assigned_sensor_freshness_minutes"] == 2
    )
    assert second_context.evaluation.measurements["operational_alert_count"] == 1
    assert {
        item["kind"] for item in second_context.evaluation.metadata["findings"]
    } == {"operational_alert"}
    serialized_sensor = json.dumps(second_context.evidence["sensor_context"])
    assert "opaque-provider-device-must-not-leak" not in serialized_sensor
    assert "provider_device_id" not in serialized_sensor

    seed_shop_products(db_session)
    sync_catalog_from_legacy(db_session)
    evaluated = client.post(
        f"/assets/{second.id}/ports-logistics/evaluate",
        headers=headers,
        json={"as_of": "2026-09-10T08:00:00"},
    )
    assert evaluated.status_code == 200, evaluated.text
    sensor_observation = (
        db_session.query(Observation)
        .filter(
            Observation.asset_id == second.id,
            Observation.observation_type == "PORT_OPERATIONAL_ALERT_CONTEXT",
        )
        .one()
    )
    assert sensor_observation.validation_status == "NEEDS_REVIEW"
    assert json.loads(sensor_observation.value_json)["safety_conclusion"] is None

    offline = IotDevice(
        public_id=f"GV-PORT-{uuid.uuid4().hex[:10]}",
        company_id=organization_id,
        site_id=site.id,
        core_asset_id=second.id,
        name="Offline sensor",
        device_type="multi_sensor",
        status="online",
        connectivity_status="offline",
        health_status="unknown",
        token_hash="hash2",
        secret_encrypted="encrypted2",
        capabilities_json="[]",
        configuration_json="{}",
    )
    db_session.add(offline)
    db_session.flush()
    db_session.add(
        DeviceAssignment(
            company_id=organization_id,
            device_id=offline.id,
            asset_id=second.id,
            status="active",
            reason="installed but offline",
            assigned_at=datetime(2026, 9, 2, 8),
        )
    )
    db_session.commit()
    degraded = build_source_context(
        db_session, asset=second, as_of=datetime(2026, 9, 10, 8)
    )
    assert degraded.evidence["sensor_context"]["status"] == "UNKNOWN"
    assert "assigned_sensor_freshness_minutes" not in degraded.evaluation.measurements

    terminal = db_session.get(Asset, terminal_payload["id"])
    terminal_context = build_source_context(
        db_session, asset=terminal, as_of=datetime(2026, 9, 10, 8)
    )
    assert terminal_context.evidence["sensor_context"]["assignment_count"] == 2
    assert all(
        item["asset_id"] in {first.id, second.id}
        for item in terminal_context.evidence["sensor_context"]["devices"]
    )
    assert workspace_id == terminal.workspace_id


def test_ports_repeated_inspection_common_lifecycle_report_and_idempotency(
    client, db_session, tmp_path
):
    owner, organization_id, workspace_id, headers = _workspace(
        client, db_session, prefix="ports-full"
    )
    terminal_payload = _asset(
        client, headers=headers, name="Synthetic terminal", asset_type="TERMINAL"
    )
    gantry_payload = _asset(
        client,
        headers=headers,
        name="Synthetic terminal gantry",
        asset_type="GANTRY",
        parent_asset_id=terminal_payload["id"],
        cadence_days=30,
    )
    gantry = db_session.get(Asset, gantry_payload["id"])
    seed_shop_products(db_session)
    sync_catalog_from_legacy(db_session)
    order = Order(
        user_id=owner.id,
        company_id=organization_id,
        organization_id=organization_id,
        workspace_id=workspace_id,
        order_number=f"GV-P31-{uuid.uuid4().hex[:10].upper()}",
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
    mission_ids: dict[str, str] = {}
    for inspection, title in (
        ("previous", "Baseline gantry inspection"),
        ("current", "Current gantry inspection"),
    ):
        response = client.post(
            "/missions/internal",
            headers=_admin_headers(client),
            json={
                "asset_id": gantry.id,
                "order_id": order.id,
                "acquisition_type": "DRONE",
                "title": title,
                "drone_details": {
                    "payload_reference": "RGB-ZOOM-THERMAL",
                    "mission_requirements": {
                        "rgb": True,
                        "zoom": True,
                        "thermal": True,
                        "mesh_3d": True,
                    },
                    "flight_metadata": {},
                },
            },
        )
        assert response.status_code == 201, response.text
        mission_ids[inspection] = response.json()["id"]
    bundle = demo_ports_bundle(asset_id=gantry.id)
    datasets = _materialize_bundle(
        db_session,
        asset=gantry,
        bundle=bundle,
        mission_ids=mission_ids,
    )
    assert {
        db_session.get(Acquisition, mission_id).asset_id
        for mission_id in mission_ids.values()
    } == {gantry.id}
    assert all(row.asset_id == gantry.id for row in datasets.values())

    capabilities = client.get("/sectors/ports-logistics/capabilities", headers=headers)
    assert capabilities.status_code == 200, capabilities.text
    assert capabilities.json()["enabled"] is True
    assert capabilities.json()["analysis_schema"] == ANALYSIS_SCHEMA
    evaluated = client.post(
        f"/assets/{gantry.id}/ports-logistics/evaluate",
        headers=headers,
        json={"as_of": "2026-09-10T08:00:00"},
    )
    assert evaluated.status_code == 200, evaluated.text
    body = evaluated.json()
    assert body["source_availability"]["historical_comparison"] == "AVAILABLE"
    assert body["source_availability"]["inspection_evidence"] == "AVAILABLE"
    assert body["source_availability"]["condition_summary"] == "AVAILABLE"
    assert body["source_availability"]["reinspection"] == "NOT_DUE"
    kpis = {item["definition"]["key"]: item for item in body["kpis"]}
    assert kpis["inspection_status"]["current"] == "CANDIDATES_REQUIRE_REVIEW"
    assert kpis["inspection_freshness_days"]["current"] == 5
    assert kpis["condition_summary"]["current"] == "REVIEW_REQUIRED"
    assert kpis["new_visual_candidate_count"]["current"] == 1
    assert kpis["new_thermal_candidate_count"]["current"] == 1
    assert kpis["reinspection_state"]["current"] == "NOT_DUE"

    counts = (
        db_session.query(KpiValue).filter(KpiValue.asset_id == gantry.id).count(),
        db_session.query(Observation).filter(Observation.asset_id == gantry.id).count(),
        db_session.query(Action).filter(Action.asset_id == gantry.id).count(),
    )
    replay = client.post(
        f"/assets/{gantry.id}/ports-logistics/evaluate",
        headers=headers,
        json={"as_of": "2026-09-10T08:00:00"},
    )
    assert replay.status_code == 200, replay.text
    assert counts == (
        db_session.query(KpiValue).filter(KpiValue.asset_id == gantry.id).count(),
        db_session.query(Observation).filter(Observation.asset_id == gantry.id).count(),
        db_session.query(Action).filter(Action.asset_id == gantry.id).count(),
    )

    observations = client.get(
        f"/assets/{gantry.id}/observations", headers=headers
    ).json()["items"]
    assert {item["type"] for item in observations} == {
        "PORT_THERMAL_ANOMALY_CANDIDATE",
        "PORT_VISUAL_ANOMALY_CANDIDATE",
    }
    for item in observations:
        assert item["validation_status"] == "NEEDS_REVIEW"
        assert all(
            item["value"][key] is None
            for key in (
                "cause",
                "condition",
                "defect",
                "structural_integrity",
                "safety_conclusion",
                "navigation_conclusion",
                "compliance_conclusion",
            )
        )
    actions = client.get(f"/assets/{gantry.id}/actions", headers=headers).json()[
        "items"
    ]
    assert {item["recommended_catalog_item_id"] for item in actions} == {
        "prod_ports_sensor_installation",
        "prod_ports_specialist_review",
    }

    history = client.get(
        f"/assets/{gantry.id}/ports-logistics/inspection-history", headers=headers
    )
    assert history.status_code == 200, history.text
    assert history.json()["total"] == 6
    assert {item["asset_id"] for item in history.json()["items"]} == {gantry.id}
    current_zoom = next(
        item
        for item in history.json()["items"]
        if item["dataset_id"] == datasets["Current gantry zoom inspection"].id
    )
    assert current_zoom["capture_mode"] == "ZOOM_RGB"
    assert (
        current_zoom["comparison_previous_dataset_id"]
        == datasets["Previous gantry visual inspection"].id
    )

    comparisons = client.get(
        f"/assets/{gantry.id}/ports-logistics/comparisons", headers=headers
    )
    assert comparisons.status_code == 200, comparisons.text
    assert {item["availability"] for item in comparisons.json()["items"]} == {
        "AVAILABLE"
    }
    layers = client.get(
        f"/assets/{gantry.id}/ports-logistics/map-layers", headers=headers
    )
    assert layers.status_code == 200, layers.text
    assert {"ASSET_BOUNDARY", "RGB_IMAGES", "THERMAL_IMAGES", "MESH_3D"}.issubset(
        {item["kind"] for item in layers.json()["items"]}
    )

    report_context = client.get(
        f"/assets/{gantry.id}/ports-logistics/report-context", headers=headers
    )
    assert report_context.status_code == 200, report_context.text
    context_body = report_context.json()
    assert context_body["schema"] == "geovision.ports.report-context.v1"
    rendered = json.dumps(context_body).lower()
    assert "no defect" in rendered
    assert not any(
        phrase in rendered
        for phrase in (
            "defect confirmed",
            "structurally sound",
            "safe for operation",
            "navigation is safe",
            "compliant with",
        )
    )

    storage = StorageService(
        LocalObjectStorageProvider(
            root=tmp_path,
            public_base_url="http://testserver",
            signing_secret="test-ports-report-signing-key",
        )
    )
    report_row, created = generate_report(
        db_session,
        actor=owner,
        asset=gantry,
        data=ReportGenerateRequest(
            report_type="PORT_ASSET_INSPECTION",
            acquisition_id=mission_ids["current"],
            idempotency_key=f"ports-report-{uuid.uuid4()}",
        ),
        storage=storage,
    )
    db_session.commit()
    assert created is True
    assert report_row.asset_id == gantry.id
    assert report_row.acquisition_id == mission_ids["current"]
    assert json.loads(report_row.context_json)["asset"]["sector"] == "PORTS_LOGISTICS"
    assert db_session.query(Report).filter(Report.asset_id == gantry.id).count() == 1

    terminal_history = client.get(
        f"/assets/{terminal_payload['id']}/ports-logistics/inspection-history",
        headers=headers,
    )
    assert terminal_history.status_code == 200
    assert {item["asset_id"] for item in terminal_history.json()["items"]} == {
        gantry.id
    }


def test_ports_permissions_workspace_tenant_and_feature_boundaries(client, db_session):
    owner, organization_id, workspace_id, headers = _workspace(
        client, db_session, prefix="ports-isolation"
    )
    asset = _asset(client, headers=headers, name="Protected quay", asset_type="QUAY")
    viewer = _user(db_session, "ports-viewer")
    membership = client.post(
        f"/organizations/{organization_id}/members",
        headers=headers,
        json={"email": viewer.email, "user_id": viewer.id, "role": "viewer"},
    )
    assert membership.status_code == 201, membership.text
    viewer_headers = _headers(viewer, workspace_id)
    assert (
        client.get(
            f"/assets/{asset['id']}/ports-logistics/report-context",
            headers=viewer_headers,
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/assets/{asset['id']}/ports-logistics/evaluate",
            headers=viewer_headers,
            json={},
        ).status_code
        == 403
    )

    second = client.post(
        f"/organizations/{organization_id}/workspaces",
        headers=headers,
        json={
            "name": "Ports disabled workspace",
            "sector_focus": "industry",
            "customer_type": "enterprise",
            "modules_enabled": ["assets", "analytics", "reports"],
        },
    )
    assert second.status_code == 201, second.text
    disabled_workspace_id = second.json()["id"]
    disabled_headers = _headers(owner, disabled_workspace_id)
    disabled_asset = _asset(
        client,
        headers=disabled_headers,
        name="Disabled terminal",
        asset_type="TERMINAL",
    )
    # Even a corrupt direct cross-workspace parent link must not enter the
    # original terminal's bounded descendant projection.
    disabled_row = db_session.get(Asset, disabled_asset["id"])
    disabled_row.parent_asset_id = asset["id"]
    hidden_dataset = _dataset(
        db_session,
        asset=disabled_row,
        name="Cross-workspace inspection must stay hidden",
        dataset_type="RGB_IMAGES",
        captured_at=datetime(2026, 9, 1, 8),
        analysis=_analysis(disabled_row.id, "cross-workspace"),
    )
    db_session.commit()
    capabilities = client.get(
        "/sectors/ports-logistics/capabilities", headers=disabled_headers
    )
    assert capabilities.status_code == 200
    assert capabilities.json()["enabled"] is False
    assert (
        client.get(
            f"/assets/{disabled_asset['id']}/ports-logistics/map-layers",
            headers=disabled_headers,
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/assets/{asset['id']}/ports-logistics/report-context",
            headers=disabled_headers,
        ).status_code
        == 404
    )
    original_history = client.get(
        f"/assets/{asset['id']}/ports-logistics/inspection-history", headers=headers
    )
    assert original_history.status_code == 200
    assert hidden_dataset.id not in {
        item["dataset_id"] for item in original_history.json()["items"]
    }

    _, _, _, outsider_headers = _workspace(client, db_session, prefix="ports-outsider")
    hidden = client.get(
        f"/assets/{asset['id']}/ports-logistics/report-context",
        headers=outsider_headers,
    )
    assert hidden.status_code == 404
