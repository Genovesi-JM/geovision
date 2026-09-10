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
| GIS and asset management | `GISProvider`, `AssetManagementProvider` | Placeholder ports only |
| Construction systems | `ConstructionProvider` | Placeholder port only |
| Maritime systems | `MaritimeProvider` | Placeholder port only |

The words “port” and “adapter” describe code boundaries, not commercial or
operational readiness. A provider is live only after credentials, external
accounts, provider-specific verification, and the owning phase's release gates
have passed.

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
satellite/weather ingestion and the provider-neutral Odoo integration are now
implemented by their owning phases. Cloud infrastructure activation, live Odoo
and notification-provider cutovers, full legacy identity/session retirement,
credential-key rotation and notification-log lifecycle management remain
deferred to their documented human gates.
