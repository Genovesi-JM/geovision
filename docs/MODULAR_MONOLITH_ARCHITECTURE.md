# GeoVision modular monolith architecture

This document defines the backend module boundaries established in Phases 1
and 2 of the GeoVision refactor. The application remains one FastAPI deployable
with one primary database and separately runnable workers as they are
introduced. The purpose of these boundaries is to make ownership, provider
isolation, and dependency direction explicit without breaking the working API
or duplicating persisted models. Provider contract details are documented in
[the provider integration architecture](PROVIDER_INTEGRATION_ARCHITECTURE.md).

## Runtime and composition

`app/main.py` is the composition root. It may assemble core primitives, common
domain modules, integrations, worker lifecycles, middleware, and HTTP
transports. Concrete routers are loaded lazily from descriptors in
`app/modules` and `app/integrations` after the database is initialized.

```text
                         app/main.py
                      composition root
                  /          |          \
          HTTP routers   integrations   workers
                  \          |          /
                 common domain module services
                              |
                         app/core
                              |
               PostgreSQL or SQLite compatibility
```

This is not a microservice topology. Module boundaries are Python package and
API boundaries inside the existing backend process. Later workers may run as a
separate process, but they must call the same domain services rather than fork
business rules.

## Dependency direction

Dependencies point toward stable shared abstractions:

```text
core <- common domain modules <- sector modules
             ^       ^
             |       |
      integrations  workers

composition root and HTTP transports -> all public module interfaces
```

The following rules apply to new code:

- `app/core` may use the Python standard library and framework libraries. It
  must not import GeoVision models, modules, sectors, integrations, routers, or
  workers.
- A common domain module may depend on `app/core` and another domain's public
  service contract. It must not import a sector package or another module's
  private repository or ORM implementation.
- A sector package composes common domain services. Common modules must never
  depend on a sector package.
- Integrations implement ports owned by common modules. Domain code must not
  initialize vendor clients or read provider credentials directly.
- Provider factories import concrete adapters lazily. Importing a domain port
  or testing it with a fake must not require the real vendor SDK.
- External provider values remain opaque references associated with an
  authoritative GeoVision UUID; they never become domain primary keys.
- Workers orchestrate public module services and integrations. They must not
  call FastAPI route handlers as business functions.
- Routers translate HTTP requests and responses. A router must not import
  another router for reusable business logic.
- Cross-module writes go through an owning service or repository. Direct ORM
  manipulation across module boundaries is forbidden for new code.
- Package `__init__.py` files must not eagerly import concrete routers or
  provider clients.

These rules are enforced where practical by
`backend/tests/test_architecture_boundaries.py`.

## Core layer

The canonical shared primitives live in `backend/app/core`:

| File | Responsibility |
|---|---|
| `config.py` | Typed settings and the application settings singleton |
| `database.py` | SQLAlchemy base, engine/session lifecycle, and existing schema compatibility |
| `passwords.py` | Bcrypt and legacy password-hash compatibility |
| `tokens.py` | JWT creation and verification |
| `encryption.py` | Encryption-at-rest compatibility |
| `security.py` | Stable facade for shared password/token primitives |
| `time.py` | UTC conversion at the current naive-datetime persistence boundary |
| `events.py` | Provider-neutral event envelope and publisher protocol |
| `integration.py` | Normalized provider results, safe errors, and timeout/retry conventions |
| `references.py` | Provider-independent external-reference value object tied to an existing GeoVision UUID |
| `observability.py` | Standard logger entry point without process-wide configuration |
| `routing.py` | Lazy router mount descriptors used by the composition root |

The prior modules `app.config`, `app.database`, `app.oauth2`, `app.utils`,
`app.crypto`, `app.security`, and `app.time_utils` remain as compatibility
imports. Existing scripts and external consumers can keep using those paths;
new code should use `app.core`.

