# Analytical reports & marketplace wiring

Two pieces that complete the "sensors → data → analytical reports → sellable" loop.

## Analytical reports
Turns stored telemetry into KPIs, not just min/max/avg.

- Engine: `backend/app/iot/analytics.py` — pure functions over ORM rows (testable without a DB).
- JSON API: `GET /iot/devices/{device_id}/analytics?days=30`.
- PDF: the existing `GET /iot/devices/{device_id}/report.pdf` now embeds the KPI table and
  **data-driven recommendations** (via `build_device_pdf(..., analytics=...)`).

KPIs computed:
- Overview: total readings, channels reporting, device status, **stale** flag, data-span ratio, **completeness %** (from median sampling cadence).
- Per channel: samples, min/max/avg/last, **time-in-range %** (against channel bounds), **duty cycle + estimated run-hours + activations** (boolean/run-status), bad-quality sample count.
- Incidents: total, by severity, open, resolved, **MTTA/MTTR**.
- Recommendations: generated from the findings (stale device, open alerts, out-of-range channels, low battery, poor data coverage).

Time-integrated figures (run-hours, uptime) are honest estimates from sample density and are labelled as such.

Tests: `tests/test_iot_platform.py::test_device_analytics_kpis`.

## Marketplace wiring
DIY kits are sold through the **existing** store — no new storefront.

- `backend/app/services/cart.py::seed_kit_products` upserts active `ShopProduct` records on every
  startup (id `prod_kit_<kit_id>`, `product_type="hardware"`, `category="sensor_kit"`) and
  deactivates standby concepts, so unsupported products do not leak into a pre-existing catalogue.
  Called from `app/main.py` startup after `seed_shop_products`.
- Prices: `price_usd` from the kit; AOA/EUR derived. KPIs become the product `deliverables`.

Tests: `tests/test_shop_api.py::test_diy_kits_appear_in_marketplace`.
