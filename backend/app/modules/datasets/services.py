"""Tenant-safe dataset lifecycle and provider-neutral upload services."""

from __future__ import annotations

from datetime import timedelta
import hmac
import json
import re
import uuid
from typing import Any, BinaryIO

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import utc_now
from app.models import Acquisition, Asset, AuditLog, Dataset, DatasetFile, Site, User
from app.modules.assets.services import (
    AssetAccessError,
    get_asset,
    synchronize_legacy_site,
)
from app.modules.datasets.domain import (
    DatasetError,
    DatasetStatus,
    ObjectArea,
    ProcessingLevel,
    normalize_provider_code,
    object_area_for,
    require_transition,
    validate_upload,
)
from app.modules.datasets.schemas import DatasetCreate, DatasetUpdate
from app.modules.identity.domain import AuthorizationContext
from app.modules.organizations.domain import permission_granted
from app.services.storage import StorageService, detect_file_type


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _object(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _array(value: str | None) -> list[Any]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _audit(
    db: Session,
    *,
    actor: User,
    action: str,
    dataset: Dataset,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=actor.id,
            user_email=actor.email,
            action=action,
            resource_type="dataset",
            resource_id=dataset.id,
            details=_json(
                {
                    "organization_id": dataset.company_id,
                    "workspace_id": dataset.workspace_id,
                    "asset_id": dataset.asset_id,
                    **(details or {}),
                }
            ),
        )
    )


def _check_version(dataset: Dataset, expected: int | None) -> None:
    if expected is not None and dataset.lifecycle_version != expected:
        raise DatasetError("version_conflict", "Dataset changed since it was last read")


def _require_workspace(
    context: AuthorizationContext,
    permission: str,
) -> tuple[str, str]:
    if not context.active_organization_id or not context.active_workspace_id:
        raise DatasetError(
            "workspace_required", "Select an active workspace before accessing datasets"
        )
    if not permission_granted(context.permissions, permission):
        raise DatasetError("dataset_access_denied", "Dataset access denied")
    return context.active_organization_id, context.active_workspace_id


def _resolve_asset(
    db: Session,
    *,
    actor: User,
    context: AuthorizationContext,
    asset_id: str | None,
    site_id: str | None,
) -> Asset:
    organization_id, _ = _require_workspace(context, "asset:update")
    if asset_id:
        return get_asset(
            db,
            context=context,
            asset_id=asset_id,
            permission="asset:update",
        )
    site = db.get(Site, site_id) if site_id else None
    if site is None or site.company_id != organization_id:
        raise DatasetError("asset_not_found", "Dataset asset was not found")
    canonical = synchronize_legacy_site(db, site, actor_user_id=actor.id)
    return get_asset(
        db,
        context=context,
        asset_id=canonical.id,
        permission="asset:update",
    )


def get_owned_dataset(
    db: Session,
    *,
    context: AuthorizationContext,
    dataset_id: str,
    write: bool,
    include_archived: bool = False,
) -> Dataset:
    organization_id, workspace_id = _require_workspace(
        context, "asset:update" if write else "asset:read"
    )
    dataset = db.get(Dataset, dataset_id)
    if (
        dataset is None
        or dataset.company_id != organization_id
        or dataset.workspace_id != workspace_id
        or (dataset.status == DatasetStatus.ARCHIVED.value and not include_archived)
    ):
        raise DatasetError("dataset_not_found", "Dataset was not found")
    if dataset.asset_id:
        get_asset(
            db,
            context=context,
            asset_id=dataset.asset_id,
            permission="asset:update" if write else "asset:read",
        )
    return dataset


