# GeoVision backend configuration guide

GeoVision loads backend configuration through the typed `Settings` class in
`app/core/config.py`. Application and adapter code should read that settings
object or receive an injected provider; it should not read credentials directly
from the process environment.

For local development, copy `.env.example` to `.env` inside `backend`. The real
file is ignored by Git. In staging and production, set the same variables in the
deployment platform and store sensitive values in its secret manager rather
than in a checked-in environment file.

## Runtime profiles

Set `ENV` to one of the following canonical values. `ENVIRONMENT` remains an
accepted compatibility alias.

| Value | Intended use | Security behavior |
|---|---|---|
| `local` | A developer workstation | An insecure or missing JWT key is replaced with an ephemeral key; fake providers may be used |
| `dev` | Shared development | Same startup tolerance as local; use stable secrets when sessions must survive restarts |
| `test` | Automated tests | Isolated databases and injected fake providers are expected |
| `staging` | Production-like verification | Startup requires a 32+ character `SECRET_KEY` that does not match a known placeholder and a valid Fernet `ENCRYPTION_KEY`; mock ERP is refused when the ERP adapter is resolved |
| `prod` | Live deployment | Same signing/encryption startup requirements as staging; structural identity configuration is checked at startup, while most other provider readiness is checked when used |

The aliases `development`, `testing`, `stage`, and `production` normalize to
their corresponding canonical values. Any other value fails validation. If
both `ENV` and `ENVIRONMENT` are present, they must resolve to the same profile
or startup fails rather than silently choosing weaker safeguards.

## Base configuration

```dotenv
ENV=local
APP_NAME=GeoVision Backend
APP_VERSION=1.0.0
PORT=8010
MIGRATE_TIMEOUT_SECONDS=120

BACKEND_BASE=http://127.0.0.1:8010
FRONTEND_BASE=http://127.0.0.1:8001
CORS_ORIGINS=http://127.0.0.1:8001,http://localhost:8001
TRUSTED_PROXY_CIDRS=

DATABASE_URL=sqlite:///./geovision.db
ACCOUNTS_DATABASE_URL=sqlite:///./accounts.db
```

`MIGRATE_TIMEOUT` remains an alias for `MIGRATE_TIMEOUT_SECONDS`. Legacy
`postgres://` database URLs are normalized to SQLAlchemy's `postgresql://`
scheme. Database URLs are treated as sensitive in configuration diagnostics.
In staging and production, `BACKEND_BASE` and `FRONTEND_BASE` must be absolute
HTTPS URLs with a host and no userinfo, query string, or fragment. Use the
dedicated GeoVision origin rather than a shared static-host origin for the
authenticated portal.

`TRUSTED_PROXY_CIDRS` is a comma-separated list of exact ingress IP networks
that are allowed to supply `X-Forwarded-For`. It defaults to empty, so a direct
caller cannot forge a new rate-limit identity with that header. Configure only
verified platform ingress networks and keep the application unreachable around
that edge. The built-in limiter is bounded but per process; multiple workers or
instances require a shared production limiter such as Redis.

## Secrets and authentication

```dotenv
SECRET_KEY=CHANGE_ME
ENCRYPTION_KEY=
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRES_MINUTES=60
REFRESH_TOKEN_EXPIRES_DAYS=30
ADMIN_PASSWORD=
ADMIN_EMAILS=

IDENTITY_PROVIDER=internal
IDENTITY_AUTO_LINK_VERIFIED_EMAIL=false
INTERNAL_TOKEN_ISSUER=geovision
INTERNAL_TOKEN_AUDIENCE=geovision-api
ACCEPT_LEGACY_ACCESS_TOKENS=true
EXTERNAL_IDENTITY_SESSION_MAX_HOURS=24
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
MICROSOFT_CLIENT_ID=
MICROSOFT_CLIENT_SECRET=
MICROSOFT_TENANT_ID=common
ENTRA_EXTERNAL_ID_ISSUER=
ENTRA_EXTERNAL_ID_AUDIENCE=
ENTRA_EXTERNAL_ID_TENANT_ID=
ENTRA_EXTERNAL_ID_DISCOVERY_URL=
ENTRA_EXTERNAL_ID_REQUIRED_SCOPE=access_as_user
ENTRA_EXTERNAL_ID_AUTHORIZED_PARTY=
ENTRA_EXTERNAL_ID_CLOCK_SKEW_SECONDS=60
ENTRA_EXTERNAL_ID_JWKS_CACHE_SECONDS=3600
```

