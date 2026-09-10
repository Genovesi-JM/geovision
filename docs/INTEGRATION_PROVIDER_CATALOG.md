# GeoVision integration provider catalogue

This catalogue distinguishes four different claims: a port exists, an adapter
is implemented, configuration is present, and live use is approved. Only the
last two together make an external provider operational. The runtime
configuration report exposes safe `configured` booleans; it never exposes a
secret.

Status terms:

- **Core** means the provider-neutral contract and GeoVision-owned records are
  implemented.
- **Local verified** means a deterministic, file, database, or mock adapter is
  suitable for tests and demos only.
- **Adapter implemented** means real protocol code exists but still needs its
  account, credentials, contract, sandbox, and release gate.
- **Scaffold** means the selection fails closed and performs no live I/O.

## Data, processing, and intelligence

| Capability | Providers | Repository status | Live requirement |
|---|---|---|---|
| Object storage | private local filesystem; S3-compatible; Azure Blob | Core; all three adapters implemented. Local is prohibited in deployed profiles. | Private bucket/container, managed identity or scoped credentials, CORS/SAS policy, checksum/copy rehearsal. |
| Processing | deterministic fake; NodeODM; PIX4D; Autodesk; Bentley | Fake locally verified; NodeODM adapter implemented; the remaining selections fail closed. | NodeODM service/account and representative output validation, or a separately implemented vendor adapter. |
| Satellite | deterministic fake; Copernicus Data Space STAC | Fake locally verified; Copernicus search/download adapter implemented. | Network, allowlisted download hosts, storage, rate/licence review, representative-area evidence. |
| Weather | deterministic fake; AEMET OpenData; Azure Maps Weather | Fake locally verified; AEMET implemented; Azure Maps is a scaffold. | AEMET key/coverage and live response rehearsal, or implemented Azure Maps adapter. |
| GIS | deterministic fake; MITECO OGC API Features; ArcGIS | Fake locally verified; bounded MITECO public-data adapter implemented; ArcGIS scaffold. | Live coverage/availability rehearsal and attribution; ArcGIS requires a new approved adapter. |
| Report narrative | deterministic offline; unavailable external boundary; legacy OpenAI-compatible route | Deterministic provider is the approved report path. External narrative is not approved as measurement authority. | Any external model needs privacy, data-location, schema, hallucination, cost, and fail-closed review. |

## Platform delivery and identity

| Capability | Providers | Repository status | Live requirement |
|---|---|---|---|
| Identity | internal sessions; Entra External ID; Google/Microsoft browser compatibility | Internal and strict Entra API-token adapters implemented. Legacy browser callbacks remain compatibility paths. | Entra tenant/apps/scope, exact issuer/audience, web/mobile MSAL exchange, invalid-token tests, and approved cutover. |
| Events | transactional database; in-memory test; Azure Service Bus; Azure Event Grid ingress | Database outbox and Azure adapters implemented. | Namespace/topics/subscriptions, managed identity, poison/retry monitoring, correlation rehearsal. |
| Notifications | in-app; local ID/file sink; SMTP; Azure Notification Hubs | Durable inbox/delivery implemented; SMTP and Azure adapters implemented. | SMTP/APNs/FCM/Azure credentials, signed native host channels, consent/preferences, delivery rehearsal. |
| IoT ingress | authenticated REST; signed MQTT; Azure IoT Hub Event Grid | REST/MQTT and Azure Event Grid normalization implemented; edge receipts support duplicate and offline replay. | Device identities, IoT Hub/Event Grid configuration, MQTT topology where used, offline watchdog deployment, fleet monitoring. |
| Observability | structured console; Azure Monitor/Application Insights | Core instrumentation and Azure configuration boundary implemented. | Workspace/connection string, retention, alerts, dashboards, incident owner. |

## Commercial and enterprise systems

| Capability | Providers | Repository status | Live requirement |
|---|---|---|---|
| Payments | manual bank transfer; Stripe; Multicaixa; PayPal | Provider-neutral lifecycle, the manual-transfer adapter, and gateway adapters are implemented. Checked-in IBAN values are placeholders, and gateway discovery proves configuration shape only; no live settlement is claimed. | Verified beneficiary/bank values and reconciliation ownership for manual transfer; merchant accounts, signed callbacks/webhooks, settlement/refund/failure rehearsal, reconciliation, and legal/fiscal approval for each gateway. |
| ERP | local mock; ERPNext; Odoo 19 JSON-2 bridge | Durable provider-pinned commands implemented; ERPNext and Odoo adapters exist. | Gate 17, least-privilege account, provider-side idempotency, signed callbacks, accounting mapping and rollback. |
| Construction | deterministic fake; Autodesk APS; Procore; Bentley iTwin; Trimble | Registry/control plane implemented; named live providers are scaffolds. | Implement and review the selected adapter, sandbox, mapping, idempotency, licence, rate, and customer cutover. |
| Asset management | deterministic fake; Seequent; Mine Enterprise; SAP EAM; IBM Maximo; Dynamics 365 Asset Management; customer CMMS | Registry/control plane implemented; named live providers are scaffolds. | Same provider-specific gate; no provider may own GeoVision Assets or intelligence. |
| Maritime | deterministic fake; MarineTraffic; Kpler; Puertos del Estado | Registry/control plane implemented; named live providers are scaffolds. | Implement an approved context-only adapter and prove provenance/licensing. |
| Customer GIS | deterministic fake; MITECO context; ArcGIS selection | Registry/control plane implemented; only the separate bounded MITECO adapter performs real I/O. | Customer connection, capability, entitlement and rollout checks plus provider-specific validation. |

The enterprise integration registry accepts only canonical Azure Key Vault
secret references. Its deterministic `fake` provider is local/test only and is
rejected in staging and production. Rollout flags cannot bypass membership,
entitlement, connection lifecycle, or operation capability checks.

## Activation checklist

1. Assign an owner and record the exact customer/provider account and region.
2. Complete authentication, scopes, data handling, licence, rate, and cost
   review.
3. Put secrets in the approved vault and store only canonical references.
4. Implement contract and negative tests with provider IDs kept opaque.
5. Prove provider-side idempotency before retrying side-effecting writes.
6. Rehearse sandbox success, timeout, rate limit, malformed data, retry, dead
   letter, reconciliation, and disconnect.
7. Enable the connection, entitlement, and member/workspace rollout only after
   release approval.
8. Record staging evidence and rollback; then promote the same image digest.
