# GeoVision — human gates

Actions the autonomous loop will NOT perform. For each: reason · action · where ·
how to confirm · what the automation does afterwards.

## Spain-first launch order

The initial commercial baseline is Spain: Spanish customer experience, EUR,
Europe/Madrid, Spanish legal and fiscal review, Stripe/card plus SEPA, and
Spain-focused Google Maps, AEMET and MITECO validation. Angola remains a
supported expansion market, but its Multicaixa and fiscal gates must not delay
the first Spanish pilot. The ordered execution plan is maintained in
[the Spain-first launch audit](docs/SPAIN_FIRST_LAUNCH_AUDIT.md).

## 1. Xcode licence / iOS toolchain
- **Reason:** The iOS Simulator build and interactive launch pass, but Xcode 15.4 is below Flutter's recommended Xcode 16+.
- **Action:** Update Xcode through the App Store and install/select a current iOS Simulator runtime.
- **Where:** Mac terminal / Xcode.
- **Confirm:** `flutter doctor` shows iOS green.
- **After:** launcher runs the iOS Simulator build automatically.

## 2. Apple Developer account, signing, App Store Connect, TestFlight
- **Reason:** Certificates, provisioning, distribution are account-bound.
- **Action:** Provide Apple Developer team; configure signing in Xcode.
- **Where:** developer.apple.com / Xcode Signing & Capabilities.
- **Confirm:** a signed device build succeeds.
- **After:** release config + TestFlight steps are prepared, not triggered.

## 3. Android release signing
- **Reason:** Keystore secrets must not be committed.
- **Action:** Create keystore + `android/key.properties` (git-ignored).
- **Confirm:** `flutter build appbundle --release` succeeds.
- **After:** debug builds already run; release wiring is ready.

## 4. Real payment credentials (Stripe / Multicaixa / Apple/Google Pay)
- **Reason:** Live payments + store billing rules.
- **Action:** Supply sandbox keys; confirm store billing policy for GeoVision's
  mix of physical services, hardware and digital subscriptions.
- **After:** mock stays default; provider activates behind its flag only.

## 4a. Production GAIA model credential and AI governance
- **Reason:** The native GAIA chat is connected to the existing `/ai/chat` backend and has a safe demo response, but production AI usage needs an account-bound API key, spending controls and approved customer-data policy.
- **Action:** Supply `OPENAI_API_KEY` through the backend secret manager, choose the production model and approve retention/escalation wording.
- **After:** the same mobile chat activates without embedding any secret in the app; human support remains available as fallback.

## 5. Map/vendor credentials (Mapbox, ArcGIS, DJI, Pix4D, satellite, weather)
- **Reason:** Tokens/SDKs are account-bound.
- **Action:** Provide tokens via `--dart-define` / secret manager.
- **After:** demo/mock stays default; real adapter activates behind its flag.

## 5a. Google Maps and delivery/logistics provider
- **Reason:** The current order tracker is a safe, fully local demonstration. Live
  courier position requires a Google Maps key, billing-enabled project and a
  logistics-provider tracking feed or GeoVision driver application.
- **Action:** Choose the delivery partner and provide restricted staging keys.
- **After:** implement the existing `DeliveryTrackingProvider`; the customer UI
  and demo fallback remain unchanged.

## 6. OAuth client IDs (Google / Microsoft / Apple sign-in)
- **Action:** Provide client IDs/secrets to the backend + redirect URIs.
- **After:** mobile OAuth buttons wire to existing backend routes.

## 7. Production database / deployment / DNS / paid cloud
- **Reason:** Destructive/irreversible or billable.
- **Action:** Human performs any prod migration/deploy/DNS/purchase.
- **After:** automation stays on `autodev/mobile-build`, never pushes to prod.

## 8. Physical hardware / drone tests
- **Reason:** Requires real devices on site.
- **After:** mock IoT + BLE provisioning prepared until hardware is available.

## 8a. DJI automated-flight activation
- **Reason:** Mission execution requires a DJI Developer application, supported
  aircraft/firmware, provider credentials, pilot validation and field safety tests.
  DJI Neo is deliberately limited to media import because it is not an MSDK V5
  automated-flight aircraft.