`ENCRYPTION_KEY` must be a URL-safe base64 Fernet key when `ENV` is `staging`
or `prod`. `IDENTITY_PROVIDER` accepts `internal`, `transition`, or
`entra_external_id`. Google and Microsoft OAuth continue through compatibility
browser routes when configured; their settings do not configure the strict Entra
External ID API access-token adapter. OAuth callback URLs are derived from
`BACKEND_BASE`; the older `GOOGLE_REDIRECT_URI` variable is not consumed.
When legacy Microsoft browser credentials remain enabled in any deployed
profile, `MICROSOFT_TENANT_ID` must be the approved tenant UUID; generic
`common`, `organizations`, and `consumers` selectors are rejected.
`ENTRA_EXTERNAL_ID_TENANT_ID` does not constrain that legacy Microsoft Graph
callback.

In deployed profiles, `ADMIN_EMAILS` and `ADMIN_PASSWORD` are an all-or-nothing
bootstrap pair. The password must contain at least 12 characters and at most 72
UTF-8 bytes; the seed path enforces the same rule before hashing.

`EXTERNAL_IDENTITY_SESSION_MAX_HOURS` is the absolute refresh-family lifetime
for sessions originating at an external provider. Rotation never extends it,
and refreshed access tokens are clamped to the same deadline. The default is 24
hours; lower it only with a tested client reauthentication experience.

Entra issuer, audience, and tenant ID must be configured together, and all are
required when Entra is selected. The adapter accepts delegated version 2 access
tokens for the GeoVision API only, never ID tokens or Microsoft Graph tokens.
Startup rejects known Microsoft Graph audiences and Graph scopes such as
`User.Read`; the adapter then requires the configured GeoVision scope and, when
set, exact authorized party. Keep
verified-email auto-linking disabled unless a separately approved linking policy
exists. `ADMIN_EMAILS` is a legacy local authorization list, not an Entra role
mapping. See [`docs/IDENTITY_PROVIDER_ARCHITECTURE.md`](../docs/IDENTITY_PROVIDER_ARCHITECTURE.md)
and [`docs/ENTRA_CUTOVER_RUNBOOK.md`](../docs/ENTRA_CUTOVER_RUNBOOK.md).

The deployed `SECRET_KEY` guard checks minimum length and known placeholder
markers; it does not measure entropy. Generate a random high-entropy value and
keep it stable for the intended token lifetime. `ALGORITHM` remains configurable
for compatibility but should remain `HS256` unless a separately tested token
migration changes both signing and verification.

Current Connector and Integration credential writes call the canonical
encryption helper for their explicit API-key, API-secret, and webhook-secret
fields. Free-form connector metadata and URL fields are not encrypted: never put
passwords, tokens, signed query strings, or other credentials in `metadata`,
`base_url`, or `webhook_url`. Without a usable key, local/dev compatibility
stores an explicit `plain:` value and emits a warning, so do not use real
connector credentials in those profiles unless encryption is configured.
Staging/prod validate the key at startup, and the encryption helper also refuses
plaintext fallback at runtime in a deployed profile.

