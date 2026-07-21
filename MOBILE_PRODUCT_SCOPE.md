# GeoVision mobile — product scope

The app is **not** a copy of geovisionops.com. The website explains GeoVision;
the app gives authenticated customers immediate operational access. The website
is used only as the source of visual identity (dark aesthetic, cyan/blue/green
accents, Inter type, card language) — translated into a native mobile design
system, not embedded in a WebView.

## Navigation

1. **Home** — organisation, selected site, critical alerts, active operations,
   latest report, device-health summary, quick actions, last-sync status.
2. **Sites** — list/search/sector-filter → site detail (KPIs, fields, areas) →
   site map. Agriculture is the first complete workflow; the model is
   multi-sector via sector-aware KPI definitions.
3. **Alerts** — list, severity filters (info/low/medium/high/critical),
   detail with location, recommended action, evidence, acknowledge / request
   intervention. Alerts originate on the backend; push routes to the app.
4. **Work** — service requests (drone op, inspection, install, maintenance,
   problem report), urgency, evidence, status tracking, offline queue.
5. **Account** — profile, organisation, reports, orders & payments, devices,
   language (EN/PT), security, privacy/terms, support, sign out, version + env.

## Agriculture workflow (prioritised depth)

KPIs: average NDVI, NDRE, vegetation coverage, water stress, infestation risk,
anomaly count, cultivated area, chemical cost/ha — each with status, trend and
sparkline, at site and field level, plus recommendations and intervention history.

## Demo mode

Clearly-labelled demo dataset (`DEMO DATA` ribbon) covering an example
organisation, agricultural sites with fields + KPIs, alerts, devices, a mission,
reports, a service request, products, and orders/payment states. The full
navigation and primary workflows are testable with zero credentials. Demo records
never mix with production data.

## Definition of done (beta) — tracked in AUTODEV_STATUS.md

Website still works · backend starts · migrations pass · `flutter analyze` clean ·
unit/widget tests pass · runs in iOS Simulator · Android buildable · coherent
design system · five nav areas work · demo mode works · maps work with mock
provider · alerts/work/reports/orders(mock) work · offline caching works · auth
works before release · no secrets committed · human gates documented · CI created.
