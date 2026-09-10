# GeoVision integration connection registry

Phase 32 adds the durable control plane for customer-owned enterprise
connections. It does not make an external vendor live. GeoVision remains the
system of record for organizations, workspaces, users, Assets, orders,
acquisitions, datasets, intelligence and reports; provider references remain
opaque secondary identifiers.

## Readiness classification

| Slice | Classification | Evidence and limitation |
|---|---|---|
| Registry schema, tenant constraints, admin API, lifecycle, audit and outbox | Implemented and automated-test verified | Portable SQLite migration round trips, ORM constraints and tenant/API regressions pass; a production-like PostgreSQL restore and rollout rehearsal is still required |
| Deterministic `fake` connections | Local/test pilot only | The complete create, flag, enable, health, sync, retry, disable and disconnect workflow is tested without network I/O; fake providers are rejected in staging and production |
| Azure App Configuration policy adapter | Runtime-wired, live smoke test pending | The read-only evaluator, lazy official-provider loader, typed endpoint, deployment endpoint and managed-identity Data Reader role are implemented; no customer rollout flag has been verified against the deployed store |
| Azure Key Vault secret adapter | Runtime-wired, live registry-secret test pending | Canonical HTTPS references, redacted values, lazy `SecretClient` composition and the deployed managed-identity Secrets User role are implemented; no named connector has resolved and used a customer credential end to end |
| Autodesk APS, Procore, Bentley iTwin, Trimble, SAP EAM, IBM Maximo, Dynamics 365 Asset Management, customer CMMS, Seequent, mine-enterprise, ArcGIS, MarineTraffic, Kpler and Puertos del Estado | Blocked | A registry row or credential reference is not authorization. Each provider still needs an approved customer account, credentials, sandbox, scopes, mapping and idempotency contract, rate/licence terms, provider-specific tests and a signed release gate |

MITECO's separately reviewed public GIS context adapter remains governed by its
own source and reuse rules. Registering `miteco` as a customer connection does
not enable or replace that adapter.

## Durable ownership model

The additive `integration_registry_v1` migration follows
`trust_economics_v1`. It preserves the legacy `connectors` and `integrations`
tables and creates four canonical tables:

| Table | Purpose |
|---|---|
| `integration_connections` | Provider family/code, organization and optional workspace/member scope, non-secret settings/configuration reference, secret references, allowed capabilities, lifecycle/health and resilience state |
| `integration_sync_runs` | One idempotent execution request with payload digest, direction, operation, retry/failure state, timing and correlation |
| `integration_sync_events` | A normalized per-resource event within a run, using GeoVision resource references and an optional opaque external reference; the request payload itself is not retained |
| `feature_flag_overrides` | Workspace or workspace-member rollout decisions with source, Azure configuration reference, ETag, configuration version and optimistic lifecycle version |

The migration also adds a redundant-but-enforceable unique key on
`accounts(id, organization_id)`. New composite foreign keys use it to reject a
workspace attached to a different organization. A member-scoped connection or
flag also references the exact `account_members(account_id, user_id)` pair.
Connection scope and sync history use restrictive deletion: lifecycle actions
must be explicit, and deleting a membership, workspace, run or connection must
not silently erase the ledger. Feature-flag rows may disappear when their exact
workspace or membership is removed.

Every mutable registry object carries a positive lifecycle version. Update,
enable/disable, disconnect, retry and flag deletion requests require the
expected version so concurrent operators receive a conflict instead of silently
overwriting one another. Feature-flag updates and deletes qualify the database
write itself by that version; the check is not a non-atomic read followed by an
unconditional write.

## Provider families and capabilities

The registry normalizes four customer-owned families. Capabilities are an
allowlist, not authorization by themselves. The fake sync harness requires a
non-empty valid set; each real adapter must map and enforce its operation against
the declared capability before provider I/O.

| Family | Registered provider codes | Allowed capabilities |
|---|---|---|
| `construction` | `fake`, `autodesk_aps`, `procore`, `bentley_itwin`, `trimble` | `project.read`, `project.write`, `inspection.read`, `document.read` |
| `asset_management` | `fake`, `sap_eam`, `ibm_maximo`, `dynamics_365_asset_management`, `customer_cmms`, `seequent`, `mine_enterprise` | `asset.read`, `asset.write`, `work_order.read`, `work_order.write` |
| `gis` | `fake`, `arcgis`, `miteco` | `layer.read`, `feature.read` |
| `maritime` | `fake`, `marinetraffic`, `kpler`, `puertos_del_estado` | `context.read`, `vessel.read` |

The fixture sync API accepts only the normalized provider-port operations below;
direction selects the minimum required capability.