Keep the deployed Fernet key backed up and stable. The current helper supports
one key, not a key ring: rotating or losing it can make existing ciphertext
undecryptable, and the legacy compatibility reader may return an undecryptable
value unchanged. Rotation therefore requires an inventory, backup, verified
decrypt/re-encrypt procedure, and rollback plan. Historical rows are not
rewritten automatically and require the same audited treatment if plaintext
values exist.

## Integration policy

The common policy establishes bounded per-provider timeouts and retry limits.
It does not make every operation safe to retry. A side-effecting operation may
be retried only when it carries an idempotency key.

```dotenv
INTEGRATION_CONNECT_TIMEOUT_SECONDS=5
INTEGRATION_READ_TIMEOUT_SECONDS=30
INTEGRATION_RETRY_ATTEMPTS=3
INTEGRATION_RETRY_INITIAL_SECONDS=0.5
INTEGRATION_RETRY_MAX_SECONDS=8
```

`INTEGRATION_RETRY_ATTEMPTS` includes the first attempt. Retry delays use
bounded exponential backoff. ERP provider calls retain this policy; the general
event worker has its own bounded claim/retry/dead-letter settings documented in
[`docs/DURABLE_EVENTS.md`](../docs/DURABLE_EVENTS.md).

## Provider selection

These variables declare the intended provider capability without exposing its
credentials to domain modules:

```dotenv
IDENTITY_PROVIDER=internal
OBJECT_STORAGE_PROVIDER=local
QUEUE_PROVIDER=database
IOT_CLOUD_PROVIDER=none
PROCESSING_PROVIDER=none
WEATHER_PROVIDER=none
SATELLITE_PROVIDER=none
ERP_PROVIDER=mock
NOTIFICATION_PROVIDER=auto
GIS_PROVIDER=none
CONSTRUCTION_PROVIDER=none
ASSET_MANAGEMENT_PROVIDER=none
MARITIME_PROVIDER=none
```

`OBJECT_STORAGE_PROVIDER`, `ERP_PROVIDER`, `NOTIFICATION_PROVIDER`,
`IDENTITY_PROVIDER`, `QUEUE_PROVIDER`, `PROCESSING_PROVIDER`,
`WEATHER_PROVIDER`, `SATELLITE_PROVIDER`, and `IOT_CLOUD_PROVIDER` drive
provider boundaries. Queue
delivery accepts `database`, test-only `in_memory`, `azure_service_bus`, or the
local-only fail-closed `null` adapter. Identity accepts `internal`,
`transition`, or `entra_external_id`; the latter two require a complete, valid
Entra configuration at startup and control the external-token exchange boundary.
Business API routes still accept only GeoVision internal sessions. Payment
methods use their own per-method factory rather than one selector. Processing
accepts `none`, local/test `fake`, or `nodeodm`; PIX4D, Autodesk Reality Capture,
and Bentley Reality Modeling names deliberately resolve to explicit unavailable
scaffolds until their adapters are implemented and approved. Satellite accepts
`none`, local/test `fake`, or `copernicus`. Weather accepts `none`, local/test
`fake`, or `aemet`; Azure Maps provider names resolve to an explicit unavailable
scaffold. GIS, construction, asset-management, and maritime remain reserved seams.

In addition to the signing and encryption guards, identity, processing,
satellite and weather selector structure is validated when settings load;
selecting AEMET also requires its API key. Most other credential completeness
is validated when a factory or provider operation is invoked, not when FastAPI
starts. Health/readiness therefore does not prove that discovery/JWKS, ERP,
storage, notifications, payments, Copernicus, AEMET, or another external
account can complete a live request.

## Satellite and weather intelligence

Satellite and weather requests are tenant-scoped, cached and recorded as
durable intelligence acquisitions. Successful results create normal
Acquisition/Dataset records plus normalized scene or observation records with
source, acquisition/observation time and provenance. Weekly schedules use the
same services through the independent worker.

