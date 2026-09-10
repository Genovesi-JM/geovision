from __future__ import annotations

import json
import uuid

from app.core.tokens import create_user_access_token
from app.models import Acquisition, Action, Asset, User
from app.modules.missions.services import asset_acquisition_outputs


def _user(db_session, prefix: str) -> User:
    user = User(
        email=f"{prefix}-{uuid.uuid4().hex}@example.com",
        role="cliente",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


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


def _workspace_and_asset(client, db_session) -> tuple[User, dict[str, str], dict]:
    owner = _user(db_session, "mission-owner")
    created = client.post(
        "/organizations",
        headers=_headers(owner),
        json={
            "name": f"Mission customer {uuid.uuid4().hex[:8]}",
            "country": "Angola",
            "timezone": "Africa/Luanda",
            "workspace": {
                "name": "Acquisition workspace",
                "customer_type": "business",
                "sector_focus": "environment",
            },
        },
    )
    assert created.status_code == 201, created.text
    workspace_id = created.json()["workspaces"][0]["id"]
    headers = _headers(owner, workspace_id)
    asset = client.post(
        "/assets",
        headers=headers,
        json={
            "sector": "ENVIRONMENTAL",
            "asset_type": "WETLAND",
            "name": "Coastal wetland",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [13.0, -9.0],
                        [13.2, -9.0],
                        [13.2, -8.8],
                        [13.0, -9.0],
                    ]
                ],
            },
        },
    )
    assert asset.status_code == 201, asset.text
    return owner, headers, asset.json()


def test_drone_and_satellite_share_one_chronological_asset_history(client, db_session):
    _, customer_headers, asset = _workspace_and_asset(client, db_session)
    admin_headers = _admin_headers(client)

    drone = client.post(
        "/missions",
        headers=customer_headers,
        json={
            "asset_id": asset["id"],
            "acquisition_type": "DRONE",
            "title": "Wetland RGB capture",
            "metadata": {"requested_resolution_cm": 4},
            "drone_details": {
                "payload_reference": "RGB-24MP",
                "mission_requirements": {"overlap_percent": 80},
                "capture_area": asset["geometry"],
                "flight_metadata": {},
            },
        },
    )
    assert drone.status_code == 201, drone.text
    assert drone.json()["acquisition_type"] == "DRONE"
    assert drone.json()["drone_details"]["payload_reference"] == "RGB-24MP"
    stored_drone = db_session.get(Acquisition, drone.json()["id"])
    assert json.loads(stored_drone.provenance_json)["adapter_version"] == (
        "geovision-acquisition-v1.0.0"
    )

    satellite = client.post(
        "/missions/internal",
        headers=admin_headers,
        json={
            "asset_id": asset["id"],
            "acquisition_type": "SATELLITE",
            "title": "Sentinel vegetation scene",
            "provider_code": "Sentinel Hub",
            "provider_reference": "provider-scene-private-42",
            "provenance": {
                "collection": "sentinel-2-l2a",
                "license": "Copernicus",
            },
            "metadata": {"cloud_cover_percent": 3.5},
            "output_refs": [
                {
                    "type": "dataset",
                    "dataset_id": "dataset-safe-42",
                    "storage_key": "private/raw/key.tif",
                    "operator_user_id": "private-staff-id",
                }
            ],
        },
    )
    assert satellite.status_code == 201, satellite.text
    satellite_payload = satellite.json()
    assert satellite_payload["provider_code"] == "sentinel_hub"
    assert satellite_payload["provider_reference"] == "provider-scene-private-42"
    assert satellite_payload["drone_details"] is None

    history = client.get(
        f"/missions/assets/{asset['id']}/history", headers=customer_headers
    )
    assert history.status_code == 200, history.text
    assert [row["id"] for row in history.json()] == [
        drone.json()["id"],
        satellite_payload["id"],
    ]
    assert [row["acquisition_type"] for row in history.json()] == [
        "DRONE",
        "SATELLITE",
    ]
    customer_text = history.text.lower()
    for private_value in (
        "provider-scene-private-42",
        "private/raw/key.tif",
        "private-staff-id",
        "provider_reference",
        "contractor_id",
        "operator_user_id",
        "fulfilment_job_id",
    ):
        assert private_value not in customer_text
    assert client.get("/missions/internal", headers=customer_headers).status_code == 403


