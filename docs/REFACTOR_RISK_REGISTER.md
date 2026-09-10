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
| R08 | Medium | Phase 6 provides expiring, single-use, tenant-scoped invitations into an existing workspace/asset/result, exact authenticated-email binding, and browser/native deep-link contracts; production HTTPS app-link association and durable invitation email delivery are not deployed yet | A deployment could fall back to browser/custom-scheme handling or fail to deliver an invitation even though acceptance itself is safe | Complete signed-domain association and notification delivery in the release/notification phases; monitor issue-to-accept conversion without recording tokens |
| R09 | Medium | IoT offline detection and retention have an independent worker and emit durable events; MQTT ingress and WebSocket fan-out remain API-local when enabled | Multiple MQTT-enabled API replicas can duplicate ingress connections, while in-memory live updates do not fan out across replicas | Deploy one MQTT ingress owner until a managed ingress is selected, run the independent IoT worker, and add distributed live fan-out before scaling MQTT/WebSocket replicas |
| R10 | High | ERP work now flows through the canonical event worker with claims, receipts, bounded retry, attempt history and operator dead-letter recovery; provider-side ERP deduplication is not yet proven | An uncertain provider write still requires reconciliation and must not be blindly repeated | Add the provider idempotency field in staging, prove uniqueness/reconciliation, and alert on canonical retry/dead-letter counts before activation |
| R11 | High | Typed configuration fails closed for signing/encryption in staging/production, but the JWT guard is syntactic rather than an entropy assessment and most provider validation occurs when a factory/adapter is used; local/development may still generate an ephemeral JWT key or explicit `plain:` connector compatibility values | Misclassified environments can invalidate sessions, weak-looking secrets can pass a length/placeholder check, or a dormant provider misconfiguration can remain undiscovered until use | Use high-entropy managed secrets, exercise every enabled provider in deployment checks, keep redacted diagnostics, require encryption anywhere real connector credentials are used, and track historical-row remediation under R24 |
| R12 | High | Phase 8 derives payment truth from the owned order, routes operations through the provider port, separates settlement/fulfilment, and deduplicates signed Stripe/Multicaixa callbacks; bank fields are still not live-validated and PayPal lacks deployed webhook verification/API-backed refunds | An operator can deploy invalid bank details or mistake an unsupported PayPal operation for a live capability | Require verified banking values and keep unavailable capability states explicit; add and verify PayPal webhook/refund support only when real credentials and provider verification are available |
| R13 | Medium | Dataset storage now has durable file identity, streaming, signed uploads, local/S3/Azure adapters, provider size/checksum verification, and recoverable deletion; legacy Document flows still use their older facade | New dataset uploads no longer require relational blobs or full buffering, but legacy documents can retain weaker storage behavior | Route new geospatial payloads through canonical datasets and harden/retire the legacy Document facade during the report/document phases |
| R14 | High | The provider-neutral ERP port preserves the current ERPNext adapter, while the playbook specifies a later Odoo integration | Replacing ERP code prematurely can interrupt commerce and accounting synchronization | Add Odoo as another adapter and retire ERPNext only after an approved Phase 21 cutover |
| R15 | High | Current deployment is DigitalOcean; Azure Blob, Service Bus and Event Grid adapters now exist behind provider boundaries, but live Azure infrastructure and identity assignments are not provisioned | A big-bang cloud move can mix domain refactoring with operational migration or activate unverified credentials | Provision and validate adapters in staging, rehearse rollback, then migrate capabilities independently rather than switching the whole platform at once |
| R16 | Medium | The current public scope hides or combines some sectors, while the playbook requires five explicit verticals including Ports/Industrial | UI, catalogue and data fixtures may contradict the new architecture or over-promise immature capabilities | Treat sector activation as later feature-flagged phases; do not change public claims during foundation work |
| R17 | Medium | Flutter top-level navigation is Portal, Assets, Store, Alerts and More rather than Home, Assets, Actions, Services and More | Early backend work could accidentally couple to a UI structure scheduled for replacement | Keep navigation changes in Phase 22 and expose backend capabilities independent of tab names |
| R18 | Medium | Agriculture has dedicated KPI definitions; other mobile sectors reuse a minimal infrastructure list | Sector dashboards can present generic or misleading metrics | Add validated KPI definitions only with provenance and source requirements in sector activation phases |
| R19 | Medium | RAG, Mapbox/Google delivery, Stripe mobile, push and several drone/processing providers are placeholders or credential-gated | Documentation or UI can imply production readiness that code does not provide | Keep explicit capability states, fake adapters and feature flags; never report credentials-gated behavior as live |
| R20 | Medium | The local Docker installation lacks the Compose plugin and its daemon is not running | The backend image and documented IoT stack cannot be reproduced on this host today | Start/repair Docker, install Compose, then validate the image and full stack without deleting existing volumes |
| R21 | Medium | The default local `.venv` is stale and the shell does not expose Flutter even though Flutter is installed | Advertised commands fail before tests begin | Use `make baseline`, recreate the backend virtual environment, and keep tool discovery in the verification script |
| R22 | Medium | Android and iOS builds pass with future plugin migration warnings | A future Flutter upgrade can turn warnings into build failures | Track `package_info_plus` Kotlin and `flutter_secure_storage` Swift Package Manager compatibility before the next SDK upgrade |
| R23 | Critical | No production backup-restore drill or migration rollback rehearsal is recorded | A structurally correct migration can still cause unrecoverable downtime or data loss | Require a production-like restore, migration dry run, rollback decision and owner sign-off before any live schema cutover |
| R24 | High | Connector and integration credential fields now use the canonical encryption helper and deployed profiles require a valid Fernet key, but free-form metadata and endpoint/base/webhook URLs remain plaintext, historical rows may contain plaintext, local/dev can retain explicit `plain:` values, and only one active encryption key is supported | Secrets embedded in unrestricted fields remain exposed; operators can assume every legacy value is encrypted; replacing or losing the key can make encrypted credentials unavailable | Forbid secrets in metadata/URLs, inventory and migrate confirmed plaintext under backup and verification, protect and back up the active key, design an audited rotation/re-encryption procedure, and consolidate overlapping persistence models before activating enterprise connectors |
| R25 | Medium | Phase 7 makes `catalog_items` authoritative and Phase 8 snapshots canonical catalogue lines into orders, while `shop_products` and `products` remain cart/client compatibility data | A legacy writer or failed projection could still make pre-checkout price, publication, or stock fields inconsistent | Route staff changes through `/catalog/internal`, monitor projection parity, compare prices again at checkout, retain immutable order snapshots, and retire old write/cart projections only after deployed clients migrate |
| R26 | High | The enterprise prototype persisted raw provider callback payloads; Phase 8 preserves that table as `legacy_payment_webhook_events` while all new callbacks use a digest-only ledger | Historical payloads may contain personal or provider-sensitive data beyond the required retention period | Restrict table access now; inventory/classify rows, define legal retention, export only required evidence, then securely purge raw payloads with Phase 25 audit approval and a verified backup/restore plan |
| R27 | High | Phase 9 stores private contractor/supplier contacts, qualifications, insurance, licences, quality notes and cost-bearing assignments in GeoVision | A broad customer/staff query, unsafe metadata field, or backup/export could expose personal data, internal margins, or another customer's operational details | Keep resource APIs internal, contractor views allowlisted and assignment-scoped, reject credentials in metadata, audit changes, restrict database/export access, define retention and document-access controls, and review live privacy/legal requirements before onboarding contractors |
| R28 | Medium | Phase 10 job graphs now publish into the canonical transactional outbox, and workers can distribute them through PostgreSQL or Service Bus | A bad future consumer or unmonitored dead letter can still delay a valid dependency chain | Keep graph guards, make every consumer idempotent, monitor dead letters, and reconcile orders, jobs, acquisitions and datasets before horizontal scaling |
| R29 | High | Phase 11 maps legacy drone missions and manual inspections into a common acquisition history while preserving both source tables and APIs | A partial cutover or repeated backfill can duplicate history, lose flight detail, leak provider/assignee metadata, or let sector code depend on drone-only structures | Keep deterministic legacy identities and uniqueness constraints, dual-write through compatibility services, expose allowlisted customer projections, test rollback/re-upgrade parity, and retire legacy tables only after deployed clients and row-count checks confirm cutover |
| R30 | High | Phase 12 pins every object reference to local, S3-compatible, or Azure Blob storage; changing the configured default deliberately does not move old bytes, and signed uploads currently use a portable single-PUT ceiling | A settings-only cutover can make historical objects unavailable, and files above the ceiling need a real multipart/block client rather than a larger advertised limit | Run a staged copy with size/checksum verification, dual-provider read window, transactional reference switch, and rollback; add provider-specific multipart/block sessions only when client/workload evidence requires them |
| R31 | High | Phase 14 adds durable processing jobs, a deterministic fake and NodeODM integration, but live photogrammetry compute capacity and measurement quality are not validated; the initial NodeODM output path reads a bounded archive into worker memory | A live node can exhaust memory/CPU/storage, a technically valid output can still be operationally inaccurate, or raising safety limits can destabilize workers | Keep automatic processing off until staging capacity and representative accuracy tests pass; pin/review the processor image, monitor queues/resources, retain NEEDS_REVIEW, and implement streamed/chunked transfer before larger workloads |
| R32 | High | Phase 15 adds Copernicus and AEMET adapters, durable cached acquisitions and normalized provenance, but live credentials, provider quotas/licences, coverage and source interpretation are not validated | Provider outages or limits can create data gaps and costs, sparse stations/cloudy scenes can mislead users, or source data can be presented as a validated sector conclusion | Keep live providers behind Gate 12; review licence/attribution and budgets, validate representative assets and source quality, monitor failures/cache/storage, preserve provenance and require sector-specific interpretation before customer claims |

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
- The catalogue exposes only GeoVision-controlled products and services; no
  public seller, seller payout, bidding, or contractor storefront exists.