```dotenv
SATELLITE_PROVIDER=none
WEATHER_PROVIDER=none
INTELLIGENCE_WORKER_IN_PROCESS=false
INTELLIGENCE_WORKER_POLL_SECONDS=30
INTELLIGENCE_WORKER_BATCH_SIZE=10
INTELLIGENCE_WORKER_CLAIM_TIMEOUT_SECONDS=600
INTELLIGENCE_MAX_ATTEMPTS=3
INTELLIGENCE_RETRY_INITIAL_SECONDS=30
INTELLIGENCE_RETRY_MAX_SECONDS=3600
SATELLITE_CACHE_TTL_SECONDS=21600
WEATHER_CACHE_TTL_SECONDS=1800
SATELLITE_DEFAULT_COLLECTION=sentinel-2-l2a
SATELLITE_DEFAULT_LOOKBACK_DAYS=14
SATELLITE_DEFAULT_MAX_CLOUD_COVER_PERCENT=60
SATELLITE_MAX_SCENES_PER_REQUEST=20
SATELLITE_DOWNLOAD_ASSETS_ENABLED=false
SATELLITE_DOWNLOAD_ASSET_KEYS=thumbnail
SATELLITE_MAX_ASSET_BYTES=268435456
COPERNICUS_STAC_BASE_URL=https://stac.dataspace.copernicus.eu/v1
COPERNICUS_ACCESS_TOKEN=
COPERNICUS_ALLOWED_DOWNLOAD_HOSTS=download.dataspace.copernicus.eu,datahub.creodias.eu
WEATHER_DEFAULT_LOOKBACK_HOURS=12
AEMET_BASE_URL=https://opendata.aemet.es/opendata
AEMET_API_KEY=
AEMET_MAX_STATION_DISTANCE_KM=150
```

For a dependency-free local demonstration, select both `fake` providers and
run `python -m app.workers.intelligence_worker`. Fake providers are rejected in
staging/production. AEMET requires a key when selected. Copernicus catalogue
searches can be public, while protected asset downloads may require the
redacted `COPERNICUS_ACCESS_TOKEN`. Downloads are disabled by default and
restricted to the configured HTTPS host allowlist and maximum size. Run the
live activation gate before enabling either provider in production. See
[`docs/SATELLITE_WEATHER_INTELLIGENCE.md`](../docs/SATELLITE_WEATHER_INTELLIGENCE.md).

## Photogrammetry processing

Processing jobs are durable PostgreSQL records. API requests only enqueue work;
the independent worker validates source images, submits to the pinned provider,
polls status, quality-checks results, stores each output through the configured
object-storage adapter, and registers normal Dataset records.

```dotenv
PROCESSING_PROVIDER=none
PROCESSING_AUTO_CREATE_ENABLED=false
PROCESSING_DEFAULT_OUTPUTS=ORTHOMOSAIC,DSM,POINT_CLOUD
PROCESSING_WORKER_IN_PROCESS=false
PROCESSING_WORKER_POLL_SECONDS=5
PROCESSING_WORKER_BATCH_SIZE=5
PROCESSING_WORKER_CLAIM_TIMEOUT_SECONDS=1800
PROCESSING_DEFAULT_MAX_RETRIES=3
PROCESSING_RETRY_INITIAL_SECONDS=10
PROCESSING_RETRY_MAX_SECONDS=900
PROCESSING_MINIMUM_IMAGES=2
PROCESSING_MAX_INPUT_BYTES=1073741824
PROCESSING_MAX_OUTPUT_ARCHIVE_BYTES=1073741824
PROCESSING_MAX_OUTPUT_UNPACKED_BYTES=2147483648
PROCESSING_MAX_OUTPUT_FILES=500
PROCESSING_PROVIDER_READ_TIMEOUT_SECONDS=300
PROCESSING_PROVIDER_WRITE_TIMEOUT_SECONDS=3600
NODEODM_BASE_URL=
NODEODM_TOKEN=
```

