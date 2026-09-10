# GeoVision release checklist

This checklist is the release record for the exact commit and immutable image
promoted through staging. A workflow being present does not authorize an Azure
deployment or close any human gate in `HUMAN_GATES.md`.

## One-time GitHub and Azure setup

- [ ] An Azure owner has run `infra/azure/deploy.sh --register-providers` once
  with subscription-level provider-registration permission.
- [ ] Separate GitHub environments named `staging` and `production` exist.
- [ ] The `production` environment requires designated reviewers, prevents
  self-review where the repository plan supports it, and allows only `main`.
- [ ] Each environment defines non-secret variables `AZURE_CLIENT_ID`,
  `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_LOCATION`,
  `AZURE_RESOURCE_GROUP`, `GEOVISION_FRONTEND_BASE_URL`, and
  `GEOVISION_CORS_ORIGINS`.
- [ ] Production also defines `AZURE_STAGING_ACR_NAME`.
- [ ] Each environment stores `GEOVISION_POSTGRES_ADMIN_PASSWORD`,
  `GEOVISION_SECRET_KEY`, and `GEOVISION_ENCRYPTION_KEY` as environment
  secrets, never repository files or workflow inputs.
- [ ] GitHub OIDC federation is restricted to the repository and matching
  environment. No long-lived Azure client secret is configured.
- [ ] The deployment identity has only the target deployment/RBAC permissions
  it needs. The production identity additionally has `AcrPull` on staging ACR
  and `AcrPush` on production ACR for digest-preserving promotion.
- [ ] Budget alerts, PostgreSQL backups, Key Vault recovery, log retention, and
  named operational owners are configured outside the workload template.

## Pull request and staging evidence

- [ ] The `release-gate` job in `CI - delivery gates` passed for the commit.
- [ ] Backend full tests and the named `security_regression` suite passed.
- [ ] The clean and representative-previous-schema PostgreSQL/PostGIS migration
  tests passed; Alembic reported exactly one current head.
- [ ] Correctness lint, Python dependency audit, npm audit, Docker build,
  Playwright, Bicep contracts, Flutter analysis/tests, Android build, and iOS
  simulator build passed.
- [ ] Any persisted SQLAlchemy model change includes a reviewed additive
  Alembic revision. Raw `alembic check` has known historical metadata noise and
  is not a substitute for the clean/upgrade tests; its debt remains explicit.
- [ ] `Deploy - staging` completed for the same commit.
- [ ] Record the staging workflow URL, commit SHA, immutable
  `geovision-backend@sha256:...` reference, operator, and timestamp.
- [ ] Any dependency-audit exception names the exact advisory, owner,
  justification, and expiry. There are no blanket or permanent ignores.

## Database and migration gate

- [ ] Restore the latest production-like backup into an isolated environment
  and rehearse the exact migration before the change window.
- [ ] Record backup identifier, restore-test evidence, retention, owner, and
  recovery-time result without copying credentials or customer data into CI.
- [ ] Confirm no other migration execution is running.
- [ ] Confirm the Container Apps migration execution uses the approved digest,
  runs `python start.py migrate`, and reaches `Succeeded` before any runtime
  revision is updated.
- [ ] Confirm `alembic current --check-heads` reports the packaged head.
- [ ] Confirm PostGIS is installed and the assets geometry GiST index exists.
- [ ] Treat a failed, stopped, degraded, or timed-out migration as a stopped
  release. Never stamp the database or use `create_all` to bypass it.

## Application and authorization smoke tests

- [ ] `/health` and `/ready` return success through the intended public route.
- [ ] An unauthenticated request to protected surfaces is rejected.
- [ ] A customer cannot reach Operations, admin, internal catalogue/order/
  mission/processing, provider-usage, or internal-cost endpoints.
- [ ] A user from organization A cannot read or mutate organization B data.
- [ ] A viewer cannot perform manager/owner mutations.
- [ ] Invitation tampering/replay and cross-tenant targets remain rejected.
- [ ] Upload initiation, transfer, confirmation, and download enforce tenant,
  assignment, expiry, size, checksum, and content-type boundaries.
- [ ] Customer payloads and logs contain no internal cost, provider cost,
  contribution, margin, token, key, or connection-string fields.

## Phase 33 end-to-end closure evidence

- [ ] `scripts/verify_phase33.sh` passed for the exact commit. Preserve its
  output and treat every warning about absent PostgreSQL/PostGIS or staging
  inputs as open evidence, not a pass for that gate.
- [ ] On a freshly migrated disposable database,
  `backend/scripts/seed_phase33_demo.py --confirm-synthetic-demo` was run twice
  to prove idempotency. All six canonical sectors each have clearly marked
  synthetic Asset, mission, dataset, KPI, observation, action, and report
  history visible through customer-safe projections. No credential was
  created, reset, or printed. The Phase 33 script name is a retained
  compatibility name.
- [ ] One service request was followed through canonical organization,
  workspace, Asset, order, fulfilment job, private assignment, acquisition,
  upload, dataset, processing, KPI/observation/action, reviewed publication, and
  report links. A retried create after a lost response reused its idempotency key
  and did not create another request or downstream commercial record, including
  after its legacy Site was renamed or deleted. Self-service account deletion
  also removed the keyed request before deleting an empty personal Workspace.
