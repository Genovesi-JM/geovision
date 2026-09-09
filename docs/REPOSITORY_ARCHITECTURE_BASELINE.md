# GeoVision repository architecture baseline

This document records the verified state of the GeoVision repository before the
LLM Refactor Prompt Playbook is applied. It is a description of the software as
it exists on 9 September 2026, not the target architecture. The main conclusion
is that GeoVision already contains substantial web, mobile, commerce, IoT and
operational functionality, but its boundaries and infrastructure do not yet
match the Azure-first modular-monolith direction in the playbook.

## Revision and working tree

- Repository: `/Users/genovesimaria/geovision`
- Branch: `feature/erp-realtime-account`
- Commit: `7bda199` (`ci: update GitHub actions runtimes`)
- Upstream branch: synchronized with `origin/feature/erp-realtime-account`
- `origin/main`: one merge commit ahead (`5559462`, merging this feature branch)
- Pre-existing uncommitted file: `mobile/ios/Podfile.lock`

The lock-file change was present before this audit and is not part of Phase 0.

## Runtime shape

```text
Static public website and customer/admin portals
                    |
                    v
         FastAPI modular application
        /       |        |         \
 authentication commerce datasets  IoT and operations
        \       |        |         /
             SQLAlchemy models
                    |
       SQLite development or PostgreSQL deployment

Flutter iOS and Android app -> FastAPI APIs
ESP32/simulator -> MQTT or authenticated REST -> FastAPI
S3-compatible object storage <- datasets and documents
ERPNext adapter <- durable integration outbox
```

This is a large single FastAPI application with feature folders, not yet a
deliberately partitioned modular monolith. It has 209 registered routes and 57
SQLAlchemy tables. IoT MQTT ingestion and the offline watchdog run inside the API
process.

## Repository components

| Component | Location | Verified state |
|---|---|---|
| Public website | Root HTML, `assets/css`, `assets/js` | Static multi-language website with no compilation step |
| Customer portal | `dashboard.html`, `assets/js/dashboard-client.js` | Authenticated web dashboard for operations, alerts, devices, reports, maps, orders and settings |
| Internal administration | `admin.html`, `assets/js/admin.js`, `assets/js/admin-ops.js` | Broad administrative surface backed by `/admin` routes |
| Backend | `backend/app` | FastAPI application with SQLAlchemy, Alembic, JWT/OAuth, commerce, datasets, risk, IoT and operational APIs |
| Mobile | `mobile` | One Flutter codebase using Riverpod, GoRouter, Dio, secure storage and offline queues |
| Firmware and simulator | `firmware/esp32`, `simulator` | PlatformIO ESP32 firmware and MQTT/REST simulator |
| Local stack | `docker-compose.yml`, `docker` | Timescale/PostgreSQL, Redis, Mosquitto, Mailpit, backend, frontend and optional simulator definitions |
| Deployment | `.do/app.yaml` | DigitalOcean App Platform definition targeting the `main` branch |
| Continuous integration | `.github/workflows` | Backend/web tests plus Flutter analyze, test, Android build and iOS simulator build |

## Backend entry points and boundaries

- `backend/start.py` runs Alembic and starts Uvicorn.
- `backend/app/main.py` constructs the application, initializes the database,
  seeds selected records, mounts routers and starts the MQTT bridge and IoT
  watchdog in the application lifespan.
- `/health` reports process liveness; `/ready` verifies a database query.
- Routers cover authentication, accounts, customer data, admin, products,
  orders, shop, payments, projects, datasets, risk, construction inspections,
  IoT, recommendations, reports, contacts, AI and mobile-specific contracts.

Feature code is partly separated into routers, services, IoT modules and ERP
adapters, but the ORM remains a single `backend/app/models.py` file and many
routers access it directly. Provider interfaces are not yet organized around a
single integration registry.

## Data model and migrations

Development defaults to `sqlite:///./geovision.db`. Deployment configuration
uses PostgreSQL. The Compose stack selects TimescaleDB, but the application does
not currently depend on PostGIS geometry types or GeoAlchemy. Sites store
latitude and longitude as numeric columns.

Alembic has a single current head, `identity_boundary_v1`. A complete migration
from an empty SQLite database reaches that head successfully. The history
includes authentication hardening, platform tables, mobile requests, ERP
outbox, drone missions, IoT, construction inspections, entitlements and account
profiles.

Important overlapping concepts exist today:

- `Account` and `AccountMember` represent workspaces selected by the customer.
- `Company` and `CompanyUser` independently scope much of the operational,
  dataset, IoT and administrative data.
- `backend/app/accounts` defines an additional accounts database and legacy
  customer/employee models.
- `Site` is the principal customer location. There is no generic cross-sector
  Asset aggregate yet; `IotAsset` is specific to the IoT/inspection layer.

These structures work for current tests but must be reconciled through
compatibility migrations rather than destructive replacement.

## Identity and authorization

The backend supports email/password login, bcrypt password hashes, versioned
GeoVision JWT sessions, rotating hashed refresh tokens, password reset tokens,
and legacy Google/Microsoft browser callbacks. Phase 3 also provides a strict
Microsoft Entra External ID adapter for GeoVision API access tokens. It validates
issuer, audience, tenant, signature, lifetime, and delegated scope; it does not
accept ID tokens or Microsoft Graph access tokens. External issuer/subject maps
to an immutable internal user UUID. A user can have multiple `AccountMember`
memberships, and requests can select a workspace using `X-Account-ID`.

