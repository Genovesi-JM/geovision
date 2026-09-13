# Provider activation — 13 September 2026

**Follow-up:** AEMET was subsequently activated and verified from the protected
Azure panel. Both API and web are now on revisions ending `--0000004`.
See [AEMET activation evidence](AEMET_ACTIVATION_20260913.md) for current images,
secret handling and real station-observation proof. The earlier AEMET/key and
revision statements below describe the preceding catalogue phase.

Scope: existing GeoVision Azure private pilot, then Kasa and Kaya. “All APIs”
means the reviewed product capabilities, not buying every competing provider.
This phase creates no vendor accounts, contracts, secret-reader grants, DNS
changes, customer/patient records, payment or message deliveries.

## Implemented in this phase

- Platform-admin-only `GET /operations/providers`: code implementation,
  runtime selection/configuration, outstanding requirements, and explicit
  `not_checked` verification. Listing never calls a vendor or resolves vault
  references. The catalogue covers 41 provider options and separately calls
  out frontend maps, observability and manual bank transfers.
- Explicit `POST /operations/providers/copernicus/check` and
  `/operations/providers/miteco/check`: fixed public Spain queries, no user
  locations, credentials, downloads, database writes or automatic retries.
- Diagnostic network reads reject redirects, proxy inheritance, encoded or
  oversized responses. There is a 20-second streaming deadline plus the
  bounded current read timeout, one concurrent check per process and a
  30-second per-provider cooldown per process. This is not a global quota.
- Integration UI distinguishes configuration from proven connectivity;
  zero-result MITECO responses do not claim coverage or measurements.
- Existing application authorization and the single-owner Microsoft gateway
  are unchanged. The two diagnostic routes do not activate operational writes.
- Browser test configuration `playwright.pilot.config.js` uses entirely
  intercepted fixtures without starting the backend or reading its `.env`.

## Provider evidence

Public adapter requests from the development machine on 13 September:
Copernicus returned two normalized Sentinel-2 catalogue scenes for a fixed
Madrid area; MITECO returned a valid empty FeatureCollection for its reviewed
biodiversity-priority-zones collection in that area. These prove the bounded
queries, not authenticated application flow, image downloads or measured KPIs.
The same explicit checks were subsequently exercised from the authenticated
Azure administration page at 07:07 Madrid time: Copernicus returned 2 records,
and MITECO returned a valid empty result. Administrator identity was visible in
the real browser. Desktop layout was inspected, along with isolated 390/1280px
test screenshots. These checks still do not validate operational KPI pipelines.

Published source is `3d531e9fc6d444cfe3a1defe415ad78f0a9ff31a`. Ready/Healthy
API revision `geovision-pilot-hcwka3w-api--0000002` uses backend image digest
`a8a3f29d7d19dc2c4af3c3e3cb541a3cca2dc438300b2a6edf44f23e7ab554de`;
gateway revision `geovision-pilot-web-hcwka3w--0000003` uses web digest
`3811d6f867d278104054e6d48134c8d93ab0b37c0ada926e41a0f38113a7caff`.
All 12 existing anonymous protection checks passed after publication; catalogue
GET and both new diagnostic POSTs separately returned 401 without credentials.
Identity, ingress, secrets and scaling configuration were preserved. The API
selects Copernicus/MITECO; satellite downloads remain explicitly disabled.
The event worker image and public production domain were not changed.

Official protocols reviewed:
[Copernicus STAC](https://documentation.dataspace.copernicus.eu/APIs/STAC.html),
[MITECO OGC services](https://www.miteco.gob.es/es/cartografia-y-sig/ide/directorio_datos_servicios/servicio-ogc-api.html),
[MITECO reuse conditions](https://www.datosabiertos.miteco.gob.es/es/aviso-legal.html).

## Remaining external gates

The Azure CLI identity was denied Key Vault secret-metadata listing. No
permission was changed and no alternate identity was used to bypass it.
The running GeoVision API has no Google/AEMET/SMTP/NodeODM provider settings
or provider secret references. This does not prove whether keys exist in a
vault or another provider portal.

The user then confirmed having no external provider keys other than an
OpenAI/ChatGPT key. The AEMET official request page is open in Chrome with the
authorized email prefilled; user CAPTCHA/submission is pending. No automated
CAPTCHA work, form submission or plaintext key collection took place.

Paid APIs require the existing account, correct project, scopes, restrictions,
quota/budget and release approval. Construction/CMMS/maritime/ArcGIS and
external narrative selections still contain unimplemented adapters. Do not
enable them merely by adding keys. Identity, events, push, IoT, payments and
ERP each require a real end-to-end test and their owning release gates.

Kasa is an internal synthetic demo without production identity, persistence or
vendor adapters; it is not ready for key insertion alone. Kaya has implemented
and partial adapters, but clinical data sharing, KYC, payment settlement and
clinical production require their own gates. Separate application keys and
identities are mandatory; no cross-project credential sharing is introduced.
