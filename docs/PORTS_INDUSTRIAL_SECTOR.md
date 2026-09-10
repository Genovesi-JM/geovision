# Ports and Logistics Provider Boundaries

Phase 31 added optional provider seams around the sector then called Ports and
Industrial. Phase 34 makes the customer and technical identity unambiguous:
this package is now **Portos & Logística**, with public ID `ports_logistics` and
technical sector `PORTS_LOGISTICS`. Indústria, Energia & Utilities is a
separate sector and package. The filename is retained as a documentation link
compatibility path, not as the current sector name.

GeoVision remains the system of record for assets, zones, acquisitions,
datasets, observations, KPIs, actions, reports, and IoT assignments. External
references are opaque context; they never replace a GeoVision UUID and never
create a seller, contractor marketplace, or provider-owned customer record.

## Document scope and core feature pointers

This document owns only the optional maritime and enterprise-provider
boundaries. The sector implementation remains authoritative in
`backend/app/sectors/ports/`, with behavior covered by
`backend/tests/test_ports_industrial_sector.py`; this guide does not redefine
its evidence rules or persistence.

| Canonical API | Purpose |
|---|---|
| `GET /sectors/ports-logistics/capabilities` | Feature state, vocabulary, KPIs, comparisons, layers, and guardrails |
| `POST /assets/{asset_id}/ports-logistics/evaluate` | Evaluate tenant-owned, quality-gated evidence |
| `GET /assets/{asset_id}/ports-logistics/inspection-history` | Asset/zone-centric repeated-inspection history |
| `GET /assets/{asset_id}/ports-logistics/comparisons` | Compatible visual, thermal, and 3D comparison evidence |
| `GET /assets/{asset_id}/ports-logistics/map-layers` | Asset, observation, and supported dataset layers |
| `GET /assets/{asset_id}/ports-logistics/report-context` | Evidence-linked report context and limitations |

The Phase 31 `/sectors/ports/*` and `/assets/{asset_id}/ports/*` paths remain
hidden compatibility aliases. New clients must use the canonical paths above.

The core KPI set covers inspection status and freshness, specialist-validated
condition summary, reinspection state, new visual and thermal candidate counts,
environmental and operational alert counts, and assigned-sensor freshness. The
first-party catalogue provides visual inspection, thermal inspection, 3D
mapping, sensor installation, recurring monitoring, and specialist review.

The repeated-inspection demo bundle is synthetic, uses explicit fixture
provenance, and proves history/comparison behavior only. It is not live port,
AIS, oceanographic, engineering, safety, or vendor-system evidence. No provider
scaffold is invoked by the core sector evaluation path.

## Asset-centric use

Maritime and enterprise-system values may supplement the history of a canonical
port, terminal, yard, corridor, or logistics asset. They do not define the
asset and cannot turn an image, temperature difference, AIS position, model
value, or provider status into a defect, engineering conclusion, safety
decision, or navigation instruction.
Repeated-inspection comparisons must remain tied to the same canonical asset or
child zone and to compatible, quality-passed evidence.

IoT devices continue to use the common auditable `DeviceAssignment` boundary.
The Portos & Logística sector must not introduce another device-assignment or
telemetry system. AEMET weather, Copernicus satellite, and MITECO GIS context
also remain in their existing provider ports and are not proxied by the
maritime adapter.

## Maritime contract

`MaritimeContextRequest` carries an authoritative GeoVision asset UUID, a
latitude/longitude, optional UTC time window, bounded search radius, and bounded
result limit. Legacy mapping requests remain supported. A normalized reading
retains:

- opaque provider reference;
- valid time and observed/model/forecast/AIS source kind;
- station reference and location;
- metric, value, unit, and quality;
- source, licence identifier/link, attribution, and provenance.

Every `MaritimeContextResult` has these immutable authority limits:

```text
measurements_authoritative = false
context_only = true
navigation_authority = false
diagnostic_authority = false
```

The local/test deterministic fake emits simulated observed and model records so
the normalization contract can be tested without a provider account. It is
rejected in staging and production, including when requested as a factory
override.

