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

The ERP outbox now pins each item to its selected provider and processes only
matching due work below the attempt limit. Retryable failures receive a bounded
next attempt. Historical `failed` rows with `next_attempt_at = NULL` receive one
compatibility processing decision; new non-retryable or exhausted failures use
`failed_terminal` and are excluded from automatic selection. ERPNext classifies
authentication, validation, timeout, rate-limit, availability, and unexpected
response failures conservatively. In particular, an unknown outcome from a
side-effecting POST/upsert is terminal for automatic processing until an adapter
can prove provider-side idempotency. The outbox still requires an independent
worker, concurrency controls, and dead-letter/operator handling in Phase 13.

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

| Capability and owning module | Port | Phase 2 implementation status |
|---|---|---|
| Dataset object storage | `ObjectStorageProvider` | Existing S3-compatible behavior is isolated in `S3ObjectStorageProvider`; no Azure Blob adapter yet |
| Domain events and queue publication | `EventPublisher`, `QueuePublisher` | Contracts and explicit null event publisher only; no durable cloud queue adapter |
| Processing | `ProcessingProvider` | Port only; processing jobs and photogrammetry adapters belong to Phase 14 |
| Weather | `WeatherProvider` | Port only; provider integration belongs to Phase 15 |
| Satellite | `SatelliteProvider` | Port only; provider integration belongs to Phase 15 |
| Payments | `PaymentProvider` | Existing bank, Stripe, Multicaixa, and PayPal adapters have a normalized facade and lazy factory; the orchestrator accepts injected adapters; Phase 8 still owns lifecycle consolidation |
| ERP | `ERPProvider` | Existing mock and ERPNext adapters implement the boundary; mock is limited to local/dev/test; no Odoo adapter yet |
| Notifications | `NotificationProvider` | SMTP adapter and metadata-only local fallback are behind a lazy factory; deployed environments require SMTP with verified STARTTLS; durable delivery remains Phase 20 work |
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

`StorageService` preserves the existing tuple, boolean, dictionary, and byte
return shapes used by routers. Internally it consumes an injected
`ObjectStorageProvider`. Its default factory lazily imports the S3-compatible
adapter, while tests can pass a fake provider without importing `boto3`.

Object keys remain provider-independent application paths. The S3 factory
rejects a partial explicit access-key pair; when neither value is supplied it
uses the SDK credential chain. Existing local-file reads are retained for
compatibility, but failed writes do not fall back locally. Uploads are currently
buffered fully in process memory, and some legacy facade methods collapse
classified provider errors into boolean or `None` return shapes. Storage
cutover, immutable file identity, dual-read migration, streaming uploads, and
checksum verification remain Phase 12 work.

### ERP

ERP outbox processing accepts an injected `ERPProvider`. The existing mock and
ERPNext adapters return normalized integration results, while the legacy
`ErpResult.external_id` accessor remains available. The outbox stores the opaque
external reference separately from its own UUID and idempotency key and is
provider-pinned at enqueue time. Changing the configured provider does not move
old rows; operators must drain or reconcile those rows with their original
adapter. ERPNext sends the GeoVision idempotency key in a custom field, but
provider-side field availability and uniqueness must be configured and verified
before retries of uncertain writes can be considered safe. The typed
`ERPNEXT_WEBHOOK_SECRET` setting is reserved and is not consumed by a webhook
handler in Phase 2.

ERPNext remains the only current live ERP adapter. GeoVision continues to own
orders, assets, missions, intelligence, and customer experience. Odoo must be
added as another adapter and cut over explicitly in Phase 21.

### Payments

The legacy payment result and route shapes remain intact. Concrete bank,
Multicaixa, Stripe, and PayPal adapters are loaded by a payment factory, the
orchestrator accepts an explicit adapter map, and a normalized facade implements
the billing module's `PaymentProvider` port. Missing credentials may produce a
clearly simulated result only in local/dev/test; deployed environments return a
provider-not-configured failure instead of a mock payment. Provider readiness is
operation-specific: creation and webhook verification do not share identical
requirements. The bank adapter retains compatibility defaults and optional
overrides, but GeoVision does not validate those values against a live bank;
deployments must explicitly supply verified values. PayPal still lacks deployed
webhook verification and an API-backed refund path. Phase 8 owns these gaps,
the canonical payment lifecycle, reconciliation, and provider-qualified
reference constraints.

### Notifications and identity

Notifications and identity own their provider protocols. Identity now separates
the immutable GeoVision user UUID from issuer/subject external identities and
normalizes authorization context; canonical organization ownership remains
Phase 4 work. Notification delivery selects SMTP or the local
metadata-only fallback behind an adapter and fails closed when a deployed
environment lacks SMTP or verified STARTTLS. It does not implement implicit
SMTPS. The local fallback records recipient and subject in
`backend/email_log.txt`; those values can contain personal data and the file has
owner-only permissions and is Git-ignored, but has no application-managed
retention or rotation lifecycle. OAuth
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

Phase 2 does not implement cloud infrastructure, durable messaging, processing
jobs, satellite/weather ingestion, the Odoo cutover, a generic external-ID
table, payment lifecycle redesign, full legacy identity/session retirement, or
durable notification delivery. Credential-key rotation and notification-log
lifecycle management are also not provided. Those changes remain assigned to
their later playbook phases.
