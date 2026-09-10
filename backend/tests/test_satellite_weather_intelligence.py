from __future__ import annotations

import base64
from datetime import datetime, timedelta
import json
from pathlib import Path
import uuid

import httpx
import pytest

from app.core.config import Settings, settings
from app.core.event_names import EventNames
from app.core.time import utc_now
from app.core.tokens import create_user_access_token
from app.integrations.satellite.copernicus import CopernicusStacProvider
from app.integrations.satellite.fake import DeterministicSatelliteProvider
from app.integrations.storage.local import LocalObjectStorageProvider
from app.integrations.weather.aemet import AemetOpenDataProvider
from app.integrations.weather.fake import DeterministicWeatherProvider
from app.models import (
    Account,
    Acquisition,
    Asset,
    Company,
    Dataset,
    EventOutbox,
    IntelligenceAcquisition,
    SatelliteScene,
    User,
    WeatherObservation,
)
from app.modules.datasets.ports import SatelliteSearchRequest
from app.modules.monitoring.intelligence_domain import IntelligenceError, IntelligenceKind
from app.modules.monitoring.intelligence_schemas import (
    IntelligenceScheduleCreate,
    SatelliteIntelligenceRequest,
    WeatherIntelligenceRequest,
)
from app.modules.monitoring.intelligence_services import (
    acquire_satellite_for_asset,
    acquire_weather_for_asset,
    create_intelligence_schedule,
    execute_intelligence_acquisition,
    execute_intelligence_schedule,
)
from app.modules.monitoring.ports import WeatherRequest
from app.services.storage import StorageService


def _config(tmp_path: Path, **values) -> Settings:
    defaults = dict(
        _env_file=None,
        satellite_provider="fake",
        weather_provider="fake",
        local_storage_root=tmp_path / "configured-objects",
        intelligence_retry_initial_seconds=0,
        intelligence_retry_max_seconds=0,
        satellite_cache_ttl_seconds=3600,
        weather_cache_ttl_seconds=600,
    )
    defaults.update(values)
    return Settings(**defaults)


def _asset(db, *, longitude: float = -3.7, latitude: float = 40.42):
    suffix = uuid.uuid4().hex
    actor = db.query(User).filter(User.email == "teste@admin.com").one()
    organization = Company(
        name=f"Intelligence {suffix[:8]}",
        email=f"intelligence-{suffix}@example.com",
        status="active",
    )
    db.add(organization)
    db.flush()
    workspace = Account(
        organization_id=organization.id,
        name="Intelligence workspace",
        sector_focus="agriculture",
        entity_type="company",
        customer_type="business",
        dashboard_profile="business",
        use_cases="[]",
        modules_enabled="[]",
    )
    db.add(workspace)
    db.flush()
    geometry = {
        "type": "Polygon",
        "coordinates": [
            [
                [longitude - 0.01, latitude - 0.01],
                [longitude + 0.01, latitude - 0.01],
                [longitude + 0.01, latitude + 0.01],
                [longitude - 0.01, latitude - 0.01],
            ]
        ],
    }
    asset = Asset(
        organization_id=organization.id,
        workspace_id=workspace.id,
        sector="AGRICULTURE",
        asset_type="FARM",
        name="Monitored field",
        status="active",
        geometry_geojson=json.dumps(geometry),
        bbox_min_x=longitude - 0.01,
        bbox_min_y=latitude - 0.01,
        bbox_max_x=longitude + 0.01,
        bbox_max_y=latitude + 0.01,
        centroid_latitude=latitude,
        centroid_longitude=longitude,
        metadata_json="{}",
    )
    db.add(asset)
    db.commit()
    return actor, organization, workspace, asset


def _storage(tmp_path: Path) -> StorageService:
    return StorageService(
        LocalObjectStorageProvider(
            root=tmp_path / "objects",
            public_base_url="http://testserver",
            signing_secret="intelligence-storage-test-key",
        )
    )


