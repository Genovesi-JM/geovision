# GeoVision — Production / Non‑Demo Launch Checklist

This is the exact list of what is already real in code vs. what still needs
**your credentials/infrastructure** to run fully live. Nothing here is
mock‑by‑design; the gates are external accounts and secrets only.

## What is real in code (no demo data)
- **Auth / accounts / Portal** — real `/auth/register`, `/auth/onboarding`,
  login, session refresh against the FastAPI backend.
- **Marketplace** — real catalogue, cart, currency conversion, checkout and
  orders. The web dashboard's old demo portfolio returns empty; KPIs, IoT,
  alerts, entitlement and geospatial come from the API.
- **Payments — bank/IBAN transfer is a fully real path** (manual confirmation,
  no gateway). The storefront now only offers payment methods that actually
  settle: gateway methods (card/Multicaixa/PayPal) are hidden until their
  credentials are configured (see `GET /shop/payment-methods`).
- **IoT** — real MQTT/REST ingestion, device provisioning, alerts, commands,
  irrigation automation. Firmware compiles.

## Run / build the app fully real (non‑demo)
The mobile app is `--dart-define` driven. Demo mode is ON only for dev builds.

```bash
# Run the app NON-DEMO against a real backend (defaults to local :8010)
make mobile-real
# Production (non-demo) release builds — hit api.geovisionops.com
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
| **Production backend hosting** | A live server for `api.geovisionops.com` (the code is ready; the instance is offline / 503). | Deploy the FastAPI app; point DNS + TLS at it. |
| **Card payments (Stripe)** | Stripe account keys. | Set `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`. Card auto‑appears in checkout. |
| **Multicaixa Express** | Merchant credentials. | Set `MULTICAIXA_MERCHANT_ID`, `MULTICAIXA_API_KEY`, `MULTICAIXA_WEBHOOK_SECRET`. |
| **PayPal** | REST app creds. | Set `PAYPAL_CLIENT_ID`, `PAYPAL_SECRET`, `PAYPAL_MODE=live`. |
| **Company IBAN** | Your real IBANs. | Set `COMPANY_IBAN`, `COMPANY_IBAN_INTL` (defaults are placeholders). |
| **Push notifications** | FCM/APNS project. | Set `GV_PUSH_PROVIDER=fcm` (+ config); currently `mock`. |
| **Maps** | Mapbox/ArcGIS key. | Set `GV_MAP_PROVIDER=mapbox` (+ token); currently `demo`. |
| **Android release signing** | A release keystore. | `signingConfigs.release` is wired — just `cp android/key.properties.example android/key.properties`, fill in the keystore path/passwords, and `make android-release`. Without it, release builds fall back to the debug cert. |
| **iOS signing / TestFlight** | Apple Developer account. | Configure signing; upload to TestFlight. |
| **App Store / Play listings** | Store accounts + Privacy/Terms URLs. | Publish `privacy.html`/`terms.html`; complete store listings. |

## Still to build (code, not gated)
- (Nothing outstanding on the code side of this checklist — remaining items
  are the external gates in the table above.)

## Recently landed (code, done)
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
  (token‑auth, optional password check, prunes tokens/identities/profile/
  memberships and empty workspaces; 3 backend tests). Mobile *More → Delete
  account* wired with a confirmation dialog; Privacy/Terms tiles open the
  published pages. Matches the deletion path promised in `privacy.html`.
- `mobile/integration_test/app_test.dart` rewritten for the live
  Portal / My assets / Marketplace / Alerts / More navigation (was driving
  the removed Sites/Work tabs). Analyzes clean; runs on a booted device.
