# GeoVision acquisitions

Phase 11 gives every asset one chronological capture history, regardless of
whether its evidence came from a drone, satellite, IoT device, manual
inspection, or licensed third-party dataset. An Acquisition records the common
lifecycle and provenance. Capture-specific fields belong to optional extension
records instead of making one modality mandatory for all others.

## Common model

Every acquisition belongs to an organization and generic Asset. It may also
reference the commercial order and fulfilment job that requested it. The common
record stores:

- a stable GeoVision acquisition number and type;
- guarded lifecycle state and optimistic version;
- scheduled, started, captured, and completed timestamps;
- provider code/reference and structured provenance for internal operations;
- safe metadata and output references;
- legacy source identity while compatibility facades remain active.

The supported type vocabulary is `DRONE`, `SATELLITE`, `IOT`,
`MANUAL_INSPECTION`, and `THIRD_PARTY_DATA`. None requires drone-specific
columns.

The guarded lifecycle is:

`DRAFT -> PLANNED -> SCHEDULED -> IN_PROGRESS -> DATA_CAPTURED -> PROCESSING -> COMPLETED`

Valid shorter paths allow direct work from planned, completion after capture,
failure/cancellation, and a drone-only `NEEDS_REFLIGHT` loop. Scheduling needs a
complete time window. Failure, cancellation, and reflight decisions require a
reason. Terminal records cannot be edited.

## Drone extension

`drone_acquisition_details` optionally records aircraft and payload references,
one internal operator or contractor, mission requirements, Polygon or
MultiPolygon capture area, flight metadata, and a reasoned link to the original
acquisition for reflights. Satellite, IoT, inspection, and third-party records
never need this extension.

## API and privacy boundaries

Customer/workspace routes under `/missions` provide owned acquisition CRUD,
safe state changes, chronological asset history, and a modality-neutral output
feed. Provider references, provenance, internal identities, and sensitive raw
storage details are removed recursively from those projections.

GeoVision Operations uses `/missions/internal` for cross-customer filters,
provider/provenance details, output registration, assignments, and full state
control. Optimistic versions reject stale writes. All material changes create
audit records.

Sector modules consume `/missions/assets/{asset_id}/outputs` or the shared
`asset_acquisition_outputs` service. They receive acquisition type, timestamp,
state, and output references without importing a drone, satellite, or IoT
provider.

## Legacy compatibility and rollback

The `acquisitions_v1` migration backfills existing `drone_missions` and
`asset_inspections` with deterministic IDs and unique source mappings. Existing
mobile-drone and construction-inspection APIs remain valid and synchronize the
canonical record additively. Original flight requirements, route, capture area,
aircraft, provider reference, inspection checklist, result, photos, and location
remain mapped.

Downgrading removes only the Phase 11 acquisition tables; legacy source data is
preserved. Re-upgrading recreates the same canonical rows without duplication.
Export new acquisition-only records before a production rollback and verify
source/canonical counts before retiring either compatibility facade.

Automated acceptance covers mixed drone/satellite history, customer/internal
authorization and redaction, lifecycle guards, reflight linkage, modality-
neutral outputs, legacy API synchronization, and SQLite/PostgreSQL migration
round trips.

The Phase 11 application contract contains 291 HTTP/WebSocket routes with route
SHA-256
`a3b0d8b5aa6aa8970fa462e8d04883069a2355530d14ed553dc901d4c104f7ff`.
Its canonical JSON OpenAPI SHA-256 is
`e80da5106dced5e34b7d75fdd07863e326a5529a034aa8f8849225c7892c210b`.
