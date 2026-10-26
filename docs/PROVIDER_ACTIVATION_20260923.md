# GeoVision provider activation — 23 September 2026

Two changes are now live in the existing private Azure pilot: GAIA uses a real
OpenAI model, and an hourly Container Apps job runs the existing weather and
satellite acquisition worker. This is a backend activation, not a FlutterFlow
deployment or a completed customer data pipeline.

The checks occurred on 23 September in Europe/Madrid; raw evidence uses UTC
and therefore carries 22 September timestamps.

## Changes deployed

| Capability | Change | Verification and limits |
|---|---|---|
| GAIA assistant | Added server-side `OPENAI_API_KEY` secret reference and `OPENAI_MODEL=gpt-4o-mini` to the API | Existing backend adapter returned a real model response to a synthetic prompt; demo fallback was not used. Authenticated customer UI/context flow was not retested. |
| Weather/satellite worker | Created scheduled job `geovision-pilot-intelligence` | Manual execution and first scheduled execution both succeeded. There were zero acquisition schedules and zero acquisition runs, so site-specific ingestion, KPIs and reports remain unverified. |

The user had obtained no new provider accounts. An existing GeoVision-local
OpenAI API credential was found, tested and placed in the backend's Container
Apps secret store. Its value was not printed or written to these artifacts.
No model key was added to a frontend or to the acquisition worker.

API ready revision: `geovision-pilot-hcwka3w-api--0000005`.
Existing backend image retained:
`geovisionpilothcwka3w.azurecr.io/geovision-backend@sha256:b3b74c015f0b1a64bb4e1269f029e2c5d019cb08bf5d09f6687a22c0c3e83383`.
The job uses that same image and the existing user-assigned identity.

The job runs at minute 17 of every hour (`17 * * * *`, UTC), with one replica,
0.25 CPU, 0.5 GiB memory, a 300-second timeout and no platform retries.
The worker batch is two and integration retry count is one. Satellite downloads
remain disabled. In-process workers remain disabled; the scheduled job owns
these acquisition cycles. This creates metered Azure execution; it is not a
monthly spending cap.

Successful executions:

- Manual: `geovision-pilot-intelligence-8jc9uja`, 23:16:53–23:17:29 UTC.
- Scheduled: `geovision-pilot-intelligence-29835317`, 23:17:00–23:17:29 UTC.

Both completed on 22 September UTC, or 23 September in Madrid.

## Existing services rechecked

| Service | Observed result | What this establishes |
|---|---|---|
| Copernicus STAC | Two scene records from the bounded Spain query | Catalogue connectivity; not imagery download or derived measurements |
| AEMET | One recent station observation containing 12 metrics; verified again after GAIA activation | Live weather credential and normalized response; not a forecast or customer KPI |
| MITECO | Reachable, valid response with zero records | Connectivity only; no coverage/data assertion |
| Azure Blob | Private container, synthetic upload/read, signed download and cleanup succeeded | Working storage round trip; no customer file was altered |
| PostgreSQL | Read-only query succeeded; schema `phase34_sector_taxonomy_v1` | Database connectivity and observed schema version |
| Azure App Configuration | Healthy current snapshot; synthetic unknown flag denied | Flag configuration availability and default denial |

API ingress remains private and API scaling remains 0–2 replicas. Existing
Key Vault references, AEMET configuration, gateway authentication, event worker
and application images were preserved. No RBAC changes were made.

Anonymous requests through the gateway returned HTTP 401 for all four checks:
`GET /auth/me`, `GET /operations/providers`, `POST /ai/chat`, and
`POST /intelligence/weather/observations`. These verify anonymous rejection,
not every authenticated authorization path.

## Remaining activation work

Configuration alone does not implement a missing adapter. The provider catalogue
contains alternative vendors; activating every alternative is not a requirement
for the product to work.

| Group | Remaining requirement |
|---|---|
| Google Places, Routes and Geocoding | Google Cloud project/API key, service enablement, billing/restrictions and live journey test |
| SMTP email | Azure configured and SPF/DKIM verified; authorized test failed with SMTP 550. Delivery diagnosis remains open; see `../infra/azure/email/README.md`. |
| NodeODM | Reachable processing deployment/capacity and real dataset processing test |
| Stripe, PayPal, Multicaixa | Merchant/sandbox credentials and checkout/webhook/reconciliation tests |
| ERPNext or Odoo | Selected ERP instance, scoped credentials, schema mapping and synchronization test |
| Entra External ID, Google/Microsoft OAuth | Application/client configuration and authenticated mobile callback test; the existing Microsoft pilot gateway is separate |
| Azure Notification Hubs / APNs / FCM | Platform credentials, push resource/configuration and real device test |
| Azure IoT Hub / MQTT / drone integration | Chosen vendor connection, hardware/native SDK where required and field test |
| Azure Service Bus / Event Grid | Resources, access and subscriptions if selected; existing database-backed event worker remains available |
| S3 / Mapbox | Credentials only if these alternatives are selected; Azure Blob and the existing OpenStreetMap capability already serve their respective roles |
| Customer weather/satellite ingestion | Authorized site schedules, coverage checks, then observation/scene-to-KPI/report validation |
| FlutterFlow | Project wiring and authenticated end-to-end proof; no FlutterFlow project was changed in this activation |

Scaffold-only providers still need implementation: Azure Maps Weather, ArcGIS,
Autodesk APS, Procore, Bentley iTwin, Trimble, Seequent, mine enterprise,
SAP EAM, IBM Maximo, Dynamics 365, customer CMMS, MarineTraffic, Kpler,
Puertos del Estado, PIX4D, Autodesk processing, Bentley processing and external
report narrative. GAIA activation does not implement the separate external
report-narrative adapter.

The next useful activation sequence is one real site's weather/satellite flow,
then Google location services and transactional email, followed by the selected
processing, payment and ERP services. Account-dependent work remains pending
because no new credentials/accounts were supplied.

## Evidence and validation

Sanitized snapshots are stored with this record:

- [Runtime provider, storage and database checks](activation-evidence/20260923/runtime-activation-evidence-20260923.json)
- [Empty acquisition cycle and App Configuration](activation-evidence/20260923/intelligence-cycle-evidence-20260923.json)
- [GAIA response and preserved AEMET connection](activation-evidence/20260923/gaia-runtime-evidence-20260923.json)
- [Final deployment and successful job executions](activation-evidence/20260923/activation-deployment-20260923.json)
- [Anonymous access protection](activation-evidence/20260923/anonymous-protection-20260923.json)

The provider inventory snapshot precedes the GAIA change; its configuration
labels are inventory metadata, not the result of the separate live checks.
Eight focused activation-helper tests passed, covering preservation of source
configuration and secrets, deployment constraints, malformed/missing keys and
duplicate activation rejection. No application code was rebuilt or changed.

Rollback, if needed, is a separate operation: disable the acquisition schedule
before changing worker configuration; remove the API's OpenAI environment
references in a new revision to restore its existing no-key fallback behavior.
Retain acquisition records and existing provider secrets until the rollback is
verified. No rollback was performed.

Protocol references:
[Azure Container Apps jobs](https://learn.microsoft.com/en-us/azure/container-apps/jobs),
[OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat).
