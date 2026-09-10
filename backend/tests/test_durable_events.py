from __future__ import annotations

from pathlib import Path
import uuid

import pytest

from app.core.config import Settings
from app.core.event_names import CANONICAL_EVENT_NAMES, EventNames
from app.core.integration import (
    IntegrationFailure,
    IntegrationResult,
    IntegrationStatus,
)
from app.integrations.events.azure_event_grid import (
    EventGridPayloadError,
    parse_event_grid_batch,
)
from app.models import (
    AccountEvent,
    Dataset,
    DatasetFile,
    EventConsumerReceipt,
    EventDeliveryAttempt,
    EventOutbox,
)
from app.services.blob_ingestion import enqueue_blob_ingestion_batch
from app.services.event_outbox import (
    EventConsumerRegistry,
    EventOutboxError,
    consume_once,
    dispatch_pending_events,
    enqueue_domain_event,
    event_from_row,
    requeue_dead_letter,
)


def _clean(db) -> None:
    db.query(EventDeliveryAttempt).delete()
    db.query(EventConsumerReceipt).delete()
    db.query(EventOutbox).delete()
    db.commit()


def _config(provider: str = "database", **values) -> Settings:
    return Settings(
        _env_file=None,
        queue_provider=provider,
        service_bus_fully_qualified_namespace=(
            "geovision-test.servicebus.windows.net"
            if provider == "azure_service_bus"
            else None
        ),
        event_retry_initial_seconds=0,
        event_retry_max_seconds=0,
        **values,
    )


class _FlakyPublisher:
    provider_name = "fake_queue"

    def __init__(self) -> None:
        self.calls = 0

    def publish(self, message):
        self.calls += 1
        if self.calls == 1:
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation="publish",
                failure=IntegrationFailure(
                    code="simulated_disconnect",
                    message="Broker was unavailable",
                    retryable=True,
                ),
                status=IntegrationStatus.RETRYING,
            )
        return IntegrationResult.succeeded(
            provider=self.provider_name,
            operation="publish",
        )


def test_commit_before_publish_survives_and_outbox_retries(db_session):
    _clean(db_session)
    row = enqueue_domain_event(
        db_session,
        name=EventNames.ORDER_CREATED,
        aggregate_type="order",
        aggregate_id=str(uuid.uuid4()),
        idempotency_key="crash-window-order-created",
        payload={"total": 42},
    )
    db_session.commit()  # Simulated process crash immediately after this commit.
    db_session.expire_all()
    assert db_session.get(EventOutbox, row.id).status == "pending"

    publisher = _FlakyPublisher()
    first = dispatch_pending_events(
        db_session,
        worker_id="worker-restart",
        registry=EventConsumerRegistry(),
        config=_config("azure_service_bus"),
        queue_publisher=publisher,
    )
    db_session.expire_all()
    retried = db_session.get(EventOutbox, row.id)
    assert first["retried"] == 1
    assert retried.status == "retry"
    assert retried.publish_attempts == 1

    second = dispatch_pending_events(
        db_session,
        worker_id="worker-restart",
        registry=EventConsumerRegistry(),
        config=_config("azure_service_bus"),
        queue_publisher=publisher,
    )
    db_session.expire_all()
    published = db_session.get(EventOutbox, row.id)
    assert second["published"] == 1
    assert published.status == "published"
    assert published.publish_attempts == 2
    assert publisher.calls == 2
    assert [attempt.outcome for attempt in db_session.query(EventDeliveryAttempt).all()] == [
        "retry",
        "published",
    ]


def test_consumer_receipt_prevents_duplicate_database_effect(db_session):
    _clean(db_session)
    row = enqueue_domain_event(
        db_session,
        name=EventNames.REPORT_PUBLISHED,
        aggregate_type="report",
        aggregate_id="report-1",
        idempotency_key="report-1-published",
        payload={"organization_id": "organization-1"},
    )
    db_session.commit()
    event = event_from_row(row)

    def handler(db, received):
        db.add(
            AccountEvent(
                company_id=str(received.payload["organization_id"]),
                event_type=received.name,
                resource_type="report",
                resource_id=received.aggregate_id,
                title="Report published",
            )
        )

    assert consume_once(
        db_session,
        consumer_name="customer_report_feed_v1",
        event=event,
        handler=handler,
    )
    db_session.commit()
    assert not consume_once(
        db_session,
        consumer_name="customer_report_feed_v1",
        event=event,
        handler=handler,
    )
    db_session.commit()
    assert db_session.query(AccountEvent).filter_by(resource_id="report-1").count() == 1
    assert db_session.query(EventConsumerReceipt).filter_by(event_id=row.id).count() == 1


