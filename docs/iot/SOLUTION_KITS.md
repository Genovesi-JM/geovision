# DIY Solution Kits

Sensors carry GeoVision's vision now (drones come later, once piloting experience
and permissions exist): **connect hardware → stream data → turn data into analytical
reports.** To make that repeatable, GeoVision ships **DIY solution kits** — homemade,
ESP32-based nodes with a fixed sensor set per industry. Picking a kit provisions a real
device with the correct channels and starter alert rules in one step.

## Where it lives
- Catalogue: `backend/app/iot/kits.py` (`SOLUTION_KITS`).
- API: `backend/app/routers/iot.py`.
- Tests: `backend/tests/test_iot_platform.py::test_solution_kit_catalogue_and_one_step_provisioning`.

Kit channel units are validated against `backend/app/iot/registry.py`, so every kit is
guaranteed ingestible by the existing MQTT/REST pipeline. No new storefront, backend or
data model was created — kits reuse the existing device/provisioning/alert code.

## Kits included
| Kit | Industry | Core channels | Starter alerts | ~BOM |
|---|---|---|---|---|
| Cold Chain Starter | cold_chain | temperature, humidity, door, compressor run | over-temp (crit), low battery | ~$65 |
| Water Tank & Pump | water | tank_level, flow, pump run | low level (warn), critically low (crit) | ~$59 |
| Agriculture Field Node (solar) | agriculture | soil moisture/temp, air temp/humidity, rainfall | dry soil, frost risk | ~$135 |
| Property & Leak Guard | facilities | door, motion, water leak | leak (crit), after-hours motion | ~$44 |
| Environment & Air | environment | CO₂, PM2.5, temp, humidity, noise | high CO₂, high PM2.5 | ~$92 |

`battery` and `signal` ride along on every kit. Prices are DIY component estimates (USD);
the sellable price adds assembly, install and the recurring monitoring subscription — see
[SENSOR_KPI_MONETISATION.md](SENSOR_KPI_MONETISATION.md).

The earlier Energy & Power prototype remains in the code as a standby concept, but it is
not listed, provisionable or sold in the current GeoVision offer.

## API
- `GET /iot/kits` — list kits (each includes `diy_bom`, `bom_total_usd`, `channels`, `alert_rules`, `kpis`).
- `GET /iot/kits/{kit_id}` — one kit.
- `POST /iot/kits/{kit_id}/provision` — body `{ "site_id", "name"?, "asset_id"? }`.
  Creates the device + channels + alert rules, returns the standard one-time provisioning
  token/QR (expires in 30 min) plus `kit_id` and `alert_rules_created`.

## Verified flow (executed in tests, 19 passed)
1. List catalogue → kits have BOM + channel templates.
2. `POST /iot/kits/water_tank_starter/provision` → device created with the kit's channels and the "Low tank level" rule.
3. Exchange provisioning token → device secret.
4. Ingest `tank_level = 3` → a **critical** `tank_level` alert fires (the kit's own rule).
5. Device report PDF generates.

## Adding a kit
Append a dict to `SOLUTION_KITS` with `channels` whose `measurement_type`/`unit` exist in
`registry.SENSOR_UNITS`, optional `alert_rules`, a `diy_bom`, and `kpis`. The catalogue and
provisioning endpoints pick it up automatically; add a row to the table above.
