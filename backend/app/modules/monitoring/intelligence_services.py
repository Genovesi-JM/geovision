"""Cached satellite/weather acquisition, persistence, retries, and schedules."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import json
import logging
from pathlib import Path
import socket
from typing import Any, Callable, Mapping
import uuid

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.event_names import EventNames
from app.core.integration import IntegrationResult, sanitize_integration_message
from app.core.observability import get_logger, log_event
from app.core.time import utc_now
from app.models import (
    Acquisition,
    Asset,
    Dataset,
    DatasetFile,
    IntelligenceAcquisition,
    IntelligenceSchedule,
    SatelliteScene,
    User,
    WeatherObservation,
)
from app.modules.assets.services import get_asset
from app.modules.datasets.domain import DatasetStatus, ProcessingLevel, QualityStatus
from app.modules.datasets.ports import (
    SatelliteProvider,
    SatelliteSceneDescriptor,
    SatelliteSearchRequest,
)
from app.modules.identity.domain import AuthorizationContext
from app.modules.monitoring.intelligence_domain import (
    IntelligenceError,
    IntelligenceKind,
    IntelligenceScheduleStatus,
    IntelligenceStatus,
    aemet_covers,
    json_array,
    json_dump,
    json_object,
    provider_code,
    request_fingerprint,
    utc_naive,
)
from app.modules.monitoring.intelligence_schemas import (
    IntelligenceScheduleCreate,
    IntelligenceScheduleUpdate,
    SatelliteIntelligenceRequest,
    WeatherIntelligenceRequest,
)
from app.modules.economics.schemas import ProviderUsageCreate
from app.modules.economics.services import record_provider_usage
from app.modules.monitoring.ports import WeatherProvider, WeatherRequest, WeatherSnapshot
from app.services.event_outbox import enqueue_domain_event
from app.services.storage import StorageService


_NAMESPACE = uuid.UUID("e9bb26de-92ce-44f9-83dc-37ab6f52188b")
logger = get_logger(__name__)
SatelliteProviderResolver = Callable[[str], SatelliteProvider]
WeatherProviderResolver = Callable[[str], WeatherProvider]


def _hash_key(prefix: str, *parts: object) -> str:
    digest = hashlib.sha256(":".join(str(part) for part in parts).encode()).hexdigest()
    return f"{prefix}:{digest}"


def _asset_geometry(asset: Asset) -> dict[str, Any]:
    try:
        value = json.loads(asset.geometry_geojson or "null")
    except (TypeError, ValueError) as exc:
        raise IntelligenceError(
            "asset_geometry_invalid", "Asset geometry is not valid GeoJSON"
        ) from exc
    if not isinstance(value, dict) or value.get("type") not in {
        "Point",
        "MultiPoint",
        "LineString",
        "MultiLineString",
        "Polygon",
        "MultiPolygon",
    }:
        raise IntelligenceError(
            "asset_geometry_required",
            "The asset needs an EPSG:4326 geometry before remote intelligence can run",
        )
    return value


def _asset_center(asset: Asset) -> tuple[float, float]:
    if asset.centroid_latitude is None or asset.centroid_longitude is None:
        _asset_geometry(asset)
        raise IntelligenceError(
            "asset_centroid_required",
            "The asset needs a calculated centroid before weather acquisition can run",
        )
    return float(asset.centroid_latitude), float(asset.centroid_longitude)


def _event(
    db: Session,
    *,
    name: str,
    row: IntelligenceAcquisition,
    key: str,
    payload: Mapping[str, Any] | None = None,
) -> None:
    enqueue_domain_event(
        db,
        name=name,
        aggregate_type="intelligence_acquisition",
        aggregate_id=row.id,
        idempotency_key=key,
        correlation_id=row.id,
        payload={
            "intelligence_acquisition_id": row.id,
            "organization_id": row.organization_id,
            "workspace_id": row.workspace_id,
            "asset_id": row.asset_id,
            "kind": row.kind,
            "provider": row.provider_code,
            **dict(payload or {}),
        },
    )


def _dataset_event(
    db: Session,
    *,
    dataset: Dataset,
    name: str,
    key: str,
    payload: Mapping[str, Any] | None = None,
) -> None:
    enqueue_domain_event(
        db,
        name=name,
        aggregate_type="dataset",
        aggregate_id=dataset.id,
        idempotency_key=key,
        correlation_id=dataset.id,
        payload={
            "dataset_id": dataset.id,
            "organization_id": dataset.company_id,
            "workspace_id": dataset.workspace_id,
            "asset_id": dataset.asset_id,
            "mission_id": dataset.mission_id,
            **dict(payload or {}),
        },
    )


def _failure_details(result: IntegrationResult[Any]) -> tuple[str, str, bool]:
    failure = result.failure
    if failure is None:
        return "provider_failed", "The provider did not return a usable result", False
    return failure.code, failure.message, failure.retryable


def _cache_lookup(
    db: Session,
    *,
    asset: Asset,
    kind: str,
    provider: str,
    fingerprint: str,
    now: datetime,
) -> IntelligenceAcquisition | None:
    return (
        db.query(IntelligenceAcquisition)
        .filter(
            IntelligenceAcquisition.organization_id == asset.organization_id,
            IntelligenceAcquisition.asset_id == asset.id,
            IntelligenceAcquisition.kind == kind,
            IntelligenceAcquisition.provider_code == provider,
            IntelligenceAcquisition.request_fingerprint == fingerprint,
            IntelligenceAcquisition.status == IntelligenceStatus.COMPLETED.value,
            IntelligenceAcquisition.cache_expires_at.isnot(None),
            IntelligenceAcquisition.cache_expires_at > now,
        )
        .order_by(IntelligenceAcquisition.completed_at.desc())
        .first()
    )


def _new_run(
    db: Session,
    *,
    asset: Asset,
    kind: str,
    provider: str,
    request: Mapping[str, Any],
    fingerprint: str,
    actor_user_id: str | None,
    schedule_id: str | None,
    config: Settings,
) -> IntelligenceAcquisition:
    now = utc_now()
    row = IntelligenceAcquisition(
        id=str(uuid.uuid4()),
        organization_id=asset.organization_id,
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        schedule_id=schedule_id,
        kind=kind,
        provider_code=provider,
        request_fingerprint=fingerprint,
        request_json=json_dump(dict(request)),
        result_summary_json="{}",
        dataset_ids_json="[]",
        status=IntelligenceStatus.REQUESTED.value,
        attempt_count=0,
        max_attempts=config.intelligence_max_attempts,
        next_attempt_at=now,
        idempotency_key=_hash_key(
            "intelligence",
            kind,
            asset.id,
            provider,
            fingerprint,
            schedule_id or uuid.uuid4(),
        ),
        created_by_user_id=actor_user_id,
        lifecycle_version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    _event(
        db,
        name=EventNames.INTELLIGENCE_ACQUISITION_REQUESTED,
        row=row,
        key=f"intelligence:{row.id}:requested",
    )
    return row


def _retry_delay(row: IntelligenceAcquisition, config: Settings) -> float:
    return min(
        config.intelligence_retry_initial_seconds * (2 ** max(0, row.attempt_count - 1)),
        config.intelligence_retry_max_seconds,
    )


def _mark_failure(
    db: Session,
    row: IntelligenceAcquisition,
    *,
    code: str,
    message: str,
    retryable: bool,
    config: Settings,
) -> None:
    now = utc_now()
    row.error_code = code[:100]
    row.error_message = sanitize_integration_message(message)[:2000]
    row.claimed_by = None
    row.claimed_at = None
    row.updated_at = now
    row.lifecycle_version += 1
    if retryable and row.attempt_count < row.max_attempts:
        row.status = IntelligenceStatus.RETRY_WAIT.value
        row.next_attempt_at = now + timedelta(seconds=_retry_delay(row, config))
    else:
        row.status = IntelligenceStatus.FAILED.value
        row.next_attempt_at = None
        row.completed_at = now
        _event(
            db,
            name=EventNames.INTELLIGENCE_ACQUISITION_FAILED,
            row=row,
            key=f"intelligence:{row.id}:failed:{row.attempt_count}",
            payload={"error_code": row.error_code, "attempts": row.attempt_count},
        )
    log_event(
        logger,
        logging.WARNING if row.status == IntelligenceStatus.RETRY_WAIT.value else logging.ERROR,
        "intelligence.acquisition.failed",
        organization_id=row.organization_id,
        workspace_id=row.workspace_id,
        asset_id=row.asset_id,
        mission_id=row.acquisition_id,
        intelligence_acquisition_id=row.id,
        provider=row.provider_code,
        kind=row.kind,
        error_code=row.error_code,
        retryable=row.status == IntelligenceStatus.RETRY_WAIT.value,
        attempt_count=row.attempt_count,
    )
    db.commit()


def _ensure_acquisition(
    db: Session,
    *,
    row: IntelligenceAcquisition,
    captured_at: datetime | None,
    provider_version: str,
) -> Acquisition:
    acquisition = db.get(Acquisition, row.acquisition_id) if row.acquisition_id else None
    if acquisition is not None:
        provenance = json_object(acquisition.provenance_json)
        if not provenance.get("adapter_version"):
            provenance["adapter_version"] = provider_version
            acquisition.provenance_json = json_dump(provenance)
            acquisition.updated_at = utc_now()
        return acquisition
    now = utc_now()
    acquisition = Acquisition(
        id=str(uuid.uuid5(_NAMESPACE, f"{row.id}:canonical-acquisition")),
        acquisition_number=f"INT-{row.kind[:3]}-{row.id[:12].upper()}",
        organization_id=row.organization_id,
        workspace_id=row.workspace_id,
        asset_id=row.asset_id,
        acquisition_type=(
            "SATELLITE"
            if row.kind == IntelligenceKind.SATELLITE.value
            else "THIRD_PARTY_DATA"
        ),
        title=(
            "Satellite monitoring acquisition"
            if row.kind == IntelligenceKind.SATELLITE.value
            else "Weather observation acquisition"
        ),
        description="Automated provider-neutral remote intelligence acquisition",
        state="COMPLETED",
        provider_code=row.provider_code,
        provider_reference=row.id,
        provenance_json=json_dump(
            {
                "intelligence_acquisition_id": row.id,
                "provider": row.provider_code,
                "adapter_version": provider_version,
                "request_fingerprint": row.request_fingerprint,
            }
        ),
        metadata_json=json_dump({"kind": row.kind}),
        output_refs_json="[]",
        started_at=row.started_at or now,
        captured_at=captured_at,
        completed_at=now,
        lifecycle_version=1,
        created_by_user_id=row.created_by_user_id,
        updated_by_user_id=row.created_by_user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(acquisition)
    row.acquisition_id = acquisition.id
    # Some worker sessions intentionally disable autoflush. Persist the
    # canonical mission before provider-usage validation resolves its FK scope.
    db.flush()
    enqueue_domain_event(
        db,
        name=EventNames.ACQUISITION_CREATED,
        aggregate_type="acquisition",
        aggregate_id=acquisition.id,
        correlation_id=row.id,
        idempotency_key=f"acquisition:{acquisition.id}:created",
        payload={
            "acquisition_id": acquisition.id,
            "organization_id": row.organization_id,
            "workspace_id": row.workspace_id,
            "asset_id": row.asset_id,
            "acquisition_type": acquisition.acquisition_type,
            "state": acquisition.state,
        },
    )
    return acquisition


def _append_outputs(acquisition: Acquisition, dataset_ids: list[str]) -> None:
    outputs = json_array(acquisition.output_refs_json)
    known = {
        str(item.get("dataset_id"))
        for item in outputs
        if isinstance(item, dict) and item.get("dataset_id")
    }
    for dataset_id in dataset_ids:
        if dataset_id not in known:
            outputs.append({"type": "dataset", "dataset_id": dataset_id})
    acquisition.output_refs_json = json_dump(outputs)
    acquisition.updated_at = utc_now()


def _satellite_assets(scene: SatelliteSceneDescriptor) -> dict[str, Any]:
    return {
        asset.key: {
            "href": asset.href,
            "media_type": asset.media_type,
            "title": asset.title,
            "roles": list(asset.roles),
            "bands": list(asset.bands),
            "size_bytes": asset.size_bytes,
            "requires_authentication": asset.requires_authentication,
        }
        for asset in scene.assets
    }


def _new_satellite_dataset(
    db: Session,
    *,
    row: IntelligenceAcquisition,
    asset: Asset,
    acquisition: Acquisition,
    scene: SatelliteSceneDescriptor,
    provider_version: str,
    storage: StorageService,
    expect_files: bool,
) -> Dataset:
    dataset_id = str(
        uuid.uuid5(
            _NAMESPACE,
            f"satellite:{asset.id}:{row.provider_code}:{scene.provider_reference}",
        )
    )
    dataset = db.get(Dataset, dataset_id)
    if dataset is not None:
        return dataset
    now = utc_now()
    dataset = Dataset(
        id=dataset_id,
        company_id=row.organization_id,
        workspace_id=row.workspace_id,
        site_id=asset.legacy_source_id if asset.legacy_source == "site" else None,
        asset_id=asset.id,
        mission_id=acquisition.id,
        name=f"{asset.name} — {scene.collection} — {scene.acquired_at.date().isoformat()}",
        description="Satellite scene discovered through the GeoVision provider boundary",
        source_tool=row.provider_code,
        data_type="satellite_image",
        source="remote_satellite_catalogue",
        dataset_type="SATELLITE_IMAGE",
        provider_code=row.provider_code,
        source_reference=scene.provider_reference,
        storage_provider=storage.provider_name,
        crs=scene.crs,
        resolution=scene.resolution_meters,
        resolution_unit="m" if scene.resolution_meters else None,
        processing_level=ProcessingLevel.RAW.value,
        quality_status=QualityStatus.PASSED.value,
        provenance_json=json_dump(
            {
                **dict(scene.provenance),
                "provider": row.provider_code,
                "adapter_version": provider_version,
                "intelligence_acquisition_id": row.id,
                "source_link": scene.source_link,
            }
        ),
        status=(DatasetStatus.PROCESSING.value if expect_files else DatasetStatus.READY.value),
        sector=asset.sector,
        capture_date=scene.acquired_at,
        metadata_json=json_dump(
            {
                "collection": scene.collection,
                "cloud_cover_percent": scene.cloud_cover_percent,
                "bands": list(scene.bands),
                "bbox": list(scene.bbox),
                "coverage": dict(scene.geometry) if scene.geometry else None,
                "assets": _satellite_assets(scene),
            }
        ),
        file_count=0,
        total_size_bytes=0,
        lifecycle_version=1,
        created_by_user_id=row.created_by_user_id,
        created_at=now,
        updated_at=now,
        processed_at=None if expect_files else now,
    )
    db.add(dataset)
    _dataset_event(
        db,
        dataset=dataset,
        name=EventNames.DATASET_CREATED,
        key=f"dataset:{dataset.id}:created",
        payload={"dataset_type": dataset.dataset_type, "intelligence_acquisition_id": row.id},
    )
    return dataset


def _download_satellite_assets(
    db: Session,
    *,
    row: IntelligenceAcquisition,
    scene: SatelliteSceneDescriptor,
    dataset: Dataset,
    provider: SatelliteProvider,
    storage: StorageService,
    requested_keys: tuple[str, ...],
    config: Settings,
) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    for asset_key in requested_keys:
        descriptor = next((item for item in scene.assets if item.key == asset_key), None)
        if descriptor is None:
            warnings.append({"asset_key": asset_key, "code": "asset_not_advertised"})
            continue
        file_id = str(uuid.uuid5(_NAMESPACE, f"{dataset.id}:file:{asset_key}"))
        file = db.get(DatasetFile, file_id)
        if file is not None and file.status == "uploaded":
            continue
        result = provider.download_asset(
            scene,
            asset_key,
            max_bytes=config.satellite_max_asset_bytes,
        )
        if not result.ok or result.value is None:
            code, _, _ = _failure_details(result)
            warnings.append({"asset_key": asset_key, "code": code})
            continue
        downloaded = result.value
        filename = Path(downloaded.filename).name
        if file is None:
            key = storage.generate_dataset_key(
                organization_id=row.organization_id,
                asset_id=row.asset_id,
                mission_id=row.acquisition_id,
                dataset_id=dataset.id,
                file_id=file_id,
                area="raw",
                filename=filename,
            )
            file = DatasetFile(
                id=file_id,
                dataset_id=dataset.id,
                filename=filename,
                storage_key=key,
                storage_provider=storage.provider_name,
                storage_uri=storage.object_uri(key),
                object_area="raw",
                file_size=len(downloaded.content),
                mime_type=downloaded.media_type,
                status="pending_upload",
                lifecycle_version=1,
                created_at=utc_now(),
            )
            db.add(file)
            dataset.object_prefix = key.rsplit("/", 1)[0]
            db.commit()
        try:
            stored_key, size, md5_hash, sha256_hash = storage.upload_bytes(
                downloaded.content,
                file.storage_key or "",
                downloaded.media_type,
                {
                    "dataset_id": dataset.id,
                    "intelligence_acquisition_id": row.id,
                    "satellite_asset_key": asset_key,
                },
            )
        except RuntimeError:
            file.status = "rejected"
            file.lifecycle_version += 1
            warnings.append({"asset_key": asset_key, "code": "storage_write_failed"})
            db.commit()
            continue
        file.storage_key = stored_key
        file.storage_uri = storage.object_uri(stored_key)
        file.file_size = size
        file.md5_hash = md5_hash
        file.sha256_hash = sha256_hash
        file.status = "uploaded"
        file.confirmed_at = utc_now()
        file.lifecycle_version += 1
        _dataset_event(
            db,
            dataset=dataset,
            name=EventNames.DATASET_FILE_UPLOADED,
            key=f"dataset-file:{file.id}:uploaded",
            payload={"file_id": file.id, "size_bytes": size},
        )
        db.commit()
    uploaded = (
        db.query(DatasetFile)
        .filter(DatasetFile.dataset_id == dataset.id, DatasetFile.status == "uploaded")
        .all()
    )
    dataset.file_count = len(uploaded)
    dataset.total_size_bytes = sum(item.file_size for item in uploaded)
    dataset.status = DatasetStatus.READY.value
    dataset.quality_status = (
        QualityStatus.WARNING.value if warnings else QualityStatus.PASSED.value
    )
    dataset.processed_at = utc_now()
    dataset.updated_at = utc_now()
    dataset.lifecycle_version += 1
    return warnings


def _register_satellite_results(
    db: Session,
    *,
    row: IntelligenceAcquisition,
    scenes: tuple[SatelliteSceneDescriptor, ...],
    provider: SatelliteProvider,
    storage: StorageService,
    requested_keys: tuple[str, ...],
    config: Settings,
) -> tuple[list[str], list[dict[str, str]]]:
    asset = db.get(Asset, row.asset_id)
    if asset is None:
        raise IntelligenceError("asset_not_found", "Intelligence asset no longer exists")
    captured_at = max((scene.acquired_at for scene in scenes), default=None)
    provider_version = str(
        getattr(provider, "adapter_version", "unavailable-unversioned")
    )
    acquisition = _ensure_acquisition(
        db,
        row=row,
        captured_at=captured_at,
        provider_version=provider_version,
    )
    dataset_ids: list[str] = []
    warnings: list[dict[str, str]] = []
    for scene in scenes:
        existing = (
            db.query(SatelliteScene)
            .filter(
                SatelliteScene.asset_id == asset.id,
                SatelliteScene.provider_code == row.provider_code,
                SatelliteScene.provider_reference == scene.provider_reference,
            )
            .one_or_none()
        )
        if existing is not None:
            dataset = db.get(Dataset, existing.dataset_id)
            if requested_keys and dataset is not None:
                warnings.extend(
                    _download_satellite_assets(
                        db,
                        row=row,
                        scene=scene,
                        dataset=dataset,
                        provider=provider,
                        storage=storage,
                        requested_keys=requested_keys,
                        config=config,
                    )
                )
            dataset_ids.append(existing.dataset_id)
            continue
        dataset = _new_satellite_dataset(
            db,
            row=row,
            asset=asset,
            acquisition=acquisition,
            scene=scene,
            provider_version=provider_version,
            storage=storage,
            expect_files=bool(requested_keys),
        )
        scene_row = SatelliteScene(
            id=str(uuid.uuid5(_NAMESPACE, f"{dataset.id}:scene")),
            organization_id=row.organization_id,
            asset_id=row.asset_id,
            intelligence_acquisition_id=row.id,
            dataset_id=dataset.id,
            provider_code=row.provider_code,
            provider_reference=scene.provider_reference,
            collection=scene.collection,
            acquired_at=scene.acquired_at,
            published_at=scene.published_at,
            cloud_cover_percent=scene.cloud_cover_percent,
            resolution_meters=scene.resolution_meters,
            crs=scene.crs,
            bands_json=json_dump(list(scene.bands)),
            bbox_json=json_dump(list(scene.bbox)),
            coverage_geojson=(json_dump(dict(scene.geometry)) if scene.geometry else None),
            assets_json=json_dump(_satellite_assets(scene)),
            provenance_json=json_dump(dict(scene.provenance)),
            source_link=scene.source_link,
            created_at=utc_now(),
        )
        db.add(scene_row)
        db.flush()
        if requested_keys:
            warnings.extend(
                _download_satellite_assets(
                    db,
                    row=row,
                    scene=scene,
                    dataset=dataset,
                    provider=provider,
                    storage=storage,
                    requested_keys=requested_keys,
                    config=config,
                )
            )
        if dataset.status != DatasetStatus.READY.value:
            dataset.status = DatasetStatus.READY.value
            dataset.processed_at = utc_now()
            dataset.updated_at = utc_now()
            dataset.lifecycle_version += 1
        _dataset_event(
            db,
            dataset=dataset,
            name=EventNames.DATASET_READY,
            key=f"dataset:{dataset.id}:ready:{dataset.lifecycle_version}",
            payload={"intelligence_acquisition_id": row.id},
        )
        dataset_ids.append(dataset.id)
    dataset_ids = list(dict.fromkeys(dataset_ids))
    _append_outputs(acquisition, dataset_ids)
    return dataset_ids, warnings


def _weather_dataset(
    db: Session,
    *,
    row: IntelligenceAcquisition,
    asset: Asset,
    acquisition: Acquisition,
    snapshots: tuple[WeatherSnapshot, ...],
    provider_version: str,
    config: Settings,
) -> Dataset:
    dataset_id = str(uuid.uuid5(_NAMESPACE, f"{row.id}:weather-dataset"))
    dataset = db.get(Dataset, dataset_id)
    if dataset is not None:
        return dataset
    observed_at = max(snapshot.observed_at for snapshot in snapshots)
    now = utc_now()
    dataset = Dataset(
        id=dataset_id,
        company_id=row.organization_id,
        workspace_id=row.workspace_id,
        site_id=asset.legacy_source_id if asset.legacy_source == "site" else None,
        asset_id=asset.id,
        mission_id=acquisition.id,
        name=f"{asset.name} — weather observations — {observed_at.isoformat(timespec='minutes')}",
        description="Normalized weather observations retrieved through GeoVision",
        source_tool=row.provider_code,
        data_type="weather",
        source="remote_weather_provider",
        dataset_type="WEATHER_DATA",
        provider_code=row.provider_code,
        source_reference=row.id,
        storage_provider=config.object_storage_provider,
        processing_level=ProcessingLevel.RAW.value,
        quality_status=QualityStatus.PASSED.value,
        provenance_json=json_dump(
            {
                "provider": row.provider_code,
                "adapter_version": provider_version,
                "intelligence_acquisition_id": row.id,
                "request_fingerprint": row.request_fingerprint,
            }
        ),
        status=DatasetStatus.READY.value,
        sector=asset.sector,
        capture_date=observed_at,
        metadata_json=json_dump(
            {
                "snapshot_count": len(snapshots),
                "source_references": list(
                    dict.fromkeys(snapshot.source_reference for snapshot in snapshots)
                ),
            }
        ),
        file_count=0,
        total_size_bytes=0,
        lifecycle_version=1,
        created_by_user_id=row.created_by_user_id,
        created_at=now,
        updated_at=now,
        processed_at=now,
    )
    db.add(dataset)
    _dataset_event(
        db,
        dataset=dataset,
        name=EventNames.DATASET_CREATED,
        key=f"dataset:{dataset.id}:created",
        payload={"dataset_type": dataset.dataset_type, "intelligence_acquisition_id": row.id},
    )
    _dataset_event(
        db,
        dataset=dataset,
        name=EventNames.DATASET_READY,
        key=f"dataset:{dataset.id}:ready:1",
        payload={"intelligence_acquisition_id": row.id},
    )
    return dataset


def _register_weather_results(
    db: Session,
    *,
    row: IntelligenceAcquisition,
    snapshots: tuple[WeatherSnapshot, ...],
    provider: WeatherProvider,
    config: Settings,
) -> tuple[list[str], int]:
    asset = db.get(Asset, row.asset_id)
    if asset is None:
        raise IntelligenceError("asset_not_found", "Intelligence asset no longer exists")
    captured_at = max((snapshot.observed_at for snapshot in snapshots), default=None)
    provider_version = str(
        getattr(provider, "adapter_version", "unavailable-unversioned")
    )
    acquisition = _ensure_acquisition(
        db,
        row=row,
        captured_at=captured_at,
        provider_version=provider_version,
    )
    existing_rows: list[WeatherObservation] = []
    new_values: list[tuple[WeatherSnapshot, Any]] = []
    for snapshot in snapshots:
        for metric in snapshot.metrics:
            existing = (
                db.query(WeatherObservation)
                .filter(
                    WeatherObservation.asset_id == row.asset_id,
                    WeatherObservation.provider_code == row.provider_code,
                    WeatherObservation.source_reference == snapshot.source_reference,
                    WeatherObservation.observed_at == snapshot.observed_at,
                    WeatherObservation.metric == metric.metric,
                )
                .one_or_none()
            )
            if existing is not None:
                existing_rows.append(existing)
            else:
                new_values.append((snapshot, metric))
    dataset_ids = list(dict.fromkeys(item.dataset_id for item in existing_rows))
    if new_values:
        dataset = _weather_dataset(
            db,
            row=row,
            asset=asset,
            acquisition=acquisition,
            snapshots=snapshots,
            provider_version=provider_version,
            config=config,
        )
        dataset_ids.append(dataset.id)
        for snapshot, metric in new_values:
            identifier = str(
                uuid.uuid5(
                    _NAMESPACE,
                    f"weather:{row.asset_id}:{row.provider_code}:{snapshot.source_reference}:"
                    f"{snapshot.observed_at.isoformat()}:{metric.metric}",
                )
            )
            observation = WeatherObservation(
                id=identifier,
                organization_id=row.organization_id,
                asset_id=row.asset_id,
                intelligence_acquisition_id=row.id,
                dataset_id=dataset.id,
                provider_code=row.provider_code,
                source_reference=snapshot.source_reference,
                source_name=snapshot.source_name,
                observed_at=snapshot.observed_at,
                metric=metric.metric,
                value=metric.value,
                unit=metric.unit,
                quality=metric.quality,
                latitude=snapshot.latitude,
                longitude=snapshot.longitude,
                distance_km=snapshot.distance_km,
                provenance_json=json_dump(dict(snapshot.provenance)),
                created_at=utc_now(),
            )
            db.add(observation)
            enqueue_domain_event(
                db,
                name=EventNames.OBSERVATION_CREATED,
                aggregate_type="weather_observation",
                aggregate_id=observation.id,
                idempotency_key=f"weather-observation:{observation.id}:created",
                correlation_id=row.id,
                payload={
                    "observation_id": observation.id,
                    "dataset_id": dataset.id,
                    "organization_id": row.organization_id,
                    "asset_id": row.asset_id,
                    "metric": observation.metric,
                    "observed_at": observation.observed_at.isoformat(),
                    "provider": row.provider_code,
                },
            )
    dataset_ids = list(dict.fromkeys(dataset_ids))
    _append_outputs(acquisition, dataset_ids)
    return dataset_ids, len(new_values)


def execute_intelligence_acquisition(
    db: Session,
    row: IntelligenceAcquisition,
    *,
    satellite_provider: SatelliteProvider | None = None,
    weather_provider: WeatherProvider | None = None,
    storage: StorageService | None = None,
    config: Settings = settings,
) -> IntelligenceAcquisition:
    if row.status not in {
        IntelligenceStatus.REQUESTED.value,
        IntelligenceStatus.RETRY_WAIT.value,
    }:
        return row
    now = utc_now()
    if row.next_attempt_at and row.next_attempt_at > now:
        return row
    row.status = IntelligenceStatus.RUNNING.value
    row.started_at = row.started_at or now
    row.attempt_count += 1
    row.next_attempt_at = None
    row.error_code = None
    row.error_message = None
    row.updated_at = now
    row.lifecycle_version += 1
    db.commit()
    request = json_object(row.request_json)
    try:
        if row.kind == IntelligenceKind.SATELLITE.value:
            if satellite_provider is None:
                raise IntelligenceError(
                    "provider_dependency_missing",
                    "Satellite provider was not supplied by the composition root",
                )
            provider = satellite_provider
            if storage is None:
                raise IntelligenceError(
                    "storage_dependency_missing",
                    "Object storage was not supplied by the composition root",
                )
            result = provider.search(
                SatelliteSearchRequest(
                    geometry=dict(request["geometry"]),
                    starts_at=datetime.fromisoformat(str(request["starts_at"])),
                    ends_at=datetime.fromisoformat(str(request["ends_at"])),
                    collection=str(request["collection"]),
                    max_cloud_cover_percent=float(request["max_cloud_cover_percent"]),
                    limit=int(request["limit"]),
                )
            )
            if not result.ok or result.value is None:
                code, message, retryable = _failure_details(result)
                _mark_failure(
                    db,
                    row,
                    code=code,
                    message=message,
                    retryable=retryable,
                    config=config,
                )
                return row
            requested_keys = tuple(str(item) for item in request.get("download_asset_keys", []))
            dataset_ids, warnings = _register_satellite_results(
                db,
                row=row,
                scenes=result.value,
                provider=provider,
                storage=storage,
                requested_keys=requested_keys,
                config=config,
            )
            summary = {
                "scene_count": len(result.value),
                "dataset_count": len(dataset_ids),
                "download_warnings": warnings,
                "provider_attempts": result.attempts,
            }
            event_name = EventNames.SATELLITE_ACQUISITION_COMPLETED
        elif row.kind == IntelligenceKind.WEATHER.value:
            if weather_provider is None:
                raise IntelligenceError(
                    "provider_dependency_missing",
                    "Weather provider was not supplied by the composition root",
                )
            provider = weather_provider
            result = provider.observations(
                WeatherRequest(
                    latitude=float(request["latitude"]),
                    longitude=float(request["longitude"]),
                    starts_at=datetime.fromisoformat(str(request["starts_at"])),
                    ends_at=datetime.fromisoformat(str(request["ends_at"])),
                    max_distance_km=float(request["max_distance_km"]),
                )
            )
            if not result.ok or result.value is None:
                code, message, retryable = _failure_details(result)
                _mark_failure(
                    db,
                    row,
                    code=code,
                    message=message,
                    retryable=retryable,
                    config=config,
                )
                return row
            dataset_ids, new_count = _register_weather_results(
                db,
                row=row,
                snapshots=result.value,
                provider=provider,
                config=config,
            )
            summary = {
                "snapshot_count": len(result.value),
                "observation_count": sum(len(item.metrics) for item in result.value),
                "new_observation_count": new_count,
                "dataset_count": len(dataset_ids),
                "provider_attempts": result.attempts,
            }
            event_name = EventNames.WEATHER_ACQUISITION_COMPLETED
        else:
            raise IntelligenceError("invalid_kind", "Intelligence acquisition kind is invalid")
        now = utc_now()
        row.status = IntelligenceStatus.COMPLETED.value
        row.dataset_ids_json = json_dump(dataset_ids)
        row.result_summary_json = json_dump(summary)
        row.cache_expires_at = now + timedelta(
            seconds=(
                config.satellite_cache_ttl_seconds
                if row.kind == IntelligenceKind.SATELLITE.value
                else config.weather_cache_ttl_seconds
            )
        )
        row.completed_at = now
        row.next_attempt_at = None
        row.claimed_by = None
        row.claimed_at = None
        row.updated_at = now
        row.lifecycle_version += 1
        record_provider_usage(
            db,
            payload=ProviderUsageCreate(
                organization_id=row.organization_id,
                workspace_id=row.workspace_id,
                intelligence_acquisition_id=row.id,
                provider=row.provider_code,
                service=(
                    "satellite_search"
                    if row.kind == IntelligenceKind.SATELLITE.value
                    else "weather_observations"
                ),
                usage_type="provider_request",
                quantity=Decimal("1"),
                unit="request",
                occurred_at=now,
                idempotency_key=f"intelligence:{row.id}:usage:completed",
                metadata={
                    "kind": row.kind,
                    "provider_attempts": summary.get("provider_attempts"),
                    "dataset_count": len(dataset_ids),
                    "result_count": (
                        summary.get("scene_count")
                        if row.kind == IntelligenceKind.SATELLITE.value
                        else summary.get("snapshot_count")
                    ),
                    "adapter_version": str(
                        getattr(provider, "adapter_version", "unavailable-unversioned")
                    ),
                },
            ),
        )
        _event(
            db,
            name=event_name,
            row=row,
            key=f"intelligence:{row.id}:completed",
            payload={"dataset_ids": dataset_ids, **summary},
        )
        log_event(
            logger,
            logging.INFO,
            "intelligence.acquisition.completed",
            organization_id=row.organization_id,
            workspace_id=row.workspace_id,
            asset_id=row.asset_id,
            mission_id=row.acquisition_id,
            intelligence_acquisition_id=row.id,
            provider=row.provider_code,
            adapter_version=str(
                getattr(provider, "adapter_version", "unavailable-unversioned")
            ),
            kind=row.kind,
            dataset_count=len(dataset_ids),
        )
        db.commit()
        return row
    except IntelligenceError as exc:
        _mark_failure(
            db,
            row,
            code=exc.code,
            message=str(exc),
            retryable=exc.retryable,
            config=config,
        )
        return row
    except (KeyError, TypeError, ValueError) as exc:
        del exc
        _mark_failure(
            db,
            row,
            code="invalid_persisted_request",
            message="The persisted intelligence request is invalid",
            retryable=False,
            config=config,
        )
        return row
    except Exception:
        _mark_failure(
            db,
            row,
            code="intelligence_execution_failed",
            message="The intelligence acquisition failed unexpectedly and can be retried",
            retryable=True,
            config=config,
        )
        return row


def _prepare_run(
    db: Session,
    *,
    asset: Asset,
    kind: str,
    provider: str,
    request: Mapping[str, Any],
    fingerprint_payload: Mapping[str, Any],
    force_refresh: bool,
    actor_user_id: str | None,
    schedule_id: str | None,
    config: Settings,
) -> tuple[IntelligenceAcquisition, bool]:
    fingerprint = request_fingerprint(fingerprint_payload)
    now = utc_now()
    if not force_refresh:
        cached = _cache_lookup(
            db,
            asset=asset,
            kind=kind,
            provider=provider,
            fingerprint=fingerprint,
            now=now,
        )
        if cached is not None:
            return cached, True
    row = _new_run(
        db,
        asset=asset,
        kind=kind,
        provider=provider,
        request=request,
        fingerprint=fingerprint,
        actor_user_id=actor_user_id,
        schedule_id=schedule_id,
        config=config,
    )
    db.commit()
    return row, False


def acquire_satellite_for_asset(
    db: Session,
    *,
    asset: Asset,
    data: SatelliteIntelligenceRequest,
    actor_user_id: str | None,
    schedule_id: str | None = None,
    provider: SatelliteProvider | None = None,
    storage: StorageService | None = None,
    config: Settings = settings,
) -> tuple[IntelligenceAcquisition, bool]:
    now = utc_now()
    relative_window = data.starts_at is None and data.ends_at is None
    ends_at = utc_naive(data.ends_at) if data.ends_at else now
    lookback_days = data.lookback_days or config.satellite_default_lookback_days
    starts_at = utc_naive(data.starts_at) if data.starts_at else ends_at - timedelta(days=lookback_days)
    if (ends_at - starts_at) > timedelta(days=366):
        raise IntelligenceError("date_range_too_large", "Satellite date range cannot exceed 366 days")
    geometry = _asset_geometry(asset)
    selected_provider = provider_code(
        getattr(provider, "provider_name", None) or config.satellite_provider
    )
    if selected_provider in {"none", "null"}:
        raise IntelligenceError("provider_not_configured", "Satellite provider is not configured")
    collection = data.collection or config.satellite_default_collection
    max_cloud = (
        data.max_cloud_cover_percent
        if data.max_cloud_cover_percent is not None
        else config.satellite_default_max_cloud_cover_percent
    )
    limit = min(
        data.limit or config.satellite_max_scenes_per_request,
        config.satellite_max_scenes_per_request,
    )
    requested_downloads = tuple(
        key
        for key in (data.download_asset_keys or list(config.satellite_download_asset_key_list))
        if config.satellite_download_assets_enabled
    )
    request = {
        "geometry": geometry,
        "starts_at": starts_at.isoformat(),
        "ends_at": ends_at.isoformat(),
        "collection": collection,
        "max_cloud_cover_percent": max_cloud,
        "limit": limit,
        "download_asset_keys": list(requested_downloads),
    }
    fingerprint_payload = {
        "geometry": geometry,
        "window": (
            {"mode": "latest", "lookback_days": lookback_days}
            if relative_window
            else {"starts_at": starts_at.isoformat(), "ends_at": ends_at.isoformat()}
        ),
        "collection": collection,
        "max_cloud_cover_percent": max_cloud,
        "limit": limit,
        "download_asset_keys": list(requested_downloads),
    }
    row, cache_hit = _prepare_run(
        db,
        asset=asset,
        kind=IntelligenceKind.SATELLITE.value,
        provider=selected_provider,
        request=request,
        fingerprint_payload=fingerprint_payload,
        force_refresh=data.force_refresh,
        actor_user_id=actor_user_id,
        schedule_id=schedule_id,
        config=config,
    )
    if not cache_hit:
        execute_intelligence_acquisition(
            db,
            row,
            satellite_provider=provider,
            storage=storage,
            config=config,
        )
    return row, cache_hit


def acquire_weather_for_asset(
    db: Session,
    *,
    asset: Asset,
    data: WeatherIntelligenceRequest,
    actor_user_id: str | None,
    schedule_id: str | None = None,
    provider: WeatherProvider | None = None,
    config: Settings = settings,
) -> tuple[IntelligenceAcquisition, bool]:
    now = utc_now()
    relative_window = data.starts_at is None and data.ends_at is None
    ends_at = utc_naive(data.ends_at) if data.ends_at else now
    lookback_hours = data.lookback_hours or config.weather_default_lookback_hours
    starts_at = utc_naive(data.starts_at) if data.starts_at else ends_at - timedelta(hours=lookback_hours)
    if (ends_at - starts_at) > timedelta(hours=168):
        raise IntelligenceError("date_range_too_large", "Weather date range cannot exceed 168 hours")
    latitude, longitude = _asset_center(asset)
    selected_provider = provider_code(
        getattr(provider, "provider_name", None) or config.weather_provider
    )
    if selected_provider in {"none", "null"}:
        raise IntelligenceError("provider_not_configured", "Weather provider is not configured")
    if selected_provider == "aemet" and not aemet_covers(latitude, longitude):
        raise IntelligenceError(
            "provider_coverage_mismatch",
            "AEMET can only be requested for assets in Spain and its territories",
        )
    max_distance = data.max_distance_km or config.aemet_max_station_distance_km
    request = {
        "latitude": latitude,
        "longitude": longitude,
        "starts_at": starts_at.isoformat(),
        "ends_at": ends_at.isoformat(),
        "max_distance_km": max_distance,
    }
    fingerprint_payload = {
        "latitude": round(latitude, 6),
        "longitude": round(longitude, 6),
        "window": (
            {"mode": "latest", "lookback_hours": lookback_hours}
            if relative_window
            else {"starts_at": starts_at.isoformat(), "ends_at": ends_at.isoformat()}
        ),
        "max_distance_km": max_distance,
    }
    row, cache_hit = _prepare_run(
        db,
        asset=asset,
        kind=IntelligenceKind.WEATHER.value,
        provider=selected_provider,
        request=request,
        fingerprint_payload=fingerprint_payload,
        force_refresh=data.force_refresh,
        actor_user_id=actor_user_id,
        schedule_id=schedule_id,
        config=config,
    )
    if not cache_hit:
        execute_intelligence_acquisition(
            db,
            row,
            weather_provider=provider,
            config=config,
        )
    return row, cache_hit


def request_satellite_intelligence(
    db: Session,
    *,
    actor: User,
    context: AuthorizationContext,
    data: SatelliteIntelligenceRequest,
    provider: SatelliteProvider | None = None,
    storage: StorageService | None = None,
    config: Settings = settings,
) -> tuple[IntelligenceAcquisition, bool]:
    asset = get_asset(db, context=context, asset_id=data.asset_id, permission="asset:update")
    return acquire_satellite_for_asset(
        db,
        asset=asset,
        data=data,
        actor_user_id=actor.id,
        provider=provider,
        storage=storage,
        config=config,
    )


def request_weather_intelligence(
    db: Session,
    *,
    actor: User,
    context: AuthorizationContext,
    data: WeatherIntelligenceRequest,
    provider: WeatherProvider | None = None,
    config: Settings = settings,
) -> tuple[IntelligenceAcquisition, bool]:
    asset = get_asset(db, context=context, asset_id=data.asset_id, permission="asset:update")
    return acquire_weather_for_asset(
        db,
        asset=asset,
        data=data,
        actor_user_id=actor.id,
        provider=provider,
        config=config,
    )


def acquisition_out(row: IntelligenceAcquisition, *, cache_hit: bool = False) -> dict[str, Any]:
    return {
        "id": row.id,
        "organization_id": row.organization_id,
        "workspace_id": row.workspace_id,
        "asset_id": row.asset_id,
        "schedule_id": row.schedule_id,
        "acquisition_id": row.acquisition_id,
        "kind": row.kind,
        "provider": row.provider_code,
        "status": row.status,
        "cache_hit": cache_hit,
        "cache_expires_at": row.cache_expires_at,
        "attempts": row.attempt_count,
        "max_attempts": row.max_attempts,
        "dataset_ids": [str(item) for item in json_array(row.dataset_ids_json)],
        "summary": json_object(row.result_summary_json),
        "error_code": row.error_code,
        "error_message": row.error_message,
        "created_at": row.created_at,
        "completed_at": row.completed_at,
    }


def scene_out(row: SatelliteScene) -> dict[str, Any]:
    return {
        "id": row.id,
        "dataset_id": row.dataset_id,
        "provider": row.provider_code,
        "provider_reference": row.provider_reference,
        "collection": row.collection,
        "acquired_at": row.acquired_at,
        "published_at": row.published_at,
        "cloud_cover_percent": row.cloud_cover_percent,
        "resolution_meters": row.resolution_meters,
        "crs": row.crs,
        "bands": [str(item) for item in json_array(row.bands_json)],
        "bbox": [float(item) for item in json_array(row.bbox_json)],
        "coverage": json_object(row.coverage_geojson) if row.coverage_geojson else None,
        "assets": json_object(row.assets_json),
        "provenance": json_object(row.provenance_json),
        "source_link": row.source_link,
    }


def observation_out(row: WeatherObservation) -> dict[str, Any]:
    return {
        "id": row.id,
        "dataset_id": row.dataset_id,
        "provider": row.provider_code,
        "source_reference": row.source_reference,
        "source_name": row.source_name,
        "observed_at": row.observed_at,
        "metric": row.metric,
        "value": row.value,
        "unit": row.unit,
        "quality": row.quality,
        "latitude": row.latitude,
        "longitude": row.longitude,
        "distance_km": row.distance_km,
        "provenance": json_object(row.provenance_json),
    }


def scenes_for_run(db: Session, row: IntelligenceAcquisition) -> list[SatelliteScene]:
    dataset_ids = [str(item) for item in json_array(row.dataset_ids_json)]
    if not dataset_ids:
        return []
    return (
        db.query(SatelliteScene)
        .filter(
            SatelliteScene.organization_id == row.organization_id,
            SatelliteScene.asset_id == row.asset_id,
            SatelliteScene.dataset_id.in_(dataset_ids),
        )
        .order_by(SatelliteScene.acquired_at.desc())
        .all()
    )


def observations_for_run(db: Session, row: IntelligenceAcquisition) -> list[WeatherObservation]:
    dataset_ids = [str(item) for item in json_array(row.dataset_ids_json)]
    if not dataset_ids:
        return []
    return (
        db.query(WeatherObservation)
        .filter(
            WeatherObservation.organization_id == row.organization_id,
            WeatherObservation.asset_id == row.asset_id,
            WeatherObservation.dataset_id.in_(dataset_ids),
        )
        .order_by(WeatherObservation.observed_at.desc(), WeatherObservation.metric)
        .all()
    )


def list_asset_scenes(
    db: Session,
    *,
    context: AuthorizationContext,
    asset_id: str,
    limit: int,
) -> list[SatelliteScene]:
    asset = get_asset(db, context=context, asset_id=asset_id, permission="asset:read")
    return (
        db.query(SatelliteScene)
        .filter(
            SatelliteScene.organization_id == asset.organization_id,
            SatelliteScene.asset_id == asset.id,
        )
        .order_by(SatelliteScene.acquired_at.desc())
        .limit(limit)
        .all()
    )


def list_asset_weather(
    db: Session,
    *,
    context: AuthorizationContext,
    asset_id: str,
    metric: str | None,
    limit: int,
) -> list[WeatherObservation]:
    asset = get_asset(db, context=context, asset_id=asset_id, permission="asset:read")
    query = db.query(WeatherObservation).filter(
        WeatherObservation.organization_id == asset.organization_id,
        WeatherObservation.asset_id == asset.id,
    )
    if metric:
        query = query.filter(WeatherObservation.metric == metric)
    return query.order_by(WeatherObservation.observed_at.desc()).limit(limit).all()


def create_intelligence_schedule(
    db: Session,
    *,
    actor: User,
    data: IntelligenceScheduleCreate,
    config: Settings = settings,
) -> IntelligenceSchedule:
    asset = db.get(Asset, data.asset_id)
    if asset is None or asset.status == "archived":
        raise IntelligenceError("asset_not_found", "Schedule asset was not found")
    default_provider = (
        config.satellite_provider
        if data.kind is IntelligenceKind.SATELLITE
        else config.weather_provider
    )
    selected_provider = provider_code(data.provider or default_provider)
    if selected_provider in {"none", "null"}:
        raise IntelligenceError("provider_not_configured", "Schedule provider is not configured")
    satellite_providers = {"fake", "deterministic", "copernicus", "cdse", "sentinel"}
    weather_providers = {
        "fake",
        "deterministic",
        "aemet",
        "aemet_opendata",
        "azure_maps",
        "azure_maps_weather",
    }
    allowed = (
        satellite_providers
        if data.kind == IntelligenceKind.SATELLITE
        else weather_providers
    )
    if selected_provider not in allowed:
        raise IntelligenceError(
            "provider_kind_mismatch",
            f"Provider '{selected_provider}' cannot serve a {data.kind.value.lower()} schedule",
        )
    if data.kind == IntelligenceKind.WEATHER and selected_provider == "aemet":
        latitude, longitude = _asset_center(asset)
        if not aemet_covers(latitude, longitude):
            raise IntelligenceError(
                "provider_coverage_mismatch", "AEMET schedules require an asset in Spain"
            )
    idempotency = data.idempotency_key or _hash_key(
        "intelligence-schedule", asset.id, data.kind.value, selected_provider
    )
    existing = (
        db.query(IntelligenceSchedule)
        .filter(IntelligenceSchedule.idempotency_key == idempotency)
        .one_or_none()
    )
    if existing is not None:
        if (
            existing.asset_id != asset.id
            or existing.kind != data.kind.value
            or existing.provider_code != selected_provider
        ):
            raise IntelligenceError(
                "idempotency_conflict", "Schedule idempotency key is already in use"
            )
        return existing
    now = utc_now()
    schedule = IntelligenceSchedule(
        id=str(uuid.uuid4()),
        organization_id=asset.organization_id,
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        kind=data.kind.value,
        provider_code=selected_provider,
        cadence_minutes=data.cadence_minutes,
        lookback_days=data.lookback_days,
        options_json=json_dump(data.options),
        status=IntelligenceScheduleStatus.ACTIVE.value,
        next_run_at=utc_naive(data.next_run_at) if data.next_run_at else now,
        consecutive_failures=0,
        idempotency_key=idempotency,
        created_by_user_id=actor.id,
        lifecycle_version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


def update_intelligence_schedule(
    db: Session,
    *,
    schedule: IntelligenceSchedule,
    data: IntelligenceScheduleUpdate,
) -> IntelligenceSchedule:
    if schedule.lifecycle_version != data.expected_version:
        raise IntelligenceError("version_conflict", "Schedule changed since it was read")
    if data.status is not None:
        schedule.status = data.status.value
    if data.cadence_minutes is not None:
        schedule.cadence_minutes = data.cadence_minutes
    if data.lookback_days is not None:
        schedule.lookback_days = data.lookback_days
    if data.options is not None:
        schedule.options_json = json_dump(data.options)
    if data.next_run_at is not None:
        schedule.next_run_at = utc_naive(data.next_run_at)
    schedule.lifecycle_version += 1
    schedule.updated_at = utc_now()
    db.commit()
    db.refresh(schedule)
    return schedule


def schedule_out(row: IntelligenceSchedule) -> dict[str, Any]:
    return {
        "id": row.id,
        "organization_id": row.organization_id,
        "workspace_id": row.workspace_id,
        "asset_id": row.asset_id,
        "kind": row.kind,
        "provider": row.provider_code,
        "cadence_minutes": row.cadence_minutes,
        "lookback_days": row.lookback_days,
        "options": json_object(row.options_json),
        "status": row.status,
        "next_run_at": row.next_run_at,
        "last_run_at": row.last_run_at,
        "last_success_at": row.last_success_at,
        "last_error_code": row.last_error_code,
        "last_error_message": row.last_error_message,
        "consecutive_failures": row.consecutive_failures,
        "lifecycle_version": row.lifecycle_version,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _schedule_request(schedule: IntelligenceSchedule) -> Any:
    options = json_object(schedule.options_json)
    if schedule.kind == IntelligenceKind.SATELLITE.value:
        return SatelliteIntelligenceRequest(
            asset_id=schedule.asset_id,
            lookback_days=schedule.lookback_days,
            collection=options.get("collection"),
            max_cloud_cover_percent=options.get("max_cloud_cover_percent"),
            limit=options.get("limit"),
            download_asset_keys=options.get("download_asset_keys") or [],
        )
    return WeatherIntelligenceRequest(
        asset_id=schedule.asset_id,
        lookback_hours=min(168, schedule.lookback_days * 24),
        max_distance_km=options.get("max_distance_km"),
    )


def execute_intelligence_schedule(
    db: Session,
    schedule: IntelligenceSchedule,
    *,
    satellite_provider_resolver: SatelliteProviderResolver,
    weather_provider_resolver: WeatherProviderResolver,
    storage: StorageService,
    config: Settings = settings,
) -> IntelligenceAcquisition:
    asset = db.get(Asset, schedule.asset_id)
    if asset is None:
        schedule.status = IntelligenceScheduleStatus.DISABLED.value
        schedule.last_error_code = "asset_not_found"
        schedule.last_error_message = "Schedule asset no longer exists"
        schedule.claimed_by = None
        schedule.claimed_at = None
        schedule.lifecycle_version += 1
        db.commit()
        raise IntelligenceError("asset_not_found", "Schedule asset no longer exists")
    data = _schedule_request(schedule)
    if schedule.kind == IntelligenceKind.SATELLITE.value:
        satellite_provider = satellite_provider_resolver(schedule.provider_code)
        row, _ = acquire_satellite_for_asset(
            db,
            asset=asset,
            data=data,
            actor_user_id=schedule.created_by_user_id,
            schedule_id=schedule.id,
            provider=satellite_provider,
            storage=storage,
            config=config,
        )
    else:
        weather_provider = weather_provider_resolver(schedule.provider_code)
        row, _ = acquire_weather_for_asset(
            db,
            asset=asset,
            data=data,
            actor_user_id=schedule.created_by_user_id,
            schedule_id=schedule.id,
            provider=weather_provider,
            config=config,
        )
    now = utc_now()
    schedule.last_run_at = now
    schedule.next_run_at = now + timedelta(minutes=schedule.cadence_minutes)
    schedule.claimed_by = None
    schedule.claimed_at = None
    if row.status == IntelligenceStatus.COMPLETED.value:
        schedule.last_success_at = now
        schedule.last_error_code = None
        schedule.last_error_message = None
        schedule.consecutive_failures = 0
    else:
        schedule.last_error_code = row.error_code or row.status.lower()
        schedule.last_error_message = row.error_message
        schedule.consecutive_failures += 1
    schedule.lifecycle_version += 1
    schedule.updated_at = now
    db.commit()
    return row


def _claim_due(
    db: Session,
    model: Any,
    *,
    statuses: tuple[str, ...],
    due_column: Any,
    worker_id: str,
    limit: int,
    claim_timeout_seconds: int,
) -> list[str]:
    now = utc_now()
    stale = now - timedelta(seconds=claim_timeout_seconds)
    query = (
        db.query(model)
        .filter(
            model.status.in_(statuses),
            due_column <= now,
            or_(model.claimed_at.is_(None), model.claimed_at < stale),
        )
        .order_by(due_column, model.created_at)
        .limit(limit)
    )
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    rows = query.all()
    for row in rows:
        row.claimed_by = worker_id
        row.claimed_at = now
    db.commit()
    return [row.id for row in rows]


def _record_schedule_execution_failure(
    db: Session,
    *,
    schedule_id: str,
    code: str,
    message: str,
) -> None:
    """Release a schedule claim without allowing one bad row to stop the worker."""

    db.rollback()
    schedule = db.get(IntelligenceSchedule, schedule_id)
    if schedule is None or schedule.status != IntelligenceScheduleStatus.ACTIVE.value:
        return
    now = utc_now()
    schedule.last_run_at = now
    schedule.last_error_code = code[:100]
    schedule.last_error_message = message[:2000]
    schedule.consecutive_failures += 1
    schedule.next_run_at = now + timedelta(minutes=schedule.cadence_minutes)
    schedule.claimed_by = None
    schedule.claimed_at = None
    schedule.lifecycle_version += 1
    schedule.updated_at = now
    db.commit()


def run_intelligence_cycle(
    db: Session,
    *,
    worker_id: str,
    satellite_provider_resolver: SatelliteProviderResolver,
    weather_provider_resolver: WeatherProviderResolver,
    storage: StorageService,
    config: Settings = settings,
) -> dict[str, int]:
    schedule_ids = _claim_due(
        db,
        IntelligenceSchedule,
        statuses=(IntelligenceScheduleStatus.ACTIVE.value,),
        due_column=IntelligenceSchedule.next_run_at,
        worker_id=worker_id,
        limit=config.intelligence_worker_batch_size,
        claim_timeout_seconds=config.intelligence_worker_claim_timeout_seconds,
    )
    schedules_completed = 0
    for schedule_id in schedule_ids:
        schedule = db.get(IntelligenceSchedule, schedule_id)
        if schedule is None:
            continue
        try:
            execute_intelligence_schedule(
                db,
                schedule,
                satellite_provider_resolver=satellite_provider_resolver,
                weather_provider_resolver=weather_provider_resolver,
                storage=storage,
                config=config,
            )
            schedules_completed += 1
        except IntelligenceError as exc:
            _record_schedule_execution_failure(
                db,
                schedule_id=schedule_id,
                code=exc.code,
                message=str(exc),
            )
        except Exception:
            _record_schedule_execution_failure(
                db,
                schedule_id=schedule_id,
                code="schedule_execution_failed",
                message="The intelligence schedule could not be executed",
            )
    run_ids = _claim_due(
        db,
        IntelligenceAcquisition,
        statuses=(
            IntelligenceStatus.REQUESTED.value,
            IntelligenceStatus.RETRY_WAIT.value,
        ),
        due_column=IntelligenceAcquisition.next_attempt_at,
        worker_id=worker_id,
        limit=config.intelligence_worker_batch_size,
        claim_timeout_seconds=config.intelligence_worker_claim_timeout_seconds,
    )
    runs_completed = 0
    runs_failed = 0
    for run_id in run_ids:
        row = db.get(IntelligenceAcquisition, run_id)
        if row is None:
            continue
        if row.kind == IntelligenceKind.SATELLITE.value:
            execute_intelligence_acquisition(
                db,
                row,
                satellite_provider=satellite_provider_resolver(row.provider_code),
                storage=storage,
                config=config,
            )
        else:
            execute_intelligence_acquisition(
                db,
                row,
                weather_provider=weather_provider_resolver(row.provider_code),
                config=config,
            )
        if row.status == IntelligenceStatus.COMPLETED.value:
            runs_completed += 1
        elif row.status == IntelligenceStatus.FAILED.value:
            runs_failed += 1
    return {
        "schedules_claimed": len(schedule_ids),
        "schedules_completed": schedules_completed,
        "runs_claimed": len(run_ids),
        "runs_completed": runs_completed,
        "runs_failed": runs_failed,
    }


def default_worker_id() -> str:
    return f"{socket.gethostname()}:{uuid.uuid4().hex[:12]}"


__all__ = [
    "acquire_satellite_for_asset",
    "acquire_weather_for_asset",
    "acquisition_out",
    "create_intelligence_schedule",
    "default_worker_id",
    "execute_intelligence_acquisition",
    "execute_intelligence_schedule",
    "list_asset_scenes",
    "list_asset_weather",
    "observation_out",
    "observations_for_run",
    "request_satellite_intelligence",
    "request_weather_intelligence",
    "run_intelligence_cycle",
    "scene_out",
    "scenes_for_run",
    "schedule_out",
    "update_intelligence_schedule",
]