def test_poison_event_dead_letters_and_operator_can_requeue(db_session):
    _clean(db_session)
    row = enqueue_domain_event(
        db_session,
        name=EventNames.PROCESSING_REQUESTED,
        aggregate_type="dataset",
        aggregate_id="dataset-poison",
        idempotency_key="dataset-poison-processing",
    )
    db_session.commit()
    failing = EventConsumerRegistry()

    def reject(_db, _event):
        raise EventOutboxError("invalid_processing_request", "Unsupported payload")

    failing.register(EventNames.PROCESSING_REQUESTED, "processor_v1", reject)
    result = dispatch_pending_events(
        db_session,
        worker_id="worker-poison",
        registry=failing,
        config=_config(),
    )
    db_session.expire_all()
    assert result["dead_lettered"] == 1
    assert db_session.get(EventOutbox, row.id).status == "dead_letter"

    recovered = requeue_dead_letter(db_session, row.id)
    assert recovered is not None
    db_session.commit()
    healthy = EventConsumerRegistry()
    healthy.register(EventNames.PROCESSING_REQUESTED, "processor_v1", lambda *_: None)
    result = dispatch_pending_events(
        db_session,
        worker_id="worker-recovery",
        registry=healthy,
        config=_config(),
    )
    assert result["published"] == 1
    assert db_session.get(EventOutbox, row.id).status == "published"


def test_event_grid_blob_created_normalizes_and_enqueues_ingestion(db_session):
    _clean(db_session)
    secret = "phase-13-event-grid-secret-value-long-enough"
    config = _config(
        azure_event_grid_enabled=True,
        azure_event_grid_webhook_secret=secret,
        azure_storage_account_url="https://geovision.blob.core.windows.net",
        azure_storage_container="geovision-datasets",
    )
    dataset_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())
    object_key = f"org/asset/mission/{dataset_id}/raw/{file_id}-ortho.tif"
    db_session.add(
        Dataset(
            id=dataset_id,
            company_id="organization-grid",
            name="Event Grid upload",
            storage_provider="azure_blob",
            status="uploading",
        )
    )
    db_session.add(
        DatasetFile(
            id=file_id,
            dataset_id=dataset_id,
            filename="ortho.tif",
            storage_key=object_key,
            storage_provider="azure_blob",
            file_size=4,
            status="pending_upload",
        )
    )
    db_session.commit()
    payload = [
        {
            "id": "831e1650-001e-001b-66ab-eeb76e069631",
            "eventType": "Microsoft.Storage.BlobCreated",
            "eventTime": "2026-09-10T00:00:00Z",
            "data": {
                "url": (
                    "https://geovision.blob.core.windows.net/"
                    f"geovision-datasets/{object_key}"
                ),
                "contentLength": 4,
                "contentType": "image/tiff",
                "eTag": "test-etag",
            },
        }
    ]
    batch = parse_event_grid_batch(
        payload,
        headers={"x-geovision-event-grid-secret": secret},
        config=config,
    )
    assert batch.notifications[0].object_key == object_key
    assert enqueue_blob_ingestion_batch(db_session, batch.notifications) == {
        "accepted": 1,
        "duplicate": 0,
        "unmatched": 0,
    }
    db_session.commit()
    db_session.expire_all()
    assert db_session.get(DatasetFile, file_id).status == "uploaded"
    event = db_session.query(EventOutbox).filter_by(
        event_type=EventNames.DATASET_INGESTION_REQUESTED
    ).one()
    assert event.status == "pending"
    assert enqueue_blob_ingestion_batch(db_session, batch.notifications) == {
        "accepted": 0,
        "duplicate": 1,
        "unmatched": 0,
    }

    validation = parse_event_grid_batch(
        [
            {
                "id": "validation-id",
                "eventType": "Microsoft.EventGrid.SubscriptionValidationEvent",
                "data": {"validationCode": "validation-code"},
            }
        ],
        headers={"x-geovision-event-grid-secret": secret},
        config=config,
    )
    assert validation.validation_code == "validation-code"
    with pytest.raises(EventGridPayloadError):
        parse_event_grid_batch(payload, headers={}, config=config)


def test_event_vocabulary_covers_every_cross_module_workflow_and_domains_are_azure_free():
    required_prefixes = {
        "organization.",
        "order.",
        "payment.",
        "fulfilment_job.",
        "acquisition.",
        "dataset.",
        "processing.",
        "observation.",
        "kpi.",
        "action.",
        "report.",
        "device.",
        "erp.",
    }
    assert all(any(name.startswith(prefix) for name in CANONICAL_EVENT_NAMES) for prefix in required_prefixes)
    module_root = Path(__file__).resolve().parents[1] / "app" / "modules"
    assert all(
        "azure." not in path.read_text(encoding="utf-8")
        for path in module_root.rglob("*.py")
    )
