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
The Phase 13 event outbox is the durable cross-process source; the WebSocket hub
remains an optional live projection.

## Provider boundaries

Provider protocols live with their owning domains rather than with vendor
code. Phase 2 declares ports for object storage, payments, ERP, notifications,
identity, text generation, processing, weather, satellite, GIS, construction
systems, asset management, and maritime context. `app/core/events.py` provides
the shared versioned event and queue publisher contracts, while
`app/services/event_outbox.py` owns transactional persistence, claims, retries,
consumer receipts, and dead-letter state.

Concrete implementations live under `app/integrations`. The storage factory
lazily selects private local, S3-compatible, or Azure Blob adapters, and the ERP
factory selects the local mock or existing ERPNext adapter. Queue composition
selects the database worker or Azure Service Bus, while the Event Grid adapter
normalizes BlobCreated ingress. Processing now selects deterministic fake or
NodeODM adapters; monitoring selects deterministic fake, Copernicus satellite,
or AEMET weather adapters at the composition boundary. Reports select a strict
offline deterministic narrative provider and retain an explicit unavailable
boundary for unapproved external models. Odoo, Azure Maps
Weather, GIS, construction, asset-management, and maritime adapters are not
activated yet.

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
| Operations | Private suppliers, generic contractors/capabilities, guarded assignments, least-privilege contractor self-access, and canonical fulfilment jobs are implemented; admin/mobile/inspection facades remain transitional |
| Missions | Provider-neutral drone, satellite, IoT, manual-inspection, and third-party acquisitions share one asset history; drone details and legacy mobile/inspection routes are compatibility extensions |
| Datasets | Asset/mission-linked metadata, lifecycle, tenant-safe streaming/signed uploads, immutable file identity, and local/S3/Azure storage adapters are implemented |
| Processing | Durable source/output-linked jobs, quality/retry states, an independent worker, deterministic fake and NodeODM adapter are implemented; paid vendor adapters remain explicit scaffolds |
| Analytics | Versioned sector calculator/rule registries, immutable KPI history, provenance-safe observations/alerts, comparisons and normalized Asset summaries are implemented; AI remains explanation-only |
| Monitoring | Provider-mapped IoT devices, canonical assignments, versioned telemetry receipts, safe offline replay, alerts, live events and watchdog behavior coexist with durable cached satellite/weather acquisitions, normalized provenance and independent workers |
| Actions | Generic source-linked recommendations, priorities, assignments, GeoVision catalogue references, optimistic lifecycle transitions, outcomes and durable events are implemented; IoT recommendation/command routes remain compatibility facades |
| Reports | Versioned immutable contexts, strict optional narrative, deterministic fallback, QA levels, PDF Dataset artifacts, review/approval/publication/supersession, customer visibility and durable audit/events are implemented; legacy Document routes are published-only compatibility facades |
| Notifications | Contact routes, email and IoT notification adapters exist; Phase 20 owns durable delivery |
| Billing | Every payment operation uses the module-owned provider port; tenant-derived payment truth, irreversible transitions, refunds, and digest-only idempotent webhook receipts are implemented |
| Audit | Audit records and domain timelines exist across middleware and routers; Phase 25 owns the unified boundary |

`app/modules/organizations/services.py` owns organization/workspace context,
customer membership policy and legacy company lookup without email-based
authorization. `app/modules/assets/services.py` owns cross-sector hierarchy,
spatial normalization, tenant filtering, archive policy, and legacy Site/IoT
mirroring. `app/modules/analytics/domain.py` owns the versioned calculator/rule
registry and status/comparison rules; `app/modules/analytics/services.py` owns
KPI and observation persistence. `app/modules/actions/services.py` owns
recommendation deduplication, assignment and outcomes. The older
`app/modules/analytics/kpi_catalog.py` remains a read-only compatibility
catalogue until the Phase 22 clients move to Asset intelligence responses.
Compatibility routers call these services instead of importing other routers.

## Sector boundaries

Sector packages declare their common-module needs without adding vertical-only
columns to common entities. The composition root mounts routes only for enabled
packages and each package registers calculators/rules through the common
versioned intelligence interfaces.

| Package | Activation phase | Compatibility notes |
|---|---:|---|
| `sectors/agriculture` | 18 | Enabled with source-fused KPIs, cautious rules, map layers and structured report context; legacy identifiers remain accepted |
| `sectors/infrastructure` | 28 | Existing infrastructure and construction behavior remains unchanged |
| `sectors/environmental` | 29 | Existing `environment` and `ambiental` identifiers remain unchanged |
| `sectors/mining` | 30 | Existing mining/industry normalization remains unchanged |
| `sectors/ports` | 31 | Boundary exists, but no public Ports behavior is activated yet |

Agriculture is enabled in Phase 18; the remaining four packages stay disabled
until their activation phases. Sector routes are composed explicitly alongside
domain/integration routes, and common modules never import sector packages.

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
