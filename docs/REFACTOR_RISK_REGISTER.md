# GeoVision refactor risk register

This register identifies the verified risks that must guide the sequential
GeoVision refactor. It protects existing customer, operational and device data
while the code moves toward the architecture in the LLM Refactor Prompt
Playbook. Risks are listed here so later phases can resolve them deliberately
instead of treating legacy structures as disposable.

## Active risks

| ID | Severity | Verified condition | Failure mode | Required control |
|---|---|---|---|---|
| R01 | Critical | Customer context is split across `Account` and `Company`, with separate membership models and additional legacy account tables | Tenant data can be orphaned, duplicated or exposed across organizations during consolidation | Define the canonical workspace identity and migrate through explicit mappings, compatibility reads and tenant-isolation tests |
| R02 | Critical | `backend/start.py` catches an Alembic failure, attempts `stamp head`, then calls `create_all` | A failed or partial production migration can be marked current without applying data transformations | Remove fail-open stamping in a later migration-safety change; require backup, dry run and verified schema revision before production rollout |
| R03 | High | Application startup runs broad legacy schema alterations and suppresses several failures | Schema drift can remain hidden and differ between SQLite and PostgreSQL | Inventory every compatibility alteration, replace it with idempotent Alembic migrations, then retire the runtime shim only after cutover |
| R04 | High | `start.py` imports the database engine value before initializing it in `_ensure_schema_columns` | Startup emits a non-fatal inspection warning and skips intended checks | Add a regression test and reference the engine from the database module when the appropriate phase touches startup safety |
| R05 | High | PostgreSQL is supported, but sites use numeric latitude/longitude and no PostGIS geometry types are active | Spatial queries, boundaries and cross-sector assets cannot safely scale from point coordinates | Introduce PostGIS and the generic Asset model through additive migrations and geometry backfill checks in Phase 5 |
| R06 | High | Static web, Flutter and external/device clients depend on the current route and payload shapes | Moving routers during modularization can break working clients | Record current OpenAPI, preserve route prefixes, add contract tests and use compatibility facades before moving implementations |
| R07 | High | Email/password, OAuth, global roles, account roles and company roles overlap | Authentication may succeed while authorization selects the wrong tenant or privilege | Create one identity boundary and one permission evaluation path; add multi-workspace and negative isolation tests before removing legacy checks |
| R08 | High | There is no invitation-first path into an existing workspace/asset/result | Post-service customers must use generic onboarding and may create duplicate sites | Add expiring, single-use, tenant-scoped invitations and deep-link tests in Phase 6 |
| R09 | High | IoT MQTT and offline detection run inside each API process; Redis fan-out is not active | Multiple API replicas can duplicate work or fail to deliver consistent live events | Move durable work behind the event/outbox boundary and add distributed coordination before scaling replicas |
| R10 | High | ERP outbox processing has retry logic but no independent scheduled worker | ERP records remain pending unless sync is invoked manually | Add an asynchronous worker with idempotency, backoff, dead-letter visibility and operator controls |
| R11 | High | Development can generate an ephemeral JWT key and can store IoT secrets without encryption; production has only partial guards | Misclassified environments can invalidate sessions or expose device credentials | Fail closed for production-like environments, centralize secret references and add configuration tests before deployment |
| R12 | High | Payment services can create mock-like responses when provider credentials are absent, although the storefront hides unavailable methods | Direct API consumers may mistake a simulated payment for a settled payment | Make provider capability/status explicit in contracts and forbid simulated settlement outside test/demo mode |
| R13 | High | Dataset/document storage is S3-compatible with a legacy local-file fallback | Azure migration can strand objects, break URLs or delete history | Add a storage interface, immutable GeoVision file IDs, dual-read migration and checksum verification before cutover |
| R14 | High | The new playbook specifies Odoo, while the current tested integration is ERPNext | Replacing ERP code prematurely can interrupt commerce and accounting synchronization | Keep the outbox contract provider-neutral; add Odoo as an adapter and retire ERPNext only after an approved cutover |
| R15 | High | Current deployment is DigitalOcean; Azure infrastructure, Blob, Service Bus and Event Grid are absent | A big-bang cloud move can mix domain refactoring with operational migration | Keep domain code portable, introduce Azure adapters behind interfaces and perform staged infrastructure migration with rollback |
| R16 | Medium | The current public scope hides or combines some sectors, while the playbook requires five explicit verticals including Ports/Industrial | UI, catalogue and data fixtures may contradict the new architecture or over-promise immature capabilities | Treat sector activation as later feature-flagged phases; do not change public claims during foundation work |
| R17 | Medium | Flutter top-level navigation is Portal, Assets, Store, Alerts and More rather than Home, Assets, Actions, Services and More | Early backend work could accidentally couple to a UI structure scheduled for replacement | Keep navigation changes in Phase 22 and expose backend capabilities independent of tab names |
| R18 | Medium | Agriculture has dedicated KPI definitions; other mobile sectors reuse a minimal infrastructure list | Sector dashboards can present generic or misleading metrics | Add validated KPI definitions only with provenance and source requirements in sector activation phases |
| R19 | Medium | RAG, Mapbox/Google delivery, Stripe mobile, push and several drone/processing providers are placeholders or credential-gated | Documentation or UI can imply production readiness that code does not provide | Keep explicit capability states, fake adapters and feature flags; never report credentials-gated behavior as live |
| R20 | Medium | The local Docker installation lacks the Compose plugin and its daemon is not running | The backend image and documented IoT stack cannot be reproduced on this host today | Start/repair Docker, install Compose, then validate the image and full stack without deleting existing volumes |
| R21 | Medium | The default local `.venv` is stale and the shell does not expose Flutter even though Flutter is installed | Advertised commands fail before tests begin | Use `make baseline`, recreate the backend virtual environment, and keep tool discovery in the verification script |
| R22 | Medium | Android and iOS builds pass with future plugin migration warnings | A future Flutter upgrade can turn warnings into build failures | Track `package_info_plus` Kotlin and `flutter_secure_storage` Swift Package Manager compatibility before the next SDK upgrade |
| R23 | Critical | No production backup-restore drill or migration rollback rehearsal is recorded | A structurally correct migration can still cause unrecoverable downtime or data loss | Require a production-like restore, migration dry run, rollback decision and owner sign-off before any live schema cutover |