def test_lifecycle_reflight_outputs_and_permission_split(client, db_session):
    _, customer_headers, asset = _workspace_and_asset(client, db_session)
    admin_headers = _admin_headers(client)
    satellite = client.post(
        "/missions/internal",
        headers=admin_headers,
        json={
            "asset_id": asset["id"],
            "acquisition_type": "SATELLITE",
            "title": "Satellite acquisition",
            "provider_code": "mock_satellite",
            "output_refs": [{"type": "dataset", "dataset_id": "dataset-1"}],
        },
    ).json()

    customer_planned = client.patch(
        f"/missions/{satellite['id']}/state",
        headers=customer_headers,
        json={"state": "PLANNED", "expected_version": satellite["lifecycle_version"]},
    )
    assert customer_planned.status_code == 200, customer_planned.text
    forbidden_start = client.patch(
        f"/missions/{satellite['id']}/state",
        headers=customer_headers,
        json={
            "state": "IN_PROGRESS",
            "expected_version": customer_planned.json()["lifecycle_version"],
        },
    )
    assert forbidden_start.status_code == 403

    current = customer_planned.json()
    for state in ("IN_PROGRESS", "DATA_CAPTURED", "PROCESSING", "COMPLETED"):
        response = client.patch(
            f"/missions/internal/{satellite['id']}/state",
            headers=admin_headers,
            json={"state": state, "expected_version": current["lifecycle_version"]},
        )
        assert response.status_code == 200, response.text
        current = response.json()
    assert current["captured_at"] is not None
    assert current["completed_at"] is not None
    invalid_terminal = client.patch(
        f"/missions/internal/{satellite['id']}/state",
        headers=admin_headers,
        json={"state": "PLANNED", "expected_version": current["lifecycle_version"]},
    )
    assert invalid_terminal.status_code == 409

    outputs = client.get(
        f"/missions/assets/{asset['id']}/outputs", headers=customer_headers
    )
    assert outputs.status_code == 200, outputs.text
    assert outputs.json() == [
        {
            "acquisition_id": satellite["id"],
            "acquisition_type": "SATELLITE",
            "captured_at": current["captured_at"],
            "state": "COMPLETED",
            "outputs": [{"dataset_id": "dataset-1", "type": "dataset"}],
        }
    ]
    assert (
        asset_acquisition_outputs(db_session, asset["id"])[0]["acquisition_id"]
        == satellite["id"]
    )

    drone = client.post(
        "/missions/internal",
        headers=admin_headers,
        json={
            "asset_id": asset["id"],
            "acquisition_type": "DRONE",
            "title": "Reflight candidate",
            "drone_details": {"mission_requirements": {}, "flight_metadata": {}},
        },
    ).json()
    for state in ("PLANNED", "IN_PROGRESS", "DATA_CAPTURED"):
        changed = client.patch(
            f"/missions/internal/{drone['id']}/state",
            headers=admin_headers,
            json={"state": state, "expected_version": drone["lifecycle_version"]},
        )
        assert changed.status_code == 200, changed.text
        drone = changed.json()
    reflight = client.patch(
        f"/missions/internal/{drone['id']}/state",
        headers=admin_headers,
        json={
            "state": "NEEDS_REFLIGHT",
            "reason": "Cloud obscured the north boundary",
            "expected_version": drone["lifecycle_version"],
        },
    )
    assert reflight.status_code == 200, reflight.text
    assert reflight.json()["drone_details"]["reflight_reason"].startswith("Cloud")

    satellite_reflight = client.patch(
        f"/missions/internal/{satellite['id']}/state",
        headers=admin_headers,
        json={
            "state": "NEEDS_REFLIGHT",
            "reason": "not valid for satellite",
            "expected_version": current["lifecycle_version"],
        },
    )
    # The completed state rejects the transition before modality validation.
    assert satellite_reflight.status_code == 409
    assert (
        db_session.query(Acquisition)
        .filter(Acquisition.asset_id == asset["id"])
        .count()
        == 2
    )


