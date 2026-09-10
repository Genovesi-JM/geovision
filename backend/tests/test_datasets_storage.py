from __future__ import annotations

import base64
import hashlib
from io import BytesIO
from urllib.parse import urlsplit
import uuid

import pytest

from app.core.integration import IntegrationFailure, IntegrationResult
from app.core.tokens import create_user_access_token
from app.integrations.storage.azure_blob import AzureBlobStorageProvider
from app.integrations.storage.local import LocalObjectStorageProvider
from app.models import Dataset, DatasetFile, User
from app.modules.datasets.ports import ObjectStorageProvider
from app.routers.datasets import _storage
from app.services.storage import StorageService


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
        "/auth/login",
        json={"email": "teste@admin.com", "password": "123456"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _workspace_asset(client, db_session, prefix: str):
    owner = _user(db_session, prefix)
    organization = client.post(
        "/organizations",
        headers=_headers(owner),
        json={
            "name": f"{prefix} {uuid.uuid4().hex[:8]}",
            "country": "Angola",
            "timezone": "Africa/Luanda",
            "workspace": {
                "name": f"{prefix} workspace",
                "customer_type": "business",
                "sector_focus": "environment",
            },
        },
    )
    assert organization.status_code == 201, organization.text
    body = organization.json()
    workspace_id = body["workspaces"][0]["id"]
    headers = _headers(owner, workspace_id)
    asset = client.post(
        "/assets",
        headers=headers,
        json={
            "sector": "ENVIRONMENTAL",
            "asset_type": "WETLAND",
            "name": f"{prefix} asset",
            "geometry": {"type": "Point", "coordinates": [13.2, -8.9]},
        },
    )
    assert asset.status_code == 201, asset.text
    return owner, headers, body["id"], workspace_id, asset.json()


def _local_storage(tmp_path) -> StorageService:
    return StorageService(
        LocalObjectStorageProvider(
            root=tmp_path / "objects",
            public_base_url="http://testserver",
            signing_secret="phase-12-local-signing-secret",
        )
    )


def _create_dataset(client, headers, asset_id: str, mission_id: str | None = None):
    response = client.post(
        "/datasets/",
        headers=headers,
        json={
            "asset_id": asset_id,
            "mission_id": mission_id,
            "name": "Wetland multispectral capture",
            "dataset_type": "MULTISPECTRAL_IMAGES",
            "provider": "GeoVision Capture",
            "source_reference": "GV-CAPTURE-12",
            "capture_time": "2026-09-10T08:00:00Z",
            "crs": "EPSG:4326",
            "resolution": 4.2,
            "resolution_unit": "cm_per_pixel",
            "processing_level": "RAW",
            "metadata": {"bands": ["red", "green", "nir"]},
            "provenance": {"method": "field_capture"},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_local_stream_upload_download_finalize_archive_and_tombstone(
    client, db_session, tmp_path
):
    owner, headers, organization_id, _, asset = _workspace_asset(
        client, db_session, "dataset-owner"
    )
    storage = _local_storage(tmp_path)
    client.app.dependency_overrides[_storage] = lambda: storage
    try:
        mission = client.post(
            "/missions",
            headers=headers,
            json={
                "asset_id": asset["id"],
                "acquisition_type": "DRONE",
                "title": "Multispectral field capture",
                "drone_details": {
                    "payload_reference": "M3M",
                    "mission_requirements": {},
                    "flight_metadata": {},
                },
            },
        )
        assert mission.status_code == 201, mission.text
        dataset = _create_dataset(client, headers, asset["id"], mission.json()["id"])
        assert dataset["company_id"] == organization_id
        assert dataset["dataset_type"] == "MULTISPECTRAL_IMAGES"
        assert dataset["storage_provider"] == "local"

        upload = client.post(
            f"/datasets/{dataset['id']}/upload",
            headers=headers,
            files={"file": ("capture.tif", b"geovision-raster", "image/tiff")},
            data={"object_area": "raw"},
        )
        assert upload.status_code == 200, upload.text
        uploaded = upload.json()
        assert uploaded["status"] == "uploaded"
        assert uploaded["size_bytes"] == len(b"geovision-raster")
        assert len(uploaded["md5_hash"]) == 32
        assert len(uploaded["sha256_hash"]) == 64
        expected_path = (
            f"organizations/{organization_id}/assets/{asset['id']}/missions/"
            f"{mission.json()['id']}/datasets/{dataset['id']}/raw/"
        )
        assert uploaded["storage_key"].startswith(expected_path)
        assert storage.provider.path_for(uploaded["storage_key"]).read_bytes() == b"geovision-raster"

        finalized = client.post(
            f"/datasets/{dataset['id']}/finalize", headers=headers
        )
        assert finalized.status_code == 200, finalized.text
        assert finalized.json()["status"] == "ready"
        linked_mission = client.get(
            f"/missions/{mission.json()['id']}", headers=headers
        )
        assert {"type": "dataset", "dataset_id": dataset["id"]} in linked_mission.json()[
            "output_refs"
        ]

        download = client.get(
            f"/datasets/{dataset['id']}/files/{uploaded['id']}/download",
            headers=headers,
        )
        assert download.status_code == 200, download.text
        signed = urlsplit(download.json()["download_url"])
        content = client.get(f"{signed.path}?{signed.query}", headers=headers)
        assert content.status_code == 200
        assert content.content == b"geovision-raster"

        disposable = client.post(
            f"/datasets/{dataset['id']}/upload",
            headers=headers,
            files={"file": ("preview.jpg", b"preview", "image/jpeg")},
        )
        assert disposable.status_code == 200, disposable.text
        disposable_path = storage.provider.path_for(disposable.json()["storage_key"])
        removed = client.delete(
            f"/datasets/{dataset['id']}/files/{disposable.json()['id']}",
            headers=headers,
        )
        assert removed.status_code == 200, removed.text
        assert not disposable_path.exists()
        tombstone = db_session.get(DatasetFile, disposable.json()["id"])
        assert tombstone is not None and tombstone.status == "deleted"

        archived = client.delete(f"/datasets/{dataset['id']}", headers=headers)
        assert archived.status_code == 200, archived.text
        assert "retained" in archived.json()["message"]
        assert storage.provider.path_for(uploaded["storage_key"]).is_file()
        assert client.get(f"/datasets/{dataset['id']}", headers=headers).status_code == 404
        listed = client.get(
            "/datasets/", headers=headers, params={"include_archived": True}
        )
        assert listed.status_code == 200
        assert any(row["status"] == "archived" for row in listed.json()["datasets"])

        relational_columns = set(Dataset.__table__.columns.keys())
        assert not {"blob", "binary", "content", "file_bytes"} & relational_columns
        assert db_session.get(Dataset, dataset["id"]).total_size_bytes == len(
            b"geovision-raster"
        )
        assert owner.id
    finally:
        client.app.dependency_overrides.pop(_storage, None)


def test_signed_local_upload_is_short_lived_size_bound_and_tenant_scoped(
    client, db_session, tmp_path
):
    _, headers_a, _, _, asset_a = _workspace_asset(client, db_session, "dataset-a")
    _, headers_b, organization_b, _, _ = _workspace_asset(
        client, db_session, "dataset-b"
    )
    storage = _local_storage(tmp_path)
    client.app.dependency_overrides[_storage] = lambda: storage
    try:
        dataset = _create_dataset(client, headers_a, asset_a["id"])
        assert client.get(f"/datasets/{dataset['id']}", headers=headers_b).status_code == 404
        assert (
            client.get(
                "/datasets/",
                headers=headers_b,
                params={"company_id": dataset["company_id"]},
            ).status_code
            == 404
        )
        reservation = client.post(
            f"/datasets/{dataset['id']}/presigned-url",
            headers=headers_a,
            json={
                "filename": "satellite.tif",
                "content_type": "image/tiff",
                "size_bytes": 6,
                "object_area": "raw",
            },
        )
        assert reservation.status_code == 200, reservation.text
        reserved = reservation.json()
        assert reserved["expires_in"] <= 900
        assert "phase-12-local-signing-secret" not in reserved["upload_url"]
        signed = urlsplit(reserved["upload_url"])

        other_tenant = client.put(
            f"{signed.path}?{signed.query}",
            headers={**headers_b, "Content-Type": "image/tiff"},
            content=b"123456",
        )
        assert other_tenant.status_code == 404
        uploaded = client.put(
            f"{signed.path}?{signed.query}",
            headers={**headers_a, "Content-Type": "image/tiff"},
            content=b"123456",
        )
        assert uploaded.status_code == 204, uploaded.text
        row = db_session.get(DatasetFile, reserved["file_id"])
        db_session.refresh(row)
        assert row.status == "uploaded"
        assert row.sha256_hash is not None

        tampered_query = signed.query.replace("signature=", "signature=0")
        tampered = client.put(
            f"{signed.path}?{tampered_query}",
            headers={**headers_a, "Content-Type": "image/tiff"},
            content=b"123456",
        )
        assert tampered.status_code in {403, 422}

        mismatch = client.post(
            f"/datasets/{dataset['id']}/presigned-url",
            headers=headers_a,
            json={"filename": "wrong-size.tif", "size_bytes": 6},
        ).json()
        mismatch_url = urlsplit(mismatch["upload_url"])
        wrong_size = client.put(
            f"{mismatch_url.path}?{mismatch_url.query}",
            headers=headers_a,
            content=b"12345",
        )
        assert wrong_size.status_code == 422
        assert not storage.provider.path_for(mismatch["storage_key"]).exists()

        confirmation = client.post(
            f"/datasets/{dataset['id']}/presigned-url",
            headers=headers_a,
            json={"filename": "confirm.tif", "size_bytes": 4},
        ).json()
        storage.provider.put_bytes(b"ABCD", confirmation["storage_key"])
        assert (
            client.post(
                f"/datasets/{dataset['id']}/confirm-upload",
                headers=headers_b,
                data={
                    "storage_key": confirmation["storage_key"],
                    "filename": "confirm.tif",
                    "size_bytes": 4,
                },
            ).status_code
            == 404
        )
        confirmed = client.post(
            f"/datasets/{dataset['id']}/confirm-upload",
            headers=headers_a,
            data={
                "storage_key": confirmation["storage_key"],
                "filename": "confirm.tif",
                "size_bytes": 4,
                "sha256_hash": hashlib.sha256(b"ABCD").hexdigest(),
            },
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["sha256_hash"] == hashlib.sha256(b"ABCD").hexdigest()

        traversal = client.post(
            f"/datasets/{dataset['id']}/presigned-url",
            headers=headers_a,
            json={"filename": "../escape.tif", "size_bytes": 3},
        )
        assert traversal.status_code == 422
        empty_reservation = client.post(
            f"/datasets/{dataset['id']}/presigned-url",
            headers=headers_a,
            json={"filename": "empty.tif", "size_bytes": 0},
        )
        assert empty_reservation.status_code == 422
        assert organization_b
    finally:
        client.app.dependency_overrides.pop(_storage, None)


def test_storage_delete_failure_retains_database_reference(
    client, db_session, tmp_path, monkeypatch
):
    _, headers, _, _, asset = _workspace_asset(client, db_session, "delete-safe")
    storage = _local_storage(tmp_path)
    client.app.dependency_overrides[_storage] = lambda: storage
    try:
        dataset = _create_dataset(client, headers, asset["id"])
        upload = client.post(
            f"/datasets/{dataset['id']}/upload",
            headers=headers,
            files={"file": ("keep.tif", b"keep-me", "image/tiff")},
        ).json()

        def failed_delete(key: str):
            del key
            return IntegrationResult.failed(
                provider="local",
                operation="delete",
                failure=IntegrationFailure(
                    code="storage_unavailable",
                    message="storage unavailable",
                    retryable=True,
                ),
            )

        monkeypatch.setattr(storage.provider, "delete", failed_delete)
        response = client.delete(
            f"/datasets/{dataset['id']}/files/{upload['id']}", headers=headers
        )
        assert response.status_code == 502
        db_session.expire_all()
        row = db_session.get(DatasetFile, upload["id"])
        assert row is not None and row.status == "uploaded"
        assert storage.provider.path_for(upload["storage_key"]).is_file()
    finally:
        client.app.dependency_overrides.pop(_storage, None)


def test_failed_stream_upload_keeps_a_reconcilable_database_reference(
    client, db_session, tmp_path, monkeypatch
):
    _, headers, _, _, asset = _workspace_asset(client, db_session, "upload-safe")
    storage = _local_storage(tmp_path)
    client.app.dependency_overrides[_storage] = lambda: storage
    try:
        dataset = _create_dataset(client, headers, asset["id"])

        def failed_upload(*args, **kwargs):
            del args, kwargs
            return IntegrationResult.failed(
                provider="local",
                operation="put_file",
                failure=IntegrationFailure(
                    code="storage_unavailable",
                    message="storage unavailable",
                    retryable=True,
                ),
            )

        monkeypatch.setattr(storage.provider, "put_file", failed_upload)
        response = client.post(
            f"/datasets/{dataset['id']}/upload",
            headers=headers,
            files={"file": ("recoverable.tif", b"tracked", "image/tiff")},
        )
        assert response.status_code == 502
        db_session.expire_all()
        row = (
            db_session.query(DatasetFile)
            .filter(
                DatasetFile.dataset_id == dataset["id"],
                DatasetFile.filename == "recoverable.tif",
            )
            .one()
        )
        assert row.status == "upload_error"
        assert row.storage_key
        assert not storage.provider.path_for(row.storage_key).exists()
    finally:
        client.app.dependency_overrides.pop(_storage, None)


def test_azure_adapter_contract_uses_scoped_sas_without_exposing_credentials():
    class Container:
        def __init__(self):
            self.uploaded = None

        def upload_blob(self, **kwargs):
            self.uploaded = kwargs

    class Service:
        def __init__(self):
            self.container = Container()

        def get_container_client(self, name):
            assert name == "datasets"
            return self.container

    captured = {}

    def sas_factory(**kwargs):
        captured.update(kwargs)
        return "sv=fake&sp=cw&sig=scoped"

    service = Service()
    provider = AzureBlobStorageProvider(
        container="datasets",
        account_url="https://geovision.blob.core.windows.net",
        account_name="geovision",
        account_key="server-only-master-key",
        service_client=service,
        sas_factory=sas_factory,
    )
    assert isinstance(provider, ObjectStorageProvider)
    uploaded = provider.put_file(BytesIO(b"azure-stream"), "org/asset/raw/file.tif")
    assert uploaded.ok and uploaded.value.size_bytes == len(b"azure-stream")
    assert service.container.uploaded["name"] == "org/asset/raw/file.tif"
    signed = provider.presign("org/asset/raw/file.tif", expires_in=300, for_upload=True)
    assert signed.ok
    assert signed.value.startswith(
        "https://geovision.blob.core.windows.net/datasets/org/asset/raw/file.tif?"
    )
    assert "server-only-master-key" not in signed.value
    assert captured["permission"] == "cw"
    assert provider.object_uri("org/asset/raw/file.tif") == (
        "azure://datasets/org/asset/raw/file.tif"
    )

    connection_capture = {}
    connection_provider = AzureBlobStorageProvider(
        container="datasets",
        connection_string=(
            "DefaultEndpointsProtocol=https;AccountName=fromconnection;"
            "AccountKey=connection-secret==;EndpointSuffix=core.windows.net"
        ),
        service_client=service,
        sas_factory=lambda **kwargs: connection_capture.update(kwargs) or "sig=scoped",
    )
    connection_url = connection_provider.presign(
        "org/asset/reports/report 12.pdf", expires_in=60
    )
    assert connection_url.ok
    assert connection_url.value.startswith(
        "https://fromconnection.blob.core.windows.net/datasets/"
        "org/asset/reports/report%2012.pdf?"
    )
    assert "connection-secret" not in connection_url.value
    assert connection_capture["account_key"] == "connection-secret=="


def test_upload_type_and_config_contracts(client, db_session, tmp_path, monkeypatch):
    from app.core.config import Settings
    from app.core.integration import IntegrationConfigurationError
    from app.integrations.storage.factory import create_object_storage_provider

    _, headers, _, _, asset = _workspace_asset(client, db_session, "upload-validation")
    storage = _local_storage(tmp_path)
    client.app.dependency_overrides[_storage] = lambda: storage
    try:
        dataset = _create_dataset(client, headers, asset["id"])
        executable = client.post(
            f"/datasets/{dataset['id']}/upload",
            headers=headers,
            files={"file": ("malware.exe", b"MZ", "application/x-msdownload")},
        )
        assert executable.status_code == 422
        monkeypatch.setattr(
            "app.modules.datasets.services.settings.dataset_direct_upload_max_bytes",
            4,
        )
        oversized = client.post(
            f"/datasets/{dataset['id']}/upload",
            headers=headers,
            files={"file": ("large.tif", b"12345", "image/tiff")},
        )
        assert oversized.status_code == 413
    finally:
        client.app.dependency_overrides.pop(_storage, None)

    local = create_object_storage_provider(
        Settings(
            _env_file=None,
            object_storage_provider="local",
            local_storage_root=tmp_path / "factory-local",
            secret_key="local-signing-secret-that-is-long-enough",
        )
    )
    assert local.provider_name == "local"
    with pytest.raises(IntegrationConfigurationError, match="incomplete"):
        create_object_storage_provider(
            Settings(
                _env_file=None,
                object_storage_provider="azure_blob",
                azure_storage_account_url="https://example.blob.core.windows.net",
                azure_storage_account_name="example",
                azure_storage_account_key=None,
            )
        )
    account_key = base64.b64encode(b"x" * 32).decode()
    azure = create_object_storage_provider(
        Settings(
            _env_file=None,
            object_storage_provider="azure_blob",
            azure_storage_account_url="https://example.blob.core.windows.net",
            azure_storage_account_name="example",
            azure_storage_account_key=account_key,
        )
    )
    assert azure.provider_name == "azure_blob"
    actual_sdk_url = azure.presign("org/asset/raw/sdk.tif", 60, for_upload=True)
    assert actual_sdk_url.ok
    assert account_key not in actual_sdk_url.value


def test_legacy_admin_dataset_routes_create_canonical_records_and_archive_safely(
    client, db_session, monkeypatch
):
    monkeypatch.setattr("app.routers.admin.settings.object_storage_provider", "local")
    headers = _admin_headers(client)
    suffix = uuid.uuid4().hex[:8]
    company = client.post(
        "/admin/companies",
        headers=headers,
        json={
            "name": f"Dataset admin {suffix}",
            "email": f"dataset-admin-{suffix}@example.com",
            "sectors": ["environment"],
        },
    )
    assert company.status_code == 200, company.text
    site = client.post(
        f"/admin/companies/{company.json()['id']}/sites",
        headers=headers,
        json={
            "name": "Admin wetland",
            "country": "Angola",
            "sector": "environment",
        },
    )
    assert site.status_code == 200, site.text

    unsafe = client.post(
        f"/admin/sites/{site.json()['id']}/datasets",
        headers=headers,
        json={
            "name": "Unsafe metadata",
            "data_type": "orthomosaic",
            "metadata": {"api_key": "must-not-be-stored"},
        },
    )
    assert unsafe.status_code == 422

    created = client.post(
        f"/admin/sites/{site.json()['id']}/datasets",
        headers=headers,
        json={
            "name": "Admin orthomosaic",
            "description": "Legacy route, canonical record",
            "data_type": "orthomosaic",
            "source": "admin-import-12",
            "metadata": {"crs": "EPSG:4326"},
        },
    )
    assert created.status_code == 200, created.text
    dataset_id = created.json()["id"]
    db_session.expire_all()
    row = db_session.get(Dataset, dataset_id)
    assert row is not None
    assert row.dataset_type == "ORTHOMOSAIC"
    assert row.asset_id is not None
    assert row.storage_provider == "local"
    assert row.status == "uploading"

    tracked = DatasetFile(
        id=str(uuid.uuid4()),
        dataset_id=row.id,
        filename="admin.tif",
        storage_key=f"organizations/{row.company_id}/admin.tif",
        storage_provider="local",
        storage_uri=f"local://organizations/{row.company_id}/admin.tif",
        object_area="raw",
        file_size=12,
        status="uploaded",
    )
    row.file_count = 1
    row.total_size_bytes = 12
    db_session.add(tracked)
    db_session.commit()

    listed = client.get(
        "/admin/datasets",
        headers=headers,
        params={"data_type": "orthomosaic"},
    )
    assert listed.status_code == 200, listed.text
    assert any(item["id"] == dataset_id for item in listed.json())

    archived = client.delete(f"/admin/datasets/{dataset_id}", headers=headers)
    assert archived.status_code == 200, archived.text
    assert "retained" in archived.json()["message"]
    db_session.expire_all()
    assert db_session.get(Dataset, dataset_id).status == "archived"
    assert db_session.get(DatasetFile, tracked.id).status == "uploaded"
