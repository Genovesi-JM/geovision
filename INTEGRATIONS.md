# GeoVision integrations

Accurate states: **Interface prepared** · **Mock working** · **Credential required**
· **Sandbox working** · **Production not activated**. A placeholder is never
reported as complete.

Latest live check: [23 September 2026 activation record](docs/PROVIDER_ACTIVATION_20260923.md).
GAIA now uses a verified real model in the private Azure pilot; the hourly
weather/satellite worker has completed manual and scheduled runs. The queue was
empty, so customer acquisition-to-KPI/report flows remain unverified.

Hosting cutover: [23 September 2026 Azure migration](docs/AZURE_CUTOVER_20260923.md).
The public website and `https://api.geovisionops.com` now use Azure with managed
TLS and the existing Azure data, as explicitly approved by the user. Google
OAuth credentials are configured on the canonical API; full account login is
still unverified. This hosting change does not activate the gated providers below.

Customer-flow follow-up: [23 September 2026 journey verification](docs/CUSTOMER_JOURNEY_20260923.md).
Email/password registration and login, the customer dashboard/map, Azure file
upload/download, and the signed-in GAIA widget have now been exercised against
Azure with synthetic data. The Google callback mismatch was corrected; Google
now opens its sign-in page, while consent and account return remain unverified.

FlutterFlow follow-up: the [16-call starter](infra/flutterflow/README.md) is now
imported in the owner's accessible project, with dynamic request bodies and
multipart upload binding. Health returned 200 and deliberately invalid login
returned 401 in the editor; screen wiring and successful authenticated FlutterFlow
journeys remain pending. [Azure transactional email](infra/azure/email/README.md)
now has a verified sending domain and SMTP configured in the canonical API.
Authentication passed from the running container; no message has been sent and
the independent notification delivery worker is not yet activated.

## DJI drones and automated missions

| Capability | Current state | Production requirement |
|---|---|---|
| DJI Neo | Media import and operation history prepared | Physical iPhone/Android import test |
| Mission planning | Boundary, altitude, speed and overlap contracts implemented | Supported aircraft and final route generator |
| Flight safety | Mandatory pilot, airspace, weather, people and aircraft checklist | Operational/legal approval |
| DJI MSDK handoff | Typed readiness and provider boundary implemented | DJI Developer credentials and native Android SDK adapter |
| Telemetry/media sync | Provider capabilities and backend storage prepared | Supported aircraft, SDK and field test |

The application never represents DJI Neo as an automated-flight aircraft. Flight
execution is separated from planning and requires an explicit provider handoff
plus pilot supervision.

