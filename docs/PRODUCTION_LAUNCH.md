# GeoVision production and non-demo launch guide

The operational deployment record is the
[release checklist](RELEASE_CHECKLIST.md). It requires the exact staging image
digest, migration-first Azure release, authorization smoke tests, worker and
integration health, reviewer evidence, and a compatible-digest rollback plan.

This is the exact list of what is already real in code vs. what still needs
**your credentials/infrastructure or client cutover work** to run fully live.

## What is real in code (no demo data)
- **Auth / accounts / Portal** — real `/auth/register`, `/auth/onboarding`,
  login, and backend refresh rotation. Flutter uses that rotation with secure
  storage. The static web client intentionally uses access-token-only sessions
  and asks the user to sign in again after the configured short expiry.
- **GeoVision catalogue** — first-party catalogue, cart, currency conversion, checkout and
  orders. The web dashboard's old demo portfolio returns empty; KPIs, IoT,
  alerts, entitlement and geospatial come from the API.
- **Payments** — the provider-neutral payment lifecycle and manual bank-transfer
  workflow are implemented. The checked-in IBAN defaults are placeholders, so
  bank transfer is not a live commercial path until finance supplies and verifies
  the legal beneficiary/bank values and owns reconciliation. Gateway methods are
  hidden until their required configuration fields are present, but that
  structural check is not proof of settlement, webhook, refund, reconciliation,
  or production approval (see `GET /shop/payment-methods`).
- **IoT** — MQTT/REST ingestion, device provisioning, alerts, commands, and
  irrigation automation are implemented. The repository includes an ESP32
  PlatformIO target and simulator; record a fresh compile for the release
  commit and complete the physical wiring, calibration, interlock, network,
  watchdog-owner, and fleet-credential gates before calling a deployment live.

## Run or build the app in non-demo configuration
The mobile app is `--dart-define` driven. Demo mode is ON only for dev builds.

```bash
# Run the app NON-DEMO against a real backend (defaults to local :8010)
make mobile-real
# Production-profile builds target api.geovisionops.com; they do not prove it is live
make android-release      # flutter build apk  --release --dart-define-from-file=dart_defines/production.json
make ios-release          # flutter build ios  --release --dart-define-from-file=dart_defines/production.json
```

`mobile/dart_defines/production.json` sets `GV_FLAVOR=production`,
`GV_DEMO_MODE=false`, `GV_API_BASE_URL=https://api.geovisionops.com`,
`GV_IOT_PROVIDER=backend`, `GV_PAYMENT_PROVIDER=bank_transfer`. Point it at any
real backend by editing `GV_API_BASE_URL` (or use `dart_defines/real-local.json`).

The public website reads `window.API_BASE`; on a `*.geovisionops.com` host it
uses `https://api.geovisionops.com` (see `assets/js/config.js`).

