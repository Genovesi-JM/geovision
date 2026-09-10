# GeoVision provider integration architecture

Phase 2 establishes provider-neutral boundaries around external systems while
keeping GeoVision's domain records and UUIDs authoritative. The backend remains
a modular monolith. Provider interfaces do not imply that a vendor is enabled,
production-ready, or deployed.

## Dependency direction

Provider ports belong to the domain that needs the capability. Concrete vendor
adapters live under `app/integrations`, and the application composition or a
compatibility service selects and injects them.

```text
HTTP or worker transport
        |
        v
domain service -> domain-owned provider port <- concrete adapter
        |                                      |
        v                                      v
GeoVision models and UUIDs                external provider
```

Domain modules must not read provider credentials, initialize vendor clients,
or import vendor SDKs. Adapter factories may read the typed settings object and
must import concrete SDK-backed adapters lazily so fake-provider tests remain
independent of vendor packages.

## Shared contracts

The provider-neutral primitives are deliberately small:

| Contract | Responsibility |
|---|---|
| `ExternalReference` | Associates an opaque provider reference with an existing GeoVision UUID without deriving either value from the other |
| `IntegrationResult[T]` | Normalizes provider, operation, status, optional value, optional external reference, safe failure details, and attempt count |
| `IntegrationStatus` | Distinguishes `succeeded`, `accepted`, `simulated`, `pending`, `retrying`, `not_configured`, and `failed` outcomes |
| `IntegrationFailure` | Carries a bounded safe message, stable code, retryability, and optional retry-after value |
| `IntegrationError` subclasses | Separate configuration, authentication, validation, timeout, unavailability, and rate-limit failures |
| `TimeoutPolicy` | Defines positive connect, read, write, and connection-pool timeout values |
| `RetryPolicy` | Applies bounded backoff and permits retry only for retryable failures and repeat-safe operations |
| `DomainEvent` and `QueueMessage` | Define immutable provider-neutral event and queue envelopes |

Failures returned or raised by an adapter must be safe to log. The sanitizer
removes common bearer tokens, credential assignments, URL user information,
line breaks, explicitly supplied secret values, and truncates messages. Raw
request headers and complete provider response bodies must not be logged.

Connector and Integration compatibility routes pass new API keys, secrets, and
webhook secrets through the canonical encryption helper. Staging and production
require a valid Fernet key at startup and the encryption runtime also fails
closed there. Local/dev retain an explicit warning-based plaintext compatibility
mode. Free-form metadata and endpoint/base/webhook URLs remain plaintext, so
secrets must never be embedded in them. Phase 2 does not guess at or rewrite
historical credential rows; any legacy plaintext migration requires a separate
inventory, backup, and verified cutover. The current single-key scheme also
requires an operator-owned backup and rotation procedure before key replacement.

## Retry and timeout convention

- Attempt counts include the first call.
- Retries are bounded by `INTEGRATION_RETRY_ATTEMPTS` and the configured maximum
  delay.
- Read-only/idempotent operations may retry a retryable failure.
- A side-effecting write may retry only when the adapter can prove the provider
  applies the idempotency key. Supplying a key in a request is not proof by
  itself.
- Configuration, authentication, and validation failures are not retryable.
- Timeout, temporary unavailability, and rate limiting are retryable; a
  provider retry-after value is honored only up to the configured delay cap.
- Each concrete adapter maps provider exceptions to a safe integration error or
  result instead of leaking the raw vendor exception into domain code.

The ERP outbox pins every command to the selected provider. The independent ERP
worker uses short leases, recovers expired claims, revalidates the resource and
payload, resolves the recorded provider, releases database locks before I/O, and
persists completion, a bounded due retry, or `dead_letter`. The legacy
`failed_terminal` state remains eligible only for the same explicit operator
requeue. The general `erp.sync_requested` event consumer performs no provider I/O;
the ERP worker emits canonical completion/failure facts after it persists the
outcome. Tenant-filtered status, command listing and reviewed requeue operations
are available under `/integrations/erp`.

