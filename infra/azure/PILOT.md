# GeoVision isolated Azure pilot

This is an explicitly selected **pilot**, not a cheaper replacement for the
existing public-production profile. The user approved EUR 100–250/month **across
GeoVision, Kaya and Kasa together** on 12 September 2026. This file does not
allocate that whole amount to GeoVision, quote a guaranteed bill, or claim a
completed deployment/data migration.

## Selection and resources

Set `AZURE_DEPLOYMENT_PROFILE=pilot` when invoking `infra/azure/deploy.sh`.
It selects `pilot.bicepparam`, resource group `rg-geovision-pilot-weu`, deployment
prefix `geovision-pilot`, and Spain Central for workload resources. The existing
empty group's metadata stays in West Europe (`resourceGroupLocation`), but no
application data is placed there by that metadata setting. West Europe rejected
the initial what-if for this new Azure tenant. Spain Central requires its own
successful what-if/capacity check before deployment. Directly selecting the checked-in
`pilot.bicepparam` through `AZURE_PARAMETERS_FILE` also selects the pilot group
defaults. Explicit operator group/location overrides remain possible and must
be reviewed, including `AZURE_RESOURCE_GROUP_LOCATION` for a different group.
Do not mix these names with an existing development/production environment.

The foundation contains:

- Private-network PostgreSQL 16 Flexible Server B1ms, 32 GB, 7-day backups,
  TLS, two logical databases: `geovision` and `geovision_accounts`; PostGIS
  allowlisted for the primary database. One server, not two billed servers.
- Container Apps Consumption environment, VNet and private PostgreSQL DNS.
- ACR Basic; private LRS Blob container `geovision-datasets` with shared-key
  and anonymous access disabled; RBAC Key Vault; App Configuration **Free**;
  Log Analytics and Application Insights; one user-assigned managed identity.
- After the migration-first release: API at 0–2 replicas (0.5 vCPU / 1 GiB
  per active replica), one **always-on** event worker (0.25 vCPU / 0.5 GiB),
  and the existing manually triggered one-shot migration job.

The free App Configuration tier does not support soft delete; its reproducible,
non-secret settings remain in infrastructure code. The template omits paid-tier
recovery properties only for `free`, retains Standard's seven-day setting and
keeps local-key authentication disabled in both. Actual secrets remain in Key
Vault with its own soft delete and purge protection. The first live deployment
caught this SKU constraint, which what-if had not rejected.

The foundation creates the App Configuration store without publishing its
values (`deployConfigurationValues=false`). Publishing requires separately
approved, resource-scoped App Configuration Data Owner access for the deployment
operator, not for the runtime identity. ARM uses Pass-through authentication;
local keys remain disabled. Runtime grants stay read-only. Required runtime
environment values also exist in the Container Apps template, but configuration
publication and feature-flag validation remain explicit release gates.

Pilot API ingress defaults to internal (`apiExternalIngress=false`) independently
of application creation. No existing public endpoint is replaced. The generic
release helper deliberately does not declare an internal API healthy from an
external curl attempt: complete in-network health/readiness checks before any
separately reviewed public exposure.

Service Bus is **not created**, its role assignments are omitted, and both
runtime and App Configuration use `QUEUE_PROVIDER=database`. This is the
existing durable `EventOutbox`/consumer path in
`backend/app/services/event_outbox.py`; the existing independent event worker
polls it. The event worker remains active when HTTP scales to zero. No custom
scheduler, in-memory replacement queue, or immediate-delivery promise is added.

ERP, notification, processing and intelligence workers are excluded by default.
The typed `workers` object offers independent creation flags. SMTP's worker
must be deliberately selected together with approved SMTP configuration. Do not
select ERP until its real provider configuration replaces the legacy mock;
processing/intelligence require their own live gates. Durable jobs for disabled
consumers can remain pending: these exclusions are not equivalent to successful
ERP, email, processing, satellite acquisition or clinical/IoT functionality.
Providers remain `{}` by default. API-hosted worker execution stays disabled.

**Existing resources are not stopped by omitting an ARM resource in incremental
deployment.** These flags govern a fresh pilot's resource creation. Changing a
flag to false in an existing environment requires a separately reviewed drain,
disable/removal procedure; do not claim cost savings or stopped work otherwise.

