# GeoVision — verified development status

_Updated: 21 July 2026 on branch `autodev/mobile-build`._

| Check | Result | Evidence |
|---|---|---|
| Flutter dependency resolution | PASS | Flutter 3.44.7 dependencies resolved |
| Dart formatting | PASS | 89 Dart files checked |
| Flutter static analysis | PASS | `flutter analyze`: no issues found |
| Flutter unit/widget tests | PASS | 14 tests passed |
| Android customer journey | PASS | Integration test passed on API 35 ARM emulator: launch → Home → Sites → Alerts → Work |
| FastAPI backend tests | PASS | 6 tests passed, including authenticated mobile site/service-request contracts |
| Alembic migration | PASS | Clean upgrade, one-step downgrade and re-upgrade passed; one migration head remains |
| Android debug build | PASS | `build/app/outputs/flutter-apk/app-debug.apk` |
| iOS Simulator build | PASS | `build/ios/iphonesimulator/Runner.app` |
| iOS interactive launch | PASS | Updated app installed and launched on iPhone 15 Pro Simulator (iOS 17.5) |

## Completed in this milestone

- Installed CocoaPods 1.17, Android command-line tools, Android SDK 36, Java 17, platform tools, build tools, NDK and CMake.
- Accepted Android SDK licences and created the `geovision_api35` emulator.
- Added authenticated `/mobile/sites` and `/mobile/service-requests` FastAPI contracts.
- Added persistent, tenant-checked mobile service requests and a reversible Alembic migration.
- Connected real-mode Sites, Work and Reports repositories to compatible backend responses.
- Added durable FIFO offline replay when connectivity returns; failed actions remain queued.
- Added the mobile reset-password completion route and secure backend integration.
- Updated the Mac launcher for CocoaPods UTF-8, Android SDK and Java 17 discovery.
- Added a customer commerce hub inspired by the supplied GeoVision concepts without copying the marketing website.
- Added seed, agricultural input, equipment, sensor/IoT and service catalogue categories.
- Added product details, cart quantities, delivery address, payment-method selection and a safe demo checkout.
- Added richer order history, order details and delivery tracking with a map-like route, vehicle marker and fulfilment timeline.
- Added a `DeliveryTrackingProvider` boundary plus explicit Google Maps placeholder; no key or live location is embedded.
- Replaced the Home reports shortcut with Store while keeping reports available from Account.
- Corrected a fractional KPI-card overflow found during live iPhone Simulator verification.

## Remaining before commercial release

- Run the complete critical journey on physical iOS and Android devices.
- Add real upload transport, signed report URLs, map tiles, push delivery and hardware-provider credentials.
- Configure OAuth mobile redirect schemes, Apple signing, production secrets and store records.
- Complete UX/accessibility review, privacy/legal content, telemetry and production monitoring.
- Validate real provider sandboxes and physical IoT/drone hardware.
- Connect the store to backend inventory, tax, delivery quotations and real logistics status.

No production deployment or production database migration was performed.
