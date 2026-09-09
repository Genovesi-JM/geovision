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
| `prod` | Live deployment | Same signing/encryption startup requirements as staging; provider readiness is checked lazily when each provider is used |

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

DATABASE_URL=sqlite:///./geovision.db
ACCOUNTS_DATABASE_URL=sqlite:///./accounts.db
```

`MIGRATE_TIMEOUT` remains an alias for `MIGRATE_TIMEOUT_SECONDS`. Legacy
`postgres://` database URLs are normalized to SQLAlchemy's `postgresql://`
scheme. Database URLs are treated as sensitive in configuration diagnostics.

## Secrets and authentication

```dotenv
SECRET_KEY=CHANGE_ME
ENCRYPTION_KEY=
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRES_MINUTES=60
REFRESH_TOKEN_EXPIRES_DAYS=30
ADMIN_PASSWORD=

IDENTITY_PROVIDER=internal
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
MICROSOFT_CLIENT_ID=
MICROSOFT_CLIENT_SECRET=
MICROSOFT_TENANT_ID=common
```

`ENCRYPTION_KEY` must be a URL-safe base64 Fernet key when `ENV` is `staging`
or `prod`. Google and Microsoft OAuth continue to work through the current
compatibility routes when configured. The `IdentityProvider` port is now
declared, but moving the OAuth flows behind concrete identity adapters belongs
to Phase 3. OAuth callback URLs are derived from `BACKEND_BASE`; the older
`GOOGLE_REDIRECT_URI` variable is not consumed by the backend.

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
bounded exponential backoff. The ERP outbox applies this convention to due
items; the independent scheduled worker and dead-letter workflow remain Phase
13 work.

## Provider selection

These variables declare the intended provider capability without exposing its
credentials to domain modules:

```dotenv
IDENTITY_PROVIDER=internal
OBJECT_STORAGE_PROVIDER=s3
QUEUE_PROVIDER=null
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

`OBJECT_STORAGE_PROVIDER`, `ERP_PROVIDER`, and `NOTIFICATION_PROVIDER` currently
drive provider factories. Payment methods use their own per-method factory rather
than one selector. `IDENTITY_PROVIDER` and the queue, processing, weather,
satellite, GIS, construction, asset-management, and maritime declarations are
reserved seams/configuration metadata in Phase 2; changing them does not wire,
enable, or disable an implementation. `none` and `null` therefore mean only that
the boundary exists with no live adapter. Do not set these declarations to an
Azure or third-party name until a matching adapter has been implemented and
tested.

Except for the signing and encryption guards described above, provider names
and credential completeness are generally validated when a factory or provider
operation is invoked, not when FastAPI starts. Health/readiness therefore does
not prove that ERP, storage, notifications, payments, or another external account
can complete a live request.

## Object storage

The current concrete implementation is the existing S3-compatible adapter. It
supports AWS S3 and compatible endpoints such as MinIO or R2. Dataset and
document code calls the `ObjectStorageProvider` port through the compatibility
storage service, so a future Azure Blob adapter can be added without changing
domain behavior.

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

The example configuration is not a self-contained local storage service: new
uploads require SDK-resolvable credentials and a reachable bucket, or a local
S3-compatible emulator configured through `S3_ENDPOINT_URL`. There is no local
filesystem write fallback. The legacy local-file path is read-only compatibility
for previously stored documents. Current uploads are read fully into memory to
calculate hashes before transfer, so large geospatial-file limits and streaming
hardening remain Phase 12 work. The compatibility service also preserves older
boolean/`None` return shapes for some calls, which can hide the distinction
between not-found and a provider failure; use the provider-level normalized
result when that distinction is operationally required.

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
```

Retention, message-age, command-TTL, and rate-limit settings are listed in
`.env.example`. The repository-level `.env.iot.example` documents the local IoT
stack.

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