The device-specific `DeviceEventHub` stays in `app/iot/events.py`. It is an
in-process monitoring transport, not the durable platform event publisher.
Durable outbox and queue behavior remains owned by Phase 13.

## Provider boundaries

Provider protocols live with their owning domains rather than with vendor
code. Phase 2 declares ports for object storage, payments, ERP, notifications,
identity, text generation, processing, weather, satellite, GIS, construction
systems, asset management, and maritime context. `app/core/events.py` provides
the shared event and queue publisher contracts.

Concrete implementations live under `app/integrations`. The current storage
factory lazily selects the S3-compatible adapter, and the ERP factory selects
the local mock or existing ERPNext adapter. No Azure Blob, Service Bus, Event
Grid, Odoo, processing, weather, satellite, GIS, construction,
asset-management, or maritime adapter is activated by this foundation work.

`app/core/config.py` is the single typed source for environment and provider
configuration. It recognizes local, development, test, staging, and production
profiles; staging and production fail closed when the JWT signing key or Fernet
encryption key is unsafe. Its supported diagnostic views redact secret values.
The complete variable and compatibility-alias list is in
[`backend/ENV_CONFIG_GUIDE.md`](../backend/ENV_CONFIG_GUIDE.md).

The provider result model distinguishes successful, accepted, simulated,
pending, retrying, unconfigured, and failed outcomes. Retry policy is bounded
and permits side-effecting operations only when they have an idempotency key.
Provider exceptions must be converted into safe failure details without raw
credentials, headers, or unbounded response bodies.

Existing dedicated external-ID fields remain unchanged. The
`ExternalReference` utility associates such an opaque value with an existing
GeoVision UUID and provider/resource namespaces. A generic persisted mapping is
deferred until workspace and generic Asset ownership are stable, so Phase 2
requires no schema or customer-data migration.

## Common domain modules

The registry in `app/modules/registry.py` is the authoritative list of common
domains. A module can own a router descriptor or be represented through a
cross-domain compatibility facade until its later phase extracts the service.

| Module | Current home and transition state |
|---|---|
| Identity | Immutable internal user IDs, versioned sessions, issuer-qualified external mappings, and a strict Entra External ID API-token adapter are implemented; legacy browser logins remain transitional, while Phase 4 owns canonical organization/RBAC consolidation |
| Organizations | Canonical organizations/workspaces, membership lifecycle, separate staff roles, server-enforced RBAC, and secure invitation-first acceptance/deep-link contracts are implemented over compatibility table names |
| Assets | Generic organization/workspace-owned hierarchy, validated GeoJSON, portable bbox queries, optional PostGIS projection, and legacy Site/IoT mirroring are implemented |
| Catalog | Canonical first-party products, services, plans, installations, inspections and analyses; legacy shop/product routes are compatibility projections |
| Orders | Canonical customer/internal order APIs, catalogue pricing snapshots, separate fulfilment/settlement state machines, optimistic lifecycle guards, and legacy shop/order projections are implemented |
| Operations | Admin, internal resources, mobile operations and inspections are compatibility facades; Phases 9 and 10 own extraction |
| Missions | Drone mission contracts exist inside the mobile facade; Phase 11 owns acquisition abstraction |
| Datasets | Dataset/file CRUD and upload flows exist; Phase 12 owns storage/provider hardening |
| Processing | Boundary only; Phase 14 owns processing jobs and photogrammetry providers |
| Analytics | KPI catalogue, risk calculations and AI explanation endpoints exist; numeric truth remains structured |
| Monitoring | IoT devices, telemetry, alerts, live events and watchdog behavior are substantial but transitional |
| Actions | Recommendations, commands and assignments exist across compatibility facades; Phase 17 owns the aggregate |
| Reports | PDF/document/deliverable behavior exists across facades; Phase 19 owns report workflow and publication |
| Notifications | Contact routes, email and IoT notification adapters exist; Phase 20 owns durable delivery |
| Billing | Every payment operation uses the module-owned provider port; tenant-derived payment truth, irreversible transitions, refunds, and digest-only idempotent webhook receipts are implemented |
| Audit | Audit records and domain timelines exist across middleware and routers; Phase 25 owns the unified boundary |

