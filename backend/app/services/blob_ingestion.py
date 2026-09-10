"""Application bridge from normalized object events to dataset ingestion."""

from __future__ import annotations

import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.event_names import EventNames
from app.core.time import utc_now
from app.integrations.events.azure_event_grid import BlobCreatedNotification
from app.models import Dataset, DatasetFile, EventOutbox
from app.services.event_outbox import EventOutboxError, enqueue_domain_event


_EVENT_GRID_NAMESPACE = uuid.UUID("deea790d-8c46-4a2b-9965-16ec190359c7")


def _refresh_counts(db: Session, dataset: Dataset) -> None:
    count, size = (
        db.query(func.count(DatasetFile.id), func.coalesce(func.sum(DatasetFile.file_size), 0))
        .filter(
            DatasetFile.dataset_id == dataset.id,
            DatasetFile.status == "uploaded",
        )
        .one()
    )
    dataset.file_count = int(count or 0)
    dataset.total_size_bytes = int(size or 0)
    dataset.updated_at = utc_now()


def enqueue_blob_ingestion(
    db: Session,
    notification: BlobCreatedNotification,
) -> str:
    """Confirm a reserved blob and enqueue ingestion in one DB transaction."""

    idempotency_key = f"azure-event-grid:{notification.event_id}"
    existing = (
        db.query(EventOutbox.id)
        .filter(EventOutbox.idempotency_key == idempotency_key)
        .first()
    )
    if existing is not None:
        return "duplicate"
    file = (
        db.query(DatasetFile)
        .filter(
            DatasetFile.storage_provider == "azure_blob",
            DatasetFile.storage_key == notification.object_key,
            DatasetFile.deleted_at.is_(None),
        )
        .one_or_none()
    )
    if file is None:
        return "unmatched"
    if file.status not in {"pending_upload", "uploaded"}:
        raise EventOutboxError(
            "upload_state_conflict",
            "BlobCreated event does not match an active upload reservation",
        )
    if (
        notification.size_bytes
        and file.file_size
        and notification.size_bytes != file.file_size
    ):
        raise EventOutboxError(
            "upload_size_mismatch",
            "BlobCreated size does not match the upload reservation",
        )
    dataset = db.get(Dataset, file.dataset_id)
    if dataset is None or dataset.status == "archived":
        raise EventOutboxError(
            "dataset_unavailable", "BlobCreated dataset is unavailable"
        )
    file.status = "uploaded"
    file.file_size = notification.size_bytes or file.file_size
    file.mime_type = file.mime_type or notification.content_type
    file.confirmed_at = file.confirmed_at or utc_now()
    file.lifecycle_version += 1
    if dataset.status in {"uploading", "ready"}:
        dataset.status = "processing"
    _refresh_counts(db, dataset)
    deterministic_event_id = uuid.uuid5(
        _EVENT_GRID_NAMESPACE,
        notification.event_id,
    )
    enqueue_domain_event(
        db,
        name=EventNames.DATASET_INGESTION_REQUESTED,
        aggregate_type="dataset",
        aggregate_id=dataset.id,
        event_id=deterministic_event_id,
        occurred_at=notification.occurred_at,
        correlation_id=str(deterministic_event_id),
        idempotency_key=idempotency_key,
        payload={
            "dataset_id": dataset.id,
            "file_id": file.id,
            "organization_id": dataset.company_id,
            "workspace_id": dataset.workspace_id,
            "asset_id": dataset.asset_id,
            "mission_id": dataset.mission_id,
            "object_key": file.storage_key,
            "size_bytes": file.file_size,
            "source_event_id": notification.event_id,
        },
    )
    return "accepted"


def enqueue_blob_ingestion_batch(
    db: Session,
    notifications: tuple[BlobCreatedNotification, ...],
) -> dict[str, int]:
    stats = {"accepted": 0, "duplicate": 0, "unmatched": 0}
    for notification in notifications:
        outcome = enqueue_blob_ingestion(db, notification)
        stats[outcome] += 1
    return stats


__all__ = ["enqueue_blob_ingestion", "enqueue_blob_ingestion_batch"]
