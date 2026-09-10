# Phase 33 closure and readiness

This record closes the GeoVision refactor playbook implementation through
Phase 33. It distinguishes code completion from deployment approval. The
classification on 10 September 2026 is:

> **Phase 34 update:** this remains the evidence record for the Phase 33 tree.
> Phase 34 subsequently established the canonical six-sector taxonomy in
> [`SECTOR_TAXONOMY.md`](SECTOR_TAXONOMY.md), separated
> Indústria, Energia & Utilities from Mineração and Portos & Logística, and
> expanded the compatibility-named Phase 33 fixture to six sectors. Re-run the
> release gates for the Phase 34 commit; the evidence counts and digest below
> must not be reused as Phase 34 evidence.

- **Implementation scope at Phase 33: complete.** The repository contained the
  then-agreed five-sector demonstration, service and IoT customer journeys, tenant tests,
  deployment foundations, and engineering documentation.
- **Pilot-ready with a guardrail.** Use one active Workspace per Organization
  for any pilot that enables the legacy IoT fleet-administration routes.
- **Production blocked.** No production claim is made until the staging,
  identity, provider, signing, operations, restore, and human gates below have
  dated evidence for the exact release digest.

## A. Status

Phases 0 through 33 are implemented sequentially. Phase 33 closes the local
code and documentation scope; it does not authorize a production deployment.
The supported pilot path uses internal identity, provider-neutral boundaries,
deterministic processing/report fallbacks, in-app notifications, and a single
Workspace in each IoT-enabled Organization.

## B. Findings and assumptions

- An adapter, environment variable, or workflow file means "implemented" or
  "configurable"; it does not mean a provider is contracted, credentialed,
  licensed, reachable, or approved.
- Synthetic data is an explicit local/test fixture, not customer evidence. It
  is marked at the Organization, Workspace, Asset, acquisition, dataset, KPI,
  observation, action, report, and portal-projection boundaries.
- A legacy row without an unambiguous Workspace is quarantined rather than
  assigned by guesswork. This applies to orphaned service requests and
  AccountEvent history in multi-Workspace Organizations.
- Customer order history is the canonical workspace-aware `GET /orders`
  route. The retained legacy router is separately namespaced at
  `GET /orders/orders` by its compatibility mount.
- The checked-in DigitalOcean definition is a rollback reference until an
  Azure traffic and data cutover is proven. No Render deployment or Firebase
  authentication implementation was found to remove.

## C. Changes completed

### Six-sector demonstration after Phase 34 alignment

`backend/scripts/seed_phase33_demo.py` creates one deterministic, local-only,
credential-free synthetic portfolio covering the six canonical sectors. Every
sector has two acquisitions and linked dataset, KPI, observation, action, and
report history, including one published report. An existing active local
password account can be attached by exact email without creating, resetting,
or printing credentials. The seed is idempotent and refuses deployed
environments. Its Phase 33 filename and deterministic identifiers remain for
compatibility; they do not reduce the Phase 34 portfolio to five sectors.

### Service-to-customer journey

The service request now snapshots Organization, Workspace, Asset, order, and
report links; uses a tenant-scoped idempotency key and request digest; follows a
validated optimistic lifecycle; and reveals a result only when its published
report, acquisition, order, Asset, Organization, and Workspace form one
consistent chain. Operations owns the linking endpoint. Invitation acceptance
can land on the result and idempotently materialize an already-published report
notification for the newly admitted member. A committed keyed request remains
replayable after its mutable legacy Site is renamed, archived, or deleted, and
self-service account deletion removes its keyed requests before deleting an
empty personal Workspace. Mobile account activity and SSE history require an
exact Workspace.

### Device-to-customer journey

Authenticated telemetry produces a durable receipt and readings, then projects
in-order numeric measurements into device-specific technical KPIs. Triggered
alerts create review-required observations, recommended actions, durable events,
workspace-scoped notifications, and Asset deep links. Duplicate packets do not
repeat projections, older store-and-forward packets do not replace the current
decision state, PostgreSQL serializes per-device ingestion, and a durable event
consumer retries isolated projection failures idempotently. Ingestion and
repair take the same PostgreSQL device-row lock, preventing two failed receipts
from racing the device/channel KPI-definition lookup.

### Cross-surface hardening

- Deployed profiles reject fake/deterministic processing even when a caller
  explicitly requests it.
