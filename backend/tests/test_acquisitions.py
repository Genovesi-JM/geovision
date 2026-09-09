from __future__ import annotations

import uuid

from app.core.tokens import create_user_access_token
from app.models import Acquisition, User
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
    assert asset_acquisition_outputs(db_session, asset["id"])[0]["acquisition_id"] == satellite["id"]

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
    assert db_session.query(Acquisition).filter(Acquisition.asset_id == asset["id"]).count() == 2
