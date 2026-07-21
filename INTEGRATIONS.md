# GeoVision integrations

Accurate states: **Interface prepared** · **Mock working** · **Credential required**
· **Sandbox working** · **Production not activated**. A placeholder is never
reported as complete.

| Provider | Purpose | State | Env / define | Webhooks | Test method | Human gate |
|----------|---------|-------|--------------|----------|-------------|------------|
| Demo map | Credential-free operational map | **Mock working** | `GV_MAP_PROVIDER=demo` | — | Widget/manual | No |
| OpenStreetMap | Credential-free site point selection | **Working** | No key; attribution required | — | iOS/Android build + simulator | No |
| Device location | Optional precise site coordinates | **Working** with foreground permission | iOS/Android permission declarations | — | Simulator + physical-device follow-up | User permission |
| Offline world geography | Countries, regions and cities for international site registration | **Working** for 11 initial markets | Bundled `country_state_city` data; Angola official override | — | Unit + native builds | No |
| Mapbox | Satellite tiles + layers | Interface prepared · Credential required | `GV_MAP_PROVIDER=mapbox`, `GV_MAPBOX_TOKEN` | — | Token in staging | Yes (account/token) |
| ArcGIS | Enterprise GIS layers | Interface prepared | `GV_MAP_PROVIDER=arcgis` | — | — | Yes |
| Demo delivery map | Order route, vehicle position and progress timeline | **Mock working** | Default in demo mode | — | Unit + iOS Simulator | No |
| Google Maps + logistics feed | Live delivery tiles, route and courier position | Interface prepared · Credential required | Future `GV_DELIVERY_PROVIDER=google_maps`, API key | Provider-dependent | Staging delivery | Yes (API/logistics account) |
| Mock payment | Demo checkout | **Mock working** | `GV_PAYMENT_PROVIDER=mock` | — | Unit | No |
| Bank transfer / IBAN | Manual confirmation | **Mock working** (instructions + pending) | `GV_PAYMENT_PROVIDER=bank_transfer` | Finance confirm | Manual | No |
| Stripe | Card payments | Interface prepared · Credential required | `GV_PAYMENT_PROVIDER=stripe`, keys | Yes | Stripe sandbox | Yes (keys + store review) |
| Apple Pay / Google Pay | Wallet | Interface prepared | — | — | — | Yes |
| Multicaixa (Angola) | Local payments | Interface prepared | — | Yes | Sandbox | Yes |
| GeoVision commerce API | Catalogue, price lists, cart, checkout and owned order history | **Backend contract working** · production not activated | `GV_API_BASE_URL`, `GV_DEMO_MODE=false` | Payment-provider dependent | FastAPI contract + Flutter mapping | No for local/staging |
| GeoVision demo commerce | Seeds, inputs, equipment, sensors and services | **Mock working** | `GV_DEMO_MODE=true` | — | Unit + iOS Simulator | No |
| ERP/accounting platform | Fiscal invoicing, procurement, warehouse and reconciliation | Integration boundary planned; not required for MVP | Provider-dependent | Provider-dependent | ERP sandbox | Yes (provider/business decision) |
| APNs | iOS push | Interface prepared (mock emits) | `GV_PUSH_PROVIDER=apns` | — | Mock stream | Yes (Apple keys) |
| FCM | Android push | Interface prepared (mock emits) | `GV_PUSH_PROVIDER=fcm` | — | Mock stream | Yes (Firebase) |
| IoT multi-provider bridge | API, MQTT, webhooks, BLE provisioning, LoRaWAN and Modbus gateways | Contract + mock outcomes working · backend adapter prepared | `GV_IOT_PROVIDER=mock|backend` | Backend bridge | Unit outcome matrix | Yes (vendor credentials/hardware) |
| DJI / Pix4D / DroneDeploy | Drone + photogrammetry | Interface planned (backend-side) | — | Vendor | — | Yes |
| Google / Microsoft / Apple sign-in | OAuth | Backend routes exist; mobile prepared | — | Redirect | Sandbox | Yes (client IDs) |

### Adding a real provider
1. Implement the interface (e.g. `MapProvider`, `PaymentProvider`, `PushProvider`, `IotProvider`).
2. Select it via the feature-flag `--dart-define`.
3. Add credentials through `--dart-define` / secret manager — never in git.
4. Add a mock-parity test; document the gate here and in `HUMAN_GATES.md`.

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