- Payment amounts, currency, organization and description are derived from the
  owned order; verified webhook IDs are unique and raw new payloads are not stored.

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

## Phase 6 outcome

- **Reduced:** R08, because invitation tokens are random, stored only as
  digests, expire, revoke, accept once, bind exclusively to the authenticated
  internal identity, and open a server-validated existing destination.
- **Contained:** Exact normalized-email matching fails closed without a client
  override. Owner roles, cross-tenant targets, viewer issuance, secret-like
  metadata, tampered tokens, and reuse by another identity are rejected.
- **Reduced:** Duplicate onboarding risk, because `view_invitation`
  registration intentionally creates no starter company/workspace and login
  suppresses legacy auto-provisioning while a recipient has a live invitation.
- **Contained:** Browser tokens remain in URL fragments and tab storage; native
  custom-scheme routing preserves the destination through authentication.
  Clear tokens are returned once and excluded from persistence and audit logs.
- **Residual:** Production HTTPS universal/app links need domain association,
  signed entitlement validation, and release testing. Durable email delivery is
  owned by Phase 20; clients currently use the secure API/deep-link contract.
- **Unchanged:** Existing legacy membership creation remains compatible.
  Historical pending memberships receive no fabricated token and require an
  explicit secure reissue.

## Phase 7 outcome

