# Valle Baobab — account and integration setup record

Last checked: 2026-09-11. This records verified preparation, not a completed
cloud deployment or a promise of production readiness.

## Ownership and scope

- Valle Baobab is the user's umbrella project brand, not a registered company.
- Use the individual's truthful legal name, billing address and applicable tax
  details wherever a provider asks for the contracting party. Do not invent a
  corporate registration, VAT registration or country of incorporation.
- GeoVision is the first workload, prioritizing demonstrations in Spain. Kasa
  and Kaya may reuse architecture and supplier relationships, not production
  credentials, customer data or unrestricted cross-project permissions.
- Inspect the existing personal Azure directory and subscriptions before
  creating anything. A university or other third-party directory must not be
  used for this independent brand without the appropriate authorization.
- A custom domain or Microsoft 365 mailbox is not required to start Azure.
  Paid email and domain purchases remain separate decisions.

## Verified external observations

| Check | Observation | What this does not prove |
|---|---|---|
| `vallebaobab.com` registry RDAP | HTTP 404 (no domain object returned) | Registrar availability, price, reservation or trademark clearance |
| `vallebaobab.es` registry lookup | Lookup timed out | Availability or registration status |
| Public Copernicus STAC `/v1/collections` | HTTP 200 | Authenticated downloads or GeoVision end-to-end integration |
| Public MITECO OGC Features `/collections` | HTTP 200 | Per-layer coverage, licensing review or GeoVision end-to-end integration |
| `https://api.geovisionops.com/health` | HTTP 503, `x-render-routing: suspend`, body `Service Suspended` | Cause of suspension or Azure state; restoring/migrating API service remains a priority |
| Azure signup | Free-account form was prepared for individual use; latest browser check is back at portal home, still showing the university directory and a no-subscription welcome | Eligibility approval, a new subscription or a new Valle Baobab directory |
| Azure portal | All Directories lists only the university directory for the current personal account | A personal Valle Baobab directory; no university resources were changed |
| Google `geovision-483710` | Maps JavaScript API already enabled; no API keys/service accounts listed; Google free trial banner says ended | Enabled Places New/Routes/Geocoding, usable billing or live GeoVision maps |

No provider keys, tokens, personal tax details or payment details belong in this
record. Repeat connectivity checks immediately before the release.

The requested address `valle@baobab.com` cannot be provisioned without control
of `baobab.com`; that domain currently hosts the unrelated Baobab Group. The
user subsequently selected `genovesi@vallebaobab.com`. This still requires
domain purchase and mailbox provisioning. No email address has been created.

## Decisions and user-controlled steps still required

- [ ] Confirm intended personal Azure directory/account and complete its MFA.
- [ ] Confirm billing country/address (Spain only if factually applicable).
- [x] Choose mailbox address: `genovesi@vallebaobab.com`; IONOS search reports the domain available, but it is not reserved or registered.
- [ ] Approve domain registration/renewal cost and email subscription term.
- [ ] Approve Azure/API service selection and estimated recurring cost.
- [ ] User completes new passwords, recovery and MFA registration privately.
- [ ] Review and approve each provider's binding terms at signup.
- [ ] Approve any new application identity, federation or role assignment with
      its exact scope before security-sensitive access is created.

Pay-as-you-go budgets are alerts, not hard spending caps. Review provider quotas,
replica ceilings, resource SKUs, retention and shutdown procedures separately.
Do not deploy the committed high-availability production profile merely to
demonstrate account setup; its baseline costs need a separate review.

## Lowest-cost functional pilot decision — 2026-09-11

The user selected lowest practical costs, not a numeric spending limit or
authorization to accept unspecified recurring charges. Prioritize a working
Spain demo and retain a path to scale; do not equate trial credits with a
permanently free production service.

### Domain and personal brand mailbox

Prepared, but did not submit, the IONOS Spain checkout:

- Correo Básico 1: one 2 GB mailbox, webmail and device synchronization.
- `vallebaobab.com`: reported available and included in the selected pack.
- Checkout contains exactly these two items; no extra domains, paid domain
  protection, AI add-ons, archiving, or additional mailboxes selected.
- Current total: EUR 1.50 before tax; checkout displays EUR 1.82 including
  21% VAT. Contract details say a one-month minimum, billed one month ahead,
  with automatic renewal. Annual base-rate equivalent: EUR 18 + VAT; invoice
  rounding may differ from the unrounded EUR 21.78 annual calculation.
