# Generic Asset and PostGIS foundation

Phase 5 introduces one cross-sector spatial hierarchy for customer-owned
operational objects. Farms, fields, environmental sites, construction assets,
mines, terminals, tanks, IoT equipment, and future sector types now share the
same `Asset` lifecycle and tenant boundary.

## Canonical ownership and identifiers

Every asset has an immutable GeoVision UUID and an `organization_id`. New API
writes also carry the selected `workspace_id`; organization-only legacy rows
remain readable through any explicitly selected workspace in that organization
until their owning clients are migrated. Parent and child assets must belong to
the same organization and selected workspace scope.

The stable sectors are:

- `AGRICULTURE`
- `INFRASTRUCTURE`
- `ENVIRONMENTAL`
- `MINING`
- `PORTS_INDUSTRIAL`

Sector and asset-type values use uppercase identifiers. The registry lists the
common types, but persistence intentionally accepts future well-formed
identifiers without a schema migration. A future sector module can therefore
add `WIND_TURBINE`, for example, without adding agriculture-specific columns to
the common table.

New canonical metadata writes are limited to 64 KiB and reject fields whose
names indicate passwords, tokens, API keys, credentials, or private keys.
Legacy metadata is preserved by the migration and therefore still requires the
historical plaintext inventory tracked in the risk register.

## Spatial representation

`geometry_geojson` is the portable source of truth. The API accepts only valid
two-dimensional EPSG:4326 `Point`, `Polygon`, or `MultiPolygon` geometry and
rejects non-finite, out-of-range, unclosed, or ambiguous coordinates. Stored
bounding-box and display-center fields provide deterministic map behavior and a
SQLite-compatible spatial-filter fallback.

On PostgreSQL, migration `generic_assets_postgis_v1` attempts to install
PostGIS. If PostGIS is available, it adds a stored generated
`geometry(Geometry, 4326)` projection and `ix_assets_geometry_gist`. The
projection is always derived from validated GeoJSON, so the application does
not maintain two independent geometry values. If the database role cannot
install PostGIS or the extension is unavailable, the migration emits a notice
and retains the portable fields; production readiness must then remain blocked
until an operator enables the extension and reruns the phase migration in a
reviewed environment.

## API and permissions

The canonical surface is `/assets`:

- `GET /assets` lists and filters the active workspace by organization,
  workspace, parent, sector, type, status, and bounding box.
- `GET /assets/{id}` reads one tenant-scoped asset.
- `POST /assets` creates an asset for the selected workspace.
- `PATCH /assets/{id}` updates mutable fields and validates hierarchy cycles.
- `DELETE /assets/{id}` performs a recoverable archive; parents with active
  children cannot be archived.
- `GET /assets/map` returns a GeoJSON `FeatureCollection`.
- `GET /assets/registry` returns stable sectors, common types, supported
  geometry shapes, and SRID.

Viewer and finance roles can read assets. Members can create and update them.
Managers, admins, and owners can also archive. All lookups filter by the
authorization context before returning data, so an inaccessible UUID is
reported as not found and cannot be used for tenant enumeration.

## Legacy compatibility

The migration copies every existing `Site` and IoT/construction `IotAsset` into
the generic table without deleting or renaming the source rows. It keeps the
source ID where collision-free, records `(legacy_source, legacy_source_id)`,
and preserves the Site-to-IoT hierarchy. Existing mobile/admin Site creation
and IoT asset provisioning dual-write through the Asset service. Existing IoT
device and construction references therefore keep working while new consumers
adopt the canonical asset UUID.

The old tables remain compatibility facades. Their retirement requires a later
inventory of all `site_id` consumers, a backfill verification in a restored
production copy, and an explicit client cutover; Phase 5 does not destroy them.

## Deployment verification

Before deploying to a PostgreSQL environment:

1. Restore a production-like backup into an isolated database.
2. Run `alembic upgrade head` and verify counts for Site and IoT legacy links.
3. Confirm `postgis_full_version()` succeeds.
4. Confirm `assets.geometry` exists as SRID 4326 and
   `ix_assets_geometry_gist` is valid.
5. Insert and retrieve Point, Polygon, and MultiPolygon examples with
   `ST_AsGeoJSON`.
6. Exercise cross-organization negative API tests before directing clients to
   `/assets`.

Do not delete legacy rows or make PostGIS readiness claims when the extension
check falls back to portable-only mode.
