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
    enqueue_domain_event,
)


def _consume_erp_sync(db: Session, event: DomainEvent) -> None:
    from app.integrations.erp import get_erp_adapter
    from app.services.erp_sync import process_outbox_item

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
    provider = get_erp_adapter()
    outcome = process_outbox_item(
        db,
        item,
        provider=provider,
        raise_retryable=True,
    )
    result_event = (
        EventNames.ERP_SYNC_COMPLETED
        if outcome == "completed"
        else EventNames.ERP_SYNC_FAILED
    )
    enqueue_domain_event(
        db,
        name=result_event,
        aggregate_type=item.aggregate_type,
        aggregate_id=item.aggregate_id,
        idempotency_key=f"erp-result:{item.id}:{outcome}",
        correlation_id=event.correlation_id,
        causation_id=str(event.event_id),
        payload={
            "integration_outbox_id": item.id,
            "organization_id": item.company_id,
            "provider": item.provider,
            "external_reference": item.external_id,
            "outcome": outcome,
        },
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
