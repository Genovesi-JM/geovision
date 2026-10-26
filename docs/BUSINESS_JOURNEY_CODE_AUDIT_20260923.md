# Business decisions and customer journey: code audit — 23 September 2026

Implementation update: approved changes and current remaining gates are recorded in [JOURNEY_FIXES_20260923.md](JOURNEY_FIXES_20260923.md). The original findings below are retained as the audit baseline.
This is a focused source-code review of the existing Flutter customer journeys,
shared contracts and decision documents. It is not a new end-to-end test of
all services, a usability study, or proof of live provider readiness. No app,
backend, payment or customer-data changes were made in this audit.

## Assessment

The shared platform, first-party commercial model, canonical assets, invitation
flow and five-destination navigation fit the accepted direction. Several native
screens still use legacy contracts or demonstration interactions. The highest
risk is a customer reaching a convincing screen without being able to complete
the promised action or receive the purchased result.

Prior API health/read checks and the successful login/home/assets journey do
not establish report delivery, evidence upload, checkout or invitation delivery.

## Concrete findings, in priority order

### 1. Report delivery is still a placeholder in the native report list — high

`mobile/lib/features/reports/presentation/reports_screen.dart:52` opens a sheet
that receives only a title and size. At line 114, Open securely dismisses the
sheet and displays `Demo: requesting signed URL…`. At line 125, Download only
closes the sheet. Neither action retrieves the document. The separate report
notification context screen presents metadata rather than a document viewer.

Customer impact: a customer can see that a report exists but cannot obtain it
through these controls. This breaks the result-delivery end of service-first
onboarding and the commercial promise of inspections/analysis.

Recommendation: prioritize an authorized real report open/download flow,
with published/reviewed state, date, scope and useful failure/retry handling.

### 2. Evidence attachment is not an upload — high

`mobile/lib/features/work/presentation/new_request_screen.dart:143` adds a
fabricated `evidence_N.jpg` string when the attachment button is pressed. It
does not select, capture or upload a file, and is not gated to demo mode.
The request sends those strings as attachments.

Customer impact: the attachment count suggests evidence was attached when no
photo or file was selected. Staff may receive an apparent attachment with no
usable evidence.

Recommendation: use file/camera selection and durable upload references, with
honest uploading/failed/offline states. Until implemented, do not offer a live
attachment control that reports success. Self-service data upload is useful,
but must not become mandatory for service-first customers.

### 3. Asset context is lost between screens — high

Assets uses the canonical `/assets` repository. NewRequestScreen watches the
legacy `sitesProvider` (line 62) and defaults to its first site (line 71).
The previous Azure audit found one canonical QA asset and zero legacy sites.
Consequently that asset can be visible in Assets but absent from the service
request selector.

`asset_detail_screen.dart:171`, `:186` and `:188` navigate to general devices,
services and request routes without carrying the selected asset. Actions and
Reports do preserve asset context, so the behaviour is inconsistent.

Customer impact: “I am looking at site B; why must I choose again, why is it
missing, or why is site A selected?” The wrong default can lead to a request
for the wrong site within the customer's workspace.

Recommendation: use the same canonical asset contract across customer flows;
preserve and visibly confirm the selected asset. Keep old API aliases only
where required for compatibility, not as a competing customer data source.

### 4. Account recovery is internally contradictory — high

`mobile/lib/core/routing/app_router.dart:70` allows only login and registration
while signed out. The reset-password route exists at line 100 but is not
exempted, so a signed-out reset link is redirected to login.
`login_screen.dart:198` also discards the forgotPassword Result and shows
resetLinkSent regardless of a request failure.

Customer impact: someone who forgot a password can be asked to authenticate
before resetting it, or be told a message was sent after a network/API error.
This is separate from the previously documented email delivery-worker gap.

Recommendation: make reset-token routes usable while signed out, preserve
anti-enumeration wording for accepted requests, distinguish transport failures,
and verify actual reset delivery and completion.

### 5. Onboarding intentions do not lead to distinct next steps — medium/high

`register_screen.dart:235` correctly offers request_service, monitor_asset,
buy_product and view_invitation. At line 299, the first three all navigate to
Home unless a return destination was supplied. Invitation handling does have
its own branch and preserves existing-work access.

Home (`home_screen.dart:93`) uses “Nothing needs your attention right now” when
there are no priority items. It has no dedicated first-use setup panel here.
This wording is not literally a health guarantee, but a new customer can
confuse no monitoring/results with an all-clear state.

Recommendation: route each accepted intention into its next useful step, and
show “not set up”, “waiting for data”, “being reviewed” and “monitoring active”
as distinct states. Preserve the invitation destination instead of restarting
onboarding. Do not make every customer create a site or upload data.

### 6. Commerce is richer in the backend than in the mobile purchase flow — high

The first-party catalogue distinguishes physical products, services,
monitoring plans, installation, inspection and analysis, with price models
and fulfilment requirements. The native GvProduct model does not retain
price_model, requires_site or requires_scheduling. ProductDetailScreen:130
uses the same Add to cart action for all items. CartScreen:122 always shows
physical delivery-address entry.

CartScreen:23 pre-fills a demonstration Madrid address without a demo-mode
condition. Its payment choices (line 40) depend on currency rather than live
provider availability. PaymentMethodsScreen:149 labels the static collection
“Accepted payments”, including providers not activated. The availability
notice does not make this equivalent to a live capability check. Product detail
also displays generic verified-quality/tracked-delivery badges for all items.

