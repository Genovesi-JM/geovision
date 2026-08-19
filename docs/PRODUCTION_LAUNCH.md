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
| **Android release signing** | A release keystore. | Store keystore; wire `signingConfigs.release` (currently debug‑signed). |
| **iOS signing / TestFlight** | Apple Developer account. | Configure signing; upload to TestFlight. |
| **App Store / Play listings** | Store accounts + Privacy/Terms URLs. | Publish `privacy.html`/`terms.html`; complete store listings. |

## Still to build (code, not gated)
- Rewrite `mobile/integration_test/app_test.dart` for the Portal/My Assets/
  Devices/Alerts/More navigation (currently references the old Sites/Work nav).
- Wire mobile Privacy/Terms + account‑deletion screens (store compliance).
- Publish web Privacy/Terms/Cookie pages.