- The cart labels the domain included without a separate renewal surcharge.
  Recheck final order terms and any later tariff-change notices before
  submitting; the domain is not reserved merely by being in the cart.
- User still needs to approve these terms/cost and complete truthful billing
  details and payment privately. No order, domain or mailbox exists yet.

Comparison: Zoho Mail Lite 5 GB is EUR 0.90/user/month paid annually (EUR 10.80
before local tax), but a domain must be purchased separately. Its free plan
is web-only and limited to selected data centres; EU eligibility was not
confirmed. Porkbun currently lists standard .com registrations/renewals at
USD 11.08 and anticipates about USD 11.81 from 2026-11-01. IONOS Basic 25's
EUR 1 introductory monthly price rises to EUR 3.50 after 12 months (before
tax), so it is not the preferred ongoing one-person plan.

For GeoVision automated messages, consider Resend Free separately from the
personal inbox: 3,000 emails/month, at most 100/day, three domains. Verified
sender setup and account terms are still required. Its SMTP supports port
587 with STARTTLS, matching the current application adapter. Do not expose
the SMTP credential or send test messages without an authorized recipient.

### Azure and API costs

- Keep the existing static frontend; no duplicate paid website hosting.
- Proposed demo profile: one small Container Apps Consumption API,
  PostgreSQL B1ms/PostGIS, private Blob storage and Key Vault, using the
  existing database-backed queue rather than Service Bus Standard.
- Use scheduled, bounded event/notification worker jobs; these schedules and
  this light deployment profile are NOT implemented or tested yet. API
  scale-to-zero alone would pause API-hosted workers. This proposal does not
  provide continuous IoT monitoring, immediate background delivery, ERP or
  drone processing.
- Eligible new Azure accounts get USD 200 for 30 days. Continuing beyond the
  trial requires separately accepting pay-as-you-go. PostgreSQL's eligible
  12-month allowance is 750 B1ms hours/month, 32 GB data and 32 GB backup.
- Container Apps' monthly allowance is 180,000 vCPU-seconds, 360,000 GiB-seconds
  and 2 million requests, shared at subscription scope. At 0.5 vCPU/1 GiB,
  compute/memory allowance is only 100 aggregate active hours, not 24/7.
- Free eligibility, region capacity and real usage remain unverified. Blob,
  secrets, logs, traffic and any registry may add costs. Do not promise EUR 0
  monthly without measured usage and exact service eligibility.
- For comparison only, current West Europe Microsoft retail rates imply
  about EUR 27.56/month for Linux App Service B1 plus PostgreSQL B1ms/32 GB
  at 730 hours, before VAT, storage extras, logs, traffic and other services.
  This always-on alternative needs a separate tested deployment profile.
- Prioritize public MITECO data, AEMET OpenData and Copernicus STAC catalogue;
  protected downloads and paid processing remain deferred. Google location
  APIs are optional until required, and need approved billing, restricted
  keys, appropriate field masks and quotas. Free allowances differ by SKU;
  neither a billing alert nor enabling an API is a hard spending cap.

Checkout is prepared for approval, not completed. The independent Azure
directory and a live working API remain blocking prerequisites for release.

## First GeoVision integration tranche

