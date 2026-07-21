# GeoVision — verified development status

_Updated: 21 July 2026 on branch `autodev/mobile-build`._

| Check | Result | Evidence |
|---|---|---|
| Flutter dependency resolution | PASS | `flutter pub get` completed with Flutter 3.44.7 |
| Dart formatting | PASS | 82 Dart files checked |
| Flutter static analysis | PASS | `flutter analyze`: no issues found |
| Flutter unit/widget tests | PASS | 11 tests passed |
| FastAPI backend tests | PASS | 4 tests passed on Python 3.12 |
| Critical integration journey | BLOCKED | no supported iOS/Android device is installed |
| iOS Simulator build | BLOCKED | Xcode first-launch components/runtime unavailable; Xcode 15.4 is below Flutter's recommended 16+; CocoaPods missing |
| Android build | BLOCKED | Android SDK not installed |

## Repairs completed in this run

- Preserved all existing work and moved development from `main` to `autodev/mobile-build`.
- Recovered from the stale Git index lock without deleting repository data.
- Corrected invalid Dart failure constructors and API error mapping.
- Fixed the development/demo environment banner startup crash.
- Replaced the generated counter test with a GeoVision customer-home smoke test.
- Corrected extension imports, stale generated-test assumptions, formatting and analyzer findings.
- Updated the Google OAuth test to match the secure fragment-based redirect contract.
- Hardened the Mac launcher so it does not reset an existing branch and uses Python 3.12/3.11 when available.

## Product completion state

The customer-focused demo foundation is implemented for Home, Sites, maps, alerts, devices, Work, reports, orders, payments, offline storage and authentication. It is not yet a finished commercial release. Real-mode API contracts for sites and service requests, complete report/file handling, full offline synchronisation, platform integrations, signing and device testing remain.

Re-run executable checks with `./START_AUTODEV_MAC.command` after completing the toolchain gates in `HUMAN_GATES.md`.