| Family | Operation | Direction → capability |
|---|---|---|
| `construction` | `synchronize_project` | inbound → `project.read`; outbound → `project.write` |
| `asset_management` | `synchronize_asset` | inbound → `asset.read`; outbound → `asset.write` |
| `gis` | `query_layers` | inbound → `layer.read` |
| `maritime` | `operational_context` | inbound → `context.read` |

Only `fake` can be enabled and synchronized in the verified workflow, and only
outside deployed profiles. Named providers deliberately return
`provider_not_approved` even if a row contains apparently complete
configuration. Provider-specific live adapters must reuse the matching
`ConstructionProvider`, `AssetManagementProvider`, `GISProvider` or
`MaritimeProvider` seam rather than writing vendor logic into the registry.

## Feature rollout and precedence

Canonical integration rollout keys are plural:

```text
geovision.integrations.<family>.<provider>
```

Sector rollout keys use `geovision.sectors.`. Other namespaces are rejected.
The current registry API checks authentication, organization/workspace access,
permission, a current integration-capable organization subscription,
provider lifecycle and the operation-specific connection capability in addition
to its rollout flag. A consuming product module must also pass any narrower
workspace/module entitlement; a flag never grants a permission or entitlement.
The organization must be `active` or `trial` and its effective tier must be one
of `professional`, `growth`, `scale`, `enterprise` or `custom`. A persisted
`CompanyEntitlement` takes precedence over the compatibility subscription-plan
field and fails closed after its explicit expiry.

Resolution is deterministic:

1. A matching member override for the selected workspace wins.
2. Otherwise the matching workspace override applies.
3. With no persisted override, the read-only Azure App Configuration evaluator
   applies its canonical UUID targeting rules.
4. If Azure has no enabled matching definition, the answer is `false`. If the
   evaluator is unconfigured, unavailable on cold start or expired, it is
   explicitly reported as `fail_closed`.

Cross-organization workspaces and users who are not current workspace members
are rejected. The Azure-compatible evaluator independently requires the caller
to be both authorized and entitled. Cold-start load failure denies access. A
last-known-good snapshot may be reported degraded and used only within its
bounded staleness window; an expired snapshot denies access. Targeting
exclusions take precedence over explicit users/groups and deterministic
percentage rollout.

The five sector HTTP modules consume the exact rollout keys
`geovision.sectors.agriculture`, `.infrastructure`, `.environmental`, `.mining`
and `.ports`. Their pre-existing workspace/module checks remain authoritative:
a rollout flag can deny an otherwise enabled module but cannot grant around
those checks. A local installation with neither an external rollout provider
nor an explicit override preserves the established enabled-by-default modules.
Once Azure App Configuration is configured, missing, unavailable or expired
external decisions fail closed. Capabilities report the effective combination,
and operational sector routes enforce it for the current workspace member.

An override with source `azure_app_configuration` must retain a non-secret
configuration reference; ETag and configuration version are optional mirroring
metadata. Phase 32 does not include an automatic Azure-to-database mirroring
worker, so an operator-created Azure-sourced row is evidence of recorded
configuration provenance, not evidence that the referenced flag was read from
Azure. The runtime instead reads the configured Azure snapshot as the fallback
after persisted member/workspace overrides.

## Secret and payload rules

Production Azure secret references must use the one canonical public-cloud
form accepted by the resolver:

```text
https://<vault-name>.vault.azure.net/secrets/<secret-name>[/<version>]
```

The canonical parser requires a lowercase reviewed vault hostname, normal HTTPS
with no explicit port, no user information, query, fragment or percent-encoded
path, and bounded Azure-compatible secret/version names. Store the reference,
never the resolved value. Versioned references are preferred for reproducible
activation and rollback; an unversioned reference deliberately follows the
vault's current version.

The registry rejects secret-bearing keys in `settings` and sync payloads;
connection settings also reject common credential-shaped text and endpoint user
information. Endpoints must be HTTPS and cannot contain user information, a
signed query or fragment. Connection responses expose only `*_configured`
booleans, never endpoint, connection configuration/settings or secret
references. Feature-flag responses may expose their non-secret App
Configuration reference, ETag and version provenance. A resolved `SecretValue`
is redacted in ordinary string and representation output and may be revealed
only inside the concrete adapter boundary.

Sync request bodies are bounded, validated and represented durably by a SHA-256
digest. Normalized resource type/ID and opaque provider reference fields remain
separate; external references cannot be URLs and never become GeoVision IDs.
Raw request headers, provider response bodies and secret values do not belong in
the database, audit log, outbox or application logs.
Idempotency keys, correlation IDs and lifecycle reasons are operator-visible
metadata; use opaque GeoVision identifiers and never place credentials, personal
data or signed URLs in them.
Validation failures on registry routes use a fixed redacted response. Rejected
values, validator context and attacker-controlled field names are not reflected
in the 422 body.

