# Report generation review and publication

## Purpose

Phase 19 adds a canonical report lifecycle around GeoVision's validated data.
Reports are versioned records, not transient PDF responses. Each report keeps
the exact structured context used to generate it, the context digest, the
narrative provider and schema, the QA decision, the reviewer and publisher,
and a PDF stored through the Dataset object-storage boundary.

AI is optional narrative assistance. It is never a calculator, measurement
source, evidence validator, reviewer, or publication authority.

## Evidence boundary

`ReportContextBuilder` creates `geovision.report-context.v1` from the requested
Asset and optional Acquisition. It includes only:

- non-legacy KPI values at or above the minimum confidence, using the latest
  eligible value for each definition and retaining bounded history;
- observations explicitly marked `VALIDATED` at or above the minimum
  confidence;
- open actions linked to those observations, or an identified human-created
  manual rule;
- ready, quality-passed source Datasets and safe file metadata;
- sector map layers whose Dataset and Observation references survived the
  same evidence selection.

Dataset storage keys, object URIs, prefixes, file paths, credentials and
secret-like metadata never enter the context or API. The canonical JSON is
sorted and hashed before narrative generation. A client idempotency key cannot
be replayed against different evidence.

Agriculture owns its report enrichment adapter. The common report module
depends on a provider registry and never imports a sector package.

## Narrative safety and fallback

Narrative providers return only `geovision.report-narrative.v1`. Unknown fields,
unknown evidence IDs and numeric literals in provider-authored prose are
rejected. This deliberately prevents a language model from copying, changing,
rounding or inventing a measurement. The renderer inserts every number from
the immutable context tables instead.

`REPORT_NARRATIVE_PROVIDER=deterministic` is the default and needs no network or
credential. If a configured external provider is unavailable or returns an
invalid response, generation continues through the deterministic provider and
records only a safe fallback reason. The unavailable Azure/OpenAI boundary is
intentional until dedicated credentials, deployment access, data handling and
model evaluation pass Gate 15.

## QA and lifecycle

States are:

```text
GENERATING -> DRAFT -> REVIEW_REQUIRED -> APPROVED -> PUBLISHED -> SUPERSEDED
                  \---------------------> APPROVED
```

Low-risk deterministic reports containing eligible indicators and no excluded
or warning evidence may be `AUTO_APPROVED`. A provider fallback, validated
warning, evidence exclusion or missing indicator requires `HUMAN_REVIEW`.
A validated critical observation requires `SPECIALIST_REVIEW` and an analyst
permission before approval.

Only GeoVision Operations, Analysts or a platform administrator can generate.
Analysts and administrators can review and publish. Customers can list, read
and download only `PUBLISHED` reports in their active organization/workspace.
Publishing a newer revision supersedes the previous published revision without
deleting it.

Every generate, review request, approval, publication, supersession and
download is audited. Lifecycle facts use the durable outbox:

- `report.generated`
- `report.review_requested`
- `report.approved`
- `report.published`
- `report.superseded`

## API

- `POST /assets/{asset_id}/reports`
- `GET /reports`
- `GET /reports/{report_id}`
- `POST /reports/{report_id}/submit`
- `POST /reports/{report_id}/approve`
- `POST /reports/{report_id}/publish`
- `GET /reports/{report_id}/download`

Generation is idempotent. Review and publication accept the expected lifecycle
version so stale clients cannot overwrite a newer decision. The download route
revalidates the stored DatasetFile and PDF signature before delivery.

## Deployment boundary

The report engine requires the ordinary database, object storage and ReportLab
runtime only. It does not require an external AI service. A live narrative
provider must be separately approved, server-side only, and must retain the
same strict output and fallback contract. A generated draft is not customer
visible until an authorized publication completes.