- Customer-visible AccountEvent payloads recursively reject credential-shaped
  fields and omit internal actor identifiers.
- Workspace selection, same-user/two-Workspace isolation, contractor
  least-privilege access, and invitation target scoping have regression tests.
- Legacy mobile drone and drone-mission compatibility routes now re-check the
  selected Workspace and read, contribute, or operate permission; foreign
  same-Organization Sites, aircraft, missions, Assets, and Acquisitions remain
  hidden, and Workspace-less aircraft are quarantined after an Organization
  gains a second active Workspace.
- An IoT alert's rule-selected delivery channels are preserved through its
  durable event. The default log-only policy creates the in-app item while
  suppressing configured email or push deliveries.
- Flutter sends one stable `Idempotency-Key` through an online attempt and any
  later offline replay.

## D. Migration

`service_request_journey_v1` was the sole Alembic head for the Phase 33 closure
after `integration_registry_v1`. It adds the service-request scope, journey,
optimistic-version, digest, check, foreign-key, and partial-unique constraints;
normalizes bounded legacy state; maps only resolvable Site/Asset history; adds
Workspace scope to AccountEvent; and backfills an AccountEvent only when its
Organization has exactly one active Workspace. Ambiguous history remains NULL
and is excluded from customer APIs. Its upgrade, downgrade, re-upgrade, row
preservation, constraints, PostGIS state, a real two-transaction
service-request insert race, and a two-worker IoT repair serialization race
were rehearsed against PostgreSQL/PostGIS 16/3.5. Phase 34 adds
`phase34_sector_taxonomy_v1` after this historical head and requires fresh
migration evidence of its own.

## E. Automated evidence

The final local release run on the Phase 33 tree produced:

| Gate | Result |
|---|---|
| Focused synthetic-demo, IoT-journey, and deployed-processing tests | 20 passed |
| PostgreSQL/PostGIS migration release gate | 5 passed, including service-request insert and IoT repair concurrency races |
| Full backend suite | 675 passed, 4 PostgreSQL-only tests skipped; 44 expected local/deprecation warnings |
| Named backend `security_regression` suite | 11 passed; 668 deselected |
| Route and OpenAPI contract pins | 9 passed |
| Python compilation, correctness-only Ruff, and diff checks | Python compilation passed; correctness-only Ruff passed; one Alembic head; script syntax and Git diff checks passed |
| Browser/portal Playwright suite | 44 passed, 1 deliberately skipped; dependency audit found 0 vulnerabilities |
| Flutter format, analysis, and unit/widget tests | 161 files unchanged, no analysis issues, 60 tests passed |
| Production-configured mobile builds | `flutter build apk --release --dart-define-from-file=dart_defines/production.json` and `flutter build ios --simulator --debug --dart-define-from-file=dart_defines/production.json` succeeded; the iOS result is an unsigned simulator app, not a distribution artifact |
| Azure Bicep validation | 12 checks passed with the official standalone Bicep CLI |
| Python deployed-requirement health | `pip check` clean; OSV audit found no known vulnerability |
| Canonical backend container | Built as non-root user `10001:10001`; the exact local image's live `/health` smoke returned `ok` (local image digest `sha256:278360685d34fd6aa8ff94cb7022666475ab46ee24b8df7910d3ddd273294829`) |

Warnings caused by intentionally absent local deployment secrets are expected
in tests; deployed configuration validation fails closed when those secrets are
required. This table is local evidence, not a substitute for main-branch CI or
staging evidence tied to an immutable image digest.

## F. Manual and external verification still required

- Run main CI for the exact Phase 33 commit and retain its immutable backend
  image digest and signed mobile artifacts.
- Deploy migration-first to an approved private Azure staging environment and
  run `scripts/staging_smoke.sh` with a short-lived customer token, its Workspace,
  and a foreign Workspace. No staging URL or token was available locally, so no
  live staging result is claimed.
- Rehearse a production-like backup restore, upgrade, rollback application
  digest, monitoring, and measured RTO/RPO.
- Complete Entra web/Flutter client exchange with a real tenant; signed Android
  and iOS distribution; native push; live maps; live IoT broker/hardware; and
  every enabled commercial/data/ERP provider gate.
- Record security, privacy/data-processing, domain-SME, accessibility-device,
  operational-owner, and Human Gate 18 approvals.