- **Action:** Register the GeoVision Android application with DJI Developer,
  provide restricted staging credentials, select a supported aircraft and approve
  the operational checklist with the responsible pilot/regulator.
- **Confirm:** A supervised staging mission completes planning → provider handoff
  → telemetry → media sync without bypassing geofencing or pilot controls.
- **After:** Activate the native DJI adapter behind its feature flag. The backend
  will continue to store plans/audit state and will never hold unrestricted
  production flight authority.

## 9. Physical-device GPS and location privacy review
- **Reason:** The simulator and native builds validate the integration, but field accuracy and the final privacy wording require a real device and legal review.
- **Action:** Test foreground location on one iPhone and one Android device; approve the privacy-policy description before release.
- **After:** tune accuracy/timeouts if required; background location remains disabled.

## 10. ERP staging and Spanish fiscal validation
- **Reason:** The provider-neutral ERP boundary, Odoo/ERPNext adapters, outbox
  and mobile account view are implemented, but production accounting requires
  hosting, a restricted API user, accounts, warehouses, taxes and numbering
  approved for the operating companies. Generic ERP capability is not proof of
  Spanish or Angolan fiscal compliance.
- **Action:** Create a Spanish staging company and restricted API user in the
  selected ERP, then have a Spanish accountant validate IVA, invoicing,
  numbering, record retention and the complete order-to-reconciliation flow.
  Validate Angolan AGT requirements separately before the Angola expansion.
- **Where:** The selected ERP staging environment and GeoVision's secret
  manager; never Git.
- **Confirm:** One sandbox order completes order → invoice → payment → delivery
  reconciliation in EUR and the Spanish accountant signs off the configuration.
- **After:** Select the reviewed `ERP_PROVIDER`, add restricted credentials,
  map custom fields, deploy the independent ERP and event workers, and alert on
  retry/dead-letter counts. Do not requeue an uncertain write until provider
  uniqueness and its external result have been reconciled.

## 11. Live photogrammetry processor activation
- **Reason:** The deterministic provider, durable processing worker and NodeODM
  adapter are implemented, but real image processing is compute-intensive and
  output quality depends on cameras, overlap, control points, terrain and the
  approved processor/version. A working API is not measurement validation.
- **Action:** Provision an isolated NodeODM staging node, pin/review its image and
  licence obligations, deliver any token through the secret manager, size CPU,
  memory and storage, and approve representative datasets for every advertised
  output. PIX4D, Autodesk and Bentley remain unavailable scaffolds unless a
  separate commercial and technical integration is approved.
- **Where:** Staging network, NodeODM host, object storage and GeoVision secret
  manager; never customer clients or Git.
- **Confirm:** A representative flight completes upload → processing → output
  registration with checked orthomosaic/elevation accuracy, retry/cancel tests,
  resource monitoring and a rollback rehearsal.
- **After:** Set `PROCESSING_PROVIDER=nodeodm`, enable automatic job creation,
  deploy the event and processing workers, and alert on `FAILED`,
  `NEEDS_REVIEW`, stale-claim and queue-depth counts.

## 12. Live satellite and weather intelligence activation

- **Reason:** Copernicus and AEMET adapters, durable scheduling, caching and
  provenance are implemented, but external availability, quotas, licences,
  geographic/station coverage and scientific interpretation require an
  account-bound operational decision. Source observations are not validated
  agronomic or engineering conclusions.
- **Action:** Approve the required Copernicus access level and AEMET OpenData
  key, attribution/licence terms, request and storage budgets, representative
  assets/date windows, allowed imagery downloads and customer-facing wording.
  Keep credentials in the server secret manager.
- **Where:** Provider portals, GeoVision staging, PostgreSQL/object storage and
  the monitoring/alerting system; never mobile/web clients or Git.
- **Confirm:** Representative Spain assets complete live scene and weather
  acquisition twice (including a cache hit), a scheduled weekly run, bounded
  retry/recovery, provenance review, tenant-isolation test and quota/cost alert.
