# GeoVision — human gates

Actions the autonomous loop will NOT perform. For each: reason · action · where ·
how to confirm · what the automation does afterwards.

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

## 10. ERPNext staging and Angolan fiscal validation
- **Reason:** The ERPNext adapter, outbox and mobile account view are implemented,
  but production accounting requires hosting, a restricted API user, accounts,
  warehouses, taxes and numbering approved for the operating companies. Generic
  ERP capability is not proof of AGT compliance.
- **Action:** Create an ERPNext staging company/API user and have an Angolan
  accountant validate IVA, SAF-T/AGT requirements and invoice workflow.
- **Where:** ERPNext staging and GeoVision's secret manager; never Git.
- **Confirm:** One sandbox order completes order → invoice → payment → delivery
  reconciliation and the accountant signs off the configuration.
- **After:** Set `ERP_PROVIDER=erpnext`, add restricted credentials, map custom
  fields, deploy the independent event worker, and alert on retry/dead-letter
  counts. Do not enable uncertain-write retries until provider uniqueness is proven.

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
  engineering, environmental, mining or port decision rules.
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
