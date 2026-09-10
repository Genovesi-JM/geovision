# GeoVision entity relationships

This is the canonical ownership map for the current modular monolith. A new
feature should extend this graph instead of introducing a second customer,
asset, order, report, or identity architecture.

## Customer and intelligence graph

```text
User
  | many-to-many through OrganizationMembership
  v
Organization
  | 1-to-many
  v
Workspace <--- many-to-many through WorkspaceMembership ---> User
  | 1-to-many
  v
Asset -- optional parent_asset_id --> Asset
  | 1-to-many                         |
  |                                   +--> IoT Device -> Receipt -> Reading/Alert
  v
Acquisition (mission)
  | 1-to-many
  v
Dataset -> DatasetFile -> ProcessingJob -> ProcessingOutput
  |                              |
  +------------------------------+
                 |
                 v
       KpiValue and Observation -> Action -> outcome
                 |
                 v
              Report -> immutable version/artifact -> publication
```

Every workspace-scoped record carries an authoritative GeoVision identifier.
Provider identifiers are opaque external references and never replace it.
Assets provide the shared cross-sector anchor, while missions, datasets, KPIs,
observations, actions, reports, devices, and commercial work reuse that anchor.

## Commercial and fulfilment graph

```text
CatalogItem (GeoVision-owned product, service, plan, or analysis)
  |
  v
Order -> OrderItem -> PaymentAttempt / Shipment
  |
  v
FulfilmentJob -> dependency / schedule / assignment -> Contractor or Staff
  |                                                        (private Operations)
  +--> Acquisition -> Dataset -> intelligence -> Report
```

An order price and provider choice are snapshotted so later catalogue changes
do not rewrite history. Odoo or another ERP receives a narrow, idempotent
commercial projection; GeoVision remains authoritative for the order,
fulfilment, Asset, mission, intelligence, report, and customer experience.

The mobile service-request facade is an entry point into this graph. Its
canonical organization, workspace, Asset, order, and report links must be used
when present; compatibility-only requests are never sufficient authorization.

```text
MobileServiceRequest (customer compatibility facade)
  +--> Organization + Workspace + requesting User
  +--> Asset
  +--> Order -> FulfilmentJob -> private assignment
  +--> published Report -> Acquisition -> Dataset / KPI / Observation / Action
```

The request stores direct links only to the canonical scope, Asset, order, and
published report. Mission, dataset, processing, KPI, observation, action, and
contractor context is reached through those owning records and services rather
than duplicated on the request. Historical rows with no unambiguous workspace
link are quarantined from customer and Operations queries until an audited
repair supplies the missing ownership.

## Identity and onboarding graph

```text
AuthIdentity -> User -> Memberships
Invitation -> pending OrganizationMembership + WorkspaceMembership
           -> accepted by the intended User
           -> existing Workspace / Asset / Report / Order destination
Notification -> recipient User + scope + typed target
             -> authorization rechecked when the deep link is resolved
```

One human identity can belong to many organizations and workspaces. Roles are
membership properties, not separate account types. Email is invitation/contact
metadata and is never an authorization join key.

## Integration and event graph

```text
Domain transaction -> OperationalDomainEvent (transactional outbox)
                   -> idempotent consumer receipt
                   -> worker or provider command

IntegrationConnection -> IntegrationSyncRun -> IntegrationSyncEvent
                      -> resilience state / retry / dead letter
                      -> opaque provider references

AccountEvent -> workspace-scoped mobile polling/SSE compatibility projection
```

The integration registry is a control plane, not another system of record. Its
organization/workspace/member scope, rollout flag, entitlements, connection
state, and operation capability must all allow an operation.

`AccountEvent` is not the durable domain outbox. It preserves the existing
mobile account activity feed while carrying an explicit workspace scope; new
asynchronous business behavior belongs to `OperationalDomainEvent` consumers.

## Compatibility names

The schema retains safe historical names to avoid destructive table renames:

| Canonical concept | SQLAlchemy compatibility name | Table |
|---|---|---|
| Organization | `Company` | `companies` |
| Workspace | `Account` | `accounts` |
| Organization membership | `CompanyUser` | `company_users` |
| Workspace membership | `AccountMember` | `account_members` |
| Durable platform event | `EventOutbox` alias | `operational_domain_events` |

Legacy `Site`, IoT asset, shop, mobile, and document routes are projections or
facades. New business rules belong to the canonical module services.