- **After:** Select `SATELLITE_PROVIDER=copernicus` and/or
  `WEATHER_PROVIDER=aemet`, deploy the independent intelligence worker, and
  monitor failed/retrying/stale acquisitions, schedule failures, provider
  latency, cache hit rate and download/storage consumption. Azure Maps Weather
  remains unavailable until a separately approved adapter is implemented.

## 13. Physical IoT/FieldBox and Azure IoT Hub activation

- **Reason:** The common telemetry contract, durable receipts, IoT Hub/Event
  Grid adapter, simulator, ESP32 queue and Raspberry Pi FieldBox reference are
  implemented, but live cloud routing and physical actuators require
  account-bound infrastructure and supervised field safety validation.
- **Action:** Provision a restricted staging IoT Hub/Event Grid subscription;
  store its random custom webhook secret in the backend secret manager; register
  exact external device IDs; commission representative ESP32 and FieldBox
  hardware; approve clock sync, disk/flash bounds and wear, queue-overflow policy,
  network loss/recovery, command allowlists, physical override and every local
  fail-safe. Do not enable mains or safety-critical loads.
- **Where:** Azure staging, GeoVision secret manager/monitoring, isolated bench,
  then a supervised field site; never customer clients or Git.
- **Confirm:** The simulator and physical devices both complete live, duplicate,
  disconnected queue, reconnect replay, out-of-order, provider retry, offline
  watchdog, command acknowledgement and forced-interlock scenarios with the
  correct canonical Asset and no duplicate readings/events.
- **After:** Set `IOT_CLOUD_PROVIDER=azure_iot_hub`, configure the exact hub and
  32+ character delivery secret, enable `AZURE_IOT_HUB_ENABLED`, deploy one IoT
  maintenance worker, and alert on rejected ingress, receipt latency/volume,
  offline devices, edge queue depth/drops and command failures. Remote actuator
  control stays disabled per device until its separate supervised approval.

## 14. Sector KPI, observation and action validation

- **Reason:** The shared engine enforces provenance, confidence, validation,
  thresholds, versioning and outcomes, but code alone cannot approve agronomic,
  construction/infrastructure, environmental, mining, industrial/energy/
  utilities, or port/logistics decision rules. Apply this gate independently
  to each canonical sector in `docs/SECTOR_TAXONOMY.md`.
- **Action:** For each sector registration, nominate an accountable subject
  expert; approve representative training/validation datasets, units,
  thresholds, baselines, geography/season/asset applicability, confidence
  calibration, false-positive/negative tolerance, customer wording and the
  actions that may be recommended automatically. Record the exact algorithm
  version and rollback trigger.
- **Where:** GeoVision staging, controlled source datasets, the algorithm/model
  register and operational review; never in client-side constants or prompts.
- **Confirm:** Golden datasets reproduce expected KPI/status results; blind
  review covers boundary values and missing/low-confidence inputs; every
  observation remains visibly validated or unvalidated; action recommendations
  are safe, reversible where applicable and link only to GeoVision offers.
- **After:** Enable only the approved sector calculator/rule versions, monitor
  drift and alert/action outcomes, and return affected KPIs to `UNKNOWN` if
  provenance, source quality or calibration falls outside the approved scope.

### 14a. Agriculture bundle 1.0.0 approval

- **Reason:** Phase 18 activates a cautious Agriculture screening bundle, but
  its initial NDVI, water-stress, soil-moisture, vegetation-coverage and area
  thresholds are not a substitute for crop-, growth-stage-, soil-, sensor- and
  season-specific validation.
- **Action:** An accountable agronomist must approve each enabled threshold,
  source schema, calibration/freshness rule, zone-area method, wording and
  recommended GeoVision follow-up for the exact intended crops and regions.
- **Confirm:** Representative drone, satellite, weather and calibrated sensor
  campaigns reproduce expected values and boundary statuses; missing,
  conflicting and out-of-range evidence stays `UNKNOWN`/`NO_DATA`; blind review
  finds no disease, pest, nutrient, chemical, irrigation-volume or yield claim.