def test_satellite_results_become_datasets_and_repeat_requests_use_cache(
    db_session, tmp_path
):
    actor, _, _, asset = _asset(db_session)
    provider = DeterministicSatelliteProvider()
    config = _config(tmp_path)
    request = SatelliteIntelligenceRequest(asset_id=asset.id, lookback_days=10)

    run, cache_hit = acquire_satellite_for_asset(
        db_session,
        asset=asset,
        data=request,
        actor_user_id=actor.id,
        provider=provider,
        storage=_storage(tmp_path),
        config=config,
    )

    assert cache_hit is False
    assert run.status == "COMPLETED"
    assert provider.search_calls == 1
    scene = db_session.query(SatelliteScene).filter_by(asset_id=asset.id).one()
    dataset = db_session.get(Dataset, scene.dataset_id)
    acquisition = db_session.get(Acquisition, run.acquisition_id)
    assert dataset is not None
    assert dataset.dataset_type == "SATELLITE_IMAGE"
    assert dataset.provider_code == "fake"
    assert dataset.capture_date == scene.acquired_at
    assert acquisition is not None and acquisition.acquisition_type == "SATELLITE"
    assert scene.bands_json == '["B02","B03","B04","B08"]'
    assert "catalog_standard" in scene.provenance_json
    assert {
        EventNames.INTELLIGENCE_ACQUISITION_REQUESTED,
        EventNames.SATELLITE_ACQUISITION_COMPLETED,
        EventNames.DATASET_READY,
    }.issubset({row.event_type for row in db_session.query(EventOutbox).all()})

    repeated, cache_hit = acquire_satellite_for_asset(
        db_session,
        asset=asset,
        data=request,
        actor_user_id=actor.id,
        provider=provider,
        storage=_storage(tmp_path),
        config=config,
    )
    assert cache_hit is True
    assert repeated.id == run.id
    assert provider.search_calls == 1


def test_satellite_download_request_reports_assets_missing_from_scene(db_session, tmp_path):
    actor, _, _, asset = _asset(db_session)
    config = _config(tmp_path, satellite_download_assets_enabled=True)

    run, cache_hit = acquire_satellite_for_asset(
        db_session,
        asset=asset,
        data=SatelliteIntelligenceRequest(
            asset_id=asset.id,
            download_asset_keys=["not-advertised"],
        ),
        actor_user_id=actor.id,
        provider=DeterministicSatelliteProvider(),
        storage=_storage(tmp_path),
        config=config,
    )

    assert cache_hit is False
    assert run.status == "COMPLETED"
    assert json.loads(run.result_summary_json)["download_warnings"] == [
        {"asset_key": "not-advertised", "code": "asset_not_advertised"}
    ]
    dataset = db_session.get(Dataset, json.loads(run.dataset_ids_json)[0])
    assert dataset is not None and dataset.quality_status == "WARNING"


def test_known_satellite_scene_can_receive_a_later_opt_in_download(db_session, tmp_path):
    actor, _, _, asset = _asset(db_session)
    provider = DeterministicSatelliteProvider()
    storage = _storage(tmp_path)
    metadata_config = _config(tmp_path, satellite_download_assets_enabled=False)
    download_config = _config(tmp_path, satellite_download_assets_enabled=True)

    first, _ = acquire_satellite_for_asset(
        db_session,
        asset=asset,
        data=SatelliteIntelligenceRequest(asset_id=asset.id),
        actor_user_id=actor.id,
        provider=provider,
        storage=storage,
        config=metadata_config,
    )
    second, _ = acquire_satellite_for_asset(
        db_session,
        asset=asset,
        data=SatelliteIntelligenceRequest(
            asset_id=asset.id,
            download_asset_keys=["thumbnail"],
            force_refresh=True,
        ),
        actor_user_id=actor.id,
        provider=provider,
        storage=storage,
        config=download_config,
    )

    assert second.id != first.id
    assert db_session.query(SatelliteScene).filter_by(asset_id=asset.id).count() == 1
    dataset = db_session.get(Dataset, json.loads(second.dataset_ids_json)[0])
    assert dataset is not None
    assert dataset.file_count == 1
    assert dataset.total_size_bytes == len(b"fixture-jpeg")


