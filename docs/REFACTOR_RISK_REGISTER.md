# GeoVision refactor risk register

This register identifies the verified risks that must guide the sequential
GeoVision refactor. It protects existing customer, operational and device data
while the code moves toward the architecture in the LLM Refactor Prompt
Playbook. Risks are listed here so later phases can resolve them deliberately
instead of treating legacy structures as disposable.

## Active risks

| ID | Severity | Verified condition | Failure mode | Required control |
|---|---|---|---|---|
| R01 | High | `Company` and `Account` table names remain for compatibility, but Phase 4 now links every workspace to a canonical organization and synchronizes membership authorization | A legacy client or unreviewed migration fallback can still use confusing vocabulary or attach an account to the wrong reviewed organization | Review deterministic backfills before live cutover, use canonical `/organizations` APIs and `X-Workspace-ID`, and retire aliases only after deployed clients migrate |
| R03 | High | Application startup runs broad legacy schema alterations and suppresses several failures | Schema drift can remain hidden and differ between SQLite and PostgreSQL | Inventory every compatibility alteration, replace it with idempotent Alembic migrations, then retire the runtime shim only after cutover |
| R05 | Medium | Phase 5 adds a generic Asset hierarchy, validated GeoJSON, bbox fallback, and an optional generated PostGIS geometry/GiST projection; legacy Site and IoT tables remain compatibility facades and a database without the extension stays in portable-only mode | Operators could mistake fallback storage for production PostGIS readiness, or later remove a legacy table before all `site_id` consumers migrate | Gate deployment on `postgis_full_version()`, geometry/index verification and a restored-data count audit; retire legacy tables only after explicit consumer cutover |
| R06 | High | Static web, Flutter and external/device clients depend on the current route and payload shapes | Moving routers during modularization can break working clients | Record current OpenAPI, preserve route prefixes, add contract tests and use compatibility facades before moving implementations |
| R07 | Medium | Customer roles and internal GeoVision assignments are now separate, but `users.role = admin` remains a documented temporary bridge for old deployments/tests | A legacy staff record can retain platform access until the bridge is removed | Audit `ADMIN_EMAILS`, verify all admins have `GV_SUPER_ADMIN`, move staff grants to `internal_role_assignments`, then remove the legacy bridge after client/cutover validation |
| R08 | High | There is no invitation-first path into an existing workspace/asset/result | Post-service customers must use generic onboarding and may create duplicate sites | Add expiring, single-use, tenant-scoped invitations and deep-link tests in Phase 6 |
| R09 | High | IoT MQTT and offline detection run inside each API process; Redis fan-out is not active | Multiple API replicas can duplicate work or fail to deliver consistent live events | Move durable work behind the event/outbox boundary and add distributed coordination before scaling replicas |
| R10 | High | ERP outbox work is provider-pinned and has bounded due-time retries plus terminal failure state, but no independent scheduled worker or dead-letter/operator workflow; provider-side ERP deduplication is not yet proven | ERP records remain pending unless sync is invoked manually, terminal work lacks a dedicated recovery surface, and an uncertain provider write requires manual reconciliation | Add an asynchronous worker with concurrency control, terminal/dead-letter visibility and operator controls in Phase 13; permit uncertain-write retries only after provider-side uniqueness/idempotency is verified |
| R11 | High | Typed configuration fails closed for signing/encryption in staging/production, but the JWT guard is syntactic rather than an entropy assessment and most provider validation occurs when a factory/adapter is used; local/development may still generate an ephemeral JWT key or explicit `plain:` connector compatibility values | Misclassified environments can invalidate sessions, weak-looking secrets can pass a length/placeholder check, or a dormant provider misconfiguration can remain undiscovered until use | Use high-entropy managed secrets, exercise every enabled provider in deployment checks, keep redacted diagnostics, require encryption anywhere real connector credentials are used, and track historical-row remediation under R24 |
| R12 | High | Payment creation and webhook verification have distinct configuration gates; local compatibility paths can accept unsigned/mock behavior, bank fields have built-in compatibility values that are not live-validated, and PayPal lacks deployed webhook verification and API-backed refund | A consumer can mistake simulation for settlement, accept an unverified callback outside production, or deploy invalid banking details | Require explicit verified overrides in deployed profiles, preserve operation-specific capability/status checks, and complete the public lifecycle, webhook, refund, and reconciliation controls in Phase 8 |
| R13 | High | Dataset/document storage uses a provider port and classifies S3 failures, but local-file support is read-only compatibility, failed writes have no local fallback, uploads are fully buffered, and some legacy facade shapes collapse error detail | Large uploads can exhaust memory, callers can lose retry/diagnostic context, and Azure migration can strand objects or break URLs | Add streaming and explicit error propagation, immutable GeoVision file IDs, an Azure Blob adapter, dual-read migration and checksum verification before cutover in Phase 12 |
| R14 | High | The provider-neutral ERP port preserves the current ERPNext adapter, while the playbook specifies a later Odoo integration | Replacing ERP code prematurely can interrupt commerce and accounting synchronization | Add Odoo as another adapter and retire ERPNext only after an approved Phase 21 cutover |
| R15 | High | Current deployment is DigitalOcean; provider ports exist but Azure infrastructure, Blob, Service Bus and Event Grid adapters are absent | A big-bang cloud move can mix domain refactoring with operational migration | Implement Azure adapters behind the established interfaces and perform staged infrastructure migration with rollback |
| R16 | Medium | The current public scope hides or combines some sectors, while the playbook requires five explicit verticals including Ports/Industrial | UI, catalogue and data fixtures may contradict the new architecture or over-promise immature capabilities | Treat sector activation as later feature-flagged phases; do not change public claims during foundation work |
| R17 | Medium | Flutter top-level navigation is Portal, Assets, Store, Alerts and More rather than Home, Assets, Actions, Services and More | Early backend work could accidentally couple to a UI structure scheduled for replacement | Keep navigation changes in Phase 22 and expose backend capabilities independent of tab names |
| R18 | Medium | Agriculture has dedicated KPI definitions; other mobile sectors reuse a minimal infrastructure list | Sector dashboards can present generic or misleading metrics | Add validated KPI definitions only with provenance and source requirements in sector activation phases |
| R19 | Medium | RAG, Mapbox/Google delivery, Stripe mobile, push and several drone/processing providers are placeholders or credential-gated | Documentation or UI can imply production readiness that code does not provide | Keep explicit capability states, fake adapters and feature flags; never report credentials-gated behavior as live |
| R20 | Medium | The local Docker installation lacks the Compose plugin and its daemon is not running | The backend image and documented IoT stack cannot be reproduced on this host today | Start/repair Docker, install Compose, then validate the image and full stack without deleting existing volumes |
| R21 | Medium | The default local `.venv` is stale and the shell does not expose Flutter even though Flutter is installed | Advertised commands fail before tests begin | Use `make baseline`, recreate the backend virtual environment, and keep tool discovery in the verification script |
| R22 | Medium | Android and iOS builds pass with future plugin migration warnings | A future Flutter upgrade can turn warnings into build failures | Track `package_info_plus` Kotlin and `flutter_secure_storage` Swift Package Manager compatibility before the next SDK upgrade |
| R23 | Critical | No production backup-restore drill or migration rollback rehearsal is recorded | A structurally correct migration can still cause unrecoverable downtime or data loss | Require a production-like restore, migration dry run, rollback decision and owner sign-off before any live schema cutover |
| R24 | High | Connector and integration credential fields now use the canonical encryption helper and deployed profiles require a valid Fernet key, but free-form metadata and endpoint/base/webhook URLs remain plaintext, historical rows may contain plaintext, local/dev can retain explicit `plain:` values, and only one active encryption key is supported | Secrets embedded in unrestricted fields remain exposed; operators can assume every legacy value is encrypted; replacing or losing the key can make encrypted credentials unavailable | Forbid secrets in metadata/URLs, inventory and migrate confirmed plaintext under backup and verification, protect and back up the active key, design an audited rotation/re-encryption procedure, and consolidate overlapping persistence models before activating enterprise connectors |