Authorization is not yet one unified RBAC model. It combines a global user role,
account membership roles, company membership roles and route-specific admin or
tenant checks. The playbook's invitation-first onboarding and internal
contractor capability model are not implemented.

## Customer experiences

The Flutter app currently uses these top-level destinations: Portal, Assets,
Store, Alerts and More. Work, reports, devices, drones, support, payments and
GAIA remain secondary routes. This differs from the playbook target of Home,
Assets, Actions, Services and More and is intentionally deferred to Phase 22.

Current canonical sector identifiers are `agro`, `environment`, `construction`,
`industry` and `infrastructure`. Mining is normalized into industry, livestock
into agriculture and there is no distinct ports module. Agriculture has a full
mobile KPI catalogue; the other mobile sectors currently share two basic
infrastructure KPIs.

The shop is first-party: customers buy GeoVision products and services. No
public seller registration, storefront ownership or contractor bidding model
was found. Phase 7 has since replaced customer-facing “marketplace” wording
with “catalogue”; the historical recommendation action value remains a
documented compatibility alias for opening the GeoVision-controlled catalogue.

## Storage and processing

- Dataset and document files use an S3-compatible `boto3` service supporting
  AWS S3, MinIO or Cloudflare R2.
- Older document records can still reference local files.
- Direct uploads and presigned upload/download URLs are implemented.
- Azure Blob Storage is not implemented.
- No photogrammetry processing provider or asynchronous processing-job system
  is implemented; DJI, Pix4D and DroneDeploy are documented or interface-level
  future work.
- The RAG pipeline is explicitly a placeholder. GAIA has a deterministic
  fallback and can call an OpenAI model when configured.

## Background work and events

- The API lifespan starts an in-process MQTT bridge and device-offline watchdog.
- An ERP integration outbox persists idempotent events and supports retries.
- ERP processing is invoked through code or the `/integrations/erp/sync`
  endpoint; no independent worker or scheduler was found.
- Redis exists in Compose but is not the active cross-instance event/fan-out
  implementation.
- Azure Service Bus and Event Grid are not implemented.

## Provider and infrastructure status

| Area | Current implementation | Playbook target difference |
|---|---|---|
| Cloud deployment | DigitalOcean App Platform and GitHub-hosted static frontend | Azure-first infrastructure is not present |
| Object storage | S3-compatible provider | Azure Blob adapter required |
| Enterprise identity | Issuer-qualified mappings, internal sessions, strict Entra External ID API-token validation, and transitional Google/Microsoft callbacks | Production cutover, legacy-session retirement, and canonical organization/RBAC remain gated |
| ERP | ERPNext adapter plus mock and outbox | Playbook names Odoo as the intended internal ERP/CRM |
| Maps | OpenStreetMap/demo working; Mapbox adapter prepared | Azure-independent provider boundary still needs consolidation |
| Payments | Bank transfer and provider abstractions; Stripe, Multicaixa and PayPal credential-gated | Provider behavior and mock fallbacks need explicit production policies |
| Push | Mock contract; APNs/FCM described but not active | Production provider not configured |
| Drones | Mission contracts, mock/backend providers and guarded handoff | Vendor SDK execution and processing remain gated |
| IoT | Substantial MQTT/REST, provisioning, telemetry, alerts, commands, reports and ESP32 implementation | Edge contract exists but needs later modularization and production validation |

No active Firebase backend dependency was found. FCM appears only as an optional
future push provider. No Render deployment definition was found.

## Baseline verification

Executed on 9 September 2026 before Phase 0 changes:

| Check | Result |
|---|---|
| Backend tests using `backend/.venv-test` | 59 passed; warnings for intentionally absent development secrets |
| Default `make backend-test` environment choice | Failed because the older local `backend/.venv` lacks `pydantic-settings` |
| Web Playwright suite | 14 passed, 1 skipped |
| Flutter version | 3.44.7, Dart 3.12.2 |
| Dart formatting check | 130 files, no changes |
| Flutter analyze | No issues |
| Flutter tests | 38 passed |
| Android debug APK | Built successfully; future Kotlin plugin migration warning |
| iOS simulator debug app | Built successfully; future Swift Package Manager warning for `flutter_secure_storage` |
| Pre-Phase-3 fresh Alembic migration | Reached the then-current `account_profiles_v1` head |
| Backend startup | `start.py` started; `/health` and `/ready` returned 200 |
| Compose validation | Not runnable on this Mac because the Docker CLI has no Compose plugin |

Phase 3 subsequently made Alembic failure fatal at startup; the service no
longer stamps a failed migration as current or substitutes `create_all` for data
migrations. The narrow legacy column compatibility check still remains until
its behavior is replaced by an explicit later migration.

## Reproducible local verification

Use the non-mutating baseline check:

```bash
make baseline
```

It selects a Python environment only after verifying its imports, locates
Flutter in the shell or common macOS install paths, and runs backend, web and
Flutter checks. To include native debug builds:

```bash
GEOVISION_BASELINE_BUILDS=1 make baseline
```

The full IoT stack additionally requires Docker Compose:

```bash
make setup
```

Do not use `START_AUTODEV_MAC.command` merely for a read-only check: that older
launcher attempts to switch or create a Git branch and rewrites
`AUTODEV_STATUS.md`.

## Phase 1 boundary

Phase 1 can reorganize the backend into explicit domain modules while retaining
route and data compatibility. It must not silently choose between Account and
Company, delete legacy tables, introduce Azure resources, change mobile
navigation, or replace ERPNext with Odoo. Those changes belong to their named
later phases and require migrations, compatibility adapters and tests.
