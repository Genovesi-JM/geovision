# GeoVision fulfilment jobs

Phase 10 separates what a customer purchases from the operational work needed
to deliver it. `orders` and `order_items` remain the commercial agreement and
immutable pricing snapshot. `fulfilment_jobs` is the private execution queue.

## Job model

Each job has a stable GeoVision number and references its order, optional order
line, and optional generic asset. It records an extensible type, priority,
guarded state, one contractor or internal assignee, schedule and actual dates,
structured requirements, optimistic lifecycle version, and internal direct
cost fields. Cost, cost reference, assignee identity, plan key, and order links
are not present on customer or contractor projections.

The standard type vocabulary is:

- `FLIGHT_CAPTURE`
- `SATELLITE_ACQUISITION`
- `SENSOR_INSTALLATION`
- `PROCESS_DATA`
- `ANALYST_REVIEW`
- `SPECIALIST_REVIEW`
- `DELIVER_PRODUCT`
- `PUBLISH_REPORT`

Types are normalized strings rather than a database enum, so a future adapter
or sector can add work without a schema migration.

## Planning and dependencies

`POST /operations/jobs/plan-order/{order_id}` expands each order line using its
catalogue fulfilment snapshot. A field service becomes capture, processing,
analyst review, and report publication. Remote analysis begins with satellite
acquisition; installations and physical products produce installation and
delivery work respectively. Stable plan keys make the operation idempotent.

Dependencies live in `fulfilment_job_dependencies`. They must stay within one
order and cannot be self-referential or cyclic. Downstream work begins blocked
and automatically becomes ready only after every upstream job completes.
Processing additionally requires an explicit completed input dependency, so a
data-processing job cannot start before its upload/acquisition work.

The guarded lifecycle is:

`PLANNED -> READY -> ASSIGNED -> SCHEDULED -> IN_PROGRESS -> QA_REVIEW -> COMPLETED`

Work may enter `WAITING_INPUT` or `BLOCKED` and resume through validated paths.
Failure and cancellation require a reason and are terminal. Starting manual
work requires an assignee; scheduling requires both an assignee and a valid
time window. Optimistic versions reject stale assignment, scheduling, and
state updates.

## API privacy boundaries

GeoVision Operations owns job creation, planning, queue filters, dependency,
assignment, scheduling, and state routes under `/operations/jobs`.

A linked contractor can read only jobs assigned to its own private profile at
`/operations/contractor/me/jobs`. The response contains execution necessities
but no order/customer identifiers, internal staff identities, direct costs,
cost references, margins, or planning keys.

An authorized customer reads `/orders/{order_id}/progress`. Status and percent
complete are derived from safe job stages. The response never reveals which
contractor or employee performs the work and contains no operational costs.

## Event boundary

Every creation, dependency, assignment, scheduling, transition, and automatic
unblock emits an idempotent event through `DomainEventPublisher`. The Phase 10
adapter stores it in `operational_domain_events` in the same transaction as the
job change. This is intentionally a replaceable local implementation; Phase 13
can add durable broker/outbox delivery without changing job services.

## Migration and rollback

`fulfilment_jobs_v1` creates jobs, dependency edges, and the local event ledger,
then adds the foreign key reserved by Phase 9 assignments. Its downgrade drops
only Phase 10 records and clears the now-invalid optional Phase 9 job link before
removing the tables. Orders, lines, contractors, and assignments remain intact.
Export Phase 10 job/event history before any production rollback.

Automated acceptance covers multi-job planning, idempotency, explicit chains,
cycle and premature-processing rejection, auto-unblocking, invalid terminal
transitions, contractor scoping, customer/cost redaction, local event emission,
and SQLite downgrade/re-upgrade preservation. PostgreSQL and full backend,
browser, and mobile regression checks are phase completion gates.

The Phase 10 application contract contains 279 HTTP/WebSocket routes with
route SHA-256
`3d1a5bcbdc1b1cf843fc102b96ce2b5f7c6239e5380bf9e9915e4318b6518a47`.
Its canonical JSON OpenAPI SHA-256 is
`bf2e0bcb4465f13d0cfce63f9768d7e1417b027733148ca402b378d0d346e18f`.
