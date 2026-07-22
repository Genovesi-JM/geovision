# GeoVision — Mac developer guide

GeoVision is one hand-coded **Flutter** application (shared Dart, native only where
required) for iOS and Android, backed by the existing **FastAPI** backend in
`/backend`. The public marketing website at the repository root is unchanged.

## TL;DR — normal usage

```bash
./START_AUTODEV_MAC.command      # full build + verify loop on the Mac toolchain
# or
make dev                         # start FastAPI + GAIA + app in one command
```

The app boots with a realistic agricultural demo dataset. `make dev` also starts
the local FastAPI backend so GAIA remains available; without an OpenAI key GAIA
uses the backend's clearly labelled deterministic demo knowledge.

## One-time setup

1. Install Flutter (stable): https://docs.flutter.dev/get-started/install/macos
2. Install Xcode + command-line tools (`xcode-select --install`) and accept the licence (`sudo xcodebuild -license`).
3. (Optional) Android Studio + SDK for Android builds.
4. `flutter doctor -v` should be green for iOS at minimum.

## Project layout

```
geovision/
├── backend/            FastAPI backend (reused, not duplicated)
├── mobile/             the Flutter app  ← all mobile work lives here
│   ├── lib/            feature-oriented Dart (see MOBILE_ARCHITECTURE.md)
│   ├── test/           unit + widget tests
│   ├── integration_test/  critical-journey test (runs on device/simulator)
│   └── assets/
├── automation/         tasks backlog + run logs
├── START_AUTODEV_MAC.command
├── Makefile
└── docs / *.md         architecture, scope, integrations, human gates
```

> The `mobile/ios` and `mobile/android` native folders are generated on first run
> by `flutter create` (the launcher does this automatically). This keeps the
> canonical platform scaffolding correct rather than hand-forged.

## Running the backend (optional, for non-demo mode)

```bash
make backend-run        # http://127.0.0.1:8010
```

Then run the app against it:

```bash
cd mobile
flutter run --dart-define=GV_FLAVOR=dev --dart-define=GV_DEMO_MODE=false
```

## Flavors / configuration

All config is passed via `--dart-define` (never committed). See `.env.example`.

| Define | Default | Purpose |
|--------|---------|---------|
| `GV_FLAVOR` | `dev` | `dev` \| `staging` \| `prod` |
| `GV_API_BASE_URL` | flavor default | Override backend URL |
| `GV_DEMO_MODE` | on for dev/staging | Force demo data on/off |
| `GV_MAP_PROVIDER` | `demo` | `demo` \| `mapbox` |
| `GV_PAYMENT_PROVIDER` | `mock` | `mock` \| `bank_transfer` \| `stripe` |
| `GV_PUSH_PROVIDER` | `mock` | `mock` \| `apns` \| `fcm` |

## What the launcher verifies (objective evidence)

Preflight → git checkpoint on `autodev/mobile-build` → `flutter pub get` →
`gen-l10n` → `dart format` → `flutter analyze` → `flutter test` → backend pytest →
iOS Simulator build → Android debug build → writes `AUTODEV_STATUS.md`.

Each step runs the real tool; a failure is recorded, never hidden.
