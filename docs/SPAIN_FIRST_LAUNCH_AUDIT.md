# GeoVision — Spain-first launch audit and timeline

_Decision date: 11 September 2026. Operating priority: Spain._

## Launch baseline

The first commercial pilot and every launch demonstration use:

- market: Spain, with Madrid as the default map and demonstration context;
- language and regional settings: Spanish (`es-ES`) and `Europe/Madrid`;
- commerce: EUR, general 21% IVA baseline, card/Stripe and SEPA/verified IBAN;
- geography and intelligence: Google Maps handoff/location, AEMET weather,
  MITECO environmental GIS and Copernicus satellite data;
- data and support: Spanish demonstration assets, addresses and workspaces,
  with email as the primary support channel.

Angola is retained as a supported expansion market. AOA, Multicaixa, the
Angolan administrative hierarchy and Angola-specific support remain available,
but are not prerequisites for the Spanish launch.

## Audit scope and result

The audit covered the public HTML pages, shared translations and commerce
JavaScript, the customer portal, FastAPI commerce and provider integrations,
Flutter defaults and demo records, deployment/runbooks, human gates and tests.

| Area | Already implemented | Missing before a real Spanish launch |
|---|---|---|
| Public experience | Spanish default, Spain/Europe-first copy, six canonical sectors, EUR-first store | Final Spanish copy/legal review, cookie consent validation and published legal identity |
| Maps/location | Madrid-first views, coordinates, provider boundary, Google/Apple navigation handoff | Restricted production key, billing/quotas, licence approval and representative Spain route/coverage tests |
| Weather/GIS/satellite | AEMET adapter, bounded MITECO adapter, Copernicus workflow | Account key where required, attribution approval, live staging rehearsals, quota/cost monitoring and scientific review |
| Commerce | EUR-first cart, Spanish billing country, 21% launch tax presentation, Stripe and bank-transfer adapters | Spanish beneficiary/IBAN, Stripe account and signed webhook, refunds, settlement, reconciliation and accountant approval |
| ERP/accounting | Provider-neutral durable boundary; Odoo and ERPNext adapters | Select the live ERP, configure a Spanish company/chart/taxes/numbering and obtain jurisdiction-specific sign-off |
| Mobile | Spanish default, Spain-first geography, EUR, Madrid demo workspaces/assets/orders | Signed store builds, device tests, production backend cutover and push/email credentials |
| IoT and processing | Common IoT contracts, worker architecture, NodeODM adapter and demo states | Physical device commissioning, calibrated Spanish field dataset and live processor capacity/quality validation |
| Security/operations | Azure infrastructure templates, readiness checks, workers, audit boundaries | Owned Azure subscription, EU-region decision, RBAC/budget, Key Vault secrets, backup/restore rehearsal and monitored cutover |

The main code gap found by this audit was not the public site; it was the mobile
and demo layer, which still made Angola, AKZ and Luanda the first experience.
That layer now follows the Spain baseline while preserving explicit Angola
options. Historical database defaults and seed/catalogue compatibility values
still contain AOA or Angola in some schemas. They are retained to avoid an
unsafe migration in this phase; every new customer-facing flow must pass an
explicit country and currency, and a future migration must be rehearsed against
real data before those legacy defaults are removed.

## Ordered launch timeline

### T0 — decisions and legal foundation (days 0–10)

1. Confirm the operating company name, Spanish address, NIF and contracting
   entity; do not publish placeholder identity or banking details.
2. Appoint Spanish accounting/legal reviewers for IVA, invoices, privacy,
   cookies, ecommerce terms, drone operations and data-processing contracts.
3. Open/confirm the EUR bank account and beneficiary name; choose Odoo or
   ERPNext for staging; approve Azure subscription, EU region and monthly budget.
4. Freeze the first pilot: one Spanish customer, sector, location, devices,
   deliverables, success KPIs and responsible reviewer.

### T1 — secure Spanish staging (days 5–20)

1. Provision isolated Azure staging, PostgreSQL, Blob Storage, Service Bus,
   monitoring, backups and Key Vault under least-privilege access.
2. Configure Entra External ID, exact redirect URIs, API scopes and test users.
3. Configure domain/TLS, `es-ES`, EUR and `Europe/Madrid`; run tenant-isolation,
   restore and rollback rehearsals before customer data enters the environment.