ERPNext and Odoo classify authentication, validation, timeout, rate-limit,
availability, and unexpected-response failures into safe shared results. A
side-effecting retry is operationally safe only after the target provider's
idempotency constraint is proven: ERPNext uses its configured custom field, while
the Odoo bridge must enforce the stable `idempotency_key` atomically. Reconcile a
dead-lettered unknown outcome before requeue.

## External references and authoritative IDs

Provider-integrated aggregates keep their GeoVision UUID authoritative. Some
legacy records still use integer, semantic, or composite internal identifiers;
Phase 2 does not migrate them. Where the `ExternalReference` value object is
used, it contains:

- the existing GeoVision UUID;
- a normalized provider namespace;
- a normalized external resource type; and
- the provider's opaque reference value.

Provider values are never parsed to produce a GeoVision ID, and GeoVision IDs
are never replaced by provider values. Existing dedicated columns such as
`provider_user_id`, `provider_reference`, and the ERP outbox `external_id`
remain compatibility storage for their owning aggregate.

Phase 2 does not add a generic external-reference table. A polymorphic table
would not yet have stable workspace, provider-account, or generic Asset scoping.
The value object can wrap current fields now; an additive canonical mapping and
backfill can be considered after those ownership boundaries are established.

## Ports and implementation status

| Capability and owning module | Port | Current implementation status |
|---|---|---|
| Dataset object storage | `ObjectStorageProvider` | Private local, S3-compatible, and Azure Blob adapters implement provider-neutral streaming, signed URLs, stat/checksum, deletion, and object URI operations |
| Domain events and queue publication | `EventPublisher`, `QueuePublisher` | Transactional database outbox, idempotent consumers, independent worker, local delivery and Azure Service Bus/Event Grid adapters are implemented |
| Processing | `ProcessingProvider` | Durable job orchestration, deterministic fake and NodeODM adapter implement submit/status/cancel/output normalization; PIX4D, Autodesk and Bentley remain explicit unavailable scaffolds |
| Weather | `WeatherProvider` | Durable acquisition/observation workflow, deterministic fake and AEMET OpenData adapter are implemented; Azure Maps remains an explicit unavailable scaffold |
| Satellite | `SatelliteProvider` | Durable acquisition/scene workflow, deterministic fake and Copernicus Data Space STAC adapter are implemented, including optional bounded asset download |
| Payments | `PaymentProvider` | Existing bank, Stripe, Multicaixa, and PayPal adapters have a normalized facade and lazy factory; the orchestrator accepts injected adapters; Phase 8 still owns lifecycle consolidation |
| ERP | `ERPProvider` | Mock, ERPNext compatibility and Odoo 19 JSON-2 adapters implement the boundary; durable commands and external mappings remain GeoVision-owned; live Odoo requires Gate 17 |
| Notifications | `NotificationProvider`, `ExternalDeliveryProvider` | Contextual inbox and provider-pinned delivery rows are durable; SMTP, Azure Notification Hubs, ID-only local and unavailable adapters are selected lazily by an independent worker; live SMTP/APNs/FCM requires Gate 16 |
| Identity | `IdentityProvider` | Internal-session and strict Entra External ID API access-token adapters implement the boundary; Google/Microsoft browser callbacks remain compatibility routes during the documented cutover |
| AI narrative | `TextGenerationProvider` | Port declared; the existing OpenAI-compatible HTTP call and demo response remain a compatibility route rather than a completed adapter migration |
| GIS | `GISProvider` | A bounded public MITECO OGC API Features adapter and local contract fake implement the port; ArcGIS remains a fail-closed scaffold |
| Asset management | `AssetManagementProvider` | Typed and mapping-compatible synchronization requests use a required idempotency key; Seequent, generic mine-enterprise, SAP EAM, IBM Maximo, Dynamics 365 Asset Management, and customer-CMMS selections remain fail-closed scaffolds, with a deterministic local/test contract fake |
| Construction systems | `ConstructionProvider` | Autodesk APS, Procore, Bentley iTwin, and Trimble have fail-closed scaffolds plus a local contract fake |
| Maritime systems | `MaritimeProvider` | Typed and mapping-compatible context contract plus a deterministic local/test fake; MarineTraffic, Kpler, and Puertos del Estado are explicit fail-closed scaffolds with no live I/O |
| Customer-owned integration control plane | `IntegrationConnection` registry | Durable tenant/workspace/member scope, rollout flags, secret references, normalized sync runs/events, resilience state, health, audit and outbox events are implemented; only the deterministic local/test workflow is approved |