- **After:** Record the approved applicability profile and algorithm version,
  monitor false-positive/negative and action outcomes, and disable or roll back
  the affected calculator when evidence falls outside that profile.

## 15. External report narrative provider and publication approval

- **Reason:** The deterministic report engine, exact-data renderer, validation,
  fallback, review and publication lifecycle are implemented. A live language
  model still requires account-bound credentials, deployment access, privacy
  review and a representative evaluation; code presence is not authorization
  to send customer evidence to an external provider.
- **Action:** Approve the provider, region, model/deployment, data retention and
  training settings, tenant and network controls, content policy, prompt/output
  schema, evaluation set, cost ceiling and rollback trigger. Assign accountable
  human and specialist reviewers for each report type and sector.
- **Where:** GeoVision staging, the provider tenant and server-side secret
  manager; never a browser/mobile client, report context, audit entry or Git.
- **Confirm:** Representative reports preserve every source number exactly,
  reject unknown fields/evidence and invented numerical claims, survive outage
  through deterministic fallback, remain invisible before publication, and
  pass cross-tenant, audit, download and supersession tests.
- **After:** Implement and enable the dedicated adapter, retain deterministic
  fallback, monitor invalid-output/fallback/review rates and disable external
  generation immediately when the approved privacy or quality scope is lost.

## 16. Live email and mobile push activation

- **Reason:** The durable inbox, retry worker, SMTP/Azure Notification Hubs
  adapters and Flutter `NativePushProvider` channel boundary are implemented,
  but real delivery still depends on signed iOS/Android host channel handlers,
  account-bound SMTP/Azure/APNs/FCM configuration and physical-device testing.
  Provider acceptance is not proof of display on a device, and neither SMTP nor
  Notification Hubs proves exactly-once delivery after an uncertain
  acknowledgement.
- **Action:** Provision a restricted SMTP account and Azure Notification Hubs
  namespace/hub; configure APNs credentials and the FCM v1 credential in Azure;
  create a backend-only least-privilege hub policy with the registration/listen
  and send rights required by installation PUT plus template delivery; approve sender/domain
  authentication, templates, privacy/retention, quotas, cost alerts and customer
  wording. Store all credentials in the server secret manager. Implement the
  signed native host side of `com.geovision.notifications/push` and
  `com.geovision.notifications/push_taps`, including permission, APNs/FCM token
  acquisition/rotation and notification-tap forwarding. Add the approved Apple
  entitlements and Firebase/Apple platform configuration files without
  embedding any Azure or SMTP server credential. Flutter sends the token to
  GeoVision; the backend decrypts and validates it, then idempotently creates or
  updates the Azure installation immediately before its targeted template send.
  Missing host support must continue to fail closed without mock delivery.
- **Where:** SMTP provider, Azure Notification Hubs, Apple Developer, Firebase,
  signed staging apps, GeoVision staging database/workers and monitoring; never
  Git, a client environment file, a push payload, an event or an audit detail.
- **Confirm:** On one physical iOS and one physical Android device, register,
  rotate and revoke an installation and receive a template push whose app data
  contains only `notification_id`. Tap report, Asset, action and order examples
  and confirm the authenticated API opens the exact current target. Revoke the
  user's membership after sending and confirm the same tap fails closed. Send
  an invitation and ordinary notification through authenticated STARTTLS SMTP;
  confirm the one-time token never appears in database plaintext or logs.
  Exercise duplicate events, a device-alert burst, quiet hours, minimum
  severity, endpoint revocation, provider timeout/throttling, retry recovery and
  dead-letter requeue. Throughout an outage, confirm the business result and
  in-app history remain intact.
- **After:** Set `NOTIFICATION_PROVIDER=smtp`, provide the approved SMTP and
  `AZURE_NOTIFICATION_HUBS_*` secrets, deploy exactly the required event and
  notification worker processes, and alert on oldest due work, retries, stale
  claims, dead letters, provider latency/errors and endpoint suppressions. Keep
  SMS disabled until its own adapter and gate exist, and reconcile uncertain
  provider outcomes rather than blindly re-sending them.

