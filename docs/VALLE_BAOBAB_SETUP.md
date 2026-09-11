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
| Azure signup | Free-account profile form now open, individual-use option selected; not submitted | Eligibility approval, a new subscription or a new Valle Baobab directory |
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
- [ ] Choose mailbox address and a domain after registrar verification.
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