## G. Principal files

- Demo: `backend/app/phase33_demo.py`,
  `backend/scripts/seed_phase33_demo.py`, and
  `backend/tests/test_phase33_demo_seed.py`.
- Service journey: `backend/app/modules/operations/mobile_services.py`,
  `backend/app/routers/mobile.py`,
  `backend/app/routers/operations_resources.py`,
  `backend/app/modules/organizations/invitations.py`, and
  `backend/tests/test_service_request_journey.py`.
- IoT journey: `backend/app/iot/intelligence.py`,
  `backend/app/iot/service.py`, `backend/app/iot/watchdog.py`,
  `backend/app/services/event_consumers.py`, and
  `backend/tests/test_phase33_iot_customer_journey.py`.
- Migration: `backend/alembic/versions/service_request_journey_v1.py`,
  `backend/tests/test_service_request_journey_migration.py`, and
  `backend/tests/test_migration_release_gate.py`.
- Mobile retry identity: `mobile/lib/features/work/data/work_repository.dart`,
  `mobile/lib/core/storage/offline_sync_service.dart`, and
  `mobile/test/features/service_request_idempotency_test.dart`.
- Release/docs: `scripts/verify_phase33.sh`, `scripts/staging_smoke.sh`, and the
  Phase 33 guides indexed by `docs/README.md`.

## H. Compatibility and rollback

The database and API work is additive. Compatibility tables, class names, and
routes remain where removal lacks usage evidence. Pre-Workspace history is
visible only through an unambiguous compatibility mapping. The DigitalOcean
definition, old mobile native integration files, internal identity path, and
deterministic report fallback remain recoverable until their replacements are
proved. Production rollback must use a schema-compatible prior image;
destructive data rollback is not the default plan.

## I. Security and data behavior

- Customer projections require both Organization and active Workspace scope;
  known cross-Workspace identifiers return no foreign data.
- Legacy mobile drone reads and writes enforce the selected Workspace plus role
  permission, including same-Organization cross-Workspace denial.
- Contractor APIs expose assigned work only and continue to suppress customer,
  billing, margin, internal-note, and unrelated-resource data.
- Invitation tokens remain hashed, single-use, expiring, exact-email bound, and
  target validated. Workspace-less legacy targets are shareable only when one
  active Workspace makes their scope unambiguous.
- Raw IoT receipt identity is authoritative. Derived projection failures do not
  discard authenticated raw telemetry, and repair revalidates the immutable
  receipt/event Organization, Workspace, Asset, and device snapshot. Repair is
  serialized with ingestion per device on PostgreSQL.
- IoT notification fan-out honors each alert rule's channel allowlist; a
  log-only rule cannot silently queue email or push.
- Synthetic markers and notices travel through customer portal summaries,
  Asset trees, KPI cards, maps, and reports. No demo credentials are installed.
- Credential-shaped metadata is rejected at public event, invitation, dataset,
  and Operations metadata boundaries; server secrets are never returned.

## J. Production blockers and enhancements

Production blockers are the missing exact-commit staging/CI record; restore and
rollback rehearsal; Entra client cutover; Android/iOS signing and distribution;
native push, maps, and live provider approval; single-owner IoT supervision;
legacy Organization-scoped IoT fleet administration; operational ownership;
and privacy/security/SME/human approval. A direct probe of
`https://api.geovisionops.com/ready` returned HTTP 503 at
`2026-09-10T16:53:15Z`; this time-stamped observation is not assumed to remain
current. Local release checks also found no private Android keystore or Apple
signing team.

Performance/capacity, long-duration edge replay, broader accessibility-device
coverage, scheduled outcome KPIs, provider cost dashboards, and later removal
of proven-unused compatibility surfaces are post-launch enhancements, not
evidence that can waive the blockers. See `KNOWN_LIMITATIONS.md` for the
maintained list and closure evidence.

## K. Safe next prompt

> Deploy the exact Phase 33 commit and immutable image digest to an approved
> private Azure staging environment with PostgreSQL/PostGIS. Keep external
> providers disabled initially and use one active Workspace per IoT-enabled
> Organization. Run migrations before application traffic, execute the full CI
> and authenticated `scripts/staging_smoke.sh` including foreign-Workspace
> denial, record worker/provider/backup/rollback evidence, and stop before any
> production traffic or irreversible provider activation.