def test_weather_results_are_normalized_observations_and_cached(db_session, tmp_path):
    actor, _, _, asset = _asset(db_session)
    provider = DeterministicWeatherProvider()
    config = _config(tmp_path)
    request = WeatherIntelligenceRequest(asset_id=asset.id)

    run, cache_hit = acquire_weather_for_asset(
        db_session,
        asset=asset,
        data=request,
        actor_user_id=actor.id,
        provider=provider,
        config=config,
    )

    assert cache_hit is False
    assert run.status == "COMPLETED"
    observations = (
        db_session.query(WeatherObservation)
        .filter(WeatherObservation.asset_id == asset.id)
        .all()
    )
    assert {item.metric for item in observations} == {
        "air_temperature",
        "relative_humidity",
        "precipitation",
        "wind_speed",
    }
    assert {item.unit for item in observations} >= {"degC", "%", "mm", "m/s"}
    dataset = db_session.get(Dataset, observations[0].dataset_id)
    acquisition = db_session.get(Acquisition, run.acquisition_id)
    assert dataset is not None and dataset.dataset_type == "WEATHER_DATA"
    assert acquisition is not None and acquisition.acquisition_type == "THIRD_PARTY_DATA"

    repeated, cache_hit = acquire_weather_for_asset(
        db_session,
        asset=asset,
        data=request,
        actor_user_id=actor.id,
        provider=provider,
        config=config,
    )
    assert cache_hit is True
    assert repeated.id == run.id
    assert provider.observation_calls == 1


def test_retryable_provider_failure_is_visible_and_recoverable(db_session, tmp_path):
    actor, _, _, asset = _asset(db_session)
    config = _config(tmp_path, intelligence_max_attempts=2)
    failed, _ = acquire_satellite_for_asset(
        db_session,
        asset=asset,
        data=SatelliteIntelligenceRequest(asset_id=asset.id),
        actor_user_id=actor.id,
        provider=DeterministicSatelliteProvider(fail=True),
        storage=_storage(tmp_path),
        config=config,
    )
    assert failed.status == "RETRY_WAIT"
    assert failed.error_code == "fixture_failure"
    failed.next_attempt_at = utc_now()
    db_session.commit()

    execute_intelligence_acquisition(
        db_session,
        failed,
        satellite_provider=DeterministicSatelliteProvider(),
        storage=_storage(tmp_path),
        config=config,
    )
    assert failed.status == "COMPLETED"
    assert failed.attempt_count == 2
    assert failed.error_code is None


def test_recurring_schedule_runs_through_same_service_boundary(db_session, tmp_path):
    actor, _, _, asset = _asset(db_session)
    config = _config(tmp_path)
    schedule = create_intelligence_schedule(
        db_session,
        actor=actor,
        config=config,
        data=IntelligenceScheduleCreate(
            asset_id=asset.id,
            kind=IntelligenceKind.SATELLITE,
            provider="fake",
            cadence_minutes=10080,
            lookback_days=7,
            options={"max_cloud_cover_percent": 30, "limit": 3},
        ),
    )
    before = schedule.next_run_at
    satellite_provider = DeterministicSatelliteProvider()
    run = execute_intelligence_schedule(
        db_session,
        schedule,
        satellite_provider_resolver=lambda _: satellite_provider,
        weather_provider_resolver=lambda _: DeterministicWeatherProvider(),
        storage=_storage(tmp_path),
        config=config,
    )

    assert run.status == "COMPLETED"
    assert run.schedule_id == schedule.id
    assert schedule.last_success_at is not None
    assert schedule.next_run_at > before
    assert schedule.next_run_at > utc_now() + timedelta(days=6)

    same = create_intelligence_schedule(
        db_session,
        actor=actor,
        config=config,
        data=IntelligenceScheduleCreate(
            asset_id=asset.id,
            kind=IntelligenceKind.SATELLITE,
            provider="fake",
        ),
    )
    assert same.id == schedule.id


