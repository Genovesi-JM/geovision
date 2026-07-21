# GeoVision integrations

Accurate states: **Interface prepared** · **Mock working** · **Credential required**
· **Sandbox working** · **Production not activated**. A placeholder is never
reported as complete.

| Provider | Purpose | State | Env / define | Webhooks | Test method | Human gate |
|----------|---------|-------|--------------|----------|-------------|------------|
| Demo map | Credential-free operational map | **Mock working** | `GV_MAP_PROVIDER=demo` | — | Widget/manual | No |
| Mapbox | Satellite tiles + layers | Interface prepared · Credential required | `GV_MAP_PROVIDER=mapbox`, `GV_MAPBOX_TOKEN` | — | Token in staging | Yes (account/token) |
| ArcGIS | Enterprise GIS layers | Interface prepared | `GV_MAP_PROVIDER=arcgis` | — | — | Yes |
| Demo delivery map | Order route, vehicle position and progress timeline | **Mock working** | Default in demo mode | — | Unit + iOS Simulator | No |
| Google Maps + logistics feed | Live delivery tiles, route and courier position | Interface prepared · Credential required | Future `GV_DELIVERY_PROVIDER=google_maps`, API key | Provider-dependent | Staging delivery | Yes (API/logistics account) |
| Mock payment | Demo checkout | **Mock working** | `GV_PAYMENT_PROVIDER=mock` | — | Unit | No |
| Bank transfer / IBAN | Manual confirmation | **Mock working** (instructions + pending) | `GV_PAYMENT_PROVIDER=bank_transfer` | Finance confirm | Manual | No |
| Stripe | Card payments | Interface prepared · Credential required | `GV_PAYMENT_PROVIDER=stripe`, keys | Yes | Stripe sandbox | Yes (keys + store review) |
| Apple Pay / Google Pay | Wallet | Interface prepared | — | — | — | Yes |
| Multicaixa (Angola) | Local payments | Interface prepared | — | Yes | Sandbox | Yes |
| GeoVision commerce catalogue | Seeds, inputs, equipment, sensors and services | **Mock working** | Demo data | — | Unit + widget/manual | No |
| APNs | iOS push | Interface prepared (mock emits) | `GV_PUSH_PROVIDER=apns` | — | Mock stream | Yes (Apple keys) |
| FCM | Android push | Interface prepared (mock emits) | `GV_PUSH_PROVIDER=fcm` | — | Mock stream | Yes (Firebase) |
| IoT (MQTT/vendor) | Device readings | **Mock working** | — | Backend bridge | Mock provider | Yes (hardware) |
| DJI / Pix4D / DroneDeploy | Drone + photogrammetry | Interface planned (backend-side) | — | Vendor | — | Yes |
| Google / Microsoft / Apple sign-in | OAuth | Backend routes exist; mobile prepared | — | Redirect | Sandbox | Yes (client IDs) |

### Adding a real provider
1. Implement the interface (e.g. `MapProvider`, `PaymentProvider`, `PushProvider`, `IotProvider`).
2. Select it via the feature-flag `--dart-define`.
3. Add credentials through `--dart-define` / secret manager — never in git.
4. Add a mock-parity test; document the gate here and in `HUMAN_GATES.md`.