def test_customer_acquisition_routes_quarantine_ambiguous_null_workspace_scope(
    client,
    db_session,
):
    owner, headers_a, asset = _workspace_and_asset(client, db_session)
    stored_asset = db_session.get(Asset, asset["id"])
    assert stored_asset is not None
    organization_id = stored_asset.organization_id
    workspace_a = stored_asset.workspace_id
    assert workspace_a is not None

    explicit_a = client.post(
        "/missions",
        headers=headers_a,
        json={
            "asset_id": asset["id"],
            "acquisition_type": "DRONE",
            "title": "Workspace A mission",
        },
    )
    assert explicit_a.status_code == 201, explicit_a.text

    stored_asset.workspace_id = None
    legacy_null = Acquisition(
        acquisition_number=f"GVAQ-LEGACY-{uuid.uuid4().hex[:8].upper()}",
        organization_id=organization_id,
        workspace_id=None,
        asset_id=asset["id"],
        acquisition_type="DRONE",
        title="Legacy organization-only mission",
        state="COMPLETED",
        output_refs_json=json.dumps([{"type": "dataset", "dataset_id": "legacy"}]),
    )
    action_a = Action(
        organization_id=organization_id,
        workspace_id=workspace_a,
        asset_id=asset["id"],
        source_rule_key="scope.regression",
        source_rule_version="1.0.0",
        priority="HIGH",
        title="Workspace A action",
        description="Must not cross into workspace B",
        status="OPEN",
        deduplication_key=f"scope-{uuid.uuid4().hex}",
    )
    db_session.add_all([legacy_null, action_a])
    db_session.commit()

    # A legacy NULL asset and mission remain usable while A is the sole active
    # workspace. New customer missions still receive explicit scope.
    sole_list = client.get("/missions", headers=headers_a)
    assert sole_list.status_code == 200, sole_list.text
    assert legacy_null.id in {row["id"] for row in sole_list.json()}
    assert (
        client.get(f"/missions/{legacy_null.id}", headers=headers_a).status_code == 200
    )
    sole_history = client.get(
        f"/missions/assets/{asset['id']}/history", headers=headers_a
    )
    assert sole_history.status_code == 200, sole_history.text
    assert legacy_null.id in {row["id"] for row in sole_history.json()}
    sole_outputs = client.get(
        f"/missions/assets/{asset['id']}/outputs", headers=headers_a
    )
    assert sole_outputs.status_code == 200, sole_outputs.text
    assert legacy_null.id in {row["acquisition_id"] for row in sole_outputs.json()}
    created_from_legacy = client.post(
        "/missions",
        headers=headers_a,
        json={
            "asset_id": asset["id"],
            "acquisition_type": "SATELLITE",
            "title": "Explicitly scoped from legacy asset",
        },
    )
    assert created_from_legacy.status_code == 201, created_from_legacy.text
    assert (
        db_session.get(Acquisition, created_from_legacy.json()["id"]).workspace_id
        == workspace_a
    )

    second = client.post(
        f"/organizations/{organization_id}/workspaces",
        headers=headers_a,
        json={
            "name": "Workspace B",
            "customer_type": "business",
            "sector_focus": "environment",
        },
    )
    assert second.status_code == 201, second.text
    workspace_b = second.json()["id"]
    headers_b = _headers(owner, workspace_b)

    missions_a = client.get("/missions", headers=headers_a)
    assert missions_a.status_code == 200, missions_a.text
    assert explicit_a.json()["id"] in {row["id"] for row in missions_a.json()}
    assert legacy_null.id not in {row["id"] for row in missions_a.json()}
    assert (
        client.get(f"/missions/{legacy_null.id}", headers=headers_a).status_code == 404
    )

    # The NULL asset can no longer carry explicit A actions or missions into B.
    assert (
        client.get(f"/assets/{asset['id']}/actions", headers=headers_b).status_code
        == 404
    )
    assert client.get(f"/actions/{action_a.id}", headers=headers_b).status_code == 404
    assert (
        client.patch(
            f"/actions/{action_a.id}/status",
            headers=headers_b,
            json={"status": "IN_PROGRESS", "expected_version": 1},
        ).status_code
        == 404
    )
    assert db_session.get(Action, action_a.id).status == "OPEN"

    missions_b = client.get("/missions", headers=headers_b)
    assert missions_b.status_code == 200, missions_b.text
    assert {explicit_a.json()["id"], legacy_null.id}.isdisjoint(
        {row["id"] for row in missions_b.json()}
    )
    for mission_id in (explicit_a.json()["id"], legacy_null.id):
        assert (
            client.get(f"/missions/{mission_id}", headers=headers_b).status_code == 404
        )
        assert (
            client.patch(
                f"/missions/{mission_id}",
                headers=headers_b,
                json={"title": "Cross-workspace overwrite", "expected_version": 1},
            ).status_code
            == 404
        )
    assert (
        client.get(
            f"/missions/assets/{asset['id']}/history", headers=headers_b
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/missions/assets/{asset['id']}/outputs", headers=headers_b
        ).status_code
        == 404
    )
    rejected_dataset = client.post(
        "/datasets/",
        headers=headers_b,
        json={
            "asset_id": asset["id"],
            "mission_id": explicit_a.json()["id"],
            "name": "Cross-workspace dataset",
            "dataset_type": "MULTISPECTRAL_IMAGES",
            "source_tool": "manual",
            "provider": "GeoVision Capture",
            "capture_time": "2026-09-10T08:00:00Z",
            "processing_level": "RAW",
        },
    )
    assert rejected_dataset.status_code == 404, rejected_dataset.text

    # Acquisition rows are independently scoped even if bad legacy data ties
    # an A mission to an otherwise valid B asset.
    asset_b = client.post(
        "/assets",
        headers=headers_b,
        json={
            "sector": "MINING",
            "asset_type": "MINE",
            "name": "Workspace B mine",
        },
    )
    assert asset_b.status_code == 201, asset_b.text
    mismatched = Acquisition(
        acquisition_number=f"GVAQ-MISMATCH-{uuid.uuid4().hex[:8].upper()}",
        organization_id=organization_id,
        workspace_id=workspace_a,
        asset_id=asset_b.json()["id"],
        acquisition_type="SATELLITE",
        title="Inconsistent workspace A mission",
        state="COMPLETED",
        output_refs_json=json.dumps([{"type": "dataset", "dataset_id": "private-a"}]),
    )
    db_session.add(mismatched)
    db_session.commit()
    assert (
        client.get(f"/missions/{mismatched.id}", headers=headers_b).status_code == 404
    )
    assert (
        client.patch(
            f"/missions/{mismatched.id}",
            headers=headers_b,
            json={"title": "Cross-workspace overwrite", "expected_version": 1},
        ).status_code
        == 404
    )
    scoped_history = client.get(
        f"/missions/assets/{asset_b.json()['id']}/history", headers=headers_b
    )
    assert scoped_history.status_code == 200, scoped_history.text
    assert mismatched.id not in {row["id"] for row in scoped_history.json()}
    scoped_outputs = client.get(
        f"/missions/assets/{asset_b.json()['id']}/outputs", headers=headers_b
    )
    assert scoped_outputs.status_code == 200, scoped_outputs.text
    assert mismatched.id not in {row["acquisition_id"] for row in scoped_outputs.json()}