def test_aemet_contract_fetches_ephemeral_data_url_and_selects_nearest_station():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/api/observacion/convencional/todas"):
            assert request.headers["api_key"] == "aemet-test-secret"
            return httpx.Response(
                200,
                json={
                    "descripcion": "exito",
                    "estado": 200,
                    "datos": "https://opendata.aemet.es/opendata/sh/temporary-data",
                    "metadatos": "https://opendata.aemet.es/opendata/sh/metadata",
                },
            )
        assert request.url.path.endswith("/opendata/sh/temporary-data")
        return httpx.Response(
            200,
            json=[
                {
                    "idema": "MAD1",
                    "ubi": "Madrid Test",
                    "lat": 40.41,
                    "lon": -3.69,
                    "alt": 650,
                    "fint": "2026-09-10T01:00:00+0000",
                    "ta": "21,5",
                    "hr": 55,
                    "prec": "Ip",
                    "vv": 3.2,
                },
                {
                    "idema": "FAR1",
                    "ubi": "Far Station",
                    "lat": 42.0,
                    "lon": -5.0,
                    "fint": "2026-09-10T01:00:00+0000",
                    "ta": 12,
                },
            ],
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = AemetOpenDataProvider(
        base_url="https://opendata.aemet.es/opendata",
        api_key="aemet-test-secret",
        client=client,
        sleeper=lambda _: None,
    )
    result = provider.observations(
        WeatherRequest(
            latitude=40.42,
            longitude=-3.70,
            starts_at=datetime(2026, 9, 9),
            ends_at=datetime(2026, 9, 11),
            max_distance_km=100,
        )
    )

    assert result.ok and result.value is not None
    assert len(calls) == 2
    snapshot = result.value[0]
    assert snapshot.source_reference == "MAD1"
    metrics = {item.metric: item.value for item in snapshot.metrics}
    assert metrics["air_temperature"] == 21.5
    assert metrics["precipitation"] == 0.0
    assert snapshot.distance_km is not None and snapshot.distance_km < 5


def test_copernicus_stac_contract_normalizes_provenance_and_downloads_allowlisted_asset():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/v1/search"):
            body = json.loads(request.content)
            assert body["collections"] == ["sentinel-2-l2a"]
            assert body["intersects"]["type"] == "Polygon"
            assert body["query"]["eo:cloud_cover"] == {"lte": 25.0}
            return httpx.Response(
                200,
                json={
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "id": "S2_TEST_SCENE",
                            "collection": "sentinel-2-l2a",
                            "bbox": [-3.8, 40.3, -3.6, 40.5],
                            "geometry": {
                                "type": "Polygon",
                                "coordinates": [[[-3.8, 40.3], [-3.6, 40.3], [-3.8, 40.3]]],
                            },
                            "properties": {
                                "datetime": "2026-09-08T10:15:00Z",
                                "published": "2026-09-08T12:00:00Z",
                                "eo:cloud_cover": 3.5,
                                "platform": "sentinel-2c",
                                "proj:code": "EPSG:32630",
                            },
                            "assets": {
                                "B04_10m": {
                                    "href": "s3://eodata/example.jp2",
                                    "alternate": {
                                        "https": {
                                            "href": "https://download.dataspace.copernicus.eu/example.jp2?signed=discarded",
                                            "auth:refs": ["oidc"],
                                        }
                                    },
                                    "type": "image/jp2",
                                    "roles": ["data", "reflectance", "gsd:10m"],
                                    "bands": [{"name": "B04"}],
                                }
                            },
                            "links": [
                                {
                                    "rel": "self",
                                    "href": "https://stac.dataspace.copernicus.eu/v1/items/S2_TEST_SCENE?token=discarded",
                                }
                            ],
                        }
                    ],
                },
            )
        assert request.url.host == "download.dataspace.copernicus.eu"
        assert request.headers["authorization"] == "Bearer copernicus-test-token"
        assert request.url.query == b""
        return httpx.Response(
            200,
            content=b"jp2-content",
            headers={"Content-Type": "image/jp2", "Content-Length": "11"},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = CopernicusStacProvider(
        base_url="https://stac.dataspace.copernicus.eu/v1",
        access_token="copernicus-test-token",
        client=client,
        sleeper=lambda _: None,
    )
    search = provider.search(
        SatelliteSearchRequest(
            geometry={
                "type": "Polygon",
                "coordinates": [[[-3.8, 40.3], [-3.6, 40.3], [-3.8, 40.3]]],
            },
            starts_at=datetime(2026, 9, 1),
            ends_at=datetime(2026, 9, 10),
            max_cloud_cover_percent=25,
            limit=2,
        )
    )
    assert search.ok and search.value is not None
    scene = search.value[0]
    assert scene.provider_reference == "S2_TEST_SCENE"
    assert scene.resolution_meters == 10
    assert scene.bands == ("B04",)
    assert "?" not in scene.assets[0].href
    assert "?" not in (scene.source_link or "")

    download = provider.download_asset(scene, "B04_10m", max_bytes=100)
    assert download.ok and download.value is not None
    assert download.value.content == b"jp2-content"
    assert len(requests) == 2


def test_aemet_rejects_non_spanish_asset_before_provider_call(db_session, tmp_path):
    actor, _, _, asset = _asset(db_session, longitude=13.2, latitude=-8.8)
    try:
        acquire_weather_for_asset(
            db_session,
            asset=asset,
            data=WeatherIntelligenceRequest(asset_id=asset.id),
            actor_user_id=actor.id,
            provider=None,
            config=_config(tmp_path, weather_provider="aemet", aemet_api_key="test-key"),
        )
    except IntelligenceError as exc:
        assert exc.code == "provider_coverage_mismatch"
    else:
        raise AssertionError("AEMET coverage guard did not reject an Angolan asset")


def test_intelligence_configuration_redacts_secrets_and_rejects_fake_deployment(tmp_path):
    config = _config(
        tmp_path,
        copernicus_access_token="copernicus-sensitive-token",
        aemet_api_key="aemet-sensitive-key",
    )
    dumped = config.model_dump()
    assert dumped["copernicus_access_token"] == "[REDACTED]"
    assert dumped["aemet_api_key"] == "[REDACTED]"

    production_values = {
        "_env_file": None,
        "env": "prod",
        "secret_key": "intelligence-production-secret-key-000001",
        "encryption_key": base64.urlsafe_b64encode(b"i" * 32).decode(),
        "frontend_base": "https://geovision.example",
        "backend_base": "https://api.geovision.example",
    }
    with pytest.raises(ValueError, match="fake satellite"):
        Settings(**production_values, satellite_provider="fake")
    with pytest.raises(ValueError, match="fake weather"):
        Settings(**production_values, weather_provider="fake")


def _user(db_session, prefix: str) -> User:
    user = User(
        email=f"{prefix}-{uuid.uuid4().hex}@example.com",
        password_hash=None,
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


def _organization(client, owner: User, name: str) -> tuple[str, str]:
    response = client.post(
        "/organizations",
        headers=_headers(owner),
        json={
            "name": name,
            "country": "Spain",
            "timezone": "Europe/Madrid",
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


def test_intelligence_api_is_tenant_scoped_and_exposes_cache_status(
    client, db_session, monkeypatch
):
    monkeypatch.setattr(settings, "satellite_provider", "fake")
    owner = _user(db_session, "intelligence-owner")
    _, workspace_id = _organization(client, owner, "Satellite API")
    headers = _headers(owner, workspace_id)
    asset_response = client.post(
        "/assets",
        headers=headers,
        json={
            "sector": "AGRICULTURE",
            "asset_type": "FARM",
            "name": "Madrid API field",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[-3.71, 40.41], [-3.69, 40.41], [-3.69, 40.43], [-3.71, 40.41]]],
            },
            "metadata": {},
        },
    )
    assert asset_response.status_code == 201, asset_response.text
    asset_id = asset_response.json()["id"]

    first = client.post(
        "/intelligence/satellite/search",
        headers=headers,
        json={"asset_id": asset_id, "lookback_days": 5},
    )
    assert first.status_code == 200, first.text
    assert first.json()["acquisition"]["status"] == "COMPLETED"
    assert first.json()["acquisition"]["cache_hit"] is False
    repeated = client.post(
        "/intelligence/satellite/search",
        headers=headers,
        json={"asset_id": asset_id, "lookback_days": 5},
    )
    assert repeated.status_code == 200
    assert repeated.json()["acquisition"]["cache_hit"] is True

    intruder = _user(db_session, "intelligence-intruder")
    _, intruder_workspace = _organization(client, intruder, "Other Tenant")
    hidden = client.get(
        f"/intelligence/assets/{asset_id}/satellite",
        headers=_headers(intruder, intruder_workspace),
    )
    assert hidden.status_code == 404