| Capability | Preparation available | Configuration / external dependency | Acceptance evidence |
|---|---|---|---|
| Backend and data | Azure templates for Container Apps, PostgreSQL/PostGIS, Blob, Key Vault, Service Bus and monitoring | Approved subscription, cost review, protected deployment identity and required secrets | Migration success; `/health` and `/ready`; authorized API and private storage smoke tests |
| Map display | Existing web map; Flutter OSM/Mapbox provider seam | Approved tile provider/terms and `GV_MAP_PROVIDER`; `GV_MAPBOX_TOKEN` if selected | Web/iOS/Android rendering, attribution, domain/application token restrictions |
| Address search and routing | Google server location adapter | `LOCATION_PROVIDER=google_maps`; `GOOGLE_MAPS_SERVER_API_KEY`; only required APIs enabled in GeoVision's Google project | Representative Spanish address, route and rejected/unrestricted-key tests; quota monitoring |
| Spanish weather | AEMET adapter | `WEATHER_PROVIDER=aemet`; `AEMET_API_KEY` | Live request, safe timeout/quota failures and source attribution |
| Environmental GIS | MITECO public OGC adapter | `GIS_PROVIDER=miteco`; reviewed official endpoint | Approved Spanish layer, attribution and missing-data behavior |
| Satellite catalogue | Copernicus STAC adapter | `SATELLITE_PROVIDER=copernicus`; protected downloads need a separate token/refresh design | Bounded Spanish AOI/date search; review assets before enabling downloads |
| Transactional email | SMTP adapter | `NOTIFICATION_PROVIDER`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_USE_TLS` | Verified sender domain, supported SMTP authentication, invitation/reset delivery and retry test |
| Drone processing (optional) | NodeODM adapter | `PROCESSING_PROVIDER`, `NODEODM_BASE_URL`, `NODEODM_TOKEN`; approved processing server | Small synthetic job; output isolation; cost/time limits |

The mailbox used by a person is distinct from the transactional-email service
used by GeoVision. Do not assume a Microsoft 365 mailbox password is compatible
with the application's SMTP authentication implementation.

Secrets should be stored in the GeoVision environment's Key Vault and supplied
to the application through managed-identity references. Provider accounts and
secret presence do not count as activation evidence. Setting a credential may
make a feature discoverable before a live acceptance test is complete.

## Deferred rather than falsely marked complete

- Customer Entra External ID: backend exchange exists; web/mobile MSAL cutover
  and a real-tenant rehearsal remain necessary. The internal workforce
  directory is not a substitute for customer identity configuration.
- Stripe/PayPal: sandbox first, then explicit live approval and verified
  settlement, webhook, refund and reconciliation. No live commercial payments
  should be enabled just to complete a list of keys.
- Native push: Notification Hubs backend exists, but signed iOS/Android host
  token/channel integration still needs implementation and device testing.
- IoT: distinguish simulator tests from real hardware, credentials,
  calibration, safety interlocks and an owned offline watchdog.
- Odoo/ERP: real account/bridge/configuration required; deployed profiles reject
  mock ERP execution. Do not advertise ERP as live with the default mock value.
- Enterprise construction, mining and maritime connectors: many are
  deliberately fail-closed scaffolds requiring provider-specific development,
  customer permission and contracts. Do not purchase them all now.

## Release handoff

Local setup work completed on 2026-09-11:

- Added opt-in typed deployment bindings for Google location, AEMET, MITECO,
  Copernicus, SMTP and NodeODM. No provider is enabled by default.
- Added fixed-name existing-Key-Vault references, per-process configuration
  scoping and an SMTP event-worker routing regression. No secret values were
  read, generated, copied or committed.
- Bicep compilation and 23 infrastructure tests passed, including independent
  review. Whitespace validation passed. These are offline tests, not proof of
  a live cloud deployment.
- See `infra/azure/PROVIDER_SETUP.md` for the exact activation contract.

Follow `RELEASE_CHECKLIST.md`, `PRODUCTION_LAUNCH.md` and `infra/azure/README.md`.
Any added provider configuration must remain opt-in, preserve default behavior
when omitted, use non-secret configuration plus Key Vault secret references,
and pass template and backend configuration checks before a cloud deployment.
Record deployed revision and live smoke evidence separately from local tests.

Reference sources checked on 2026-09-11:

- https://azure.microsoft.com/en-us/pricing/purchase-options/azure-account
- https://learn.microsoft.com/en-us/entra/fundamentals/create-new-tenant
- https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/spending-limit
- https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-acm-create-budgets
- https://www.microsoft.com/es-es/microsoft-365/exchange/exchange-online-business-plans-and-pricing
- https://rdap.verisign.com/com/v1/domain/vallebaobab.com
- https://www.ionos.es/soluciones-oficina/email-hosting
- https://www.ionos.es/soluciones-oficina/correo
- https://www.zoho.com/mail/zohomail-pricing.html
- https://www.zoho.com/mail/help/adminconsole/subscription.html
- https://porkbun.com/products/domains
- https://kb.porkbun.com/article/201-why-did-com-prices-go-up-and-how-high-will-they-go
- https://resend.com/pricing
- https://resend.com/docs/send-with-smtp
- https://learn.microsoft.com/en-us/azure/container-apps/billing
- https://prices.azure.com/api/retail/prices
- https://developers.google.com/maps/billing-and-pricing/pricing
- https://documentation.dataspace.copernicus.eu/Quotas.html
