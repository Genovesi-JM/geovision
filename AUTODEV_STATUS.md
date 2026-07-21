# GeoVision — verified development status

_Updated: 22 July 2026 on branch `autodev/mobile-build`._

| Check | Result | Evidence |
|---|---|---|
| Flutter dependency resolution | PASS | Flutter 3.44.7 dependencies resolved |
| Dart formatting | PASS | 89 Dart files checked |
| Flutter static analysis | PASS | `flutter analyze`: no issues found |
| Flutter unit/widget tests | PASS | 27 tests passed |
| Android customer journey | PASS | Integration test passed on API 35 ARM emulator: launch → Home → Sites → Alerts → Work |
| FastAPI backend tests | PASS | 9 tests passed, including authenticated commerce and customer site creation |
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
- Added AKZ, EUR and USD store presentation with AKZ as the default customer currency and explicit demo-rate safeguards.
- Expanded product descriptions with suitability, included services and responsible-use context.
- Promoted Request and Store into the persistent customer footer alongside Home, Sites, Alerts, Work and Account.
- Reconciled the mobile catalogue against the live Supply Hub, sector pages and backend seed catalogue.
- Expanded the demo catalogue to 23 sector-aware offerings across agro, livestock, mining, construction, infrastructure and environmental operations.
- Added working product search, type filters, sector filters and service deliverables.
- Replaced presentation-only currency conversion for catalogue items with explicit backend-aligned AKZ/AOA, USD and EUR price-list values.
- Reframed HMA as aerial documentation/GIS support and explicitly excluded mine detection or replacement of accredited field teams.
- Added persistent Portuguese, English, Spanish and French language selection, generated localization classes and iOS locale declarations.
- Localized the persistent navigation and device integration states; established the localization keys used for progressive screen coverage.
- Expanded the IoT contract across API, MQTT, webhook, BLE, LoRaWAN and Modbus gateway transports.
- Added typed success, pending, offline, permission, credential, unsupported, rejected, timeout and error outcomes.
- Added a backend IoT bridge, safe polling fallback, diagnostic/provisioning/command contracts and explicit command confirmation.
- Added demo devices covering every meaningful operational state and automated tests for outcome handling.
- Connected real-mode mobile catalogue, persistent cart, quantity updates, currency selection, authenticated checkout and order history to FastAPI/PostgreSQL.
- Kept demo commerce operational without credentials and added typed cart/checkout response models.
- Added an editable delivery address and currency-faithful order totals; recorded AKZ as ISO `AOA` at the API boundary.
- Restricted order details and order-number lookup to the owning customer or an administrator.
- Fixed checkout payment persistence by normalising numeric order totals to integer minor units.
- Added a backend contract test covering catalogue price lists, cart quantities, AKZ/USD conversion, checkout, ownership enforcement and order history.
- Rebuilt Android and iOS, then installed and launched the updated app on the iPhone 15 Pro Simulator.
- Simplified the persistent footer to six destinations: Home, Sites, Alerts, Work, Store and Account; service requests remain available from Home and Work.
- Added an authenticated customer flow to create a new organisation site with sector, country, province, municipality, area and optional coordinates.
- Enforced organisation ownership and subscription site limits in the FastAPI creation endpoint, with a credential-free demo implementation in Flutter.
- Replaced free-text country, province and municipality fields with the official current Angola hierarchy: 21 provinces and 326 dependent municipality options.
- Added precise site positioning on an OpenStreetMap map and optional high-accuracy device location, requested only after explicit customer action.
- Added iOS and Android foreground-location permission declarations and localized the complete site-creation flow in Portuguese, English, Spanish and French.
- Expanded structured offline geography to Angola, Mozambique, Namibia, Zambia, South Africa, Democratic Republic of the Congo, Republic of the Congo, Portugal, Spain, France and Brazil.
- Added dependent country → province/state → city/municipality selection with localized country names; Angola retains its verified 21-province/326-municipality override.
- Added an offline Visual Guides centre accessible from Account, Devices and relevant Store products.
- Added illustrated step-by-step guidance for soil sensors, weather stations, equipment maintenance, alerts/KPIs, offline synchronisation and drone-operation preparation.
- Added localized Portuguese, English, Spanish and French guide content, category/search filters, safety warnings and direct technician-request actions for high-risk work.

## Remaining before commercial release

- Run the complete critical journey on physical iOS and Android devices.
- Add real upload transport, signed report URLs, map tiles, push delivery and hardware-provider credentials.
- Configure OAuth mobile redirect schemes, Apple signing, production secrets and store records.
- Complete UX/accessibility review, privacy/legal content, telemetry and production monitoring.
- Validate real provider sandboxes and physical IoT/drone hardware.
- Connect real supplier stock, tax/fiscal invoicing, delivery quotations and live logistics status.

No production deployment or production database migration was performed.