`app/modules/organizations/services.py` owns organization/workspace context,
customer membership policy and legacy company lookup without email-based
authorization. `app/modules/assets/services.py` owns cross-sector hierarchy,
spatial normalization, tenant filtering, archive policy, and legacy Site/IoT
mirroring. `app/modules/analytics/kpi_catalog.py` owns KPI selection.
Compatibility routers call these services instead of importing other routers.

## Sector boundaries

Sector packages declare their common-module needs but do not activate new
analytics or change current customer identifiers in Phase 1.

| Package | Activation phase | Compatibility notes |
|---|---:|---|
| `sectors/agriculture` | 18 | Existing `agro`, agriculture and livestock identifiers remain unchanged |
| `sectors/infrastructure` | 28 | Existing infrastructure and construction behavior remains unchanged |
| `sectors/environmental` | 29 | Existing `environment` and `ambiental` identifiers remain unchanged |
| `sectors/mining` | 30 | Existing mining/industry normalization remains unchanged |
| `sectors/ports` | 31 | Boundary exists, but no public Ports behavior is activated yet |

Every sector is disabled by default in this registry. Activation, KPIs,
catalogue items, reports, map layers and integrations belong to the named
sector phase and must reuse the common modules.

## HTTP compatibility ownership

`app/bootstrap.py` combines the domain and integration router descriptors and
mounts them in the exact Phase 0 order. Existing implementation files remain in
`app/routers` so public clients see no path or payload change.

Important compatibility details intentionally retained:

- `/products/products` and `/orders/orders` remain mounted as they were.
- `/orders` is the canonical order history while `/orders/orders` remains the
  historical physical-order compatibility path.
- The mobile and admin routers remain cross-domain facades.
- IoT's primary and mobile routers remain separate mounts from the same module.
- `app/routers/dashboard.py` and `app/routers/services.py` remain unregistered;
  registering them now would add or break public behavior.
- FastAPI health and readiness routes remain at `/health` and `/ready`.

The Phase 0 contract contains 204 application HTTP method/path pairs and one
WebSocket path. Tests hash the complete sorted set, including hidden legacy
aliases, and reject duplicate method/path registration.

## Worker boundary

`app/workers/lifecycle.py` owns startup and shutdown of the existing MQTT bridge
and device watchdog. They still run inside each API process for compatibility.
This boundary does not imply that in-process execution is production-safe at
multiple replicas; Phase 13 and Phase 16 must introduce durable/distributed
coordination before scaling them horizontally.

## Transitional persistence layer

`app/models.py` remains the single SQLAlchemy mapping source. Copying mapped
classes into new packages in Phase 1 would risk duplicate metadata, circular
imports and unsafe table changes. Each owning phase may move models behind a
repository/service contract only with additive migrations and compatibility
tests.

The runtime legacy-schema shim also remains temporarily in `core/database.py`.
It is grandfathered behavior, not a pattern for new domain schema changes. New
persisted changes must use Alembic, and the migration risks recorded in
`docs/REFACTOR_RISK_REGISTER.md` remain active.

## Adding code safely

For a new capability:

1. Choose the owning common module.
2. Put business rules in that module's service/domain layer, not in a router.
3. Define any provider need as a module-owned interface.
4. Add only secret-redacted, typed provider configuration to `app/core/config.py`.
5. Implement vendor behavior in `app/integrations` and inject it at the
   composition root or a compatibility service.
6. Normalize provider results, failures, timeouts, retries, and external
   references through the shared core contracts.
7. Have HTTP and worker transports call the same public service.
8. Add negative tenant/permission tests when data is workspace-scoped.
9. Add an Alembic migration for every persisted schema change.
10. Update route-contract expectations only when a later phase intentionally
   adds, deprecates or removes a public route.
