# GeoVision — verified development status

_Updated: 21 July 2026 on branch `autodev/mobile-build`._

| Check | Result | Evidence |
|---|---|---|
| Flutter dependency resolution | PASS | Flutter 3.44.7 dependencies resolved |
| Dart formatting | PASS | 84 Dart files checked |
| Flutter static analysis | PASS | `flutter analyze`: no issues found |
| Flutter unit/widget tests | PASS | 11 tests passed |
| Android customer journey | PASS | Integration test passed on API 35 ARM emulator: launch → Home → Sites → Alerts → Work |
| FastAPI backend tests | PASS | 6 tests passed, including authenticated mobile site/service-request contracts |
| Alembic migration | PASS | Clean upgrade, one-step downgrade and re-upgrade passed; one migration head remains |
| Android debug build | PASS | `build/app/outputs/flutter-apk/app-debug.apk` |
| iOS Simulator build | PASS | `build/ios/iphonesimulator/Runner.app` |
| iOS customer journey | NOT RUN | iOS build passes; an iOS Simulator runtime/device still needs to be selected for interactive testing |

## Completed in this milestone

- Installed CocoaPods 1.17, Android command-line tools, Android SDK 36, Java 17, platform tools, build tools, NDK and CMake.
- Accepted Android SDK licences and created the `geovision_api35` emulator.
- Added authenticated `/mobile/sites` and `/mobile/service-requests` FastAPI contracts.
- Added persistent, tenant-checked mobile service requests and a reversible Alembic migration.
- Connected real-mode Sites, Work and Reports repositories to compatible backend responses.
- Added durable FIFO offline replay when connectivity returns; failed actions remain queued.
- Added the mobile reset-password completion route and secure backend integration.
- Updated the Mac launcher for CocoaPods UTF-8, Android SDK and Java 17 discovery.

## Remaining before commercial release

- Run the same critical journey on an iOS Simulator and physical devices.
- Add real upload transport, signed report URLs, map tiles, push delivery and hardware-provider credentials.
- Configure OAuth mobile redirect schemes, Apple signing, production secrets and store records.
- Complete UX/accessibility review, privacy/legal content, telemetry and production monitoring.
- Validate real provider sandboxes and physical IoT/drone hardware.

No production deployment or production database migration was performed.