- [ ] The intended customer accepted a one-time invitation, received only
  recipient-bound inbox items, opened the authorized typed destination, and saw
  the result in both service-request and order history. Replay, tampering,
  revocation, expiry, and foreign-scope opens were rejected.
- [ ] Duplicate and out-of-order IoT envelopes, durable projection retry, offline
  detection/recovery, KPI/observation/action materialization, notification, and
  customer Asset visibility were exercised without duplicate decisions. Record
  which watchdog worker owned offline detection.
- [ ] Cross-organization denial, two accessible workspaces in one organization,
  an unauthorized workspace, and two contractor assignments were exercised.
  Customer reads stayed in the selected workspace, and a contractor could not
  enumerate another assignment, customer membership, margin, credential, or
  internal Operations data. Legacy mobile drone listing, registration, mission
  creation, and approval also denied a same-Organization foreign Workspace and
  denied viewer writes.
- [ ] `scripts/staging_smoke.sh` passed with an approved short-lived customer
  token and selected workspace. If
  `GEOVISION_STAGING_FOREIGN_WORKSPACE_ID` was not supplied, record the
  cross-workspace staging check as missing rather than complete.

## Phase 34 six-sector alignment evidence

- [ ] Public website, onboarding, account profiles, dashboard, catalogue, KPI
  responses, mobile selectors, backend registry, Asset sectors, and synthetic
  fixtures expose the same ordered six-sector contract from
  `docs/SECTOR_TAXONOMY.md`.
- [ ] New responses and writes use only `agriculture`,
  `construction_infrastructure`, `environment`, `mining`,
  `industry_energy_utilities`, and `ports_logistics`; Asset/evidence writes use
  only their six mapped uppercase technical values.
- [ ] Legacy public and technical aliases remain readable, while tests prove
  that mining is not mapped to industry and ports/logistics is not combined
  with industry/energy/utilities.
- [ ] Canonical Industry/Energy/Utilities and Ports/Logistics capability routes
  pass authorization, Workspace-module, rollout, missing-data, and
  cross-tenant negative tests; hidden legacy Industry and Ports paths preserve
  compatibility.
- [ ] `phase34_sector_taxonomy_v1` passed clean upgrade, downgrade,
  re-upgrade, row-count, unknown-extension preservation, and one-head checks
  against a production-like PostgreSQL/PostGIS copy.
- [ ] Browser and Flutter contract tests verify exact Portuguese labels, order,
  IDs, aliases, filters, and no stale combined sector copy. Record the exact
  Phase 34 commit and do not reuse Phase 33 test counts or image digests.

## Background workers and integrations

- [ ] Event worker revision is healthy; pending age, retries, delivery attempts,
  and dead-letter count are within the agreed threshold.
- [ ] ERP worker revision is healthy and an approved staging command reaches
  its configured adapter without duplicate external documents.
- [ ] Notification worker revision is healthy; a test delivery is idempotent
  and no recipient/body content is exposed in operational logs.
- [ ] Processing worker revision is healthy; a bounded representative job
  reaches the expected state or fails safely to review.
- [ ] Intelligence worker revision is healthy; scheduled acquisition/provider
  failures remain visible and do not invent observations.
- [ ] Blob upload/download, Service Bus publish/consume/retry, Key Vault secret
  resolution, and Application Insights correlation were verified.
- [ ] Every enabled external integration has an owner and fresh health evidence:
  Entra External ID, Odoo, SMTP/push, AEMET, Copernicus, NodeODM, payments, and
  IoT as applicable. Disabled providers fail closed without mock production data.

## Production approval and deployment

- [ ] Human Gate 18 and every integration-specific human gate are approved.
- [ ] Start `Deploy - production` from `main` and supply the exact approved
  staging digest. Do not supply a tag.
- [ ] Required production-environment reviewers compare the requested digest,
  staging evidence, change record, backup evidence, and rollback digest before
  approving the job.
- [ ] Confirm production ACR contains the same manifest digest; the workflow
  promotes it without rebuilding source.
- [ ] Confirm the migration execution succeeds before API/workers change.
- [ ] Repeat database, API, authorization, worker, integration, telemetry, and
  error-rate checks after traffic reaches the new revision.
- [ ] Record deployment URL, Azure deployment names, image digest, database
  revision, reviewers, timestamps, and monitoring links. Record no secrets.

## Rollback

- [ ] Identify a previously deployed digest proven compatible with the current
  database schema.
- [ ] Stop or drain new provider/worker commands when required by the incident.
- [ ] Set `GEOVISION_IMAGE_DIGEST=sha256:...` and run
  `infra/azure/deploy.sh --runtime-only` with the target environment parameters.
  This changes runtime revisions without executing an older migration bundle.
- [ ] Re-run readiness, authorization, queue, worker, integration, and error-rate
  checks. Keep the failed revision and logs available for investigation.
- [ ] Do not run automatic Alembic downgrades. If forward recovery is unsafe,
  follow the separately approved restore/cutover plan and account for writes
  made after the backup.
- [ ] `.do/app.yaml` remains a provider-level reference, not permission to point
  DigitalOcean at the Azure database without a rehearsed data cutover.

Development teardown remains a separate, explicitly destructive operation:
delete only the validated development resource group after retaining required
database and blob backups. Never apply that procedure to staging or production.
