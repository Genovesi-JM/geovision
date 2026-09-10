# GeoVision event catalogue

`backend/app/core/event_names.py` is the executable authority for the event
vocabulary. Events are immutable provider-neutral facts in past tense; names
ending in `.requested` are durable commands for later work. They are written in
the same database transaction as the state change, then claimed with bounded
retry and idempotent consumer receipts.

| Domain | Canonical events |
|---|---|
| Organization and invitation | `organization.created`, `organization.updated`, `organization.member_added`, `organization.member_invited`, `organization.member_updated`, `organization.member_removed`, `invitation.created` |
| Order, payment, and shipment | `order.created`, `order.state_changed`, `shipment.state_changed`, `payment.authorized`, `payment.settled`, `payment.failed`, `payment.state_changed` |
| Fulfilment | `fulfilment_job.created`, `fulfilment_job.dependency_added`, `fulfilment_job.assignment_changed`, `fulfilment_job.schedule_changed`, `fulfilment_job.dependencies_satisfied`, `fulfilment_job.state_changed` |
| Acquisition | `acquisition.created`, `acquisition.updated`, `acquisition.state_changed`, `acquisition.upload_completed` |
| Dataset | `dataset.created`, `dataset.upload_reserved`, `dataset.file_uploaded`, `dataset.file_deleted`, `dataset.ingestion_requested`, `dataset.ready`, `dataset.archived` |
| Processing and monitoring acquisition | `processing.requested`, `processing.needs_review`, `processing.completed`, `processing.failed`, `processing.cancelled`, `intelligence.acquisition_requested`, `intelligence.acquisition_failed`, `satellite.acquisition_completed`, `weather.acquisition_completed` |
| Intelligence and reports | `observation.created`, `kpi.updated`, `action.requested`, `action.completed`, `report.generated`, `report.review_requested`, `report.approved`, `report.published`, `report.superseded` |
| Notifications | `notification.created`, `notification.delivered`, `notification.delivery_failed` |
| IoT | `device.telemetry_received`, `device.state_changed`, `device.alert_triggered`, `device.offline_detected`, `device.command_result_recorded` |
| ERP | `erp.sync_requested`, `erp.sync_completed`, `erp.sync_failed` |
| Integration registry | `integration.connection.created`, `integration.connection.updated`, `integration.connection.enabled`, `integration.connection.disabled`, `integration.connection.disconnected`, `integration.sync_requested`, `integration.sync_started`, `integration.sync_succeeded`, `integration.sync_failed`, `integration.retry_scheduled`, `integration.dead_lettered`, `integration.circuit_opened`, `integration.circuit_closed` |

## Current durable consumers

| Consumer | Input | Effect |
|---|---|---|
| Notification materializer | invitation, published report, requested action, IoT alert/offline, order/shipment, fulfilment state/schedule | Creates a recipient-bound inbox row and provider-pinned delivery rows; target authorization is checked again on open. |
| IoT intelligence repair | `device.telemetry_received` with `projection_failed` | Reconstructs the validated reading/alert snapshot from the durable receipt and idempotently retries KPI, observation, and action projection. On PostgreSQL it holds the same per-device row lock as ingestion so concurrent repairs cannot split a device/channel KPI definition. |
| ERP signal consumer | `erp.sync_requested` | Validates the referenced ERP outbox command. Provider I/O belongs to the ERP worker. |
| Automatic processing consumer | `dataset.ready` when enabled | Creates an idempotent processing job for an eligible dataset. |

Independent ERP, notification, processing, and intelligence workers own their
provider calls. The event worker never calls HTTP route handlers and commits a
consumer receipt with each local side effect.

## Compatibility realtime projections

`AccountEvent` (`account_events`) is a separate customer-facing activity
projection consumed by `/mobile/account/events` and `/mobile/account/stream`.
It currently carries the compatibility facts `site.created`,
`service_request.created`, `service_request.updated`, and the legacy-shop
`order.created`. Workspace-aware producers record both organization and
workspace. The migration backfills a legacy unscoped row only when its
organization has exactly one active workspace; any row that remains unscoped is
not visible through the customer feed. These names are not transactional-outbox
commands and must not be used to start provider work. New asynchronous behavior
belongs in the canonical vocabulary above.

The in-process IoT `DeviceEventHub` used by WebSocket clients is also a live
projection, not durable delivery. Raw telemetry receipts and the transactional
outbox remain the recovery boundary.

## Contract rules

- Add a name to `EventNames` before emitting it. The documentation contract
  flags drift from that canonical vocabulary; the outbox itself accepts a
  bounded dotted extension name so separately deployed consumers can evolve.
- Service and schema boundaries reject credential-shaped input before an event
  is built. The outbox validates JSON shape and size, but it is not a secret
  scanner; emitter tests must prove canonical payloads contain no credentials.
- Payloads carry GeoVision IDs, correlation/causation IDs, bounded safe values,
  and versioned semantics. They do not carry credentials or raw provider
  responses.
- Use a stable business idempotency key. Consumer idempotency is keyed by
  consumer and event ID; provider writes also require provider-side
  idempotency proof.
- Renaming or changing the meaning of an event is a compatibility change. Add a
  new event/version or an explicit compatibility consumer instead.
