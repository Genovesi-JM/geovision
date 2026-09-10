# GeoVision engineering guide

GeoVision is a first-party operational-intelligence platform for six distinct
customer sectors: Agricultura & Pecuária, Construção & Infraestruturas,
Ambiente, Mineração, Indústria, Energia & Utilities, and Portos & Logística.
Their exact identifiers, labels, marketing anchors, technical mappings, and
legacy aliases are defined in the [canonical sector taxonomy](SECTOR_TAXONOMY.md).
The backend is one FastAPI modular monolith with PostgreSQL/PostGIS and
independent durable workers. The static desktop portal and Flutter mobile app
consume the same organization, workspace, Asset, intelligence, catalogue,
order, and notification contracts.

For a first local run, use the repository [developer runbook](../README.md).
For release decisions, start with the
[canonical sector taxonomy](SECTOR_TAXONOMY.md) and the
[release checklist](RELEASE_CHECKLIST.md); [Phase 33 readiness](PHASE_33_READINESS.md)
is the historical evidence baseline that must be rerun for Phase 34. The
current classification is **pilot-ready in the verified local/integrated
environment within the documented single-Workspace IoT-administration
guardrail, and production blocked until the external gates listed there are
closed**.

## Read in this order

1. [Modular monolith architecture](MODULAR_MONOLITH_ARCHITECTURE.md) explains
   ownership, dependency direction, sector composition, and workers.
2. [Canonical sector taxonomy](SECTOR_TAXONOMY.md) defines the six-sector
   vocabulary and compatibility contract used by every surface.
3. [Entity relationships](ENTITY_RELATIONSHIPS.md) explains the canonical data
   graph and the retained compatibility names.
4. [Organization, workspace, and RBAC](ORGANIZATION_WORKSPACE_RBAC.md) and the
   [exact permissions matrix](PERMISSIONS_MATRIX.md) explain authorization.
5. [Provider catalogue](INTEGRATION_PROVIDER_CATALOG.md) distinguishes an
   implemented adapter from a configured or live one.
6. [Event catalogue](EVENT_CATALOG.md) lists the provider-neutral facts and
   commands persisted in the transactional outbox.
7. [Customer onboarding](ONBOARDING_FLOW.md) covers self-service and the
   service-first invitation flow.
8. [Extending GeoVision](EXTENDING_GEOVISION.md) shows how to add a sector,
   sensor, provider, or first-party service without creating parallel cores.
9. [Production launch](PRODUCTION_LAUNCH.md), the
   [Azure runbook](../infra/azure/README.md), and the
   [known limitations](KNOWN_LIMITATIONS.md) define deployment and remaining
   work.

## Core workflow

```text
Acquire -> Dataset -> Process -> KPI and Observation -> Action -> Report
   ^                                                        |
   |                                                        v
Monitor outcome <- IoT and repeat acquisition <- Fulfil <- Order <- Catalogue
```

Customers see GeoVision as the only seller and service provider. Supplier,
pilot, agronomist, technician, analyst, and contractor records belong to the
private Operations surface; none is a public marketplace identity.

## Local verification

```bash
make baseline
```

Set `GEOVISION_BASELINE_BUILDS=1` to include Android and iOS simulator builds.
The CI workflow adds PostgreSQL/PostGIS migration tests, dependency audits,
Docker, browser tests, and production-configured mobile builds. A staging smoke
is intentionally separate because it needs a deployed URL and approved test
identity.

For the broader Phase 33 local gate, including the named security suite,
Alembic graph, backend container, Android, and iOS builds, run:

```bash
bash scripts/verify_phase33.sh
```

The command reports PostgreSQL/PostGIS or staging checks as open warnings when
their environment variables are absent; a local pass must not be recorded as
that external evidence. Build tools can refresh generated/native lock files, so
run it in a clean checkout and inspect `git status` afterwards. With an approved
short-lived staging identity, set `GEOVISION_STAGING_API_URL`,
`GEOVISION_STAGING_ACCESS_TOKEN`, and `GEOVISION_STAGING_WORKSPACE_ID`; the
wrapper then invokes `scripts/staging_smoke.sh` without printing the token.

## Synthetic six-sector workspace

After applying migrations to a local or test database, create the explicit,
credential-free demonstration portfolio with:

```bash
cd backend
.venv/bin/python scripts/seed_phase33_demo.py \
  --confirm-synthetic-demo \
  --attach-user-email you@example.com
```

The command refuses staging/production, never runs during application startup,
is idempotent, and labels every owned record as synthetic. The optional email
must identify an existing active local password account; the command never
creates, resets, or prints credentials. Omit `--attach-user-email` for a
database-only fixture. It creates one workspace with the six canonical sector
histories spanning acquisition, dataset, KPI, observation, action, and report
records. Never present those records as customer evidence. The Phase 33 script
name is retained for compatibility even though Phase 34 expands its fixture to
six sectors.
