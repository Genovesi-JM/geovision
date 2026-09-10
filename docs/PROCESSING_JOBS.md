# GeoVision photogrammetry processing jobs

GeoVision now turns finalized raw drone imagery into provider-neutral processing
jobs. PostgreSQL remains authoritative for job identity, state, retries, cost,
quality, provenance and generated Dataset references. A provider task reference
is opaque metadata and never replaces the GeoVision UUID.

## End-to-end flow

1. A raw `RGB_IMAGES`, `MULTISPECTRAL_IMAGES`, or `THERMAL_IMAGES` Dataset is
   finalized and emits `dataset.ready` in the transactional outbox.
2. When automatic processing is enabled, the idempotent event consumer creates
   one `ProcessingJob` with source datasets and requested outputs.
3. The independent processing worker claims due rows, validates readiness,
   tenancy, storage provider, image count, byte limits and SHA-256 evidence, then
   submits through `ProcessingProvider`.
4. The worker polls provider-neutral status. Bounded retry state is durable and
   stale claims can be recovered by another worker after a crash.
5. Completed artifacts are normalized and checked for missing, duplicate, empty,
   unsafe or oversized output files.
6. Each output becomes a regular Dataset and DatasetFile in processed/derived
   object storage. Reservations are committed before object writes, and stable
   output IDs make crash recovery idempotent.
7. The same transaction records `processing.completed`, `processing.failed`, or
   `processing.needs_review`; generated datasets emit their normal lifecycle
   events for later analytics and reporting.

The job states are `REQUESTED`, `VALIDATING`, `SUBMITTED`, `RUNNING`,
`RETRY_WAIT`, `NEEDS_REVIEW`, `COMPLETED`, `FAILED`, and `CANCELLED`. Operators
can inspect all fields at `/processing/jobs`, retry failed/review jobs, and
cancel active work where the provider supports cancellation. These routes are
restricted to the separate GeoVision Operations permission surface.

## Provider boundary

`ProcessingProvider` defines `submit`, `status`, `cancel`, `retrieve_outputs`
and `normalize_outputs`. Business services import that interface only. Concrete
adapters live under `app/integrations/processing` and are selected by the worker
composition root.

- `fake` is deterministic, credential-free, and produces small test artifacts.
  It exists for CI and local demos, not production measurements.
- `nodeodm` implements the official NodeODM task creation, task-info, cancel and
  `all.zip` download contracts. A stable `set-uuid` derived from the GeoVision
  job makes an ambiguous repeated submission provider-idempotent.
- `pix4d`, `autodesk_reality_capture`, and `bentley_reality_modeling` are explicit
  unavailable scaffolds. Selecting them cannot silently simulate success and
  does not purchase or require a vendor account.

The NodeODM adapter follows the official
[NodeODM API documentation](https://github.com/OpenDroneMap/NodeODM/blob/master/docs/index.adoc)
and [OpenDroneMap Docker guidance](https://github.com/OpenDroneMap/NodeODM).
NodeODM reports task codes 10/20/30/40/50 for queued/running/failed/completed/
cancelled. GeoVision normalizes those values before domain code sees them.

## Local NodeODM

NodeODM is intentionally not assumed to be installed. Docker users can start
the optional stack without changing the default GeoVision stack:

```bash
docker compose -f docker-compose.yml -f docker-compose.processing.yml \
  --profile processing up nodeodm event-worker processing-worker backend db
```

The overlay sets NodeODM's internal URL and shares GeoVision's local object
storage with the processing worker. The official image is CPU-intensive; size
the host for real imagery and pin an approved image digest before staging.

For a native-backend local demo without NodeODM:

```dotenv
PROCESSING_PROVIDER=fake
PROCESSING_AUTO_CREATE_ENABLED=true
```

Run `python -m app.workers.event_worker` and
`python -m app.workers.processing_worker` from the backend environment.

## Output normalization and provenance

Supported normalized outputs are orthomosaic, DSM, DTM, point cloud, 3D mesh,
NDVI, NDRE and GNDVI where the selected processor produces them. Index rasters
are derived datasets; other photogrammetry products are processed datasets.
Every generated Dataset records the processing job UUID, source Dataset UUIDs,
provider code, processor name/version and provider output path. It never records
provider credentials or raw response bodies.

An output is not marked complete merely because the provider says it finished.
All requested output types must be recognized and pass file and size validation.
Missing or invalid results move the job to `NEEDS_REVIEW` with a structured
quality report. Provider/configuration errors become visible `FAILED` rows after
bounded retries. Either state can be retried explicitly after correction.

## Operational limits and remaining live gates

The current NodeODM adapter downloads the bounded `all.zip` result into worker
memory, validates the archive without extracting paths to disk, and stores only
recognized artifacts. Very large jobs should use a future streamed/chunked
NodeODM upload and direct-to-object-storage output path; do not raise limits
without a memory/capacity test. Live activation still requires processor
capacity, HTTPS/network isolation, secret-manager delivery of any token, object
storage access, an approved NodeODM image/version, licence review, representative
image quality tests, monitoring and a rollback rehearsal.
