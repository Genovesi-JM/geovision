# GeoVision Mobile

Customer-focused Flutter application for GeoVision on iOS and Android. It is an operational companion—not a copy of the public marketing website.

## Current capabilities

- Five-destination customer shell: Home, Sites, Alerts, Work and Account
- Agricultural-first, multi-sector site and KPI models
- Demo maps, alerts, IoT devices, reports, service requests, catalogue and orders
- Provider adapters for maps, push notifications, IoT and payments
- Offline cache and durable pending-action queue
- FastAPI authentication integration with secure token storage
- English and Portuguese localisation foundation

## Run in demo mode

```bash
flutter pub get
flutter run --dart-define=GV_FLAVOR=dev --dart-define=GV_DEMO_MODE=true
```

## Verify

```bash
dart format --output=none --set-exit-if-changed lib test integration_test
flutter analyze
flutter test
flutter build ios --simulator --debug
flutter build apk --debug
```

The platform builds require the toolchains listed in `../HUMAN_GATES.md`. Provider credentials must be supplied through `--dart-define` or a secret manager and must never be committed.
