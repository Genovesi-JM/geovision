# Customer journey fixes — 23 September 2026

The approved audit in `BUSINESS_JOURNEY_CODE_AUDIT_20260923.md` is being applied to the existing Flutter app and Azure backend. No FlutterFlow rebuild is required for this release.

Follow-up: [real evidence uploads and email delivery diagnosis](EVIDENCE_UPLOADS_20260923.md) supersede the attachment/email status below. The rollout and test counts in this document describe the first batch.

## Implemented

- Published report actions fetch PDF bytes through the authenticated API with workspace headers. Open uses the native PDF viewer; save/share opens the OS sheet. Invalid or forbidden responses show an error with retry, rather than success. Report notification destinations have the same actions. Temporary copies are removed on logout/account deletion. Demo reports are explicitly identified and cannot masquerade as downloadable PDFs.
- Service requests select canonical `/assets` records. Existing asset context survives the asset → catalogue → offer → request path. The backend accepts exactly one of `asset_id` or the legacy `site_id`, validates workspace/organization/archived state and retains idempotent retries. Existing clients using Site IDs remain compatible; no schema migration was needed.
- Missing assets are never silently replaced by the first item. HTTP validation/permission rejections are shown as failures; transport/server failures retain a durable pending request. Pending detail pages explain that GeoVision has not yet received the request.
- Removed fabricated evidence filenames. Attachment controls are explicitly disabled until a real upload flow is implemented.
- Password reset routes are reachable when signed out. Forgot-password feedback uses the API result and prevents repeated submissions while waiting. Email delivery itself is a separate outstanding validation.
- All four registration intents route to their next step: request service, choose an asset for monitoring, browse products or accept an invitation. The router survives authentication changes instead of resetting the selected route.
- Services, subscriptions, quotes and offers requiring a site/scheduling lead to an enquiry. Submitted enquiries explicitly require confirmation of scope, price and schedule. Physical products keep the cart flow. Quote-only prices read “Price on request”. Removed generic verification/delivery badges and invented fallback deliverables.
- The live checkout starts with an empty address, uses server totals, and offers only supported, enabled settlement methods. Disabled/mock live configurations offer no payment methods. Native card/PayPal/Multicaixa checkout remains unavailable pending complete authorization flows. Manual transfer details can be displayed when explicitly enabled.
- Bank transfer availability now requires explicit operator activation. Sandbox gateway credentials are not advertised as real settlement. `/shop/checkout` rejects unavailable methods before creating an order.
- Asset map/actions/monitoring/reports/services shortcuts navigate directly. Monitoring uses canonical device-to-asset IDs. “History” was renamed “Record” because it contains asset metadata, not a complete timeline. Service requests have a separate entry from commerce orders.
- Added Spanish launch copy for the changed core paths and clear first-use choices to add an asset or accept an invitation. Full translation coverage of every legacy screen remains outside this batch.
- The unimplemented KPI-alert acknowledgement is disabled in live mode; it no longer fabricates local success or claims to have queued a change. Intervention requests retain asset context.

## Azure rollout

- API: `geovision-api`, resource group `rg-geovision-pilot-weu`.
- Ready revision: `geovision-api--journey0923`; healthy, active, 100% traffic.
- Image: `geovisionpilothcwka3w.azurecr.io/geovision-backend@sha256:681a6dfe8cc073b67e3ca6ebefed56e6f527a8289bf026fbb71f72b6ec866cd1`.
- Previous revision: `geovision-api--smtp0923` (retained for rollback).
- All nine existing secret names and the existing deployment configuration were preserved; only the API image was changed. No provider was newly activated, payment taken, or customer message sent.
- Live validation used the Azure FQDN from `mobile/config/azure-live.json`. This does not establish propagation of the custom API hostname on every resolver.

## Verification

- 19 backend commerce/service-journey tests passed, including canonical-only assets, tenant denial, archived assets and idempotency.
- 36 additional backend readiness/security/ERP atomicity tests passed.
- Flutter: 101 tests passed, 2 existing opt-in tests skipped; static analysis clean.
- iOS simulator debug build succeeded with the new native file plugins. The iPhone 15 simulator also passed the live Azure login/workspace/home/assets/request asset-selection/logout/login acceptance test.
- Native PDF acceptance also passed on iPhone: a valid synthetic PDF rendered in the iOS viewer and the native call completed after dismissing it. Screenshot: `mobile-evidence/20260923/journey-native-pdf.png`. This validates native opening; it does not substitute for a published Azure customer-report test. The save/share action is covered through an injected native handoff in widget tests, not an external file transfer.
- Azure live proof: existing synthetic QA asset accepted a request with no legacy Site; replay returned the same request; unavailable checkout returned 409; catalogue exposes price models; no real settlement method is enabled. Evidence: `mobile-evidence/20260923/journey-live-validation.json`.
- One clearly labelled synthetic service request was retained for repeatable QA. It is not a customer booking/order.

## Remaining launch gates

1. Real evidence uploads are intentionally unavailable, not simulated.
2. Provider onboarding and end-to-end payment authorization are still required before enabling payments. Manual banks require verified bank details plus `BANK_TRANSFER_ANGOLA_ENABLED=true` or `BANK_TRANSFER_INTERNATIONAL_ENABLED=true`; do not activate against unverified defaults.
3. Validate password-reset email delivery to an authorized test recipient. No email was sent during this work.
4. The Azure QA workspace has no published reports. Authenticated retrieval/error handling is covered in tests, but a real published Azure PDF still needs an end-to-end customer acceptance check.
5. Mobile changes are source/simulator builds, not an App Store or Play Store release. FlutterFlow project/screens were not overwritten.

The normal Azure-connected app was rebuilt and relaunched in the iPhone 15 simulator after the integration tests.

The owner's pre-existing iOS Podfile.lock edit (44 deletions) was preserved. Native compilation used an isolated copy under `/tmp`.
