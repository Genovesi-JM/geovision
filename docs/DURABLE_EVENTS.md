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
python -m app.workers.erp_worker
python -m app.workers.iot_worker
python -m app.workers.notification_worker
```

`--once` processes one cycle for release checks or local operations. The API can
host the event worker or IoT watchdog only through explicit local-development
flags; both flags default to false. External notification delivery remains an
independent process.

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

The contextual notification consumer currently subscribes to
`invitation.created`, `report.published`, `action.requested`,
`device.alert_triggered`, `device.offline_detected`,
`fulfilment_job.schedule_changed`, `fulfilment_job.state_changed`,
`order.created`, `order.state_changed`, and `shipment.state_changed`. It derives
customer content and targets from current GeoVision records rather than trusting
event-provided URLs/text. `notification.created`, `notification.delivered`, and
`notification.delivery_failed` are reserved names; the current delivery worker
persists its state directly and does not emit them yet.

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
provider status surface. Enqueuing it also creates `erp.sync_requested` in the
general outbox in the domain transaction. The general event consumer validates
and acknowledges that signal without provider I/O. The independent ERP worker
claims the provider-pinned command using a short lease, releases database locks
before the request, and records `erp.sync_completed` or `erp.sync_failed` after
the result. The old administrator sync endpoint remains compatible during
cutover. Odoo results populate a narrow provider/GeoVision UUID mapping and may
project invoice, stock and purchase status; an Odoo ID never replaces the
aggregate identity.

Odoo calls one custom JSON-2 bridge method with the same stable idempotency key.
The bridge must enforce that key before retry of an uncertain external write is
safe. A signed Odoo callback has a five-minute replay window, a unique
provider/event receipt and a raw-body digest; it can update only status fields on
an existing matching mapping. Callback failure never removes or rolls back the
owning GeoVision order.

Administrators inspect ERP counts, safe command details, tenant-filtered status
projections and controlled requeue under `/integrations/erp`. The separate
`/integrations/events` endpoints expose canonical-event state and attempts.
`python -m app.workers.erp_worker --requeue <OUTBOX_ID>` provides a server-side
ERP requeue. Requeue only after correcting the provider/data problem and
reconciling any timeout with the Odoo idempotency/mapping record. Switching
`ERP_PROVIDER` affects new commands; it does not reroute rows already pinned to
Odoo or ERPNext. See
[the Odoo 19 integration runbook](ODOO_19_INTEGRATION.md).

## Contextual notification projection

`notification_materializer_v1` stores one unique source-event/recipient link.
Repeated device/action facts inside the configured 15-minute grouping window
link to one notification and increase its occurrence count without enqueueing a
push/email for every reading. Inbox state is separate from the external
delivery queue, so SMTP or push failure cannot remove customer history or roll
back an owning aggregate.

The independent notification worker uses database claims, current membership,
preference/quiet-hour and endpoint revalidation, provider-pinned deliveries,
bounded backoff, stale-lease recovery and explicit dead-letter state. Push data
contains only the notification ID. The authenticated API resolves typed targets
against current authorization when opened. See
[the notification delivery contract](NOTIFICATION_DELIVERY.md).

## Remaining background boundaries

- MQTT remains an ingress adapter hosted with the API when explicitly enabled;
  it persists telemetry and a durable event before broadcasting the optional
  in-memory WebSocket update. A dedicated managed MQTT/IoT ingress and
  cross-replica WebSocket fan-out remain deployment work.
- Object deletion retains the Phase 12 database tombstone saga because an
  external delete cannot share a SQL transaction. Its reconciler can move to a
  dedicated event consumer when provider migration requires it.
- Future fan-out and processing engines must register idempotent consumers
  rather than execute long work inside HTTP requests.

No Azure package is imported by a domain module, and local development requires
no Azure account or emulator.