For a dependency-free local demonstration use `PROCESSING_PROVIDER=fake` and
run `python -m app.workers.processing_worker`. To create jobs automatically
after raw imagery is finalized, also set `PROCESSING_AUTO_CREATE_ENABLED=true`
and run `python -m app.workers.event_worker`. The fake provider is rejected for
automatic processing in staging/production. NodeODM requires an absolute URL;
deployed profiles require HTTPS. `NODEODM_TOKEN` is redacted from all settings
representations. See [`docs/PROCESSING_JOBS.md`](../docs/PROCESSING_JOBS.md).

## Object storage

Canonical datasets use private local filesystem, S3-compatible, or Azure Blob
adapters behind `ObjectStorageProvider`. Local is the default only for
local/dev/test and is rejected when resolved in a deployed runtime.

```dotenv
OBJECT_STORAGE_PROVIDER=local
LOCAL_STORAGE_ROOT=./data/object-storage
DATASET_DIRECT_UPLOAD_MAX_BYTES=524288000
DATASET_SIGNED_UPLOAD_MAX_BYTES=4294967296
DATASET_SIGNED_URL_EXPIRY_SECONDS=900
```

S3-compatible storage supports AWS S3 and endpoints such as MinIO or R2:

```dotenv
OBJECT_STORAGE_PROVIDER=s3
S3_BUCKET=geovision-datasets
S3_REGION=eu-west-1
S3_ENDPOINT_URL=
S3_ACCESS_KEY_ID=
S3_SECRET_ACCESS_KEY=
```

`AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` remain accepted aliases. When
explicit keys are absent, the S3 SDK may use its normal credential chain. If one
explicit key is supplied without the other, provider creation fails instead of
silently falling back to that chain.

Azure Blob is selected independently:

```dotenv
OBJECT_STORAGE_PROVIDER=azure_blob
AZURE_STORAGE_ACCOUNT_URL=https://example.blob.core.windows.net
AZURE_STORAGE_CONTAINER=geovision-datasets
AZURE_MANAGED_IDENTITY_CLIENT_ID=
AZURE_STORAGE_CONNECTION_STRING=
AZURE_STORAGE_ACCOUNT_NAME=
AZURE_STORAGE_ACCOUNT_KEY=
```

Staging/production uses managed identity when no account key is configured.
Account keys and account-key connection strings are intended for controlled
local integration testing and are redacted from settings diagnostics. The
factory rejects incomplete explicit name/key credentials. Dataset uploads
stream, or use short-lived scoped URLs with durable reservations and explicit
completion. Existing object rows remain pinned to their original provider; a
provider change requires a staged copy/checksum/reference migration rather than
a settings-only switch. See `docs/DATASET_STORAGE.md` for the object-key,
authorization, deletion, and rollback contracts.

## ERP

GeoVision remains the system of record. The existing ERPNext adapter consumes
the provider-neutral ERP port and the local integration outbox remains the
idempotency boundary.

Local development and tests may use:

```dotenv
ERP_PROVIDER=mock
```

To select the existing ERPNext adapter, configure its required outbound values:

```dotenv
ERP_PROVIDER=erpnext
ERPNEXT_BASE_URL=https://erp.example.invalid
ERPNEXT_API_KEY=
ERPNEXT_API_SECRET=
```

`ERPNEXT_WEBHOOK_SECRET` is a reserved typed setting for a future inbound webhook
flow; Phase 2 does not consume it and setting it does not enable webhook
verification.

Every new outbox row records its selected provider, and processing selects only
rows pinned to the provider being run. A provider change therefore does not
silently reroute new or pending rows. Before a cutover, drain or explicitly
reconcile work pinned to the old provider. For compatibility, a legacy row with
`status="failed"` and `next_attempt_at=NULL` receives one processing decision:
success completes it, a retryable failure receives a due time, and a
non-retryable or exhausted failure becomes `failed_terminal`. New terminal
failures also use `failed_terminal` and are not selected again automatically.