- **Reduced:** R06, because one public `/catalog/items` contract now covers all
  six offer types while `/shop/products`, carts, orders, `/products`, and old
  admin URLs retain compatibility projections and stable item identifiers.
- **Reduced:** R16, because applicability is normalized to the five common
  sector identifiers without publicly activating unready sector capabilities.
- **Contained:** Supplier contact and qualification data live in an internal
  procurement table and are never serialized to customers. Customer roles
  cannot manage items; only explicit GeoVision staff permissions can do so.
- **Contained:** Only published items are customer-visible. Publication enforces
  price rules, archives preserve history, and credential-like metadata keys are
  rejected. The historical delete endpoint now performs a reversible archive.
- **Introduced and controlled:** R25 records the temporary dual-model projection.
  Additive migration, write-through compatibility, parity tests, and retained
  source identifiers protect existing carts and order data during cutover.
- **Unchanged:** Payment settlement, order/service lifecycle, fulfilment jobs,
  supplier qualification, recommendation-action migration, and installed-device
  creation remain owned by Phases 8, 9, 10, and 17.

## Phase 8 outcome

- **Reduced:** R06 and R12, because canonical `/orders` customer/internal APIs
  coexist with legacy routes, settlement is separate from fulfilment, every
  payment operation uses the billing provider port, and provider references
  never replace GeoVision IDs.
- **Reduced:** Cross-tenant payment risk, because payment creation now derives
  organization, amount, currency and description from an owned order; customer
  reads/lists and the old shop cancellation path enforce ownership.
- **Contained:** Webhook retries and reordering, because signature verification
  precedes a unique provider/event receipt, duplicate delivery has no second
  effect, and stale events cannot reverse terminal settlement.