## Controls that already reduce risk

- The Git repository and remote feature branch are synchronized.
- Alembic reaches one head from an empty database.
- Backend, web and mobile automated suites are currently green when run with
  healthy local toolchains.
- IoT ingestion includes tenant scoping, per-device credentials, replay
  protection and test coverage.
- ERP events use durable GeoVision idempotency keys and provider-pinned outbox
  rows; this does not yet prove provider-side deduplication.
- Staging and production configuration apply a minimum syntactic JWT guard and
  require a valid Fernet encryption key before application startup; deployed
  encryption calls also fail closed if the runtime cannot encrypt.
- Configuration representations and diagnostic dumps redact known secret,
  credential, bank, and database URL fields.
- Provider ports are domain-owned; the S3-compatible storage adapter is selected
  lazily, and consuming services can receive fake providers without importing a
  vendor SDK.
- The S3 factory rejects partial explicit credentials, and the adapter maps
  provider authentication, configuration, validation/not-found, and transient
  failures into normalized outcomes.
- ERP outbox retries are bounded and scheduled only when a retryable failure is
  due. Legacy `failed` rows with a NULL next-attempt time receive one
  compatibility decision; new terminal/exhausted failures use
  `failed_terminal`. Unknown outcomes from side-effecting ERPNext writes are not
  retried automatically without proven provider-side idempotency.