Runtime `ENV=staging` preserves deployed fail-closed checks. Pilot flags cannot
weaken an environment named `prod`: production keeps Service Bus, all workers,
at least two API replicas and its existing HA database/ZRS storage selection.

## Remaining cost drivers

The database, ACR Basic and event worker have a continuing baseline. API requests
and active compute, logs, Blob, Key Vault, networking and data transfer may add
cost. Scale-to-zero does not make this whole stack free. The pilot has a
0.1 GB/day Log Analytics ingestion soft cap and 30-day retention; the cap can
be exceeded and is not a spending limit. Subscription budget alerts are
configured separately; provider quotas still require explicit configuration. Azure credits and
free grants have separate eligibility/expiry rules; budget alerts are not caps.
Current region/SKU capacity and the aggregate three-project budget must be
checked before deploying billable resources.

## Identity and secret scope manifest

Pilot provider registrations: `Microsoft.App`, `Microsoft.AppConfiguration`,
`Microsoft.Authorization`, `Microsoft.ContainerRegistry`,
`Microsoft.DBforPostgreSQL`, `Microsoft.Insights`, `Microsoft.KeyVault`,
`Microsoft.ManagedIdentity`, `Microsoft.Network`,
`Microsoft.OperationalInsights`, `Microsoft.Storage`. The helper excludes
`Microsoft.ServiceBus` registration for this profile.

The workload identity receives only resource-scoped ACR Pull, Storage Blob Data
Contributor, Key Vault Secrets User, and App Configuration Data Reader on this
environment's resources. It has no Service Bus grants in pilot. No Entra app
registration, directory-wide role or cross-project permission is introduced.
Deployment/provider-registration and secret-operator authority are separate
from runtime grants and must be approved with their exact target scopes.

Both databases currently share the template's database administrator credential
and runtimes share one managed identity: logical databases separate schemas,
not security principals. Per-process identities and least-privilege database
roles remain explicit production-hardening work. Do not claim per-worker secret
isolation or hardened database-role separation.

The existing protected deployment inputs remain
`GEOVISION_POSTGRES_ADMIN_PASSWORD`, `GEOVISION_SECRET_KEY`,
`GEOVISION_ENCRYPTION_KEY`. An added fixed vault secret
`accounts-database-url` supplies `ACCOUNTS_DATABASE_URL` to the runtime and
migration job. It addresses the separate logical database, uses TLS, and is not
emitted as a public output. Reuse approved stable signing/encryption material
when migrating encrypted existing data; never silently rotate it or load files
containing secrets into this document, source control, chat or command history.

## Migration and release gates

`start.py migrate` now runs primary Alembic, the **independent versioned accounts
Alembic chain**, then the compatibility bootstrap. Runtime revisions still
start only after the migration job succeeds. Accounts migration requires its
explicit URL, rejects the primary database as the same target, rejects SQLite
in deployed profiles, and reports safe failure text rather than driver details.
It creates `customer_accounts` and `employees` on a clean isolated database.
Unversioned existing tables are deliberately rejected, not silently adopted or
stamped. Existing SQLite/customer data must be backed up and imported through a
reviewed explicit rehearsal; this migration performs **no data copy**.

Strict deployed `/ready` now checks both primary and accounts packaged migration
heads. The API does not create either schema during import or its
`--skip-migrations` startup. The accounts store is the legacy customer/employee
directory, distinct from the primary authentication/users/organizations tables.

Offline tests exercise pilot/standard/prod policy, independent worker flags,
conditional resource references, disposable SQLite accounts migration/re-run,
legacy-table fail-closed behavior, PostgreSQL DDL generation, separate readiness
head and protected startup argument handling. These do not replace execution
against fresh PostgreSQL/PostGIS, an existing-data restore/import rehearsal,
cloud what-if, secret resolution/RBAC, DNS/TLS and tenant-denial/API/queue tests.

No public cutover, data deletion, production signing/store release, paid gateway,
Entra client cutover, hardware commission or scientific/clinical approval is
implied. Retain the previous deployment and backups until the new endpoints,
private object transfer and rollback are verified.