- **Contained:** Lifecycle shortcuts, because explicit forward transitions,
  payment gates, reasons for exceptional states, and optimistic versions reject
  invalid or stale operational changes.
- **Reduced:** R25, because order lines point to canonical catalogue items and
  preserve immutable pricing/fulfilment snapshots while cart compatibility
  remains in service.
- **Introduced and controlled:** R26 records the preserved raw legacy webhook
  archive. The Phase 8 migration never writes new raw payloads and restores the
  historical table on rollback; retention/purge requires Phase 25 approval.
- **Unchanged:** Supplier/resource qualification, fulfilment jobs, event-bus
  dispatch, PayPal provider gaps, and production backup/restore sign-off remain
  owned by later phases.

## Phase 9 outcome

- **Reduced:** The supplier/contractor gap, because private procurement sources
  and generic operational resources now carry region, service area,
  qualification, insurance, equipment, document, availability, quality, and
  capability data without a drone-only or public-seller model.
- **Reduced:** Resource matching risk, because GeoVision Operations can combine
  country/region, capability or sector, resource type, status, and availability
  filters against a normalized, extensible capability taxonomy.
- **Contained:** Contractor access, because an optional linked internal user can
  read only its own allowlisted profile and assignment necessities. Cross-profile
  IDs return not found and internal costs, margins, order/customer identifiers,
  notes, staff identities, supplier data, and unrelated assets are omitted.
- **Contained:** Destructive history loss, because supplier/contractor delete
  operations deactivate records; guarded assignment states and optimistic
  versions prevent reopening or stale decisions.
- **Introduced and controlled:** R27 tracks the personal, qualification, and
  commercial sensitivity of private resource records. Structured fields reject
  credential-like keys and changes are audited, but production retention,
  document authorization, and legal onboarding review remain required.
- **Unchanged:** Phase 10 still owns canonical fulfilment jobs and will attach
  the reserved assignment job reference. Customer-facing marketplace sellers,
  provider bidding, contractor payouts, and public profiles remain absent.

## Phase 10 outcome

- **Resolved:** A commercial order is no longer treated as its own work queue.
  An idempotent planner expands each purchased line into explicit capture,
  acquisition, installation, processing, review, delivery, and publication jobs.
- **Contained:** Dependency risk, because edges are same-order, non-self,
  duplicate-safe and cycle-checked. Readiness, assignment, scheduling, and work
  start are gated on completed upstream work; `PROCESS_DATA` cannot start
  without an explicit completed input dependency.
- **Contained:** Operational privacy, because internal job projections alone
  expose direct costs, cost references, order links, and assignee identities.
  Contractor views are own-assignment allowlists; customer progress is derived
  only from safe stage/status aggregates.
- **Contained:** Stale or invalid updates, because a guarded state machine,
  optimistic lifecycle versions, schedule/assignee validation, audit records,
  and transactional domain events cover every material mutation.
- **Introduced and controlled:** R28 records job-graph and local dispatch risk.
  The publisher is a replaceable domain port and its current implementation is
  an idempotent transactional ledger; distributed dispatch remains Phase 13.

## Phase 11 outcome

- **Resolved:** Drone, satellite, IoT, manual inspection, and third-party data
  capture now share a provider-neutral Acquisition lifecycle linked to a generic
  asset and, when appropriate, an order or fulfilment job.
- **Contained:** Drone-only aircraft, payload, operator, capture-area, flight,
  and reflight fields live in an optional extension; no non-drone acquisition
  requires them. Sector consumers read common output references without knowing
  which modality captured the data.
- **Contained:** Customer projections omit provider references, provenance,
  internal resource identities, raw storage keys, and credential-like metadata.
  Internal mission routes retain the operational detail behind staff roles.
- **Contained:** Legacy drone missions and asset inspections use deterministic,
  idempotent mappings. Additive migration, rollback, and re-upgrade tests verify
  source preservation and stable acquisition counts.
- **Introduced and controlled:** R29 records the compatibility and privacy risk
  during dual-write cutover. Legacy retirement remains explicitly deferred.

## Phase 12 outcome

- **Reduced:** R13, because canonical dataset bytes remain outside relational
  storage and local, S3-compatible, and Azure Blob adapters now support
  streaming, short-lived signed URLs, stat/checksum evidence, and safe errors
  behind the dataset-owned provider port.