## API surface

All routes require a GeoVision session and canonical authorization context.
Send `X-Workspace-ID` when operating in a selected workspace. Inaccessible
organization/workspace/connection/member scopes return a non-disclosing 404.

| Method and path | Permission | Purpose |
|---|---|---|
| `GET /integration-connections` | `organization:read` | List visible organization-wide and selected-workspace connections; member-scoped rows are visible only to that member |
| `POST /integration-connections` | `organization:manage` | Create a disabled connection with allowlisted family/provider/capabilities |
| `GET /integration-connections/{id}` | `organization:read` | Read the redacted connection projection |
| `PATCH /integration-connections/{id}` | `organization:manage` | Update non-secret configuration and secret references using `expected_version` |
| `POST /integration-connections/{id}/enable` | `organization:manage` | Enable an approved connection; currently succeeds only for local/test `fake` |
| `POST /integration-connections/{id}/disable` | `organization:manage` | Stop new synchronization without deleting history |
| `POST /integration-connections/{id}/disconnect` | `organization:manage` | Clear stored secret references and terminalize pending work while retaining history |
| `POST /integration-connections/{id}/health` | `organization:manage` | Record and return a safe boundary health result; not a named-vendor connectivity proof |
| `GET/POST /integration-connections/{id}/sync-runs` | read/manage | Inspect runs or request a fixture sync with an idempotency key |
| `POST /integration-connections/{id}/sync-runs/{run_id}/retry` | `organization:manage` | Retry only a due `retry_scheduled` fixture run with the expected version |
| `GET /integration-connections/{id}/sync-events` | `organization:read` | Inspect normalized per-resource events, optionally filtered by run |
| `GET /integration-connections/feature-flags` | `organization:read` | List selected-workspace overrides |
| `GET /integration-connections/feature-flags/resolve/{key}` | `organization:read` | Resolve member → workspace → Azure evaluator → deny precedence |
| `PUT /integration-connections/feature-flags/{key}` | `organization:manage` | Create or version-update a workspace/member override |
| `DELETE /integration-connections/feature-flags/overrides/{id}` | `organization:manage` | Delete an override with `expected_version` |

The current sync request exposes `simulation_outcome` only for deterministic
contract testing. It is not a public live-provider contract and must be removed
or confined to a separately authenticated test harness before any real adapter
is activated.

## Resilience and health semantics

- Per-connection timeout, maximum attempts, base retry delay and optional
  per-minute rate state are bounded and snapshotted into durable work.
- Attempt counts include the first attempt. Timeout, temporary unavailability
  and rate limiting may schedule a bounded retry; validation/authentication and
  unknown failures remain terminal unless explicitly normalized.
- A side-effecting live call may retry only after provider-side idempotency is
  proven. A GeoVision idempotency key alone does not prove the external write
  was deduplicated.
- Rate-limit deadlines block calls until due and are separate from circuit
  failures. Rate limiting must not itself trip the availability circuit.
- Repeated transient availability failures open the circuit. Calls remain
  blocked through the cooldown; a subsequent half-open probe may close it on
  success or reopen it on a retryable failure.
- Connection state is locked while a fixture attempt transitions the persisted
  rate-limit/circuit state, serializing the half-open probe on PostgreSQL.
- Organization-wide connections still write each run/event to one required
  workspace. History reads, retries and idempotency uniqueness are qualified by
  that workspace, so selecting a shared connection never exposes another
  workspace's ledger.
- `health_status` is operator context, not customer truth. `healthy` currently
  proves only that the local control plane accepted an enabled deterministic
  provider as available. Application
  `/health` or `/ready` never proves a named external account can complete an
  operation.
- A failure in any connection remains isolated. Asset, report and customer
  functionality continues against GeoVision-owned records.

## Auditing, events and redaction

Connection create/update, enable/disable, health, disconnect, flag changes and
sync requests/retries record scoped audit events. Lifecycle and sync state
changes also publish stable, idempotent domain events through the transactional
outbox. Operator lifecycle reasons pass the bounded integration-message
sanitizer before audit persistence. Audit/outbox payloads contain GeoVision IDs,
family/provider codes, capability names, state, bounded error codes, attempt
counts and configured booleans. They must not contain endpoints, configuration
bodies, secret references, resolved secrets, request payloads or raw provider
errors.

The outbox does not execute provider I/O inside the business transaction. A
future worker must claim work durably, release database locks before network
I/O, revalidate connection/flag/scope immediately before the call, then persist
the outcome and enqueue its event atomically.

## Operator runbook

### Local/test verified workflow

1. Create a `fake` connection for one organization and optional selected
   workspace/member. Begin with the minimum capability list.