- Deployed SMTP delivery requires STARTTLS with certificate verification; the
  local metadata log remains a development-only compatibility adapter.
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
- **Reduced:** R06, because all 206 application HTTP/WebSocket contracts and
  the legacy router order now have automated compatibility checks.
- **Contained:** R01, R07, R16, R18 and R19 now have explicit owning domain or
  sector boundaries, but their underlying product work remains unchanged.
- **Unchanged:** R02, R03, R05 and R08-R23 remain active and belong to later
  phases. Phase 1 did not alter persisted schema, providers, deployment, public
  sector activation, or customer navigation.
- **Introduced and controlled:** Registry metadata could drift from real route
  ownership; import-time validation and architecture tests fail when module
  names, dependencies, orders, or router targets conflict.

## Phase 2 outcome

- **Reduced:** R10, because ERP provider calls are injectable and outbox retries
  now honor provider pinning, attempt limits, due times, bounded backoff, and
  terminal failure classification. Legacy failed rows with no scheduled next
  attempt receive one compatibility processing decision. Unknown outcomes from
  side-effecting ERPNext writes are terminal until provider-side idempotency can
  be proved. The independent worker, reconciliation, and dead-letter controls
  remain outstanding.
- **Reduced:** R11, because all runtime/provider settings now have one typed
  source, staging and production fail closed for syntactically unsafe signing
  and invalid encryption secrets, and supported diagnostics are redacted. The
  JWT check is not an entropy audit, and provider validation remains partly
  use-time. Legacy persisted connector secrets remain covered by R24.
- **Reduced:** R24, because every current Connector/Integration credential write
  uses the canonical encryption helper and deployed profiles cannot start
  without valid Fernet configuration. No automatic legacy-value rewrite was
  attempted; plaintext metadata/URLs, key rotation, and a future audited data
  migration remain outstanding.
- **Reduced:** R13, because dataset/document storage now consumes a domain-owned
  provider port, partial explicit S3 credentials are rejected, errors are
  classified, and the S3-compatible SDK adapter is isolated behind a lazy
  factory. Azure Blob, immutable file identity, streaming, full error
  propagation, and dual-read migration remain Phase 12 work.
- **Reduced:** R14 and R15, because external capabilities have provider-neutral
  ports and normalized result/error conventions. ERPNext remains available,
  Odoo and Azure adapters are not falsely presented as active, and GeoVision
  UUIDs remain authoritative.
- **Reduced:** R12, because payment configuration is typed, adapters are
  injectable and lazily selected, deployed environments fail closed when a
  credential-gated provider is unavailable, and the normalized facade marks
  local mock behavior as simulated. Phase 8 must still expose that distinction
  consistently, validate bank deployment values, and close PayPal webhook and
  refund gaps through the public payment lifecycle.