- **Contained:** Cross-tenant object access, because dataset operations require
  exact active organization/workspace ownership and local signed routes repeat
  that authorization at read/write time. File paths use immutable GeoVision IDs
  and provider credentials are never serialized to clients.
- **Contained:** Orphan-state risk, because upload reservations precede provider
  writes, file deletion persists a recoverable intermediate state, failed
  provider deletion restores the reference, and dataset deletion is an archive
  that retains tracked objects.
- **Contained:** Legacy data migration, because additive backfill maps Site
  datasets to generic Assets/workspaces where possible, keeps original rows and
  keys, and passes rollback/re-upgrade checks on SQLite and PostgreSQL.
- **Introduced and controlled:** R30 records provider-cutover and very-large-file
  strategy. Existing rows remain provider-pinned; live Azure RBAC and a staged
  copy/checksum cutover are deployment gates, and files above the portable
  single-PUT ceiling are not falsely advertised as supported.

## Phase 13 outcome

- **Reduced:** R09, R10 and R28, because organization, commerce, fulfilment,
  acquisition, dataset, IoT and ERP facts now share a transactional outbox.
  Independent workers recover stale claims, apply bounded retries, record safe
  attempt history and expose recoverable dead letters.
- **Contained:** At-least-once delivery, because consumers commit a unique
  `(consumer_name, event_id)` receipt with their database effects. Service Bus
  `MessageId` duplicate detection is defense in depth rather than correctness.
- **Reduced:** R15, because Azure Service Bus publishing/peek-lock consumption
  and Event Grid BlobCreated normalization are isolated adapters. Domain modules
  import no Azure SDK and local mode needs no Azure service.
- **Contained:** Upload ingress, because authenticated Event Grid events must
  match the configured account/container and an existing provider-pinned file
  reservation before `dataset.ingestion_requested` is committed.
- **Deferred explicitly:** MQTT connection ownership and cross-replica
  WebSocket fan-out remain under R09; provider-side ERP uniqueness remains under
  R10; live Azure provisioning and role assignment remain under R15.

## Phase 14 outcome

- **Reduced:** R19, because photogrammetry is no longer only a placeholder.
  Provider-neutral jobs persist sources, outputs, progress, costs, retries,
  errors and processor provenance; a deterministic provider exercises the full
  path without claiming real measurements.
- **Contained:** Provider lock-in, because business services depend only on
  `ProcessingProvider`. NodeODM owns its HTTP/task/archive details, while PIX4D,
  Autodesk and Bentley names fail explicitly through future adapter scaffolds.
- **Contained:** Missing and unsafe output risk, because a provider completion
  is insufficient by itself. Requested artifacts must be recognized, non-empty,
  allowlisted and within configured archive/file limits before normal Dataset
  records are marked ready; otherwise the job becomes `NEEDS_REVIEW`.
- **Contained:** Restart and duplicate risk, because jobs use durable claims,
  bounded retries, stable submission/output identities and object reservations
  before writes. Generated datasets emit the canonical downstream events.
- **Introduced and controlled:** R31 records the remaining live capacity,
  accuracy, image/licence approval and large-transfer work. Automatic processing
  remains opt-in and paid vendor adapters remain unavailable.

## Phase 15 outcome

- **Reduced:** R19, because satellite and weather capabilities are no longer
  placeholders. Provider-neutral services now persist attempts, cache keys,
  normalized scenes/observations, Acquisition/Dataset links and provenance.
- **Contained:** Provider coupling, because Copernicus STAC and AEMET OpenData
  details remain in adapters injected at the transport/worker boundary. Azure
  Maps Weather is an explicit unavailable scaffold and fake providers are
  rejected in deployed profiles.
- **Contained:** Restart, duplicate and provider-failure risk, because weekly
  schedules and retries use durable claims, bounded attempts/backoff, stable
  fingerprints and reusable completed results. Safe error details and schedule
  failure counters remain inspectable.
- **Contained:** Download and credential exposure, because imagery downloads
  are opt-in, size-bounded and HTTPS-host allowlisted; stored source links drop
  query strings/fragments and all provider credentials remain server-side.
- **Introduced and controlled:** R32 records remaining external quota, licence,
  coverage, source-quality, cost and interpretation work. Gate 12 must pass
  before live activation; source data alone is not a sector conclusion.
