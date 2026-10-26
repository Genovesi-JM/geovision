# Existing Flutter app → Azure, 2026-09-23

The existing app in `mobile/` is the maintained frontend. Its screens connect
directly to the GeoVision FastAPI API on Azure. The FlutterFlow starter remains
available, but rebuilding the existing screens there is not part of this work.

## Implemented changes

- Added `mobile/config/azure-live.json` and a documented launch command.
- Live mode now selects the backend device adapter and defaults to OpenStreetMap.
- Missing payment configuration returns an unavailable result, never a simulated approval.
- Live login hides the demo entry button.
- Workspace membership and dependent screen data reload across authentication changes.
- GAIA includes canonical `/assets` data, including assets created from the web portal;
  legacy site metrics supplement only the same asset.
- Added regression tests and an opt-in native Azure journey test.

## Azure API verification

An existing synthetic QA customer was used. Native login returned access and
refresh tokens; logout succeeded. No real customer records were changed.
The following reads all returned HTTP 200:

| Screen/function | API |
|---|---|
| Workspace selection and permissions | `/mobile/experience` |
| Home | `/mobile/home` |
| Assets | `/assets` |
| Legacy site metrics | `/mobile/sites` |
| Account | `/mobile/account/overview` |
| Devices | `/mobile/devices` |
| KPI alerts | `/kpi/alerts` |
| Actions | `/mobile/actions` |
| Service requests | `/mobile/service-requests` |
| Published reports | `/reports?status=PUBLISHED` |
| Orders | `/orders` |
| Catalog | `/shop/products` |
| Notifications and preferences | `/notifications`, `/notification-preferences` |

The QA account had one canonical asset, zero legacy sites and 40 catalog
products. Empty lists are valid; these checks do not prove every mutation or
provider integration works. Sanitized evidence is in
`mobile-evidence/20260923/azure-endpoint-audit.json`.

## Remaining integration work

- Native dataset/file upload has no screen/repository yet. The web portal upload
  journey was verified separately; it is not evidence of a native upload flow.
- Legacy KPI alert acknowledgement calls an API route that the backend does not
  expose. It requires a supported action contract before release.
- Payments, native push and hardware commands require their provider setup and
  end-to-end checks. Real device listing does not establish hardware control.
- Azure SMTP configuration and authentication were verified separately. A
  notification delivery worker and recipient-approved email delivery test remain.
- The Azure hostname is used during validation because the local resolver
  previously retained the old Render API route. Production custom-domain access
  should be rechecked on a real phone before distribution.
- Store signing/distribution and a physical-device Keychain/persistent-session
  check have not been performed in this pass.

## Validation

- `flutter analyze`: no issues.
- `flutter test`: 90 passed, 2 skipped (opt-in visual snapshots).
- Explicit live-provider/session/GAIA regression run: 4 passed.
- All 16 Azure endpoint checks, including login/logout: HTTP 200.
- The local resolver was rechecked and still returned the old Render CNAME;
  a canonical-host health request timed out. The Azure test profile deliberately
  uses the Container Apps hostname.
- iPhone 15 simulator (iOS 17.5): native acceptance passed. The app checked Azure
  health, signed in, loaded the assigned workspace and home, displayed the exact
  synthetic canonical asset from a fresh response, logged out, signed in again
  and logged out again. Test token storage was mocked and isolated.
- The first native login attempt timed out. A subsequent run with a health
  preflight passed in 12 seconds. The cause is not established; cold-start and
  real-device network reliability remain follow-up checks before distribution.
- Native build setup: Finder metadata prevented signing in the Documents copy;
  building under `/tmp` resolved it. UTF-8 locale resolved the CocoaPods error.

The normal `lib/main.dart` app was also built and launched with the Azure
profile on the iPhone 15 simulator, without the QA test or credential-path
define. It is left on the sign-in screen. Screenshot:
`mobile-evidence/20260923/azure-ios-login.png`.

The existing source-tree Podfile.lock edit is preserved.