- **Contained:** R19, because normalized results distinguish simulated,
  unconfigured, pending, retrying, and failed outcomes and documentation lists
  placeholder boundaries separately from concrete adapters. Owning provider
  and release phases must still enforce live readiness.
- **Unchanged:** R01-R03, R05-R09, R16-R18, and R20-R23 remain assigned to their
  later phases. Phase 2 did not change public routes, persisted schema,
  deployment infrastructure, sector activation, or customer navigation.
- **Introduced and controlled:** Provider protocols can drift from concrete
  implementations; structural runtime checks, fake-provider tests, lazy SDK
  imports, and compatibility facades now guard the representative ERP and
  object-storage paths.

## Phase 3 outcome

- **Resolved:** R02 and R04. Startup exits on an Alembic timeout/failure and no
  longer stamps the database or calls `create_all` as a migration substitute.
  The remaining narrow compatibility repair references the initialized database
  module; R03 tracks its eventual removal.

- **Reduced:** R07, because GeoVision now resolves external issuer/subject to an
  immutable internal user UUID and builds permissions from persisted local roles
  and memberships. Automatic verified-email linking is disabled by default and
  first external login provisions only a user, mapping, and minimal profile.
  `ADMIN_EMAILS` and the overlapping Account/Company authorization models remain
  explicit Phase 4 risks.
- **Reduced:** R11, because version 2 GeoVision sessions require the configured
  internal issuer/audience and carry the internal UUID as subject. Legacy access
  tokens remain an explicit temporary switch and require a planned expiry or
  forced-login event plus separate refresh-token revocation when appropriate.
- **Contained:** Entra External ID validation accepts only delegated version 2
  access tokens for the configured GeoVision API audience, tenant, issuer, scope,
  and optional authorized party. ID tokens, application tokens, and Microsoft
  Graph access tokens are outside this boundary and must fail closed.
- **Contained:** Legacy Google identifiers can be safely issuer-qualified;
  historical Microsoft Graph object IDs are not relabelled as Entra subjects.
  Historical `raw_data` may contain personal data and remains subject to an
  audited retention/deletion and backup policy.
- **Unchanged:** R01 and the canonical organization/RBAC portion of R07 remain
  owned by Phase 4. Phase 3 does not consolidate Account, Company, organization,
  invitations, entitlements, or sector assets. No Firebase identity integration
  exists or was introduced.
- **Operational gate:** Follow `docs/ENTRA_CUTOVER_RUNBOOK.md` for staged
  transition, mapping review, negative-token tests, session retirement,
  monitoring, and rollback before enabling Entra as the external login/exchange
  authority. Business APIs continue to authorize UUID-based internal sessions.
- **Operational residual:** The identity migration must run with old writers and
  registration paused after normalized-email, Google-subject, refresh-family,
  and Company/User mapping review. The migration fails before DDL on detected
  identity collisions. External revocation is bounded by the absolute family
  deadline plus already-issued short access tokens; trusted proxies must also
  sanitize `X-Forwarded-For` until the in-memory limiter is replaced.

## Phase 5 outcome

- **Reduced:** R05, because all verticals can now use one organization/workspace
  Asset hierarchy with stable sectors, extensible types, validated EPSG:4326
  GeoJSON, portable bounding-box filters, and a PostgreSQL PostGIS/GiST
  projection when the extension is available.
- **Contained:** Existing `Site` and IoT/construction asset rows are copied and
  linked through non-destructive legacy identifiers. Current mobile, admin, and
  IoT creation paths mirror new writes; the source tables remain operational.
- **Contained:** Customer asset reads and writes use the selected authorization
  context. Viewer mutation, parent crossover, hierarchy cycles, and
  cross-organization UUID access fail closed in automated tests.
- **Residual:** A portable-only database is supported for CI and development but
  is not production PostGIS evidence. A restored-data PostgreSQL rehearsal must
  verify extension/version, generated geometry, GiST validity, row counts, and
  rollback before live cutover under R23.
- **Unchanged:** Sector-specific semantics, datasets, missions, observations,
  KPI provenance, IoT edge behavior, and customer navigation remain owned by
  their later phases; the common Asset table contains no sector-specific
  measurement columns.
