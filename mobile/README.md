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

## Run the existing screens against Azure

```bash
flutter pub get
flutter run --dart-define-from-file=config/azure-live.json
```

Choose an iOS simulator, Android emulator or connected device. This profile
uses the Azure Container Apps HTTPS address directly, disables demo mode,
loads devices from the backend and selects OpenStreetMap. Online payments and
push delivery remain disabled until their providers are configured. The file
contains public configuration only; do not put passwords or provider secrets
in Dart defines because they are embedded in the client build.

The Flutter screens connect directly to the GeoVision API. FlutterFlow is not
required to run or maintain this app. See `../docs/MOBILE_AZURE_20260923.md` for
verified connections and remaining gaps.

An opt-in integration test uses an existing synthetic QA account. It reads a
private JSON file at runtime with `email`, `password`, `workspace_id` and
`asset_id` fields; do not commit this file. The simulator must be able to read
that path. The test uses isolated mock token storage, so it does not validate
the native Keychain or persistent session restoration.

```bash
LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 flutter test integration_test/azure_live_test.dart \
  -d <simulator-id> --dart-define-from-file=config/azure-live.json \
  --dart-define=GV_QA_CREDENTIALS_PATH=/absolute/private/qa-customer.json
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

### Customer journey release (2026-09-23)

See `../docs/JOURNEY_FIXES_20260923.md` for the implemented journey fixes, Azure revision, verification and remaining launch gates. New native dependencies require `flutter pub get` and a normal iOS/Android rebuild. The live profile intentionally keeps payments disabled. Report saves use the native OS save/share sheet; evidence upload and live KPI acknowledgement are explicitly unavailable.
