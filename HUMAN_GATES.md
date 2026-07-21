# GeoVision — human gates

Actions the autonomous loop will NOT perform. For each: reason · action · where ·
how to confirm · what the automation does afterwards.

## 1. Xcode licence / iOS toolchain
- **Reason:** `flutter doctor` reports Xcode first-launch components missing, Xcode 15.4 below Flutter's recommended Xcode 16+, and CocoaPods missing.
- **Action:** Update Xcode, open it once and install prompted components, run `sudo xcodebuild -runFirstLaunch`, install an iOS Simulator runtime, and install CocoaPods.
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

## 3a. Android development toolchain
- **Reason:** No Android SDK is currently installed, so even debug builds cannot run.
- **Action:** Install Android Studio and its SDK/platform tools, accept Android licences, and create an emulator.
- **Confirm:** `flutter doctor -v` shows the Android toolchain and `flutter devices` lists the emulator.
- **After:** run `flutter build apk --debug` and the mobile integration journey.

## 4. Real payment credentials (Stripe / Multicaixa / Apple/Google Pay)
- **Reason:** Live payments + store billing rules.
- **Action:** Supply sandbox keys; confirm store billing policy for GeoVision's
  mix of physical services, hardware and digital subscriptions.
- **After:** mock stays default; provider activates behind its flag only.

## 5. Map/vendor credentials (Mapbox, ArcGIS, DJI, Pix4D, satellite, weather)
- **Reason:** Tokens/SDKs are account-bound.
- **Action:** Provide tokens via `--dart-define` / secret manager.
- **After:** demo/mock stays default; real adapter activates behind its flag.

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
