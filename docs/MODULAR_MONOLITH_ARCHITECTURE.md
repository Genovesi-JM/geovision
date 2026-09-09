# GeoVision modular monolith architecture

This document defines the backend module boundaries established in Phase 1 of
the GeoVision refactor. The application remains one FastAPI deployable with one
primary database and separately runnable workers as they are introduced. The
purpose of these boundaries is to make ownership and dependency direction
explicit without breaking the working API or duplicating persisted models.

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
| `observability.py` | Standard logger entry point without process-wide configuration |
| `routing.py` | Lazy router mount descriptors used by the composition root |

The prior modules `app.config`, `app.database`, `app.oauth2`, `app.utils`,
`app.crypto`, `app.security`, and `app.time_utils` remain as compatibility
imports. Existing scripts and external consumers can keep using those paths;
new code should use `app.core`.

The device-specific `DeviceEventHub` stays in `app/iot/events.py`. It is an
in-process monitoring transport, not the durable platform event publisher.
Durable outbox and queue behavior remains owned by Phase 13.

## Common domain modules

The registry in `app/modules/registry.py` is the authoritative list of common
domains. A module can own a router descriptor or be represented through a
cross-domain compatibility facade until its later phase extracts the service.

| Module | Current home and transition state |
|---|---|
| Identity | Authentication, OAuth, sessions and profiles are implemented but transitional; Phase 3 owns provider identity separation |
| Organizations | Account, Company and legacy accounts work but overlap; Phase 4 owns canonical workspaces and RBAC |
| Assets | Sites, devices, aircraft and inspected assets exist; Phase 5 owns the generic Asset/PostGIS model |
| Catalog | Product, shop-product, kit and service catalogue behavior exists; Phase 7 owns consolidation |
| Orders | Legacy order routes and the richer shop lifecycle exist; Phase 8 owns the standard lifecycle |
| Operations | Admin, internal resources, mobile operations and inspections are compatibility facades; Phases 9 and 10 own extraction |
| Missions | Drone mission contracts exist inside the mobile facade; Phase 11 owns acquisition abstraction |
| Datasets | Dataset/file CRUD and upload flows exist; Phase 12 owns storage/provider hardening |
| Processing | Boundary only; Phase 14 owns processing jobs and photogrammetry providers |
| Analytics | KPI catalogue, risk calculations and AI explanation endpoints exist; numeric truth remains structured |
| Monitoring | IoT devices, telemetry, alerts, live events and watchdog behavior are substantial but transitional |
| Actions | Recommendations, commands and assignments exist across compatibility facades; Phase 17 owns the aggregate |
| Reports | PDF/document/deliverable behavior exists across facades; Phase 19 owns report workflow and publication |
| Notifications | Contact routes, email and IoT notification adapters exist; Phase 20 owns durable delivery |
| Billing | Payment, reconciliation and entitlement behavior exists; Phase 8 owns provider/lifecycle consolidation |
| Audit | Audit records and domain timelines exist across middleware and routers; Phase 25 owns the unified boundary |

`app/modules/organizations/services.py` now owns legacy company-context lookup,
and `app/modules/analytics/kpi_catalog.py` owns KPI selection. Compatibility
routers call these services instead of importing other routers.

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
4. Implement vendor behavior in `app/integrations` and inject it at the
   composition root.
5. Have HTTP and worker transports call the same public service.
6. Add negative tenant/permission tests when data is workspace-scoped.
7. Add an Alembic migration for every persisted schema change.
8. Update route-contract expectations only when a later phase intentionally
   adds, deprecates or removes a public route.
