# KPI, observation, alert, and action engine

## Purpose

Phase 17 provides one intelligence contract for every GeoVision sector. A
sector package registers calculators and rules; the common engine persists
their structured results. The core never imports a sector package, and no
frontend owns operational thresholds.

The data flow is:

```text
normalized dataset / telemetry / reviewed input
                  |
       versioned sector calculator
                  |
      immutable KPI measurement history
                  |
          versioned sector rules
             /             \
 structured observation   recommended action
             \             /
       normalized asset summary / alert queue
```

Narrative AI may explain these records but is not a calculator, measurement
source, validation authority, or action-completion authority.

## KPI contract

`kpi_definitions` now carries a stable sector/key, customer name and unit,
calculator key and version, `PRIMARY`/`SECONDARY`/`TECHNICAL` importance,
display formatting, and an explicit status policy. Old `label` data is retained
as a compatibility alias and is backfilled into the canonical `name`.

Every `kpi_values` row is immutable measurement history linked to its
organization, workspace and generic Asset. It records:

- the rendered and numeric value;
- `GOOD`, `WATCH`, `WARNING`, `CRITICAL`, or `UNKNOWN` status;
- confidence, measurement time, source and algorithm version;
- mission and dataset references when present;
- bounded, credential-free provenance;
- whether the row is a reviewed baseline.

The API derives current, previous, change, percentage change, baseline and
baseline change from history. It does not overwrite old values to maintain a
current snapshot. Missing values, weak confidence, absent policies, and invalid
policies resolve to `UNKNOWN`, never an invented safe state.

Supported threshold policies are higher-is-better, lower-is-better, target
range and boolean expectation. Display rules can control units, multiplier,
precision, prefixes/suffixes and missing-data text. Both are backend data and
are returned for transparency; clients render them but do not recalculate
status.

## Observation and alert contract

An `Observation` is a generic finding tied to an Asset and optionally its
Acquisition mission and Dataset. It supports portable validated GeoJSON,
structured/numeric values, unit, severity, confidence, source, algorithm key
and version, provenance, metadata and detection time.

Validation is explicit: `UNVALIDATED`, `NEEDS_REVIEW`, `VALIDATED`, or
`REJECTED`. Low confidence does not become validation. The alert endpoint is a
projection of non-rejected `WARNING` and `CRITICAL` observations, so an alert
keeps the same source, confidence, validation state and algorithm version as
the finding that caused it. Existing device-specific IoT alert routes remain a
compatibility surface.

## Action contract

An `Action` links a recommendation to the Asset, source observation and
versioned rule that created it. It carries priority, title/description, due
date, optional active workspace assignee, optional published GeoVision
catalogue reference, additional typed recommendation references, and an
audited outcome.

Action creation is idempotent per organization/rule/recommendation/source
observation. Catalogue references must point to a published GeoVision-owned
item compatible with the Asset; no supplier or external marketplace identity
is exposed. Valid lifecycle transitions are enforced on the server. Completion
requires a structured outcome and uses optimistic lifecycle versions, so stale
clients cannot overwrite newer work.

## Registration and evaluation

Sector modules construct their own `CalculatorRegistry`/`RuleRegistry` entries
or register with the application registries in
`app.modules.analytics.domain`. A calculator definition and implementation are
registered together under `(sector, key, version)`. The latest version is
selected by default while an exact historical version remains resolvable.

Rules receive only an `EvaluationContext` and the calculation results. They
return structured observation and action proposals. The shared persistence
services validate Asset/source ownership, record algorithm provenance, enqueue
durable `kpi.updated`, `observation.created`, `action.requested`, and
`action.completed` facts, and never commit outside the caller's transaction.

This allows crop stress, construction progress, stockpile change, port anomaly
and environmental change logic to share the same entities and APIs without
putting sector-only fields on `Asset`.

## Customer APIs

- `GET /assets/{asset_id}/summary`
- `GET /assets/{asset_id}/kpis`
- `GET /assets/{asset_id}/observations`
- `GET /assets/{asset_id}/alerts`
- `GET /assets/{asset_id}/actions`
- `GET /actions` and `GET /actions/{action_id}`
- `PATCH /actions/{action_id}` for assignment/due date
- `PATCH /actions/{action_id}/status` for lifecycle/outcome changes

Reads require access to the selected workspace and Asset. Mutations require
Asset update permission. All list and lookup paths constrain organization,
workspace and Asset IDs server-side; a supplied ID never selects another
tenant.

## Migration and compatibility

The migration is additive. It backfills legacy KPI names, calculator keys,
versions, workspace/organization/Asset links where deterministic, measurement
times, unknown status and zero confidence. It does not reinterpret historical
placeholder values as validated facts. Existing KPI, IoT-alert and mobile
routes remain mounted while clients move to the normalized APIs.

Before live sector activation, Gate 14 requires representative datasets,
approved thresholds, algorithm/version records, confidence calibration and
expert review. A working calculator is not evidence that its result is fit for
an agronomic, construction, infrastructure, environmental, mining,
industrial, energy, utility, port, or logistics decision. The six public
identities and their technical KPI sectors are defined in
[`SECTOR_TAXONOMY.md`](SECTOR_TAXONOMY.md).