The words “port” and “adapter” describe code boundaries, not commercial or
operational readiness. A provider is live only after credentials, external
accounts, provider-specific verification, and the owning phase's release gates
have passed.

## Tenant connection registry and rollout control

Phase 32 adds a durable control plane around the four enterprise families:
construction, asset management, GIS and maritime. `IntegrationConnection`
retains the provider code, authoritative organization and optional
workspace/member scope, allowlisted capabilities, non-secret configuration,
canonical secret references, health and resilience state. Normalized sync runs
and events keep GeoVision resource UUIDs separate from opaque external
references and retain only a request digest rather than a raw payload. The
registry does not make any provider a system of record.

All administration routes are authenticated and use the canonical
authorization context. Read operations require `organization:read`; connection,
sync, health and rollout mutations require `organization:manage`. A selected
workspace is carried by `X-Workspace-ID`, and inaccessible tenant or member
scopes return a non-disclosing 404. Member connections are visible only to that
member. Shared organization connections still bind every run, event, retry and
idempotency key to the selected workspace. Mutable records use atomic
version-qualified writes. Responses expose
configured booleans and safe error codes for connections, never connection
settings, endpoints, secret references, resolved credentials or raw provider
responses. Flag projections may retain their non-secret Azure configuration
reference, ETag and configuration-version provenance.

Integration flags use the plural canonical name:

```text
geovision.integrations.<family>.<provider>
```

Resolution is member override, then workspace override, then the read-only
Azure App Configuration evaluator, then deny. The registry API independently
checks authorization, membership, a current integration-capable organization
subscription, connection lifecycle and the operation-specific capability; each
consuming product module must also enforce any narrower workspace/module
entitlement. A flag cannot grant any of them. Azure targeting uses only
canonical organization/workspace/user UUID keys. Cold-start failure denies
access, a failed refresh may use a bounded last-known-good snapshot, and an
expired snapshot denies access.

The Agriculture, Infrastructure, Environmental, Mining and Ports HTTP modules
consume their `geovision.sectors.<sector>` decision for the current workspace
member and combine it with their existing workspace/module gate. Local systems
with no configured rollout source preserve the established enabled-by-default
baseline; after Azure is configured, an unavailable or absent decision denies.
The evaluator accepts the provisioned store's mixed snapshot by selecting only
reviewed GeoVision feature-flag entries and ignoring unrelated configuration.

Credential and webhook fields accept only canonical Azure Key Vault HTTPS
references:

```text
https://<vault-name>.vault.azure.net/secrets/<secret-name>[/<version>]
```

The deployed factory uses managed identity for read-only App Configuration and
Key Vault access. The Azure template supplies the App Configuration endpoint
and the least-privilege data-reader/secrets-user roles. This is portable runtime
wiring, not proof that a customer flag, secret or provider account has been
verified. The registry never stores resolved secret values.
Registry-specific validation responses also remove rejected input, validator
context and attacker-controlled field names so malformed credential attempts
cannot be echoed to a client.

Only `fake` is enabled by the verified admin workflow, and deployed profiles
reject it. Every named provider stays disabled until the exact customer account,
credentials, sandbox, scopes, mapping, external idempotency behavior, rate and
licence terms, contract tests and release approval are recorded. Disconnecting
clears GeoVision's secret references and cancels pending work but preserves
completed sync and GeoVision-owned domain history; external credentials must be
revoked at the provider and vault as a separate operator action. See
[`INTEGRATION_CONNECTION_REGISTRY.md`](INTEGRATION_CONNECTION_REGISTRY.md) for
the API and operator runbook.

## Current adapters and compatibility facades

### Object storage

`StorageService` preserves legacy return shapes while canonical dataset
services consume an injected `ObjectStorageProvider`. The lazy factory selects
a private filesystem adapter in local/dev/test, an S3-compatible adapter, or an
Azure Blob adapter. Domain imports and fake-provider tests do not initialize a
vendor SDK.

