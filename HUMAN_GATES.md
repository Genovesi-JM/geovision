# GeoVision — human gates

Actions the autonomous loop will NOT perform. For each: reason · action · where ·
how to confirm · what the automation does afterwards.

## 1. Xcode licence / iOS toolchain
- **Reason:** The iOS Simulator build and interactive launch pass, but Xcode 15.4 is below Flutter's recommended Xcode 16+.
- **Action:** Update Xcode through the App Store and install/select a current iOS Simulator runtime.
- **Where:** Mac terminal / Xcode.
- **Confirm:** `flutter doctor` shows iOS green.
- **After:** launcher runs the iOS Simulator build automatically.

## 2. Apple Developer account, signing, App Store Connect, TestFlight
- **Reason:** Certificates, provisioning, distribution are account-bound.
- **Action:** Provide Apple Developer team; configure signing in Xcode.
- **Where:** developer.apple.com / Xcode Signing & Capabilities.
- **Confirm:** a signed device build succeeds.
- **After:** release config + TestFlight steps are prepared, not triggered.

## 3. Android release signing
- **Reason:** Keystore secrets must not be committed.
- **Action:** Create keystore + `android/key.properties` (git-ignored).
- **Confirm:** `flutter build appbundle --release` succeeds.
- **After:** debug builds already run; release wiring is ready.

## 4. Real payment credentials (Stripe / Multicaixa / Apple/Google Pay)
- **Reason:** Live payments + store billing rules.
- **Action:** Supply sandbox keys; confirm store billing policy for GeoVision's
  mix of physical services, hardware and digital subscriptions.
- **After:** mock stays default; provider activates behind its flag only.

## 4a. Production GAIA model credential and AI governance
- **Reason:** The native GAIA chat is connected to the existing `/ai/chat` backend and has a safe demo response, but production AI usage needs an account-bound API key, spending controls and approved customer-data policy.
- **Action:** Supply `OPENAI_API_KEY` through the backend secret manager, choose the production model and approve retention/escalation wording.
- **After:** the same mobile chat activates without embedding any secret in the app; human support remains available as fallback.

## 5. Map/vendor credentials (Mapbox, ArcGIS, DJI, Pix4D, satellite, weather)
- **Reason:** Tokens/SDKs are account-bound.
- **Action:** Provide tokens via `--dart-define` / secret manager.
- **After:** demo/mock stays default; real adapter activates behind its flag.

## 5a. Google Maps and delivery/logistics provider
- **Reason:** The current order tracker is a safe, fully local demonstration. Live
  courier position requires a Google Maps key, billing-enabled project and a
  logistics-provider tracking feed or GeoVision driver application.
- **Action:** Choose the delivery partner and provide restricted staging keys.
- **After:** implement the existing `DeliveryTrackingProvider`; the customer UI
  and demo fallback remain unchanged.

## 6. OAuth client IDs (Google / Microsoft / Apple sign-in)
- **Action:** Provide client IDs/secrets to the backend + redirect URIs.
- **After:** mobile OAuth buttons wire to existing backend routes.

## 7. Production database / deployment / DNS / paid cloud
- **Reason:** Destructive/irreversible or billable.
- **Action:** Human performs any prod migration/deploy/DNS/purchase.
- **After:** automation stays on `autodev/mobile-build`, never pushes to prod.

## 8. Physical hardware / drone tests
- **Reason:** Requires real devices on site.
- **After:** mock IoT + BLE provisioning prepared until hardware is available.

## 9. Physical-device GPS and location privacy review
- **Reason:** The simulator and native builds validate the integration, but field accuracy and the final privacy wording require a real device and legal review.
- **Action:** Test foreground location on one iPhone and one Android device; approve the privacy-policy description before release.
- **After:** tune accuracy/timeouts if required; background location remains disabled.