## Gates that need YOU (external accounts / secrets)
| Gate | What's needed | How to flip it on |
|---|---|---|
| **Production backend hosting** | A live, healthy server for `api.geovisionops.com`; verify readiness rather than assuming the saved deployment state. | Deploy the FastAPI app; point DNS + TLS at it. |
| **Entra External ID** | An external tenant, GeoVision API registration and delegated API scope, approved client registrations, exact issuer/audience/tenant configuration, and the web/mobile MSAL client cutover. | Build the client exchange described below, then follow the [Entra cutover runbook](ENTRA_CUTOVER_RUNBOOK.md); prove Graph and invalid tokens are rejected before switching the external login/exchange provider. |
| **Card payments (Stripe)** | Approved Stripe account, keys, webhook, settlement/refund and reconciliation evidence. | Validate the sandbox and signed webhook first; only then set `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, and `STRIPE_WEBHOOK_SECRET` in the deployment secret store. A non-empty key makes the method discoverable, so configuration alone must not be treated as approval. |
| **Multicaixa Express** | Approved merchant account, credentials, signed callback, settlement/refund and reconciliation evidence. | Validate the provider workflow first; only then set `MULTICAIXA_MERCHANT_ID`, `MULTICAIXA_API_KEY`, and `MULTICAIXA_WEBHOOK_SECRET` in the deployment secret store. |
| **PayPal** | Approved REST app, webhook/capture/refund and reconciliation evidence. | Validate the sandbox and production cutover first; only then set `PAYPAL_CLIENT_ID`, `PAYPAL_SECRET`, and `PAYPAL_MODE=live` in the deployment secret store. |
| **Company IBAN** | Your real IBANs. | Set `COMPANY_IBAN`, `COMPANY_IBAN_INTL` (defaults are placeholders). |
| **Odoo 19 ERP/CRM** | Odoo Custom plan/database, reviewed GeoVision bridge addon, least-privilege bot/API key, signed callback, accounting/fiscal configuration and tested rollback. | Complete [Gate 17](../HUMAN_GATES.md#17-odoo-19-live-erpcrm-activation), then select `ERP_PROVIDER=odoo` with server-managed `ODOO_*` secrets and deploy the ERP and event workers. See the [Odoo runbook](ODOO_19_INTEGRATION.md). |
| **Push notifications** | Azure Notification Hubs plus APNs/FCM credentials, signed-app capabilities, platform configuration files and native host channel handlers. | Flutter's channel boundary and backend-managed Azure installation/delivery are implemented. Complete [Gate 16](../HUMAN_GATES.md#16-live-email-and-mobile-push-activation), wire/test the signed host side, then select `apns`, `fcm`, or `azure_notification_hubs` with `GV_PUSH_PROVIDER`. Missing host support fails closed without mock push. |
| **Maps** | Mapbox/ArcGIS key. | Set `GV_MAP_PROVIDER=mapbox` (+ token); currently `demo`. |
| **Android release signing** | A release keystore. | `signingConfigs.release` is wired — just `cp android/key.properties.example android/key.properties`, fill in the keystore path/passwords, and `make android-release`. Without it, release builds fall back to the debug cert. |
| **iOS signing / TestFlight** | Apple Developer account. | Configure signing; upload to TestFlight. |
| **App Store / Play listings** | Store accounts + Privacy/Terms URLs. | Publish `privacy.html`/`terms.html`; complete store listings. |

## Still to build or cut over

- Web and Flutter MSAL sign-in that requests the GeoVision delegated API scope
  and exchanges that access token through `POST /auth/identity/session`, plus a
  real-tenant end-to-end login rehearsal. Phase 3 supplies and tests the secure
  backend boundary; it deliberately does not claim the client cutover is live.
- The signed iOS/Android host must implement the existing
  `com.geovision.notifications/push` method channel and
  `com.geovision.notifications/push_taps` event channel, obtain/rotate the
  platform token and forward taps as the notification ID only. Flutter already
  registers the protected endpoint with GeoVision; the backend manages the
  Azure Notification Hubs installation before delivery.
- A live IoT deployment must assign the offline watchdog/broker subscription to
  one worker owner or add distributed coordination; multiple API replicas must
  not each own that work.

Canonical organizations/workspaces, invitations, Assets, catalogue/orders,
private contractors, missions, datasets, processing, all five sector engines,
reports, notifications, portal capability discovery, durable events, Azure
deployment foundations, and the enterprise integration registry are complete
in code. See [Phase 33 readiness](PHASE_33_READINESS.md) for the evidence and
[known limitations](KNOWN_LIMITATIONS.md) for the remaining external gates.

## Recently landed (code, done)
- **Odoo 19 boundary** — the server-side JSON-2 adapter calls one configured
  bridge, durable order commands remain provider-pinned, and signed callbacks
  project only mapped invoice/stock/purchase status. GeoVision remains
  authoritative; the account, bridge, credentials and live workflow still
  require Gate 17.
- **Android release signing** — `app/build.gradle.kts` now loads
  `android/key.properties` (git-ignored) and signs `release` with the private
  keystore when present, falling back to the debug cert otherwise. Validated:
  `./gradlew :app:signingReport` → BUILD SUCCESSFUL. Template at
  `android/key.properties.example`.
- **Legal pages** — `privacy.html` + `terms.html` published (GeoVision‑specific
  content, site chrome, linked in the footer of index/about/technology,
  `nav.privacy`/`nav.terms` i18n). Satisfies the store‑review Privacy/Terms URL
  requirement; essential‑only cookies noted in the policy.
- **Account deletion (self‑service)** — real `DELETE /auth/account`
  (token auth plus required current-password step-up for password accounts;
  prunes tokens/identities/profile/memberships and empty workspaces). Mobile
  *More → Delete account* collects the password in its confirmation dialog.
  External-only deletion remains gated on a dedicated provider reauthentication
  flow; Privacy/Terms tiles open the published pages.
- `mobile/integration_test/app_test.dart` rewritten for the live
  Portal / My assets / Catalogue / Alerts / More navigation (was driving
  the removed Sites/Work tabs). Analyzes clean; runs on a booted device.