Canonical object keys use organization, Asset, Acquisition/standalone,
dataset, area, immutable file ID, and safe filename segments. Backend uploads
stream and calculate MD5/SHA-256. Larger uploads use short-lived scoped URLs,
durable reservations, explicit confirmation, provider size/checksum evidence,
and a portable single-PUT ceiling. Azure deployment uses managed identity and
user-delegation SAS by default; master credentials stay server-side. Dataset
archive retains objects, while file deletion uses a recoverable intermediate
state and tombstone. Existing rows stay pinned to their provider, so a provider
cutover still requires copy/checksum/reference migration and rollback rather
than changing the default setting. See `docs/DATASET_STORAGE.md`.

### Satellite and weather intelligence

The monitoring module owns provider-neutral satellite search and weather
observation requests. Its services validate tenant-owned asset geometry,
persist every attempt, cache equivalent requests, register ordinary
Acquisition and Dataset records, and retain normalized source/time/provenance
metadata. Scheduled work uses claimed database records and the independent
intelligence worker; providers are injected at the router or worker composition
boundary.

The Copernicus adapter uses the public STAC search contract and normalizes
Sentinel scene time, cloud cover, resolution, bands, coverage and assets. Asset
downloads are disabled by default, size-bounded, restricted to an HTTPS host
allowlist and stored through `ObjectStorageProvider`; signed query material is
never persisted. The AEMET adapter follows the OpenData metadata-to-data URL
flow, restricts the second request to the configured AEMET host and selects the
nearest station within a configured radius. Azure Maps Weather is deliberately
unavailable until its commercial adapter is implemented. See
`docs/SATELLITE_WEATHER_INTELLIGENCE.md`.

### Official MITECO environmental GIS context