The local outbox and unique idempotency key prevent duplicate GeoVision queue
rows, but they do not alone guarantee exactly-once behavior in ERPNext. The
adapter sends `custom_geovision_idempotency_key`; the ERPNext deployment must
provide and enforce a suitable custom field or other provider-side deduplication.
An unknown outcome from the side-effecting POST/upsert is terminal for manual
reconciliation unless an adapter can prove provider-side idempotency. The mock
ERP adapter is rejected in staging and production when the adapter is resolved,
not at application startup. Odoo is not active; its implementation and controlled
cutover remain Phase 21 work.

## Notifications

The notification port and message contract are provider-neutral. `auto` selects
SMTP when it is configured, writes the recipient and subject only to the local
file fallback in local/dev/test, and returns an unconfigured result in
staging/prod when SMTP is unavailable. Message bodies and reset tokens are not
written, but recipient addresses and subjects can still contain personal or
operational information. The default `backend/email_log.txt` file is Git-ignored
and created with owner-only permissions, but it is not rotated or removed by the
application. Restrict access and remove it when no longer needed.

```dotenv
NOTIFICATION_PROVIDER=auto
SMTP_HOST=
SMTP_PORT=25
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=
SMTP_USE_TLS=true
SMTP_TIMEOUT_SECONDS=15
```

The legacy aliases `MAIL_HOST`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`,
and `MAIL_FROM` remain accepted. Selecting `file`, `log`, or `local_file` is
also refused in staging/prod. Deployed SMTP also refuses `SMTP_USE_TLS=false`.
When enabled, this adapter uses STARTTLS with the platform's default certificate
verification; it does not implement implicit TLS/SMTPS. The TLS handshake is
verified when a message is sent, not during application startup. Push providers
and durable delivery belong to Phase 20.

## Payments

Payment configuration is typed centrally, while Phase 8 remains responsible
for completing the normalized payment lifecycle. Bank transfer is the existing
manual settlement path. Provider creation readiness and webhook readiness are
separate: Multicaixa creation requires merchant ID plus API key; Stripe creation
requires its secret key; their deployed webhook endpoints additionally require
their webhook secrets. Local/dev webhook-secret absence is compatibility behavior
that accepts any supplied signature, so never expose such a runtime as a shared
or public payment endpoint.

PayPal creation requires client ID plus secret, but a local/dev token failure can
fall back to a clearly marked simulation. Deployed PayPal webhook verification
and API refunds are not implemented; refunds remain a dashboard/manual operation.
None of these interfaces alone proves a provider is live.

```dotenv
MULTICAIXA_API_URL=https://api.multicaixa.co.ao/v1
MULTICAIXA_MERCHANT_ID=
MULTICAIXA_API_KEY=
MULTICAIXA_WEBHOOK_SECRET=
MULTICAIXA_CALLBACK_URL=

STRIPE_SECRET_KEY=
STRIPE_PUBLISHABLE_KEY=
STRIPE_WEBHOOK_SECRET=

