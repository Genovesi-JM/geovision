"""Composition of application-level event consumers."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.event_names import EventNames
from app.core.events import DomainEvent
from app.models import IntegrationOutbox
from app.services.event_outbox import (
    EventConsumerRegistry,
    EventOutboxError,
)


def _consume_erp_sync(db: Session, event: DomainEvent) -> None:
    """Acknowledge the wake-up signal; the ERP worker owns provider I/O.

    This consumer deliberately performs no network calls. Rolling back the
    generic event transaction can therefore never erase an ERP attempt or its
    retry/dead-letter state.
    """
    item_id = str(event.payload.get("integration_outbox_id") or "")
    if not item_id:
        raise EventOutboxError(
            "erp_event_invalid",
            "ERP sync request is missing its integration outbox ID",
        )
    query = db.query(IntegrationOutbox).filter(IntegrationOutbox.id == item_id)
    if db.get_bind().dialect.name == "postgresql":
        query = query.with_for_update()
    item = query.one_or_none()
    if item is None:
        raise EventOutboxError(
            "erp_item_missing", "ERP sync request no longer has a source record"
        )
    event_provider = str(event.payload.get("provider") or "")
    if event_provider and event_provider != item.provider:
        raise EventOutboxError(
            "erp_provider_mismatch",
            "ERP sync signal does not match the provider pinned on its source record",
        )


def _consume_dataset_ready(
    db: Session,
    event: DomainEvent,
    *,
    config: Settings,
) -> None:
    from app.modules.processing.services import ensure_automatic_processing_job

    dataset_id = str(event.payload.get("dataset_id") or event.aggregate_id or "")
    if not dataset_id:
        raise EventOutboxError(
            "dataset_event_invalid", "Dataset-ready event is missing its dataset ID"
        )
    ensure_automatic_processing_job(db, dataset_id=dataset_id, config=config)


def _consume_notification_event(
    db: Session,
    event: DomainEvent,
    *,
    config: Settings,
) -> None:
    from app.modules.notifications.materializer import materialize_notification_event

    materialize_notification_event(db, event, config=config)


def default_event_consumers(config: Settings = settings) -> EventConsumerRegistry:
    registry = EventConsumerRegistry()
    from app.modules.notifications.materializer import NOTIFICATION_EVENT_NAMES

    for event_name in NOTIFICATION_EVENT_NAMES:
        registry.register(
            event_name,
            "notification_materializer_v1",
            lambda db, event, config=config: _consume_notification_event(
                db, event, config=config
            ),
        )
    registry.register(
        EventNames.ERP_SYNC_REQUESTED,
        "erp_sync_outbox_v1",
        _consume_erp_sync,
    )
    if config.processing_auto_create_enabled:
        registry.register(
            EventNames.DATASET_READY,
            "automatic_processing_job_v1",
            lambda db, event: _consume_dataset_ready(db, event, config=config),
        )
    return registry


__all__ = ["default_event_consumers"]