2. Create the exact rollout key
   `geovision.integrations.<family>.fake` for that workspace. Add a member
   override only when a narrower pilot is intended.
3. Enable with the current `version`, then call the connection health route.
4. Submit one allowlisted operation/direction with its required capability and
   an idempotency key. Verify its run, event, audit and outbox records. Replay
   the same key/body and confirm the same run is returned; reuse with a different
   body must conflict.
5. Exercise timeout, rate-limit, unavailable and invalid-request outcomes.
   Verify bounded retries, due-time enforcement and dead-letter visibility.
6. Disable, then disconnect. Confirm pending runs become cancelled, pending
   events become skipped, secret-reference fields are cleared, and completed
   GeoVision history remains readable.

Never perform this fake-provider workflow in staging or production.

### Azure rollout smoke test

1. In staging, create the exact feature-flag ID
   `geovision.integrations.<family>.<provider>` in the provisioned App
   Configuration store. Use canonical target keys only:
   `organization:<uuid>`, `workspace:<uuid>` and `user:<uuid>`.
2. Remove any persisted member/workspace override for the test subject so it
   does not intentionally take precedence over Azure. Confirm an exclusion wins
   over inclusions and that an unauthorized, unentitled or untargeted subject is
   denied.
3. Keep ordinary application configuration keys in the store; the evaluator
   selects reviewed GeoVision feature-flag entries and ignores unrelated values.
   Through the approved staging deployment check or adapter contract harness,
   confirm a current snapshot reports available without exposing its endpoint or
   raw definition. Exercise refresh failure within the last-known-good window
   and expiry after the configured maximum staleness; expiry must deny. There is
   no public raw-flag diagnostic endpoint.
4. Restore the flag to disabled and record the result. A successful flag smoke
   test does not authorize a named provider or prove its credential/connectivity.

### Live-provider activation gate

Before replacing `fake`, record all of the following for the exact customer and
workspace:

- signed customer/provider authorization and data-processing/licence terms;
- approved sandbox and least-privilege account/scopes;
- canonical versioned Key Vault references and managed-identity access;
- reviewed field mapping with GeoVision ownership and opaque external IDs;
- provider-side idempotency/reconciliation behavior for uncertain writes;
- documented quotas, retry-after behavior, timeout and circuit thresholds;
- contract tests, representative tenant-isolation tests and a redacted health
  probe in staging;
- disable, credential-revocation, reconciliation and rollback owners.

Until every item passes, leave the named connection disabled and its feature
flag false.

### Incident, rotation and disconnect

- For a due retry, inspect the safe run/event error code and reconcile any
  uncertain external write before retrying. Never edit attempt counters or
  lifecycle versions directly.
- When a circuit is open, investigate the provider/sandbox and wait for the
  controlled probe; do not repeatedly toggle the connection to bypass it.
- To rotate a secret, create a new Key Vault version, update the reference with
  optimistic concurrency, verify in the approved sandbox, then revoke the old
  version. Never copy the secret value through the API or logs.
- `disconnect` is a GeoVision control-plane action. It clears stored references
  and stops pending work but cannot revoke a provider account or Key Vault
  secret by itself. Revoke those externally and retain evidence in the incident
  record.
- Do not hard-delete connection/run/event rows. Their restrictive foreign keys
  intentionally preserve the operational history.

## Migration and rollback

Before applying `integration_registry_v1`, take a verified database backup and
record row counts for `accounts`, `account_members`, `connectors` and
`integrations`. Run the normal single-owner migration job, verify Alembic reports
one head, then verify the four new tables, composite foreign keys, unique
idempotency/flag indexes and unchanged legacy row counts.

A downgrade to `trust_economics_v1` drops the four Phase 32 tables. It does not
drop legacy connector/integration rows or GeoVision domain history, but it does
destroy registry configuration, rollout overrides and sync-ledger rows. Use it
only before live registry adoption or after restoring/exporting the required
records under an approved rollback plan. Do not use a schema downgrade as a
provider disconnect mechanism.

## Legacy compatibility debt

`Connector` and `Integration` remain separate compatibility models with older
credential/configuration behavior and organization-wide scope. Phase 32 neither
backfills nor deletes them. They are not automatically governed by the new
workspace/member flags, lifecycle, secret-reference, health or sync-ledger
rules. Inventory their consumers and any historical plaintext before cutover;
migrate one reviewed connection at a time, reconcile external identities, then
retire legacy writers only after deployed clients and rollback evidence agree.

See [the provider boundary](PROVIDER_INTEGRATION_ARCHITECTURE.md),
[the environment guide](../backend/ENV_CONFIG_GUIDE.md), and
[the refactor risk register](REFACTOR_RISK_REGISTER.md).
