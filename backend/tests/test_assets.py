from __future__ import annotations

import uuid

from app.core.tokens import create_user_access_token
from app.models import Asset, User


def _user(db_session, prefix: str) -> User:
    user = User(
        email=f"{prefix}-{uuid.uuid4().hex}@example.com",
        password_hash=None,
        role="cliente",
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
    headers = {"Authorization": f"Bearer {token}"}
    if workspace_id:
        headers["X-Workspace-ID"] = workspace_id
    return headers


def _organization(client, owner: User, name: str = "Asset Test") -> tuple[str, str]:
    response = client.post(
        "/organizations",
        headers=_headers(owner),
        json={
            "name": name,
            "country": "Angola",
            "timezone": "Africa/Luanda",
            "workspace": {
                "name": f"{name} Workspace",
                "customer_type": "business",
                "sector_focus": "agro",
            },
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body["id"], body["workspaces"][0]["id"]


def _create_asset(client, headers, **overrides):
    payload = {
        "sector": "AGRICULTURE",
        "asset_type": "FARM",
        "name": "Kwanza Farm",
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
        "metadata": {"source": "surveyed"},
    }
    payload.update(overrides)
    response = client.post("/assets", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_cross_sector_hierarchy_spatial_filters_and_geojson_map(client, db_session):
    owner = _user(db_session, "asset-owner")
    organization_id, workspace_id = _organization(client, owner)
    headers = _headers(owner, workspace_id)

    farm = _create_asset(client, headers)
    field = _create_asset(
        client,
        headers,
        parent_asset_id=farm["id"],
        asset_type="FIELD",
        name="Field A",
        geometry={"type": "Point", "coordinates": [13.1, -8.9]},
    )
    terminal = _create_asset(
        client,
        headers,
        sector="PORTS_INDUSTRIAL",
        asset_type="TERMINAL",
        name="Port Terminal A",
        geometry={
            "type": "MultiPolygon",
            "coordinates": [
                [
                    [
                        [12.9, -8.9],
                        [13.0, -8.9],
                        [13.0, -8.8],
                        [12.9, -8.9],
                    ]
                ]
            ],
        },
    )
    extension = _create_asset(
        client,
        headers,
        sector="RENEWABLE_ENERGY",
        asset_type="WIND_TURBINE",
        name="Future registry type",
        geometry=None,
    )

    assert farm["organization_id"] == organization_id
    assert farm["workspace_id"] == workspace_id
    assert farm["bbox"] == [13.0, -9.0, 13.2, -8.8]
    assert field["parent_asset_id"] == farm["id"]
    assert terminal["sector"] == "PORTS_INDUSTRIAL"
    assert extension["sector"] == "RENEWABLE_ENERGY"
    assert extension["asset_type"] == "WIND_TURBINE"

    children = client.get(
        "/assets",
        headers=headers,
        params={"parent_asset_id": farm["id"]},
    )
    assert children.status_code == 200
    assert [row["id"] for row in children.json()] == [field["id"]]

    agriculture = client.get(
        "/assets",
        headers=headers,
        params={
            "organization_id": organization_id,
            "workspace_id": workspace_id,
            "sector": "agro",
        },
    )
    assert agriculture.status_code == 200
    assert {row["id"] for row in agriculture.json()} == {farm["id"], field["id"]}

    spatial = client.get(
        "/assets",
        headers=headers,
        params={"bbox": "13.05,-8.95,13.15,-8.85", "asset_type": "FIELD"},
    )
    assert spatial.status_code == 200
    assert [row["id"] for row in spatial.json()] == [field["id"]]

    map_response = client.get("/assets/map", headers=headers)
    assert map_response.status_code == 200
    feature_collection = map_response.json()
    assert feature_collection["type"] == "FeatureCollection"
    assert {feature["id"] for feature in feature_collection["features"]} == {
        farm["id"],
        field["id"],
        terminal["id"],
    }

    columns = set(Asset.__table__.columns.keys())
    assert not {"farm_id", "crop", "field_area", "mine_grade"} & columns


def test_hierarchy_cycle_and_archive_lifecycle_are_guarded(client, db_session):
    owner = _user(db_session, "hierarchy-owner")
    _, workspace_id = _organization(client, owner, "Hierarchy")
    headers = _headers(owner, workspace_id)
    parent = _create_asset(client, headers, name="Parent")
    child = _create_asset(
        client,
        headers,
        name="Child",
        asset_type="FIELD",
        parent_asset_id=parent["id"],
    )

    cycle = client.patch(
        f"/assets/{parent['id']}",
        headers=headers,
        json={"parent_asset_id": child["id"]},
    )
    assert cycle.status_code == 409

    parent_first = client.delete(f"/assets/{parent['id']}", headers=headers)
    assert parent_first.status_code == 409
    archived_child = client.delete(f"/assets/{child['id']}", headers=headers)
    assert archived_child.status_code == 200
    assert archived_child.json()["status"] == "archived"
    archived_parent = client.delete(f"/assets/{parent['id']}", headers=headers)
    assert archived_parent.status_code == 200
    assert archived_parent.json()["archived_at"] is not None

    active_list = client.get("/assets", headers=headers)
    assert active_list.status_code == 200
    assert active_list.json() == []
    archive_list = client.get(
        "/assets",
        headers=headers,
        params={"include_archived": True},
    )
    assert {row["id"] for row in archive_list.json()} == {parent["id"], child["id"]}
    cannot_edit = client.patch(
        f"/assets/{child['id']}", headers=headers, json={"name": "Too late"}
    )
    assert cannot_edit.status_code == 409


def test_tenant_isolation_and_viewer_cannot_mutate_assets(client, db_session):
    owner = _user(db_session, "tenant-owner")
    viewer = _user(db_session, "asset-viewer")
    outsider = _user(db_session, "asset-outsider")
    organization_id, workspace_id = _organization(client, owner, "Tenant A")
    headers = _headers(owner, workspace_id)
    asset = _create_asset(client, headers)

    member = client.post(
        f"/organizations/{organization_id}/members",
        headers=headers,
        json={"email": viewer.email, "user_id": viewer.id, "role": "viewer"},
    )
    assert member.status_code == 201, member.text
    viewer_headers = _headers(viewer, workspace_id)
    assert client.get(f"/assets/{asset['id']}", headers=viewer_headers).status_code == 200
    assert client.post(
        "/assets",
        headers=viewer_headers,
        json={"sector": "AGRICULTURE", "asset_type": "FIELD", "name": "No"},
    ).status_code == 404
    assert client.patch(
        f"/assets/{asset['id']}", headers=viewer_headers, json={"name": "No"}
    ).status_code == 404
    assert client.delete(f"/assets/{asset['id']}", headers=viewer_headers).status_code == 404

    _, outsider_workspace = _organization(client, outsider, "Tenant B")
    outsider_headers = _headers(outsider, outsider_workspace)
    assert client.get(f"/assets/{asset['id']}", headers=outsider_headers).status_code == 404
    outsider_asset = _create_asset(client, outsider_headers, name="Other tenant")
    cross_tenant_parent = client.post(
        "/assets",
        headers=headers,
        json={
            "sector": "AGRICULTURE",
            "asset_type": "FIELD",
            "name": "Cross-tenant child",
            "parent_asset_id": outsider_asset["id"],
        },
    )
    assert cross_tenant_parent.status_code == 404
    mismatched_filter = client.get(
        "/assets",
        headers=headers,
        params={"workspace_id": outsider_workspace},
    )
    assert mismatched_filter.status_code == 404


def test_geometry_validation_rejects_unsafe_or_ambiguous_shapes(client, db_session):
    owner = _user(db_session, "geometry-owner")
    _, workspace_id = _organization(client, owner, "Geometry")
    headers = _headers(owner, workspace_id)

    unclosed = client.post(
        "/assets",
        headers=headers,
        json={
            "sector": "ENVIRONMENTAL",
            "asset_type": "ENVIRONMENTAL_SITE",
            "name": "Unclosed",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[13, -9], [14, -9], [14, -8], [13, -8]]],
            },
        },
    )
    assert unclosed.status_code == 422
    out_of_bounds = client.post(
        "/assets",
        headers=headers,
        json={
            "sector": "MINING",
            "asset_type": "MINE",
            "name": "Invalid point",
            "geometry": {"type": "Point", "coordinates": [181, -9]},
        },
    )
    assert out_of_bounds.status_code == 422
    unsupported = client.post(
        "/assets",
        headers=headers,
        json={
            "sector": "INFRASTRUCTURE",
            "asset_type": "ROAD",
            "name": "Line not yet supported",
            "geometry": {"type": "LineString", "coordinates": [[13, -9], [14, -9]]},
        },
    )
    assert unsupported.status_code == 422
    secret_metadata = client.post(
        "/assets",
        headers=headers,
        json={
            "sector": "INFRASTRUCTURE",
            "asset_type": "SITE",
            "name": "Unsafe metadata",
            "metadata": {"provider": {"api-key": "must-not-be-persisted"}},
        },
    )
    assert secret_metadata.status_code == 422


def test_legacy_site_and_iot_asset_writes_are_mirrored(client, db_session):
    owner = _user(db_session, "legacy-asset-owner")
    _, workspace_id = _organization(client, owner, "Legacy Mirror")
    headers = _headers(owner, workspace_id)

    site_response = client.post(
        "/mobile/sites",
        headers=headers,
        json={
            "name": "Mirrored Environment Site",
            "sector": "environment",
            "country": "Angola",
            "province": "Huambo",
            "municipality": "Caála",
            "latitude": -12.852,
            "longitude": 15.561,
        },
    )
    assert site_response.status_code == 201, site_response.text
    site_id = site_response.json()["id"]
    site_asset = (
        db_session.query(Asset)
        .filter(Asset.legacy_source == "site", Asset.legacy_source_id == site_id)
        .one()
    )
    assert site_asset.sector == "ENVIRONMENTAL"
    assert site_asset.workspace_id == workspace_id

    iot_response = client.post(
        "/iot/assets",
        headers=headers,
        json={
            "name": "Water Tank A",
            "site_id": site_id,
            "asset_type": "tank",
            "latitude": -12.853,
            "longitude": 15.562,
        },
    )
    assert iot_response.status_code == 201, iot_response.text
    core_asset_id = iot_response.json()["core_asset_id"]
    core_response = client.get(f"/assets/{core_asset_id}", headers=headers)
    assert core_response.status_code == 200
    assert core_response.json()["parent_asset_id"] == site_asset.id
    assert core_response.json()["asset_type"] == "TANK"
    assert core_response.json()["legacy_source"] == "iot_asset"