## Controls that already reduce risk

- The Git repository and remote feature branch are synchronized.
- Alembic reaches one head from an empty database.
- Backend, web and mobile automated suites are currently green when run with
  healthy local toolchains.
- IoT ingestion includes tenant scoping, per-device credentials, replay
  protection and test coverage.
- ERP events use durable idempotency keys.
- Production configuration refuses the known default JWT secret and requires
  encryption when production MQTT is enabled.
- Environment files and local virtual environments are ignored by Git.
- The shop exposes GeoVision-controlled products and services; no public seller
  or contractor marketplace was found.

## Phase gate policy

Every phase must state which risks it reduces, adds or leaves unchanged. Schema
changes require additive Alembic migrations and a fresh-database test. Identity,
tenant, invitation and integration changes require negative isolation tests.
No phase may mark itself complete by deleting customer data, stamping around a
failed migration, embedding provider secrets, or weakening an existing route
without a compatibility plan.

## Phase 1 outcome

- **Reduced:** R04, because startup now references the live canonical database
  module after initialization instead of retaining an `engine = None` snapshot.
- **Reduced:** R06, because all 205 application HTTP/WebSocket contracts and
  the legacy router order now have automated compatibility checks.
- **Contained:** R01, R07, R16, R18 and R19 now have explicit owning domain or
  sector boundaries, but their underlying product work remains unchanged.
- **Unchanged:** R02, R03, R05 and R08-R23 remain active and belong to later
  phases. Phase 1 did not alter persisted schema, providers, deployment, public
  sector activation, or customer navigation.
- **Introduced and controlled:** Registry metadata could drift from real route
  ownership; import-time validation and architecture tests fail when module
  names, dependencies, orders, or router targets conflict.