The recently added unavailable-payment adapter does not solve this whole flow:
OrdersRepository.checkout posts directly to `/shop/checkout`; `pay()` is a
separate method. This audit does not assert that money was charged or that the
backend fabricates successful payment.

Customer impact: “Am I buying a one-time product, requesting a quote, booking
an inspection, or subscribing? What does this price include? Why do I need a
shipping address for analysis? Is this payment method actually available?”

Recommendation: choose the action by offer type and actual availability:
Buy product / Request quote / Book service / Start monitoring. Show one-off and
recurring charges, inclusions, site, schedule and deliverables explicitly.
Use verified customer addresses; show only available payment methods. An order
being recorded must remain distinct from payment and fulfilment confirmation.

### 7. The Spain-first presentation is incomplete — medium

Home, Assets, Services, New request and Invitation contain hard-coded English
headings and body copy despite localized navigation/registration. Checkout also
constructs a Portuguese “Referência” message. Broad currency choices, multiple
currency totals and Angola payment methods remain prominent.

Recommendation: complete one coherent Spanish launch experience. Preserve
international support underneath, but show country/currency choices only when
relevant. Localize product terms and empty/error states as well as labels.

### 8. Navigation labels sometimes promise more than the content — medium

Asset detail exposes up to seven sections. Several contain another button to
open a screen, rather than the relevant information. The History section is
an updated timestamp and metadata dump (`asset_detail_screen.dart:224`), not
an intervention/result timeline. “Services” currently opens the catalogue and
order-history screen; service requests live on `/work` and are reached through
other entry points. These are not duplicate database concepts, but customers
must infer how they relate.

Recommendation: retain the five agreed destinations; make Services explain
Request / In progress / Completed / Explore offers. Put meaningful summaries
on an asset's page and preserve context. Prefer customer language such as
“Sites & equipment” where “Assets” is unclear; keep canonical internal names.

### 9. The legacy acknowledgement flow conceals failure — high when exposed

AlertsRepository.acknowledge (`alerts_repository.dart:61`) calls
`/kpi/alerts/{id}/acknowledge` and swallows exceptions. That route was absent
from the backend API in the previous connection audit. The comment mentions
queued/best-effort work, but this method does not enqueue it.

Recommendation: choose the supported action contract, persist acknowledgement
and display truthful results. Do not substitute an unrelated IoT endpoint.

## What should be retained

- GeoVision as the only customer-facing seller and accountable service provider.
- Self-service and invitation/service-first entry paths using one identity.
- Shared canonical asset/workspace ownership across web, mobile and Operations.
- Home, Assets, Actions, Services, More: coherent top-level architecture.
- Evidence, reviewed results, action and outcome history as the operational loop.
- Capability/permission-based visibility and private contractor execution.
- Existing native Flutter screens and Azure backend, with GAIA as contextual help.
- Backend sector/provider extensibility where it is kept out of unready offers.

## Excess to hide, defer or consolidate

- Rebuilding the same frontend in FlutterFlow: duplicates behaviour, maintenance
  and testing without a demonstrated requirement. Keep the API starter as optional.
- Showing every market, currency and payment provider in the Spanish pilot:
  increases decisions and implied availability without helping the first customer.
- Treating all six sectors as equally ready: keep the taxonomy, expose only
  sellable, supported offers for the customer's actual context.
- Extra intermediate asset screens and empty sections: add taps without value.
- Public-facing technical details about signed URLs and raw record identifiers:
  replace with a clear View report action and human-readable references.
- Activating every provider before selecting a paid pilot: accounts, cost,
  failure modes and support work grow faster than proven customer value.

Do not delete tenant isolation, ownership checks, evidence provenance,
publication review or private Operations. That complexity serves real product
requirements; it is not the same as unnecessary customer-facing complexity.

## What can confuse the owner and future assistants

- “Implemented”, “configured”, “API verified”, “customer journey verified” and
  “commercially deliverable” are different states. Screen count and HTTP 200
  counts should never substitute for customer acceptance.
- Older MOBILE_PRODUCT_SCOPE.md describes Home/Sites/Alerts/Work/Account while
  ONBOARDING_FLOW.md and the router use Home/Assets/Actions/Services/More.
- Earlier milestones retain Angola-first assumptions; the 11 September Spain
  decision supersedes them. Monetary examples are not approved price lists.
- Asset/Site, Services/Work/Orders, canonical/compatibility APIs and public versus
  private Operations naming require explicit mappings, not guessing from names.
- This assistant previously suggested upload-first onboarding. It was not an
  accepted business decision and must not overwrite service-first requirements.

Maintain one dated decision register with status, acceptance source, superseded
records and customer-visible consequences; link each journey to its screen,
API, delivery owner and acceptance evidence.

## Recommended order

1. Restore trust: real report retrieval, real/disabled attachment control,
   account recovery, truthful payment availability and removal of live demo defaults.
2. Preserve the customer goal and selected asset through onboarding and requests.
3. Complete one Spanish service-first journey: request → reviewed quote/order →
   progress → reviewed report → follow-up, including the invited-customer path.
4. Make the self-service monitoring path equally explicit; upload is optional.
5. Complete the Spanish copy and simplify irrelevant/empty choices.
6. Expand providers, sectors and markets only for a validated delivery need.

Recommendations in this audit are proposed changes, not new owner-approved
business requirements.