### T2 — Spain data providers (days 10–25)

1. Restrict the Google Maps client/server keys by app, domain and API; set
   budgets and quotas; test Madrid plus the exact pilot region.
2. Activate AEMET and MITECO in staging with attribution, caching, provenance,
   degraded-state and quota monitoring.
3. Rehearse Copernicus acquisition and NodeODM processing on one approved
   Spanish dataset; validate accuracy with the accountable sector specialist.

### T3 — EUR commerce and accounting (days 15–30)

1. Validate Stripe test mode, signed webhooks, duplicate delivery, decline,
   refund, dispute and reconciliation paths.
2. Replace every placeholder with the verified Spanish EUR beneficiary/IBAN;
   assign manual SEPA reconciliation ownership.
3. Configure the Spanish ERP company, chart, products, taxes, invoice numbering,
   warehouses and customer records; prove order → invoice → payment → delivery.
4. Keep Multicaixa disabled for the Spanish launch. Activate it later through
   its own Angolan merchant, settlement and fiscal gates.

### T4 — demonstration and pilot proof (days 25–40)

1. Use only Spain-labelled workspaces, assets, orders and map positions in the
   launch demo; remove personal or unapproved customer data.
2. Run the six-sector presentation, but make the contracted pilot sector deep:
   validated KPIs, evidence, report, alert, action and commercial follow-up.
3. Test one iPhone, one Android device, representative browser sizes, weak
   connectivity, offline recovery, accessibility and Spanish customer language.
4. Complete physical drone/IoT safety and regulatory checks for the exact pilot;
   software readiness is not permission to operate equipment.

### T5 — controlled pilot and production decision (days 40–60)

1. Run an internal demo, then a supervised customer acceptance session in
   staging. Record defects, owners and acceptance evidence.
2. Release to a small canary only after all P0 gates below are signed off.
3. Monitor authentication, provider failures, worker queues, payments, data
   isolation, costs and backups through the agreed observation window.
4. Decide production expansion from evidence. Begin Angola payment/fiscal
   activation only when its commercial timeline requires it.

## Priorities

### P0 — blocks the first Spanish customer

- legal company identity, NIF, contracts, privacy/cookies and Spanish invoices;
- Azure staging, Entra, EU data-residency decision, secrets, monitoring and restore;
- EUR pricing, Stripe/card, verified SEPA/IBAN, refunds and reconciliation;
- restricted Google Maps keys plus AEMET/MITECO live validation;
- Spain-only launch demo data and one validated pilot-sector KPI/report path;
- signed mobile/browser release checks and named incident/support owners.

### P1 — complete during the pilot

- Copernicus and NodeODM live quality/cost validation;
- physical IoT/FieldBox commissioning and device calibration;
- email/push activation, store distribution, richer Spanish supplier/logistics data;
- specialist validation for the remaining five sectors.

### P2 — expansion after Spanish proof

- Multicaixa and Angolan fiscal/accounting activation;
- additional countries/currencies, logistics integrations and map-provider options;
- provider scaffolds that have no contracted Spanish pilot requirement.

## Inputs only the owner can supply or approve

- legal company/NIF/address and approved Spanish legal text;
- Azure/Entra ownership, region, budget and production cutover approval;
- Stripe, bank/IBAN, AEMET and other account-bound credentials;
- selected ERP subscription/database and accountant sign-off;
- exact pilot customer/site, devices, drone/field authority and KPI specialist;
- Apple/Google developer accounts, signing identities and store approval.

No credential belongs in Git, chat, Flutter or public JavaScript. Configuration
alone is not proof that payments, tax, flight, scientific outputs or production
operations are approved.

## Official review anchors

- [Agencia Tributaria](https://sede.agenciatributaria.gob.es/) for Spanish tax
  and invoicing guidance;
- [Agencia Española de Protección de Datos](https://www.aepd.es/) for privacy
  and security obligations;
- [BOE](https://www.boe.es/) for the controlling Spanish legal texts;
- [AEMET OpenData](https://opendata.aemet.es/centrodedescargas/inicio) and
  [MITECO](https://www.miteco.gob.es/) for provider terms and attribution;
- [AESA](https://www.seguridadaerea.gob.es/) for the applicable drone-operation
  requirements.

These links are review inputs, not legal or accounting sign-off.
