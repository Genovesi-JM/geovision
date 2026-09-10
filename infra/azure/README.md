# GeoVision Azure infrastructure

This Bicep stack creates a lean, isolated Azure environment while leaving the
DigitalOcean rollback definition at `.do/app.yaml` untouched.

## Resources

- VNet-integrated Azure Container Apps environment with public TLS API,
  independent event, ERP, notification, processing, and intelligence workers,
  and a manual one-replica migration job.
- Basic Azure Container Registry with admin access disabled.
- private PostgreSQL Flexible Server 16 (`Standard_B1ms`, 32 GiB) and database.
  Bicep allowlists `POSTGIS`; the existing Alembic migration executes the
  idempotent `CREATE EXTENSION postgis` inside the database.
- private Blob container with shared-key and anonymous access disabled.
- RBAC-mode Key Vault, App Configuration, Service Bus Standard topic and
  subscription, Log Analytics, and workspace-based Application Insights.
- one lean development user-assigned identity with scoped ACR pull, Blob data,
  Key Vault secret, Service Bus send/receive, and App Configuration read roles.

The development App Configuration store uses the Free SKU. It is a small
configuration catalog for the exact `Settings` names; the current backend still
receives those values directly as Container Apps environment variables because
it does not load the Azure App Configuration SDK. Free-tier request/storage
quotas are suitable for this catalog, not a high-volume runtime dependency.

## Prerequisites and secrets

Use Azure CLI with permission to create the resource group, resources, and role
assignments. The helper registers all required resource providers. Export the
three values referenced by `dev.bicepparam`:

```bash
export GEOVISION_POSTGRES_ADMIN_PASSWORD='...'
export GEOVISION_SECRET_KEY='at-least-32-random-characters...'
export GEOVISION_ENCRYPTION_KEY='a-valid-url-safe-base64-Fernet-key='
```

Generate the Fernet key with
`python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`.
Secrets flow through secure Bicep parameters into Key Vault and are referenced
by managed identity; they are not committed or stored as plain Container App
secrets.

## Validate and preview

```bash
infra/azure/validate.sh
infra/azure/deploy.sh --what-if
```

Set `BICEP_BIN=/path/to/bicep` when the standalone CLI is not on `PATH`.

## Guarded release

```bash
GEOVISION_IMAGE_TAG="$(git rev-parse --short HEAD)" infra/azure/deploy.sh
```

The helper deliberately performs three incremental deployments:

1. foundation only (`deployApplications=false`, `deployMigrationJob=false`),
   removing the empty-registry bootstrap deadlock;
2. ACR build, then migration-job-only deployment and a blocking successful job
   execution (`python start.py migrate`);
3. runtime deployment only after the migration succeeds. API replicas run
   `python start.py serve --skip-migrations`, disable compatibility schema
   writes, and refuse readiness when Alembic is not at head.

On an existing environment, step 2 does not modify the running API or worker
revisions. Never run two migration executions concurrently.

Useful outputs are `acrName`, `acrLoginServer`, `backendImage`, `apiUrl`,
`migrationJobName`, `keyVaultName`, `appConfigurationEndpoint`,
`storageAccountName`, `serviceBusNamespace`, `postgresServerName`, and the five
individual `*WorkerName` outputs.

## Rollback and teardown

Database migrations are forward-only. To roll back application code, select an
already-pushed image tag known to be compatible with the migrated schema and
update runtime revisions without running an older migration bundle:

```bash
GEOVISION_IMAGE_TAG='<previous-tag>' infra/azure/deploy.sh --runtime-only
```

The previous Container Apps revision remains observable, and the preserved
`.do/app.yaml` remains the provider-level rollback reference. Do not point the
DigitalOcean service at the Azure database until a separately approved data
cutover and restore rehearsal are complete.

For a disposable **development-only** environment, the resource group is the
teardown boundary:

```bash
az group delete --name rg-geovision-dev-weu
```

This permanently removes Azure resources after soft-delete behavior has run;
retain required database/blob backups first. Main dev cost drivers are the
always-on PostgreSQL B1ms server, Service Bus Standard namespace (topics require
Standard), Log Analytics ingestion, and six minimum-one worker/API replicas.
Container Apps uses Consumption, ACR uses Basic, storage uses LRS, and App
Configuration uses Free. Set budget alerts outside this workload stack.