## 17. Odoo 19 live ERP/CRM activation

- **Reason:** The provider-neutral ERP boundary, Odoo 19 JSON-2 adapter,
  provider-pinned durable commands, external-reference/status projection and
  signed replay-safe callback contract are implemented. A live Odoo database,
  bridge addon, API key, accounting setup and callback signer are account- and
  deployment-bound. The adapter is not evidence of fiscal correctness or safe
  provider-side idempotency.
- **Action:** Acquire an Odoo 19 Custom plan; create a duplicate/staging database;
  install and review the custom `geovision.integration.bridge` addon; verify its
  field/resource allowlist, company scoping and unique idempotency constraint;
  create a dedicated least-privilege bot and API key; configure the independent
  callback HMAC secret; approve network/TLS restrictions, retention, monitoring,
  expiry ownership and a key rotation schedule of no more than three months.
  Configure companies, currencies, taxes, accounts, warehouses, suppliers and
  numbering with an accountant qualified for the operating jurisdictions.
- **Where:** Odoo staging, GeoVision staging/secret manager, edge gateway and
  monitoring; never Flutter/web clients, Git, event payloads or logs.
- **Confirm:** The target database reports Odoo 19 and its `/doc` page exposes the
  reviewed bridge. A representative GeoVision order syncs twice with one Odoo
  result, then signed invoice, stock and purchase callbacks update only its
  external projection. Reject a bad signature, expired/future timestamp,
  duplicate/conflicting event, unknown mapping, external-ID mismatch and
  cross-organization attempt. Exercise timeout, throttling, Odoo outage, stale
  claim, bounded retry, dead-letter inspection/requeue, API-key rotation,
  backup/restore and rollback. Throughout, GeoVision checkout, assets and
  intelligence remain available and the accountant signs off the commercial and
  Spanish launch workflow. Repeat the jurisdiction-specific sign-off before an
  Angolan commercial cutover.
- **After:** Set `ERP_PROVIDER=odoo`, load `ODOO_*` values only from the server
  secret manager, deploy the independent ERP and event workers and alert on oldest due
  work, claim age, retry/dead-letter volume, authentication/rate-limit errors,
  callback rejects/age and mapping drift. Retain the old provider long enough to
  drain or reconcile rows already pinned to it; never relabel those rows. Follow
  [the Odoo 19 runbook](docs/ODOO_19_INTEGRATION.md) for rotation and rollback.

## 18. Azure subscription deployment and production cutover

- **Reason:** The Azure Bicep foundation, shared container image, explicit
  migration job, readiness checks and guarded release helper are implemented,
  but no account-bound Azure resources, billable services, production data,
  DNS, certificates or live provider credentials have been created or tested.
  Local validation cannot prove regional quota, tenant policy, real workload
  performance, backup restore, data migration or a zero-loss traffic cutover.
- **Action:** An Azure owner must approve the subscription, region, resource
  names, budget/alerts, RBAC assignees, data residency and network policy. Run
  the documented `what-if`, provision an isolated dev/staging environment,
  build an immutable image, rehearse backup/restore and migration, configure
  approved provider secrets, and approve the DNS/traffic change only after the
  staging evidence is reviewed.
- **Where:** Azure staging and the organization DNS/provider consoles, following
  [the Azure deployment runbook](infra/azure/README.md) and
  [release checklist](docs/RELEASE_CHECKLIST.md); secrets stay in the
  protected deployment environment and Key Vault, never Git or chat logs.
- **Confirm:** `/health` and schema-gated `/ready` pass; authentication and
  organization isolation pass; all five workers consume and recover work;
  Blob, Service Bus, monitoring and external integrations pass representative
  checks; database restore and compatible-image rollback are rehearsed; and a
  monitored canary shows no error, latency or data-consistency regression.
- **After:** Cut traffic gradually, retain the DigitalOcean definition and last
  compatible image/database recovery point through the agreed observation
  window, then decommission the old environment only under a separate human
  approval. **Production cutover is not currently safe or authorized.**
