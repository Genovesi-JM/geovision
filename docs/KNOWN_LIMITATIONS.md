# GeoVision known limitations and backlog

The restructure is **pilot-ready in the strongest verified local/integrated
environment, provided IoT administration uses one Workspace per
Organization**. It is **not production-ready** until the launch blockers below
have external evidence and approval. An implemented adapter or workflow file
is not evidence that a live provider or deployment works.

## Production launch blockers

| Blocker | Required evidence to close it |
|---|---|
| No approved staging deployment evidence for the Phase 34 six-sector commit | Successful main CI, staging workflow URL, commit, immutable image digest, API URL, `phase34_sector_taxonomy_v1` execution, operator and timestamp. Phase 33 evidence is historical and cannot close this gate. |
| Production-like PostgreSQL/PostGIS migration and restore rehearsal is external | Backup ID, isolated restore, upgrade to the single Alembic head, PostGIS/index verification, measured recovery result, and compatible rollback digest. |
| Entra client cutover is incomplete | Real tenant/app/scope configuration, web and Flutter MSAL exchange, issuer/audience and negative-token proof, rollback, and Gate approval. Internal auth remains the pilot path. |
| Mobile distribution is not approved | Private Android release signing, Apple team/TestFlight signing, store accounts/listings, privacy declarations, and device-level install/update evidence. |
| Live push/email is not approved | Signed native APNs/FCM channel implementation, Azure Notification Hubs/SMTP secrets, endpoint rotation/tap rehearsal, and delivery monitoring. In-app inbox remains available. |
| Live IoT offline supervision is not deployed independently | Approved IoT Hub/MQTT topology, one watchdog owner outside horizontally scaled API replicas, fleet credential rotation, alert delivery and offline recovery rehearsal. |
| Legacy IoT fleet administration is organization-scoped | Replace or harden the compatibility asset/device/rule/alert routes so every operation resolves the selected Workspace and proves same-organization cross-workspace denial. Until then, an IoT pilot must use one Workspace per Organization. Customer KPI, observation, action, notification, and deep-link projections remain workspace-scoped. |
| Sector KPI, observation, and action policies lack field/scientific approval | Complete Human Gate 14 and the Agriculture-specific Gate 14a with representative golden datasets, calibrated sensors, boundary/missing-data tests, accountable specialist approval, exact applicability profiles, monitored drift, and rollback triggers. Until then the results are technical pilot evidence, not validated operational prescriptions. |
| Customer report publication governance is not approved | Complete Human Gate 15 with named reviewers per report type/sector, representative exact-number and cross-tenant tests, publication/supersession rehearsal, privacy review, and a rollback rule. Keep deterministic narrative and the review lifecycle; do not activate an external model merely because an adapter can be configured. |
| External commercial/provider gates are unverified | Merchant/ERP/provider accounts, least-privilege secrets, mapping, licences, cost limits, idempotency, failure/reconciliation tests, monitoring and rollback for each enabled provider. |
| Operational ownership is external to code | Named on-call/release/data owners, budgets, alerts, retention, incident runbooks, RTO/RPO approval, data-processing/privacy review, and Human Gate 18. |

## Pilot constraints

- Synthetic six-sector data and deterministic providers are clearly marked and
  must never be mixed with customer evidence or enabled in deployed profiles.
- The local test database is SQLite. PostgreSQL/PostGIS is the deployment
  target and the CI migration service is the authoritative automated rehearsal.
- The static portal has browser contract tests and uses backend capability
  responses, but final staging tests need an approved test identity and real
  deployed URL.
- Raw IoT receipts remain the telemetry source of truth. Only in-order numeric
  readings linked to a canonical Workspace Asset become technical KPIs; old
  store-and-forward replay is retained without changing the current decision
  projection. A failed derived projection is retried idempotently from the
  durable receipt by the event worker. Alert observations begin as
  `NEEDS_REVIEW`.
- Legacy IoT provisioning and fleet-management routes retain company-level
  authorization semantics and do not consistently select `X-Workspace-ID`.
  Linked customer intelligence is workspace-scoped, but multi-workspace fleet
  administration requires a reviewed canonical replacement before production.
- Deterministic report narrative is the approved fallback. The legacy external
  AI route is not measurement or diagnostic authority.
- Payment-method discovery checks configuration shape, not provider approval or
  successful settlement. The checked-in IBANs are placeholders; expose no live
  payment method until finance/provider validation and reconciliation ownership
  are recorded.
- Compatibility routes/classes/tables remain for deployed clients. New code
  must use canonical module services; removal needs usage evidence and a
  separately rehearsed migration.
- Historical mobile service requests whose legacy Site was deleted before the
  canonical workspace migration are quarantined with no inferred tenant scope.
  They are intentionally absent from customer and Operations APIs until an
  operator completes an audited data repair; guessing a workspace would risk a
  cross-customer disclosure.
- `.do/app.yaml` is retained as a recoverable provider-level rollback reference
  until Azure traffic/data cutover is proven. No Render configuration is
  present. Mobile native platform files related to push/signing are retained;
  removing them before signed-host cutover would be unsafe.

## Post-launch enhancements

- Implement only the provider scaffolds justified by a contracted customer,
  then close their individual live gates.
- Move any remaining API-hosted MQTT/watchdog compatibility lifecycle into an
  explicitly single-owner IoT worker/topology before high-availability scale.
- Replace legacy mobile service and shop facades after all clients use the
  canonical order/fulfilment/report contracts and telemetry proves no use.
- Upgrade `package_info_plus` before Flutter enforces built-in Kotlin plugin
  support, and upgrade `flutter_secure_storage` before Flutter makes iOS Swift
  Package Manager support mandatory. Current pinned dependencies still analyze,
  test, and build successfully.
- Add scheduled outcome-verification KPIs for more catalogue services as field
  evidence becomes available.
- Add performance, capacity, long-duration edge-replay, accessibility-device,
  and disaster-recovery exercises beyond the functional release suite.
- Complete provider cost/usage dashboards and automated SLO alerts once live
  traffic establishes defensible thresholds.