| `MARITIME_PROVIDER` | Phase 31 behavior | Failure code |
|---|---|---|
| `none`, `null` | Disabled; no I/O | `integration_disabled` |
| `fake`, `deterministic` | Local/test contract fixture only | Deployed use: `fixture_disabled` |
| `marinetraffic` | Named unavailable AIS scaffold | `provider_not_configured` |
| `kpler` | Named unavailable maritime-data scaffold | `provider_not_configured` |
| `puertos_del_estado` | Named unavailable official-data scaffold | `authorization_terms_not_approved` |

MarineTraffic/Kpler API access is customer- and contract-specific. No endpoint,
credential field, entitlement, request quota, or authentication method is
guessed in Phase 31. AIS remains supplementary situational context and must not
be used for collision avoidance, navigation, port control, security, or safety
authority.

## Puertos del Estado authorization gate

Puertos del Estado publishes measured and modelled waves, sea level, currents,
temperature, salinity, wind, and related oceanographic context through Portus
and Portuscopia. Its
[official oceanography FAQ](https://www.puertos.es/servicios/oceanografia/faqs)
also says that downloaded data are authorized for the specific purpose of the
download, may not be transferred to third parties, and require source credit.
The older
[datos.gob.es catalogue record](https://datos.gob.es/es/catalogo/ea0001277-datos-de-medida-y-modelos-del-medio-fisico)
does not override that more specific condition.

GeoVision therefore performs no Puertos request in this phase. Written
permission and a reviewed access agreement must explicitly cover:

- customer-facing SaaS display and third-party access;
- commercial reuse, caching, retention, and deletion;
- derived alerts and transformed/combined products;
- automated access, approved HTTPS origins, quotas, and retry behavior;
- required attribution, update metadata, quality notices, and disclaimers;
- treatment of observed, modelled, forecast, station, datum, and directional
  semantics.

Free download availability and the separately documented ability to embed an
official widget are not treated as permission to scrape, normalize, cache, or
redistribute the underlying data.

## Enterprise asset-management scaffolds

The existing `AssetManagementProvider` remains the only enterprise asset-sync
boundary. Its writes require a keyword-only idempotency key and return an
explicit context-only receipt. Phase 31 adds only these named unavailable
selections:

| `ASSET_MANAGEMENT_PROVIDER` | Intended future system | Phase 31 behavior |
|---|---|---|
| `sap_eam` | SAP Enterprise Asset Management | `provider_not_configured` |
| `ibm_maximo` | IBM Maximo | `provider_not_configured` |
| `dynamics_365_asset_management` | Dynamics 365 Asset Management | `provider_not_configured` |
| `customer_cmms` | Customer-selected CMMS | `provider_not_configured` |

The scaffolds perform no network request and import no vendor SDK. They do not
add global credentials, endpoints, work-order tables, or mappings. SAP
communication arrangements, Maximo API users/keys, Dynamics Entra applications
and data entities, and other CMMS authentication are tenant-specific. Phase 32
must provide the encrypted integration registry, customer ownership, approved
sandbox, exact product/version contract, mappings, authorization, secret
rotation, audit trail, and provider-side idempotency proof before live work.

Existing Phase 30 `seequent` and `mine_enterprise` behavior is unchanged.
Bentley iTwin remains a `ConstructionProvider`, Bentley Reality Modeling a
`ProcessingProvider`, and ArcGIS/MITECO `GISProvider` implementations; the
asset-management factory does not duplicate them.

## Operational gates

Before activating any live maritime or CMMS adapter, record all of the
following as reviewed human gates:

1. Customer and workspace ownership plus least-privilege provider account.
2. Written licence/redistribution and data-retention approval.
3. Approved sandbox and exact API/version/endpoint documentation.
4. Secret storage and rotation through the Phase 32 registry, never global
   plaintext configuration or logs.
5. Bounded time/location/result queries, timeouts, quotas, safe retries, and
   provider-side idempotency where writes occur.
6. Provenance, attribution, quality, source-time, spatial applicability, and
   authority limitations preserved end to end.
7. Contract, security, tenant-isolation, failure, and rollback tests completed
   without making live CI calls.

Until every applicable gate is complete, factories must continue returning the
documented fail-closed result.