def create_dataset(
    db: Session,
    *,
    actor: User,
    context: AuthorizationContext,
    data: DatasetCreate,
    storage: StorageService,
) -> Dataset:
    asset = _resolve_asset(
        db,
        actor=actor,
        context=context,
        asset_id=data.asset_id,
        site_id=data.site_id,
    )
    mission = db.get(Acquisition, data.mission_id) if data.mission_id else None
    if data.mission_id and (
        mission is None
        or mission.organization_id != asset.organization_id
        or mission.asset_id != asset.id
    ):
        raise DatasetError(
            "mission_not_found", "Acquisition mission was not found for this asset"
        )
    dataset_id = str(uuid.uuid4())
    capture_time = data.capture_time or data.capture_date
    dataset = Dataset(
        id=dataset_id,
        company_id=asset.organization_id,
        workspace_id=asset.workspace_id,
        site_id=data.site_id or (
            asset.legacy_source_id if asset.legacy_source == "site" else None
        ),
        asset_id=asset.id,
        mission_id=mission.id if mission else None,
        name=data.name.strip(),
        description=data.description,
        source_tool=data.source_tool.value,
        data_type=data.dataset_type.lower(),
        source=data.source,
        dataset_type=data.dataset_type,
        provider_code=normalize_provider_code(data.provider or data.source_tool.value),
        source_reference=data.source_reference,
        storage_provider=storage.provider_name,
        crs=data.crs,
        resolution=data.resolution,
        resolution_unit=data.resolution_unit,
        processing_level=data.processing_level.value,
        quality_status=data.quality_status.value,
        provenance_json=_json(data.provenance),
        status=DatasetStatus.UPLOADING.value,
        sector=data.sector or asset.sector,
        capture_date=capture_time,
        metadata_json=_json(data.metadata),
        file_count=0,
        total_size_bytes=0,
        created_by_user_id=actor.id,
        lifecycle_version=1,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db.add(dataset)
    _audit(
        db,
        actor=actor,
        action="dataset.created",
        dataset=dataset,
        details={"dataset_type": dataset.dataset_type, "mission_id": dataset.mission_id},
    )
    return dataset


def list_owned_datasets(
    db: Session,
    *,
    context: AuthorizationContext,
    asset_id: str | None = None,
    site_id: str | None = None,
    sector: str | None = None,
    status: str | None = None,
    source_tool: str | None = None,
    dataset_type: str | None = None,
    include_archived: bool = False,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[Dataset], int]:
    organization_id, workspace_id = _require_workspace(context, "asset:read")
    query = db.query(Dataset).filter(
        Dataset.company_id == organization_id,
        Dataset.workspace_id == workspace_id,
    )
    if not include_archived:
        query = query.filter(Dataset.status != DatasetStatus.ARCHIVED.value)
    if asset_id:
        get_asset(
            db,
            context=context,
            asset_id=asset_id,
            permission="asset:read",
        )
        query = query.filter(Dataset.asset_id == asset_id)
    if site_id:
        query = query.filter(Dataset.site_id == site_id)
    if sector:
        query = query.filter(Dataset.sector == sector)
    if status:
        query = query.filter(Dataset.status == status)
    if source_tool:
        query = query.filter(Dataset.source_tool == source_tool)
    if dataset_type:
        query = query.filter(Dataset.dataset_type == dataset_type)
    total = query.count()
    rows = (
        query.order_by(Dataset.capture_date.desc(), Dataset.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return rows, total


def _active_files(dataset: Dataset) -> list[DatasetFile]:
    return [file for file in dataset.files if file.status != "deleted"]


def dataset_file_out(file: DatasetFile) -> dict[str, Any]:
    return {
        "id": file.id,
        "filename": file.filename,
        "file_type": detect_file_type(file.filename),
        "size_bytes": file.file_size or 0,
        "storage_key": file.storage_key,
        "storage_provider": file.storage_provider,
        "storage_uri": file.storage_uri,
        "object_area": file.object_area,
        "status": file.status,
        "mime_type": file.mime_type,
        "md5_hash": file.md5_hash,
        "sha256_hash": file.sha256_hash,
        "confirmed_at": file.confirmed_at,
        "created_at": file.created_at,
    }


def dataset_out(dataset: Dataset) -> dict[str, Any]:
    files = [dataset_file_out(file) for file in _active_files(dataset)]
    return {
        "id": dataset.id,
        "company_id": dataset.company_id,
        "workspace_id": dataset.workspace_id,
        "site_id": dataset.site_id,
        "asset_id": dataset.asset_id,
        "mission_id": dataset.mission_id,
        "name": dataset.name,
        "description": dataset.description,
        "source_tool": dataset.source_tool,
        "data_type": dataset.data_type,
        "dataset_type": dataset.dataset_type,
        "provider": dataset.provider_code,
        "source": dataset.source,
        "source_reference": dataset.source_reference,
        "status": dataset.status,
        "sector": dataset.sector,
        "capture_time": dataset.capture_date,
        "capture_date": dataset.capture_date,
        "crs": dataset.crs,
        "resolution": float(dataset.resolution) if dataset.resolution is not None else None,
        "resolution_unit": dataset.resolution_unit,
        "processing_level": dataset.processing_level,
        "quality_status": dataset.quality_status,
        "metadata": _object(dataset.metadata_json),
        "provenance": _object(dataset.provenance_json),
        "object_prefix": dataset.object_prefix,
        "storage_provider": dataset.storage_provider,
        "files": files,
        "file_count": dataset.file_count or 0,
        "total_size_bytes": dataset.total_size_bytes or 0,
        "lifecycle_version": dataset.lifecycle_version,
        "archived_at": dataset.archived_at,
        "created_at": dataset.created_at,
        "updated_at": dataset.updated_at,
    }


def update_dataset(
    db: Session,
    *,
    actor: User,
    dataset: Dataset,
    data: DatasetUpdate,
) -> Dataset:
    _check_version(dataset, data.expected_version)
    if dataset.status == DatasetStatus.ARCHIVED.value:
        raise DatasetError("dataset_archived", "Archived dataset cannot be updated")
    changed = data.model_dump(exclude_unset=True, mode="python")
    changed.pop("expected_version", None)
    target_status = changed.pop("status", None)
    if target_status:
        require_transition(dataset.status, target_status.value)
        dataset.status = target_status.value
    capture_time = changed.pop("capture_time", None) or changed.pop("capture_date", None)
    if capture_time is not None:
        dataset.capture_date = capture_time
    if "metadata" in changed:
        metadata = _object(dataset.metadata_json)
        metadata.update(changed.pop("metadata") or {})
        dataset.metadata_json = _json(metadata)
    if "provenance" in changed:
        provenance = _object(dataset.provenance_json)
        provenance.update(changed.pop("provenance") or {})
        dataset.provenance_json = _json(provenance)
    if "processing_level" in changed:
        dataset.processing_level = changed.pop("processing_level").value
    if "quality_status" in changed:
        dataset.quality_status = changed.pop("quality_status").value
    for field in (
        "name",
        "description",
        "crs",
        "resolution",
        "resolution_unit",
    ):
        if field in changed:
            setattr(dataset, field, changed[field])
    dataset.lifecycle_version += 1
    dataset.updated_at = utc_now()
    _audit(
        db,
        actor=actor,
        action="dataset.updated",
        dataset=dataset,
        details={"fields": sorted(data.model_fields_set)},
    )
    return dataset


def _file_size(file_obj: BinaryIO) -> int:
    file_obj.seek(0, 2)
    size = int(file_obj.tell())
    file_obj.seek(0)
    return size


def _key_for(
    storage: StorageService,
    *,
    dataset: Dataset,
    file_id: str,
    filename: str,
    area: ObjectArea,
) -> str:
    if not dataset.asset_id:
        raise DatasetError("asset_not_found", "Dataset has no canonical asset")
    return storage.generate_dataset_key(
        organization_id=dataset.company_id,
        asset_id=dataset.asset_id,
        mission_id=dataset.mission_id,
        dataset_id=dataset.id,
        file_id=file_id,
        area=area.value,
        filename=filename,
    )


def _refresh_counts(db: Session, dataset: Dataset) -> None:
    db.flush()
    uploaded = [file for file in dataset.files if file.status == "uploaded"]
    dataset.file_count = len(uploaded)
    dataset.total_size_bytes = sum(file.file_size or 0 for file in uploaded)
    dataset.updated_at = utc_now()


def upload_dataset_file(
    db: Session,
    *,
    actor: User,
    dataset: Dataset,
    file_obj: BinaryIO,
    filename: str,
    content_type: str | None,
    storage: StorageService,
    object_area: ObjectArea | None = None,
) -> DatasetFile:
    if dataset.status == DatasetStatus.ARCHIVED.value:
        raise DatasetError("dataset_archived", "Archived dataset cannot accept uploads")
    size_bytes = _file_size(file_obj)
    validate_upload(
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        max_size_bytes=settings.dataset_direct_upload_max_bytes,
    )
    area = object_area or object_area_for(dataset.processing_level)
    file_id = str(uuid.uuid4())
    key = _key_for(
        storage,
        dataset=dataset,
        file_id=file_id,
        filename=filename,
        area=area,
    )
    now = utc_now()
    file = DatasetFile(
        id=file_id,
        dataset_id=dataset.id,
        filename=filename,
        storage_key=key,
        storage_provider=storage.provider_name,
        storage_uri=storage.object_uri(key),
        object_area=area.value,
        file_size=size_bytes,
        mime_type=content_type,
        status="pending_upload",
        lifecycle_version=1,
        created_at=now,
    )
    db.add(file)
    dataset.storage_provider = storage.provider_name
    dataset.object_prefix = key.rsplit("/", 1)[0]
    dataset.updated_at = now
    _audit(
        db,
        actor=actor,
        action="dataset.upload_reserved",
        dataset=dataset,
        details={"file_id": file.id, "size_bytes": size_bytes, "mode": "stream"},
    )
    try:
        db.commit()
        db.refresh(file)
    except SQLAlchemyError:
        db.rollback()
        raise

    try:
        stored_key, actual_size, md5_hash, sha256_hash = storage.upload_file(
            file_obj,
            key,
            content_type,
            {
                "dataset_id": dataset.id,
                "asset_id": dataset.asset_id or "standalone",
                "mission_id": dataset.mission_id or "standalone",
            },
        )
    except RuntimeError:
        file.status = "upload_error"
        file.lifecycle_version += 1
        db.commit()
        raise

    file.storage_key = stored_key
    file.storage_uri = storage.object_uri(stored_key)
    file.file_size = actual_size
    file.md5_hash = md5_hash
    file.sha256_hash = sha256_hash
    file.status = "uploaded"
    file.confirmed_at = utc_now()
    file.lifecycle_version += 1
    if dataset.status in {
        DatasetStatus.UPLOADING.value,
        DatasetStatus.READY.value,
    }:
        dataset.status = DatasetStatus.PROCESSING.value
    _refresh_counts(db, dataset)
    _audit(
        db,
        actor=actor,
        action="dataset.file_uploaded",
        dataset=dataset,
        details={"file_id": file.id, "size_bytes": actual_size},
    )
    try:
        db.commit()
        db.refresh(file)
    except SQLAlchemyError:
        # The durable reservation remains after rollback and still references
        # the uploaded key, allowing confirmation/reconciliation without an
        # untracked object in provider storage.
        db.rollback()
        raise
    return file


def reserve_upload(
    db: Session,
    *,
    actor: User,
    dataset: Dataset,
    filename: str,
    content_type: str | None,
    size_bytes: int,
    storage: StorageService,
    object_area: ObjectArea | None = None,
) -> tuple[DatasetFile, str, int]:
    if dataset.status == DatasetStatus.ARCHIVED.value:
        raise DatasetError("dataset_archived", "Archived dataset cannot accept uploads")
    validate_upload(
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        max_size_bytes=settings.dataset_signed_upload_max_bytes,
    )
    area = object_area or object_area_for(dataset.processing_level)
    file_id = str(uuid.uuid4())
    key = _key_for(
        storage,
        dataset=dataset,
        file_id=file_id,
        filename=filename,
        area=area,
    )
    expires_in = settings.dataset_signed_url_expiry_seconds
    file = DatasetFile(
        id=file_id,
        dataset_id=dataset.id,
        filename=filename,
        storage_key=key,
        storage_provider=storage.provider_name,
        storage_uri=storage.object_uri(key),
        object_area=area.value,
        file_size=size_bytes,
        mime_type=content_type,
        status="pending_upload",
        upload_expires_at=utc_now() + timedelta(seconds=expires_in),
        lifecycle_version=1,
        created_at=utc_now(),
    )
    db.add(file)
    dataset.storage_provider = storage.provider_name
    dataset.object_prefix = key.rsplit("/", 1)[0]
    dataset.updated_at = utc_now()
    try:
        upload_url = storage.get_presigned_url(
            key=key,
            expires_in=expires_in,
            for_upload=True,
        )
        _audit(
            db,
            actor=actor,
            action="dataset.upload_reserved",
            dataset=dataset,
            details={"file_id": file.id, "expires_in": expires_in},
        )
        db.commit()
        db.refresh(file)
    except Exception:
        db.rollback()
        raise
    return file, upload_url, expires_in


def _reserved_file(dataset: Dataset, storage_key: str) -> DatasetFile:
    file = next(
        (candidate for candidate in dataset.files if candidate.storage_key == storage_key),
        None,
    )
    if file is None or file.status not in {"pending_upload", "uploaded"}:
        raise DatasetError("upload_not_found", "Reserved upload was not found")
    return file


def complete_reserved_upload_from_stream(
    db: Session,
    *,
    actor: User,
    dataset: Dataset,
    storage_key: str,
    file_obj: BinaryIO,
    content_type: str | None,
    storage: StorageService,
) -> DatasetFile:
    file = _reserved_file(dataset, storage_key)
    if file.status == "uploaded":
        return file
    if file.storage_provider != storage.provider_name:
        raise DatasetError("storage_provider_mismatch", "Upload provider has changed")
    if file.upload_expires_at and file.upload_expires_at < utc_now():
        raise DatasetError("upload_expired", "Upload reservation has expired")
    size_bytes = _file_size(file_obj)
    validate_upload(
        filename=file.filename,
        content_type=content_type or file.mime_type,
        size_bytes=size_bytes,
        max_size_bytes=settings.dataset_signed_upload_max_bytes,
    )
    if file.file_size and file.file_size != size_bytes:
        raise DatasetError("file_size_mismatch", "Uploaded file size does not match reservation")
    stored_key, actual_size, md5_hash, sha256_hash = storage.upload_file(
        file_obj,
        storage_key,
        content_type or file.mime_type,
        {"dataset_id": dataset.id, "file_id": file.id},
    )
    now = utc_now()
    file.storage_key = stored_key
    file.storage_uri = storage.object_uri(stored_key)
    file.file_size = actual_size
    file.mime_type = content_type or file.mime_type
    file.md5_hash = md5_hash
    file.sha256_hash = sha256_hash
    file.status = "uploaded"
    file.confirmed_at = now
    file.lifecycle_version += 1
    if dataset.status in {
        DatasetStatus.UPLOADING.value,
        DatasetStatus.READY.value,
    }:
        dataset.status = DatasetStatus.PROCESSING.value
    _refresh_counts(db, dataset)
    _audit(
        db,
        actor=actor,
        action="dataset.file_uploaded",
        dataset=dataset,
        details={"file_id": file.id, "size_bytes": actual_size},
    )
    try:
        db.commit()
        db.refresh(file)
    except SQLAlchemyError:
        db.rollback()
        try:
            storage.delete_file(stored_key)
        except RuntimeError:
            pass
        raise
    return file


def confirm_reserved_upload(
    db: Session,
    *,
    actor: User,
    dataset: Dataset,
    storage_key: str,
    filename: str,
    claimed_size_bytes: int,
    sha256_hash: str | None,
    storage: StorageService,
) -> DatasetFile:
    file = _reserved_file(dataset, storage_key)
    if file.filename != filename:
        raise DatasetError("upload_mismatch", "Filename does not match upload reservation")
    if file.status == "uploaded":
        return file
    if file.storage_provider != storage.provider_name:
        raise DatasetError("storage_provider_mismatch", "Upload provider has changed")
    if file.upload_expires_at and file.upload_expires_at < utc_now():
        raise DatasetError("upload_expired", "Upload reservation has expired")
    info = storage.stat_file(storage_key)
    if info is None:
        raise DatasetError("upload_missing", "File was not found in object storage")
    actual_size = int(info.get("size_bytes") or 0)
    try:
        validate_upload(
            filename=filename,
            content_type=file.mime_type or info.get("content_type"),
            size_bytes=actual_size,
            max_size_bytes=settings.dataset_signed_upload_max_bytes,
        )
        if claimed_size_bytes != actual_size or (
            file.file_size and file.file_size != actual_size
        ):
            raise DatasetError(
                "file_size_mismatch", "Uploaded file size does not match reservation"
            )
    except DatasetError:
        storage.delete_file(storage_key)
        file.status = "rejected"
        file.lifecycle_version += 1
        db.commit()
        raise
    if sha256_hash and not re.fullmatch(r"[a-fA-F0-9]{64}", sha256_hash):
        raise DatasetError("invalid_checksum", "SHA-256 checksum is invalid")
    # Only provider-calculated checksums are trusted here. Client-controlled
    # object metadata must never be treated as proof of content integrity.
    trusted_sha256 = info.get("sha256_hash")
    trusted_md5 = info.get("md5_hash")
    if (
        sha256_hash
        and trusted_sha256
        and not hmac.compare_digest(sha256_hash.lower(), str(trusted_sha256).lower())
    ):
        storage.delete_file(storage_key)
        file.status = "rejected"
        file.lifecycle_version += 1
        db.commit()
        raise DatasetError("checksum_mismatch", "Uploaded file checksum does not match")
    file.file_size = actual_size
    file.mime_type = file.mime_type or info.get("content_type")
    file.md5_hash = (
        str(trusted_md5).lower()
        if trusted_md5 and re.fullmatch(r"[a-fA-F0-9]{32}", str(trusted_md5))
        else None
    )
    file.sha256_hash = (
        str(trusted_sha256).lower()
        if trusted_sha256
        and re.fullmatch(r"[a-fA-F0-9]{64}", str(trusted_sha256))
        else None
    )
    file.status = "uploaded"
    file.confirmed_at = utc_now()
    file.lifecycle_version += 1
    if dataset.status in {
        DatasetStatus.UPLOADING.value,
        DatasetStatus.READY.value,
    }:
        dataset.status = DatasetStatus.PROCESSING.value
    _refresh_counts(db, dataset)
    _audit(
        db,
        actor=actor,
        action="dataset.upload_confirmed",
        dataset=dataset,
        details={"file_id": file.id, "size_bytes": actual_size},
    )
    db.commit()
    db.refresh(file)
    return file


def download_url(
    *,
    dataset: Dataset,
    file_id: str,
    storage: StorageService,
) -> tuple[DatasetFile, str, int]:
    file = next(
        (
            candidate
            for candidate in dataset.files
            if candidate.id == file_id and candidate.status == "uploaded"
        ),
        None,
    )
    if file is None or not file.storage_key:
        raise DatasetError("file_not_found", "Dataset file was not found")
    if file.storage_provider != storage.provider_name:
        raise DatasetError("storage_provider_mismatch", "File provider is unavailable")
    expires_in = settings.dataset_signed_url_expiry_seconds
    return (
        file,
        storage.get_presigned_url(file.storage_key, expires_in, for_upload=False),
        expires_in,
    )


def delete_dataset_file(
    db: Session,
    *,
    actor: User,
    dataset: Dataset,
    file_id: str,
    storage: StorageService,
) -> DatasetFile:
    file = next((candidate for candidate in dataset.files if candidate.id == file_id), None)
    if file is None or file.status == "deleted":
        raise DatasetError("file_not_found", "Dataset file was not found")
    if file.storage_provider != storage.provider_name:
        raise DatasetError("storage_provider_mismatch", "File provider is unavailable")
    previous_status = file.status
    if file.storage_key and file.status in {"uploaded", "deleting"}:
        # Persist a recoverable intermediate record before the external side
        # effect. A crash can then be reconciled without losing object identity.
        if file.status != "deleting":
            file.status = "deleting"
            file.lifecycle_version += 1
            dataset.updated_at = utc_now()
            db.commit()
        try:
            storage.delete_file(file.storage_key)
        except RuntimeError:
            if previous_status == "uploaded":
                file.status = previous_status
                file.lifecycle_version += 1
                db.commit()
            raise
    file.status = "deleted"
    file.deleted_at = utc_now()
    file.lifecycle_version += 1
    _refresh_counts(db, dataset)
    _audit(
        db,
        actor=actor,
        action="dataset.file_deleted",
        dataset=dataset,
        details={"file_id": file.id},
    )
    db.commit()
    return file


def finalize_dataset(
    db: Session,
    *,
    actor: User,
    dataset: Dataset,
) -> Dataset:
    if not any(file.status == "uploaded" for file in dataset.files):
        raise DatasetError("dataset_empty", "Dataset has no completed files")
    require_transition(dataset.status, DatasetStatus.READY.value)
    dataset.status = DatasetStatus.READY.value
    dataset.processed_at = utc_now()
    dataset.updated_at = utc_now()
    dataset.lifecycle_version += 1
    if dataset.mission_id:
        acquisition = db.get(Acquisition, dataset.mission_id)
        if acquisition is not None:
            outputs = _array(acquisition.output_refs_json)
            if not any(
                isinstance(item, dict) and item.get("dataset_id") == dataset.id
                for item in outputs
            ):
                outputs.append({"type": "dataset", "dataset_id": dataset.id})
                acquisition.output_refs_json = _json(outputs)
                acquisition.updated_at = utc_now()
    _audit(
        db,
        actor=actor,
        action="dataset.finalized",
        dataset=dataset,
        details={"file_count": dataset.file_count},
    )
    return dataset


def archive_dataset(
    db: Session,
    *,
    actor: User,
    dataset: Dataset,
) -> Dataset:
    if dataset.status == DatasetStatus.ARCHIVED.value:
        return dataset
    require_transition(dataset.status, DatasetStatus.ARCHIVED.value)
    dataset.status = DatasetStatus.ARCHIVED.value
    dataset.archived_at = utc_now()
    dataset.updated_at = utc_now()
    dataset.lifecycle_version += 1
    _audit(
        db,
        actor=actor,
        action="dataset.archived",
        dataset=dataset,
        details={"retained_object_count": dataset.file_count},
    )
    return dataset


__all__ = [
    "archive_dataset",
    "complete_reserved_upload_from_stream",
    "confirm_reserved_upload",
    "create_dataset",
    "dataset_file_out",
    "dataset_out",
    "delete_dataset_file",
    "download_url",
    "finalize_dataset",
    "get_owned_dataset",
    "list_owned_datasets",
    "reserve_upload",
    "update_dataset",
    "upload_dataset_file",
]
