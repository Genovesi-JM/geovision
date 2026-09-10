# GeoVision datasets and object storage

Phase 12 makes captured and imported geospatial files first-class datasets.
PostgreSQL stores ownership, lifecycle, provenance, checksums, sizes, and object
references. File bytes remain in the configured object-storage provider.

## Dataset contract

Every canonical dataset belongs to an organization, workspace, and generic
Asset. It may also reference the Acquisition that produced it. The record
stores source/provider references, CRS, resolution, capture time, processing
level, quality status, JSON metadata/provenance, object prefix, file counts,
total bytes, lifecycle version, and archive time.

The built-in type vocabulary is `RGB_IMAGES`, `MULTISPECTRAL_IMAGES`,
`THERMAL_IMAGES`, `ORTHOMOSAIC`, `DSM`, `DTM`, `POINT_CLOUD`, `MESH_3D`,
`NDVI`, `NDRE`, `GNDVI`, `SATELLITE_IMAGE`, `WEATHER_DATA`, `TELEMETRY`,
`AIS_DATA`, and `BIM_MODEL`. Stable uppercase identifiers allow additional
types without a schema change.

Dataset lifecycle is `uploading -> processing -> ready`, with explicit `error`
and terminal `archived` states. Adding a new file to a ready dataset moves it
back to processing. Finalization requires at least one completed file. Updates
support optimistic lifecycle versions.

## Object identity and paths

Each file receives an immutable GeoVision UUID before a signed or streamed
write begins. Provider keys do not become database IDs. Canonical keys are:

```text
organizations/{organization_id}/assets/{asset_id}/missions/{mission_id|standalone}/
datasets/{dataset_id}/{raw|processed|derived|reports}/{file_id}_{safe_filename}
```

The same key convention is used by local filesystem, S3-compatible, and Azure
Blob adapters. Mission and dataset business logic only consume the
`ObjectStorageProvider` port.

## Upload and download flows

Current clients have two safe choices:

1. Backend-mediated streaming accepts files up to the configured direct limit,
   streams rather than loading the whole file into memory, computes MD5 and
   SHA-256, and persists a reservation before the provider write.
2. Short-lived signed upload URLs are intended for larger files. The client
   reserves an exact filename, content type, byte count, dataset, and object
   area, uploads to that key, then confirms completion. GeoVision verifies
   provider size and any provider-calculated checksum before marking the file
   complete. Local signed URLs remain authenticated and tenant-scoped.

Signed single-PUT uploads default to a portable 4 GiB maximum, below both S3
and Azure single-request ceilings. Reservations and immutable keys make a
failed attempt safely retryable. The current web/mobile stack has no multipart
client, so it does not advertise a false larger limit; an explicit S3
multipart/Azure block-session port is required before accepting files above
this ceiling.

Downloads use short-lived provider URLs. Local development uses an
authenticated, HMAC-signed backend stream. Storage account master credentials
are never returned to a client.

## Ownership and validation

- Every customer operation requires the active organization/workspace and an
  owned Asset. A supplied legacy company ID is only a compatibility assertion;
  it cannot select another tenant.
- Local signed routes resolve the reserved file and re-run dataset ownership
  checks before reading or writing.
- Filenames reject traversal/control characters and use an allowlist covering
  geospatial raster/vector, point-cloud, model, telemetry, weather, image, and
  report formats. Executable/script MIME types and empty or oversized files are
  rejected.
- Metadata and provenance reject credential-like keys. Provider failures are
  normalized and raw credentials are excluded from diagnostics and API errors.
- Relational models contain keys, URIs, metadata, sizes, and checksums only; no
  binary/blob content column exists.

## Providers and local setup

`OBJECT_STORAGE_PROVIDER=local` is the default for local/dev/test. Set
`LOCAL_STORAGE_ROOT` to a private writable directory and use a stable
development `SECRET_KEY` when signed URLs must survive process restarts. Local
storage is rejected in a deployed runtime profile.

For Azure Blob, select `azure_blob`, configure a private container and account
URL, then use managed identity in staging/production. A user-assigned identity
can be selected with `AZURE_MANAGED_IDENTITY_CLIENT_ID`. Account keys or an
account-key connection string are supported for controlled local integration
testing; their values are redacted. Upload/download SAS tokens are
object-scoped, permission-scoped, and short-lived. Live Azure account/RBAC
verification remains a deployment gate because this phase uses an SDK-contract
mock when no account is available.

The S3-compatible adapter remains supported. Explicit access credentials must
be complete; otherwise the SDK credential chain is used.

Changing the configured provider affects new datasets only. Existing file rows
remain pinned to their original provider and fail safely if that adapter is not
available. A real provider migration must copy bytes, verify sizes/checksums,
update references transactionally, retain a rollback window, and only then
retire the old provider. No mission or Acquisition record needs to change.

## Archive, deletion, and recovery

Deleting a dataset archives its metadata and retains tracked objects. A file
delete first persists a `deleting` state, performs the provider deletion, then
commits a tombstone. A crash therefore leaves a reconcilable database identity
whether it occurs before or after the external side effect. Provider failure
restores the uploaded state. Direct uploads also persist their reservation
before writing bytes, so an uncertain provider/database outcome cannot produce
an unidentifiable object.

The `datasets_storage_v2` migration backfills legacy Site datasets onto generic
Assets/workspaces where mappings exist, normalizes types and lifecycle values,
pins legacy storage providers, preserves all original records/files, and adds
restrict/set-null foreign-key behavior. Downgrade removes Phase 12 columns but
keeps source data and conservative ownership/deletion constraints. Export any
new Phase 12-only metadata before a production rollback.

The Phase 12 application contract contains 293 HTTP/WebSocket routes with route
SHA-256
`cb22fdc2931448fad8ad64938a5b9137440f0e8cb6ca52ee69837dab0bfef068`.
Its canonical JSON OpenAPI SHA-256 is
`25e11f2b06d0d951008f521125df3a9999322fdfefa91750fad92689017b9825`.
