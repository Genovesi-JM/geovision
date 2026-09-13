# Provider activation — 13 September 2026

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
Azure deployment/runtime evidence is recorded separately after publication.

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