PAYPAL_CLIENT_ID=
PAYPAL_SECRET=
PAYPAL_MODE=sandbox
PAYPAL_RETURN_URL=http://127.0.0.1:8001/loja.html?paypal=success
PAYPAL_CANCEL_URL=http://127.0.0.1:8001/loja.html?paypal=cancel
```

Bank destination fields are also available as `COMPANY_IBAN`, `COMPANY_BIC`,
`COMPANY_BANK_NAME`, `COMPANY_IBAN_INTL`, `COMPANY_BIC_INTL`, and
`COMPANY_BANK_INTL`. Non-empty built-in values remain for compatibility and are
not validated as a live beneficiary. Override every applicable field with
approved deployment values before enabling bank transfer; application startup
does not enforce this replacement. Supply them through managed configuration
rather than adding real bank details to examples.

## GAIA

```dotenv
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
```

Without an API key, the existing context-aware demo response remains active.
The model explains structured GeoVision context and is not a source of measured
values.

## Report narrative

```dotenv
REPORT_NARRATIVE_PROVIDER=deterministic
REPORT_NARRATIVE_MODEL=
```

`deterministic` is the production-safe offline default. `mock` selects the same
behavior for tests. `azure_openai` and `openai` currently select an explicit
unavailable boundary, causing a recorded deterministic fallback; they do not
reuse generic GAIA credentials or imply that customer report data may be sent
externally. Gate 15 must approve a dedicated server-side adapter, model access,
privacy controls and evaluation before either external selection is activated.

## IoT and MQTT

MQTT is opt-in. The default web application and tests do not require a broker.

```dotenv
MQTT_ENABLED=false
MQTT_HOST=127.0.0.1
MQTT_PORT=1883
MQTT_USERNAME=
MQTT_PASSWORD=
MQTT_TLS=false
MQTT_TOPIC_PREFIX=geovision
MQTT_CLIENT_ID=geovision-backend
IOT_WATCHDOG_IN_PROCESS=false
IOT_WATCHDOG_INTERVAL_SECONDS=30
IOT_MESSAGE_MAX_AGE_SECONDS=300
IOT_OFFLINE_AFTER_SECONDS=120
IOT_COMMAND_TTL_SECONDS=300
IOT_MAX_MESSAGES_PER_MINUTE=120
IOT_RAW_RETENTION_DAYS=30
IOT_AGGREGATE_RETENTION_DAYS=730
IOT_STORE_FORWARD_MAX_AGE_DAYS=30

# Optional Azure IoT Hub -> Event Grid ingress
IOT_CLOUD_PROVIDER=none
AZURE_IOT_HUB_ENABLED=false
AZURE_IOT_HUB_WEBHOOK_SECRET=
AZURE_IOT_HUB_NAME=
```

REST, signed MQTT, FieldBox replay, and IoT Hub deliveries all validate the
same `geovision.telemetry.v1` envelope and write the same receipt/readings
ledger. Store-and-forward samples may be older than the live message window
only when they carry an explicit queue time, stream, and sequence; their maximum
age cannot exceed raw retention. Run the independent IoT worker in deployed
environments rather than enabling one copy in every API replica.

IoT Hub delivery is disabled by default. When enabled, Event Grid must send the
configured random custom header to `/iot/providers/azure-iot-hub/events`; a
deployed profile requires a 32+ character secret and exact hub name. This
webhook secret and all device credentials remain backend-only. The
repository-level `.env.iot.example` documents the local MQTT stack, and
[`docs/IOT_EDGE_CONTRACT.md`](../docs/IOT_EDGE_CONTRACT.md) covers both gateway
topologies and the live activation gate.

## Safe diagnostics

Use the redacted summary when diagnosing configuration:

```bash
cd backend
python3 -c "from app.core.config import settings; print(settings.safe_summary())"
```

Run that command only after activating a healthy virtual environment with the
backend requirements installed. On this repository host the default `.venv` is
known to be stale; `make baseline` discovers a healthy test environment, while
R21 tracks rebuilding the default environment.

`safe_summary()` reports provider names and configuration booleans, not values.
Secret fields are excluded from the settings representation, and
`settings.model_dump()` replaces configured sensitive values with
`[REDACTED]`. Do not print `os.environ`, provider request headers, raw connector
records, or the settings object's private storage.

For runtime checks, use `/health` and `/ready`. A provider port or configuration
flag proves only that a boundary is available; live readiness still requires a
configured account and an adapter-specific verification.

## Unsupported legacy variables

Older documentation named DJI Terra, Pix4D, DroneDeploy, BIM 360, Procore, and
ArcGIS variables. The Phase 2 settings model does not consume those variables,
and no live adapter for them is activated. Add future credentials only alongside
the corresponding tested adapter and typed settings fields.
