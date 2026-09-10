# Durable events and background workers

## Guarantee

GeoVision records every important cross-module fact in
`operational_domain_events`. The physical name is retained so existing Phase 10
data and imports survive, but the table is now the canonical transactional
outbox and is also exposed in Python as `EventOutbox`.

A domain service changes its aggregate and adds the event row using the same
SQLAlchemy session. It does not commit the event separately and it does not call
a broker. Therefore:

1. a rollback removes both the domain change and its event;
2. a commit makes both durable;
3. a crash after the commit but before broker delivery leaves a `pending` row;
4. a worker restart claims and publishes that row later.

The independent worker claims due rows in order. PostgreSQL uses
`FOR UPDATE SKIP LOCKED`; local SQLite uses the single-worker fallback. A claim
has a timeout, so a process crash cannot strand `processing` rows. Failures use
bounded exponential backoff. Malformed events, non-retryable failures, and
exhausted events move to `dead_letter`. Every attempt is recorded without
credentials or raw provider responses.

Run workers independently from API replicas:

```bash
python -m app.workers.event_worker
python -m app.workers.iot_worker
```

`--once` processes one cycle for release checks or local operations. The API can
host the event worker or IoT watchdog only through explicit local-development
flags; both flags default to false.

## Event contract

The wire envelope follows CloudEvents 1.0 fields and adds one `geovision`
extension containing the aggregate, schema version, correlation/causation IDs,
topic, and idempotency key. Payloads are bounded and contain internal GeoVision
IDs rather than credentials or provider SDK objects.

Canonical names cover organization and member lifecycle; order, payment, and
fulfilment; acquisition, upload, dataset, and processing; observations, KPIs,
actions, and reports; device telemetry/offline state; and ERP synchronization.
Names are lowercase dotted facts such as `dataset.file_uploaded`. Requested work
uses an explicit `*.requested` suffix.

The Phase 17 engine writes each KPI measurement and `kpi.updated`, each
observation and `observation.created`, and each generated Action and
`action.requested` in the same caller transaction. Completing an Action writes
its structured outcome and `action.completed` atomically. Event payloads carry
only GeoVision IDs, status/provenance identifiers and timestamps—not raster
values, unrestricted metadata or credentials.

Consumers insert an `event_consumer_receipts` row before applying database
effects. The receipt and effects share one transaction and the pair
`(consumer_name, event_id)` is unique. Azure Service Bus is deliberately treated
as at-least-once delivery: a redelivered message is safe even if broker-side
duplicate detection is unavailable or its history window has elapsed.

## Providers

`QUEUE_PROVIDER=database` is the credential-free default. The worker invokes
registered consumers and persists receipts directly. An in-memory publisher is
available only as a deterministic test double. `null` is rejected for deployed
environments and sends work to dead letter instead of silently discarding it.

`QUEUE_PROVIDER=azure_service_bus` publishes to a configured topic. Prefer
`SERVICE_BUS_FULLY_QUALIFIED_NAMESPACE` with workload or managed identity;
`SERVICE_BUS_CONNECTION_STRING` is a secret compatibility option. The worker
uses peek-lock receiving, completes only after the consumer transaction commits,
abandons retryable failures, and dead-letters deliveries that reach the bounded
attempt limit. Configure Standard or Premium topic duplicate detection and use
the GeoVision event UUID as `MessageId`; consumer receipts remain mandatory.

The required Azure identity needs only the data-plane sender or receiver role on
the intended namespace/entity. API identities do not need Service Bus access
because domain requests only write PostgreSQL.

## Azure BlobCreated bridge

`POST /integrations/events/azure/blob-created` accepts Event Grid schema or
CloudEvents 1.0 deliveries. It performs the subscription validation handshake,
checks the configured custom delivery secret and optional subscription name,
restricts HTTPS blob URLs to the configured storage account/container, and
normalizes only `Microsoft.Storage.BlobCreated`.

The dataset application service receives a provider-neutral object notification.
It matches an existing Azure upload reservation, checks the reserved size, marks
the file uploaded, and enqueues `dataset.ingestion_requested` in the same
database transaction. The Event Grid event ID becomes a deterministic
idempotency key, so delivery retries cannot enqueue ingestion twice. Unmatched
objects are reported but never attached to a tenant or dataset.

## ERP migration and operations

The older `integration_outbox` remains the ERP-specific command record and
provider status surface. Enqueuing it now also creates `erp.sync_requested` in
the general outbox. The event worker locks and processes the pinned ERP record,
then records `erp.sync_completed` or `erp.sync_failed`. The old administrator
sync endpoint remains compatible during cutover. Provider-side uniqueness is
still required before uncertain external writes may be considered exactly once.

Administrators can inspect counts, dead letters, and attempt history under
`/integrations/events`. Requeue resets the delivery budget but retains the prior
attempt audit. Requeue only after correcting the payload consumer, provider
configuration, or downstream data problem.

## Remaining background boundaries

- MQTT remains an ingress adapter hosted with the API when explicitly enabled;
  it persists telemetry and a durable event before broadcasting the optional
  in-memory WebSocket update. A dedicated managed MQTT/IoT ingress and
  cross-replica WebSocket fan-out remain deployment work.
- Object deletion retains the Phase 12 database tombstone saga because an
  external delete cannot share a SQL transaction. Its reconciler can move to a
  dedicated event consumer when provider migration requires it.
- Email/push fan-out and future processing engines must register idempotent
  consumers rather than execute long work inside HTTP requests.

No Azure package is imported by a domain module, and local development requires
no Azure account or emulator.