| Provider | Purpose | State | Env / define | Webhooks | Test method | Human gate |
|----------|---------|-------|--------------|----------|-------------|------------|
| Demo map | Credential-free operational map | **Mock working** | `GV_MAP_PROVIDER=demo` | — | Widget/manual | No |
| OpenStreetMap | Credential-free site point selection and operational asset tiles | **Working** | `GV_MAP_PROVIDER=openstreetmap`; attribution required | — | Provider tests + iOS/Android build | No for pilot; tile-policy review for production volume |
| Device location | Optional precise site coordinates | **Working** with foreground permission | iOS/Android permission declarations | — | Simulator + physical-device follow-up | User permission |
| Offline world geography | Countries, regions and cities for international site registration | **Working** for 11 initial markets | Bundled `country_state_city` data; Angola official override | — | Unit + native builds | No |
| Mapbox | Satellite tiles on asset maps through the shared map renderer | **Adapter working** · Credential required | `GV_MAP_PROVIDER=mapbox`, `GV_MAPBOX_TOKEN` | — | Provider contract + restricted token in staging | Yes (account/token/licence) |
| ArcGIS | Enterprise GIS layers | Future integration-registry adapter; not a mobile selector | Server-managed connection | Provider-dependent | — | Yes |
| Demo delivery map | Order route, vehicle position and progress timeline | **Mock working** | Default in demo mode | — | Unit + iOS Simulator | No |
| Google Maps / Apple Maps handoff | Open driving directions to a validated asset coordinate | **Working** through allowlisted universal links; no API key | No credential | — | URL contract + native launcher | No |
| Google Places, Routes + Geocoding APIs | Server-side autocomplete, selected-place coordinates, driving estimates and reverse address lookup | **Adapter + authenticated API working** · live credential not activated | `LOCATION_PROVIDER=google_maps`, server-only `GOOGLE_MAPS_SERVER_API_KEY` | — | Deterministic journey + mocked official HTTP contracts | Yes (billing, restrictions, EEA terms, quota and coverage) |
| Google Maps + logistics feed | Live delivery tiles, route and courier position | Interface prepared · Credential required | Future `GV_DELIVERY_PROVIDER=google_maps`, API key | Provider-dependent | Staging delivery | Yes (API/logistics account) |
| Mock payment | Demo checkout | **Mock working** | `GV_PAYMENT_PROVIDER=mock` | — | Unit | No |
| Bank transfer / IBAN | Manual confirmation | **Mock working** (instructions + pending) | `GV_PAYMENT_PROVIDER=bank_transfer` | Finance confirm | Manual | No |
| Stripe | Card payments | Interface prepared · Credential required | `GV_PAYMENT_PROVIDER=stripe`, keys | Yes | Stripe sandbox | Yes (keys + store review) |
| Apple Pay / Google Pay | Wallet | Interface prepared | — | — | — | Yes |
| Multicaixa (Angola) | Local payments | Interface prepared | — | Yes | Sandbox | Yes |
| GeoVision commerce API | Catalogue, price lists, cart, checkout and owned order history | **Backend contract working** · production not activated | `GV_API_BASE_URL`, `GV_DEMO_MODE=false` | Payment-provider dependent | FastAPI contract + Flutter mapping | No for local/staging |
| GeoVision demo commerce | Seeds, inputs, equipment, sensors and services | **Mock working** | `GV_DEMO_MODE=true` | — | Unit + iOS Simulator | No |
| GAIA assistant | Short explanations of the customer's current sites, areas, KPIs, alerts, devices, work and store products | **Live model and authenticated Azure web widget verified with synthetic customer/site context** · wider customer scenarios remain unverified | Backend `OPENAI_API_KEY`, `OPENAI_MODEL=gpt-4o-mini` | — | Real UI response plus scoped OpenAI usage records; no demo fallback | Customer rollout and AI governance |
| GeoVision support channels | WhatsApp, Instagram and support email from the public website | **Working** through native external links | Maintained website contact records | — | iOS/Android native build | No |
| Website payment methods | Multicaixa Express, Angola IBAN, Visa/Mastercard, international IBAN and PayPal presentation | **Working in mobile UI and checkout selection** · live providers gated | Backend/provider-specific | Provider-dependent | Flutter tests + native builds | Yes for live processing |
| ERPNext | Sales, purchasing, inventory, warehouse, invoices and reconciliation | **Adapter + durable outbox working in mock mode** · staging credentials required | `ERP_PROVIDER=erpnext`, `ERPNEXT_BASE_URL`, restricted API credentials | Inbound webhook after staging schema approval | Mock adapter + backend contract | Yes (hosting, credentials, fiscal validation) |
| Azure Service Bus | Durable cross-module event topic and consumers | **Adapter + local database worker working** · live namespace not activated | `QUEUE_PROVIDER=azure_service_bus`, namespace or connection secret, topic/subscription | Topic subscription | Fake adapter + outbox failure-mode tests | Yes (Azure resource/RBAC) |
| Azure Event Grid | BlobCreated to dataset-ingestion bridge | **Authenticated adapter working** · live subscription not activated | Event Grid enable flag, custom delivery secret, storage account/container | BlobCreated + validation handshake | Contract + duplicate-ingestion tests | Yes (subscription/RBAC) |
| NodeODM / OpenDroneMap | Automated orthomosaic, elevation, point-cloud, mesh and supported index processing | **Adapter + durable worker + deterministic fake working** · live processor not activated | `PROCESSING_PROVIDER=nodeodm`, `NODEODM_BASE_URL`, optional server-side token | Polling through official task API | Fake end-to-end pipeline + mocked official HTTP contract | Yes (capacity/network/licence/quality review) |
| PIX4D / Autodesk Reality Capture / Bentley Reality Modeling | Future photogrammetry engines | Interface scaffold only; fails explicitly when selected | Future provider-specific configuration | Provider-dependent | Not available until adapter implementation | Yes (account/purchase/integration approval) |
| Copernicus Data Space / Sentinel-2 | Asset-scoped satellite scene discovery and optional imagery ingestion | **Live catalogue verified; hourly worker active** · downloads disabled; customer acquisition flow unverified | `SATELLITE_PROVIDER=copernicus`, STAC URL, optional server-side token and download allowlist | Hourly scheduled polling | Two real catalogue records; successful empty-queue worker executions | Quota/licence/coverage/quality review before customer rollout |
| AEMET OpenData | Spain weather observations near an asset | **Live key and observation verified; hourly worker active** · customer acquisition flow unverified | `WEATHER_PROVIDER=aemet`, `AEMET_API_KEY`, base URL and distance limit | Hourly scheduled polling | One real recent station observation with 12 metrics; successful empty-queue worker executions | Quota/station coverage review before customer rollout |
| Azure Maps Weather | Future weather provider | Interface scaffold only; fails explicitly when selected | Future Azure Maps credential configuration | Provider-dependent | Not available until adapter implementation | Yes (account/purchase/integration approval) |
| APNs | iOS push | Interface prepared (mock emits) | `GV_PUSH_PROVIDER=apns` | — | Mock stream | Yes (Apple keys) |
| FCM | Android push | Interface prepared (mock emits) | `GV_PUSH_PROVIDER=fcm` | — | Mock stream | Yes (Firebase) |
| IoT multi-provider bridge | API, MQTT, webhooks, BLE provisioning, LoRaWAN and Modbus gateways | Contract + mock outcomes working · backend adapter prepared | `GV_IOT_PROVIDER=mock|backend` | Backend bridge | Unit outcome matrix | Yes (vendor credentials/hardware) |
| DJI / DroneDeploy | Drone acquisition and media import | Interface planned (backend-side) | — | Vendor | — | Yes |
| Google sign-in | OAuth | **Azure callback saved and Google sign-in page verified** · full account login unverified | Server-only `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | `/auth/google/callback` | Deterministic tests + real Google redirect acceptance | Actual account consent/login verification |
| Microsoft / Apple sign-in | OAuth | Backend routes exist; mobile prepared | — | Redirect | Sandbox | Yes (client IDs) |

### Adding a real provider
1. Implement the interface (e.g. `MapProvider`, `PaymentProvider`, `PushProvider`, `IotProvider`).
2. Select it via the feature-flag `--dart-define`.
3. Add credentials through `--dart-define` / secret manager — never in git.
4. Add a mock-parity test; document the gate here and in `HUMAN_GATES.md`.

Map rendering and address/search/routing are separate capabilities. A map-tile
token must not be treated as authorization for geocoding, Places, Directions,
live fleet location, or customer enterprise GIS. See
[`docs/MAPS_AND_LOCATION.md`](docs/MAPS_AND_LOCATION.md).

### IoT outcome contract

Every provisioning, diagnostic and command operation returns one typed state:
`success`, `pending`, `offline`, `permissionRequired`, `credentialsRequired`,
`unsupported`, `rejected`, `timeout` or `error`. Remote commands default to
explicit confirmation. Vendor secrets remain in the backend; the phone only
uses BLE for nearby setup and the GeoVision API for durable monitoring.

### Commercial source of truth

PostgreSQL remains the MVP source of truth for catalogue, explicit AKZ/AOA,
EUR and USD price lists, stock, carts, orders, payment state and delivery events.
`AKZ` is shown to customers as requested; integrations must use the ISO currency
code `AOA`. The mobile demo now mirrors explicit price lists instead of deriving
catalogue prices from live exchange rates; production checkout always accepts
the API's recorded price. An ERP becomes appropriate for statutory invoicing,
supplier purchasing, multiple warehouses and accounting reconciliation; it
should synchronize through an adapter instead of replacing the mobile API.

### ERPNext document mapping

GeoVision remains the only API used by the mobile app. The durable outbox maps
customer, product, order, invoice, payment and delivery events to ERPNext
`Customer`, `Item`, `Sales Order`, `Sales Invoice`, `Payment Entry` and
`Delivery Note` documents. The independent event worker claims requests and
retries with a unique idempotency key; exhausted work is visible and recoverable
through the dead-letter API. ERP downtime does not block customer checkout. No
ERP credential or internal accounting data is returned to the mobile app.
