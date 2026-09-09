# GeoVision Operations resources

Phase 9 keeps suppliers and contractors on GeoVision's private operational
surface. They are qualification and assignment records, not sellers, public
profiles, bidders, storefronts, or payment recipients. Customers continue to
buy only from GeoVision.

## Resource model

`procurement_suppliers` remains the internal source attached to first-party
catalogue items. It now records country/region, service areas, procurement
capabilities, certification and insurance metadata, document references,
quality score, and last review time. Existing supplier IDs, catalogue links,
notes, and contact data are preserved.

`operations_contractors` represents pilots, agronomists, technicians,
installers, surveyors, analysts, engineers, companies, and future resource
types without imposing drone-only fields. A profile can optionally link one
GeoVision user identity for restricted access. Its private qualification record
includes:

- country, region, and structured service areas;
- status and current availability;
- certifications/licences and insurance metadata;
- equipment capabilities and document references;
- verified capability links, quality score, and internal notes; and
- operational contact details.

Sensitive credential-like keys are rejected from all structured resource,
insurance, equipment, document, location, requirement, and upload metadata.
Secret material belongs in the platform's configured secret stores, never in a
supplier or contractor profile.

## Capability taxonomy

`operational_capabilities` is extensible and categorized rather than tied to a
single worker type. The migration seeds RGB, RTK, MULTISPECTRAL, THERMAL,
LIDAR; all five sector expertise codes; and baseline agronomy, IoT installation,
field technician, surveying, and data-analysis skills. GeoVision Operations can
add or deactivate future capabilities without a schema change.

Contractors link to capabilities through `contractor_capabilities`, leaving
space for proficiency, verification, expiry, and private notes. Search can
combine country, region, capability or sector, resource type, availability,
status, and free text.

## Assignment and least-privilege access

`contractor_assignments` is a provider-independent assignment record. It can
reference both a GeoVision order and the canonical Phase 10 fulfilment job; the
database now enforces that job reference. Its guarded lifecycle is:

`OFFERED -> ACCEPTED -> ACTIVE -> COMPLETED`

An offer can be declined or cancelled; accepted/active work can be cancelled.
Terminal states cannot be reopened. Optimistic lifecycle versions reject stale
decisions and updates.

The authenticated contractor surface exposes only the contractor's own:

- profile fields and qualification document references;
- assignment reference, title, status, location and time window;
- mission/work requirements and required documents; and
- opaque GeoVision upload area.

It deliberately omits order IDs, organization IDs, billing totals, agreed
contractor costs, margins, internal notes, assigning staff IDs, supplier data,
and unrelated assets or assignments. Cross-contractor assignment IDs return
not found. A customer without an active linked contractor profile receives no
contractor access.

## Internal APIs

GeoVision Operations (`GV_OPERATIONS` or `GV_SUPER_ADMIN`) owns:

- `GET/POST/PATCH /operations/capabilities`
- `GET/POST/PATCH/DELETE /operations/contractors`
- `GET/POST/PATCH /operations/assignments`

`DELETE` deactivates a contractor rather than destroying qualification or
assignment history. Catalogue/inventory/sales/operations staff retain private
supplier management under:

- `GET/POST /catalog/internal/suppliers`
- `GET/PATCH/DELETE /catalog/internal/suppliers/{supplier_id}`

Supplier and contractor list endpoints support private search. No public or
customer route lists either resource type.

The restricted linked-contractor API is:

- `GET /operations/contractor/me/profile`
- `GET /operations/contractor/me/assignments`
- `GET /operations/contractor/me/assignments/{assignment_id}`
- `POST /operations/contractor/me/assignments/{assignment_id}/decision`

## Migration and rollback

`operations_resources_v1` additively extends supplier rows, creates the
capability, contractor, link, and assignment tables, and seeds deterministic
baseline capability IDs. It does not rewrite supplier contact/qualification
data or customer/order records.

Rollback removes only Phase 9 tables and supplier enrichment columns. Existing
supplier rows, catalogue links, orders, users, and earlier phase data remain.
Any Phase 9 contractor/assignment records must be exported and reviewed before
a production rollback because their tables are intentionally phase-owned.

## Acceptance coverage

Automated coverage proves internal permission checks, region/capability
matching, generic non-flight fields, supplier search, metadata secret rejection,
contractor self-access, cross-assignment denial, financial/internal-field
redaction, guarded assignment decisions, baseline taxonomy seeding, and
SQLite migration downgrade/re-upgrade preservation. PostgreSQL migration and
full web/mobile regression checks remain part of the phase completion gate.

The Phase 9 application contract contains 268 HTTP/WebSocket routes with route
SHA-256 `ca4d3f3e585033daa743a0f03de562b5711dfdd1444fd4c3dbbc3110b1a67d31`.
Its canonical JSON OpenAPI SHA-256 is
`7fb493843a0b77ad5486b9324d22d9113d7b1a8de9ddf5bf3646032e6a0c1ad1`.
