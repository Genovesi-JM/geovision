"""Composition of application-level event consumers."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.event_names import EventNames
from app.core.events import DomainEvent
from app.models import (
    Asset,
    IotAlert,
    IotDevice,
    IntegrationOutbox,
    TelemetryReading,
    TelemetryReceipt,
)
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


def _consume_iot_projection_repair(db: Session, event: DomainEvent) -> None:
    """Retry an isolated IoT customer-intelligence projection failure."""

    if event.payload.get("intelligence_reason") != "projection_failed":
        return
    receipt_id = str(event.payload.get("receipt_id") or "")
    device_id = str(event.payload.get("device_id") or event.aggregate_id or "")
    organization_id = str(event.payload.get("organization_id") or "")
    asset_id = str(event.payload.get("asset_id") or "")
    workspace_id = str(event.payload.get("workspace_id") or "")
    receipt = db.get(TelemetryReceipt, receipt_id) if receipt_id else None
    device_query = db.query(IotDevice).filter(IotDevice.id == device_id)
    # Ingestion holds this same lock. Repair workers must join that serialized
    # device stream so two failed receipts cannot concurrently create the same
    # query-then-insert KPI definition or split its measurement history.
    if db.get_bind().dialect.name == "postgresql":
        device_query = device_query.with_for_update()
    device = device_query.one_or_none() if device_id else None
    asset = db.get(Asset, asset_id) if asset_id else None
    if (
        receipt is None
        or device is None
        or asset is None
        or receipt.out_of_order
        or not organization_id
        or not asset_id
        or not workspace_id
        or receipt.device_id != device.id
        or receipt.company_id != organization_id
        or receipt.core_asset_id != asset_id
        or device.company_id != organization_id
        or asset.organization_id != organization_id
        or asset.workspace_id != workspace_id
    ):
        raise EventOutboxError(
            "iot_projection_event_invalid",
            "IoT projection repair scope does not match its durable receipt",
        )

    rows = (
        db.query(TelemetryReading)
        .filter(
            TelemetryReading.receipt_id == receipt.id,
            TelemetryReading.device_id == device.id,
            TelemetryReading.company_id == organization_id,
        )
        .order_by(TelemetryReading.channel.asc(), TelemetryReading.id.asc())
        .all()
    )
    if len(rows) != receipt.measurement_count:
        raise EventOutboxError(
            "iot_projection_readings_incomplete",
            "IoT projection repair is waiting for all receipt readings",
            retryable=True,
        )

    readings = []
    for row in rows:
        if row.numeric_value is not None:
            value = row.numeric_value
        elif row.boolean_value is not None:
            value = row.boolean_value
        else:
            value = row.text_value
        readings.append(
            {
                "channel": row.channel,
                "value": value,
                "unit": row.unit,
                "quality": row.quality,
            }
        )

    alert_ids = tuple(
        str(value) for value in event.payload.get("alert_ids", ()) if str(value).strip()
    )
    alerts = (
        db.query(IotAlert)
        .filter(
            IotAlert.id.in_(alert_ids),
            IotAlert.device_id == device.id,
            IotAlert.company_id == organization_id,
        )
        .all()
        if alert_ids
        else []
    )
    unit_by_channel = {row.channel: row.unit for row in rows}
    alert_events = [
        {
            "type": "alert.triggered",
            "id": alert.id,
            "severity": alert.severity,
            "message": alert.message,
            "channel": alert.channel,
            "value": alert.value,
            "unit": unit_by_channel.get(alert.channel),
        }
        for alert in alerts
    ]

    from app.iot.intelligence import materialize_iot_intelligence

    result = materialize_iot_intelligence(
        db,
        device=device,
        receipt=receipt,
        readings=readings,
        alert_events=alert_events,
        measured_at=receipt.recorded_at,
    )
    if not result.materialized:
        raise EventOutboxError(
            "iot_projection_repair_deferred",
            "IoT projection repair dependencies are not currently available",
            retryable=True,
        )


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
    registry.register(
        EventNames.DEVICE_TELEMETRY_RECEIVED,
        "iot_intelligence_projection_repair_v1",
        _consume_iot_projection_repair,
    )
    if config.processing_auto_create_enabled:
        registry.register(
            EventNames.DATASET_READY,
            "automatic_processing_job_v1",
            lambda db, event: _consume_dataset_ready(db, event, config=config),
        )
    return registry


__all__ = ["default_event_consumers"]