The MITECO adapter implements `GISProvider` against the Ministry's reviewed
[OGC API Features endpoint](https://www.miteco.gob.es/es/cartografia-y-sig/ide/directorio_datos_servicios/servicio-ogc-api.html).
It is a public-data adapter and needs no credentials. Its configured base URL is
nevertheless fixed to
`https://gis.miteco.gob.es/geoserver/ogc/features/v1`; validation rejects any
other origin or path, and the HTTP client rejects redirects.

The application exposes only collection keys listed in the reviewed MITECO
manifest. Callers cannot supply provider URLs or arbitrary GeoServer collection
IDs. A query must carry an authoritative GeoVision UUID, a CRS84 bounding box
intersecting Spain and a bounded feature limit. The adapter also bounds decoded
response bytes, property depth/node/string counts and geometry nesting; checks
content type, explicit CRS, feature count, coordinates and bboxes; and rejects
malformed GeoJSON as a normalized failure. It retries only repeat-safe GETs for
timeouts, transport errors, `429` and `5xx`, using the common capped backoff and
`Retry-After` policy. No live provider call is part of CI or readiness.

Successful results keep MITECO collection and feature identifiers as external
references. Collection and feature provenance includes the canonical source,
metadata record, protocol, query and response CRS, bbox, fetch and provider
timestamps, per-resource reuse conditions and reuse notice. It retains MITECO's
suggested attribution `Origen de los datos: Ministerio para la Transición
ecológica y el Reto Demográfico` and explicitly records that reuse cannot imply
endorsement. MITECO's
[reuse notice](https://www.datosabiertos.miteco.gob.es/es/aviso-legal.html)
permits commercial and noncommercial reuse subject to attribution,
update-metadata preservation, no distortion and no implied endorsement, while
disclaiming service continuity and data completeness/currentness.

Every normalized layer is explicitly `context_only`,
`measurements_authoritative=false` and `diagnostic_authority=false`. Official
context can support review but cannot by itself diagnose cause, replace a
GeoVision measurement or trigger an automatic conclusion. Copernicus satellite
and AEMET weather acquisition remain in their existing adapters and factories;
the MITECO implementation does not duplicate or proxy either client. Outside
Spain, MITECO returns a coverage mismatch while global providers can continue
independently.

### Asset-management scaffolds

`AssetManagementProvider` is a narrow cross-sector synchronization seam; it is
not a mining model, volume calculator, geology engine, safety assessment, or
system of record. `AssetSynchronizationRequest` keeps the authoritative
GeoVision UUID separate from an optional opaque provider reference. Writes
require a keyword-only idempotency key, and the receipt carries explicit
`measurements_authoritative=false`, `diagnostic_authority=false`, and
`context_only=true` limits. Legacy mapping requests remain accepted while new
composition code can use the typed request and receipt.

`ASSET_MANAGEMENT_PROVIDER` accepts `none`/`null`, local/test-only
`fake`/`deterministic`, `seequent`, `mine_enterprise`, `sap_eam`, `ibm_maximo`,
`dynamics_365_asset_management`, or `customer_cmms`. The deterministic fake
performs no network I/O and produces the same opaque external reference for the
same GeoVision UUID, asset kind, and idempotency key. It ignores caller-supplied
provider references and metadata when producing the receipt, so fixtures cannot
be mistaken for operational measurements or decisions. Both fake aliases fail
closed in staging and production, even when passed as a factory override.

Seequent is a named unavailable scaffold. `SEEQUENT_CLIENT_ID` and
`SEEQUENT_CLIENT_SECRET` are typed, redacted inputs used only to report whether
the pair is complete; missing credentials yield `provider_not_configured`, and
a complete pair still yields `adapter_unavailable`. The scaffold imports no
vendor SDK and performs no request. `mine_enterprise` is always unavailable
even though the Phase 32 registry can now record a concrete customer selection.
It still requires approved credentials, a sandbox, a reviewed authentication
and mapping contract, provider-side idempotency, and provider-specific tests;
the global factory deliberately invents no generic credential or endpoint
settings.

SAP EAM, IBM Maximo, Dynamics 365 Asset Management, and customer CMMS are also
named unavailable scaffolds. They use the existing typed, idempotent asset-sync
contract but perform no request and introduce no work-order persistence,
endpoint, SDK, or credential field. Their configuration is customer/workspace
specific. The durable secret-reference-only registry establishes tenant
ownership and lifecycle, but no live write may be implemented until the exact
provider account, approved sandbox, authentication method, field mapping and
provider-side idempotency behavior are verified.

Existing capability boundaries remain authoritative: Bentley iTwin project
synchronization stays behind `ConstructionProvider`, Bentley Reality Modeling
stays behind `ProcessingProvider`, and ArcGIS plus MITECO stay behind
`GISProvider`. The asset-management factory rejects those provider names rather
than duplicating their clients or implying interchangeable capabilities. No
generic polymorphic domain-reference table or enterprise work-order model is
introduced; Phase 32 sync events record only normalized resource UUIDs and
opaque external references within one connection ledger.

### Maritime context scaffolds

`MaritimeProvider` accepts a typed `MaritimeContextRequest` or a legacy mapping
and returns a normalized `MaritimeContextResult`. Each reading explicitly keeps
its opaque provider reference, UTC-valid time, station reference, latitude and
longitude, metric, value, unit, quality, source, source kind, licence,
attribution, and provenance. `MaritimeSourceKind` keeps observed, model,
forecast, and AIS values distinct. Every result is `context_only=true`,
`measurements_authoritative=false`, `navigation_authority=false`, and
`diagnostic_authority=false`.

`MARITIME_PROVIDER` accepts `none`/`null`, local/test-only
`fake`/`deterministic`, `marinetraffic`, `kpler`, or `puertos_del_estado`. The
deterministic fixture validates the GeoVision UUID, coordinate bounds, time
window, search radius, and result limit. It returns fixed simulated observed
and model readings with a deterministic opaque reference; it does not represent
AIS, oceanographic, operational, or safety truth. Deployed profiles reject both
fixture names even when a factory override requests one.

MarineTraffic and Kpler selections return `provider_not_configured`. API
entitlement, customer scope, rate terms, authentication, a sandbox, and the
per-workspace registry selection must all be approved before a live adapter
exists. Creating the registry row alone leaves the provider blocked.
No global API-key field is provided. AIS is supplementary context and must never
be used as collision-avoidance, navigation, port-control, security, or safety
authority.

Puertos del Estado exposes valuable measured and modelled oceanographic context
through Portus and Portuscopia, but its
[official oceanography FAQ](https://www.puertos.es/servicios/oceanografia/faqs)
states that downloaded data are authorized only for the specific download
purpose and may not be transferred to third parties. A GeoVision customer SaaS
display, cache, or derived alert therefore requires written permission and a
reviewed HTTPS access contract. The scaffold performs no network request and
returns `authorization_terms_not_approved`; free download availability is not
treated as redistribution permission. If permission is later granted, the live
adapter must preserve observed versus model semantics, UTC timestamps, station
and vertical-datum metadata, quality flags, attribution, licence/reuse terms,
update times, spatial applicability, and source-specific warnings.

AEMET weather, Copernicus satellite, and MITECO GIS remain in their existing
ports, factories, and provenance models. The maritime package imports none of
those clients and does not proxy or duplicate them. `safe_summary()` reports the
selected maritime name while keeping `configured.maritime=false`, because no
live maritime connectivity is available in this phase.

### ERP

The independent ERP worker claims and revalidates provider-pinned commands using
short transactions, performs provider I/O without a database lock, and persists
bounded retry or dead-letter state afterwards. It accepts an injected
`ERPProvider`. The mock, ERPNext and Odoo 19 JSON-2 adapters return normalized
integration results, while the legacy
`ErpResult.external_id` accessor remains available. The outbox stores the opaque
external reference separately from its own UUID and idempotency key and is
provider-pinned at enqueue time. Changing the configured provider does not move
old rows; operators must drain or reconcile those rows with their original
adapter. ERPNext sends the GeoVision idempotency key in a custom field, but
provider-side field availability and uniqueness must be configured and verified
before retries of uncertain writes can be considered safe. The typed legacy
`ERPNEXT_WEBHOOK_SECRET` remains reserved and is not consumed by a handler.

The Odoo adapter calls only the configured
`geovision.integration.bridge.sync_from_geovision` method through Odoo 19
JSON-2. It sends canonical resource values and a stable idempotency key; neither
events nor customer input can choose arbitrary Odoo models/methods. A provider
response creates or updates the local `erp_external_references` projection while
the GeoVision UUID remains authoritative. A callback authenticated with
`ODOO_WEBHOOK_SECRET`, a five-minute replay window and a unique event receipt can
update only allowlisted invoice, stock and purchase status fields on a matching
mapping. The raw callback body is represented by its digest, not persisted.

GeoVision continues to own identities, orders, assets, missions, intelligence
and customer experience. Live Odoo needs a Custom plan, an installed reviewed
bridge addon, least-privilege bot/key, callback signer and
[Gate 17](../HUMAN_GATES.md#17-odoo-19-live-erpcrm-activation). See
[the Odoo 19 contract and runbook](ODOO_19_INTEGRATION.md).

### Payments

The legacy payment result and route shapes remain intact. Concrete bank,
Multicaixa, Stripe, and PayPal adapters are loaded by a payment factory and are
normalized before every live create, status, refund, or webhook-verification
operation uses the billing module's `PaymentProvider` port. Missing credentials
may produce a clearly simulated result only in local/dev/test; deployed
environments return a provider-not-configured failure instead of a mock payment.
Provider readiness is operation-specific: creation and webhook verification do
not share identical requirements. The bank adapter retains compatibility
defaults and optional overrides, but GeoVision does not validate those values
against a live bank; deployments must explicitly supply verified values. PayPal
still lacks deployed webhook verification and an API-backed refund path, so
those capabilities remain unavailable rather than simulated when deployed.

Phase 8 binds idempotency keys to an immutable tenant/order/amount/currency/
provider tuple, derives public payment requests from the GeoVision-owned order,
and records verified callbacks in a raw-payload-free digest ledger. Payment
state is separate from fulfilment state and provider references never replace a
GeoVision UUID. See `docs/ORDER_PAYMENT_LIFECYCLE.md` for transition and rollback
details.

### Notifications and identity

Notifications and identity own their provider protocols. Identity now separates
the immutable GeoVision user UUID from issuer/subject external identities and
normalizes authorization context; canonical organization ownership remains
Phase 4 work. Durable notification delivery pins a channel/provider to each
queue row, then the independent worker selects SMTP, Azure Notification Hubs,
an ID-only local sink, or an unavailable adapter. Deployed SMTP fails closed
without complete configuration and verified STARTTLS; it does not implement
implicit SMTPS. Azure push uses a template payload containing only the
GeoVision notification ID, and target navigation is reauthorized by the API.
The client-supplied APNs/FCM token is encrypted and digest-checked. The delivery
worker decrypts it only at the adapter boundary; the Azure adapter idempotently
creates or updates the installation and its platform template before the
opaque-installation targeted send. Flutter supplies a fail-closed method/event
channel boundary, while signed iOS/Android host handlers and live platform
configuration remain Gate 16 work.

The new local delivery sink records only delivery/notification IDs and channel
in `backend/notification_delivery_log.txt`. The older compatibility fallback
records recipient and subject in `backend/email_log.txt`; those values can
contain personal data and that file has owner-only permissions and is
Git-ignored. Neither file has application-managed retention or rotation, and
neither is allowed as a deployed provider. OAuth
callbacks must still be described as compatibility behavior, not as proof of a
complete identity-provider implementation.

### Enterprise construction and GIS scaffolds

Phase 28 makes the existing `ConstructionProvider` and `GISProvider` seams
selectable without representing any vendor as connected. Construction supports
the stable provider names `autodesk_aps`, `procore`, `bentley_itwin`, and
`trimble`; GIS supports `arcgis`. Each named vendor resolves to an explicit,
contract-correct unavailable adapter. With no credentials it returns
`provider_not_configured`; with a complete client-ID/client-secret pair it still
returns `adapter_unavailable`, because credentials alone do not prove tenant
consent, product entitlement, project scope, API compatibility, or live access.
No scaffold performs network I/O or imports a vendor SDK.

Local and test profiles may select `fake`. The deterministic fakes validate an
authoritative GeoVision UUID and return `simulated` results with opaque vendor
values held only in `ExternalReference`. They do not produce progress,
measurement, schedule, BIM, or GIS truth. Deployed profiles reject fake
selection, and factory overrides also fail closed there.

Construction synchronization requires an idempotency key at the port boundary.
This makes the side-effecting nature explicit, but a future live adapter must
still prove provider-side deduplication before retrying an uncertain write. GIS
layer queries are read-only. Both scaffold families carry the shared
`TimeoutPolicy`; no retry is attempted while adapters are unavailable.

The optional credential fields are server-side and redacted from settings
representations and safe diagnostics. Factories reduce them to a boolean and do
not retain the values. External provider project, model, hub, and layer IDs are
data references, not configuration or GeoVision identities. Phase 28 adds no
generic provider/reference persistence. Phase 32 later adds a tenant-scoped
connection and sync ledger, but deliberately does not turn opaque provider
values into GeoVision identities or backfill the legacy connector tables.

A live adapter requires a real customer account and sandbox, reviewed OAuth
scopes and callback flow, verified tenant/project authorization, vendor-specific
contract tests, rate-limit/error classification, and a release gate. Until all
of those exist, `/health`, `/ready`, credential-completeness flags, and provider
selection must not be described as connectivity checks.

## Adding an adapter

1. Use the port owned by the relevant common domain; extend it only when the
   capability genuinely requires another domain operation.
2. Put the concrete implementation in `app/integrations`, with vendor imports
   isolated to that adapter module.
3. Add typed, redacted settings in `app/core/config.py`; never read credentials
   in a domain service or router.
4. Map timeouts, responses, failures, and external references into the shared
   integration contracts. Classify uncertain side-effecting outcomes as
   terminal unless provider-side deduplication is demonstrably enforced.
5. Select the adapter in a lazy factory or the application composition root.
6. Test the consuming service with a fake that structurally satisfies the port,
   without importing the vendor SDK.
7. Add provider-specific contract tests and live verification gates before
   describing the adapter as active.

## Deferred work

The initial Phase 2 boundary did not implement these later capabilities.
Durable messaging, processing jobs, payment lifecycle consolidation,
satellite/weather ingestion, the provider-neutral Odoo integration, and the
tenant integration registry are now implemented by their owning phases. Live
named enterprise adapters, customer credential/sandbox verification, production
App Configuration and Key Vault smoke tests, full legacy identity/session
retirement, credential-key rotation and notification-log lifecycle management
remain deferred to their documented human gates.
