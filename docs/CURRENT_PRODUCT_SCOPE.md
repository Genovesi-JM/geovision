# GeoVision current product scope

This register separates the current customer offer from ideas retained for later. It is
based on the accepted direction in the ChatGPT discussions **Business Failure Analysis**,
**Find missing Geovision page items**, **Next steps after ESP32**, and the subsequent
website/app implementation discussion.

## Platform capability now

- The six public sectors are Agricultura & Pecuária, Construção &
  Infraestruturas, Ambiente, Mineração, Indústria, Energia & Utilities, and
  Portos & Logística. They use one shared platform and the canonical IDs in
  [`SECTOR_TAXONOMY.md`](SECTOR_TAXONOMY.md); mining is not an industry alias,
  and ports/logistics is not an industrial bucket. Availability in a customer
  workspace remains controlled by entitlement, modules, rollout flags,
  evidence, and delivery maturity.
- A simple entry experience for a farm, property/site, or individual device, backed by
  the same platform as the advanced enterprise experience.
- Connected-sensor software for near-real-time readings, device health, alerts,
  intervention history, reports, maps, and site/customer management. A live
  physical deployment still requires the hardware, calibration, safety, network,
  watchdog-owner, and provider gates in `HUMAN_GATES.md`.
- Practical first devices for air/comfort, soil, water/tank/pump, weather, leaks, and
  small-site monitoring.
- Aerial work that can be delivered with current equipment or partners: basic mapping,
  visual inspection, progress documentation, and appropriate agricultural imaging.
- GeoVision Supply as an inventory-light commercial layer connected to detected needs.

## Keep in code, but do not imply live commercial availability

- Mining and Portos & Logística backend workflows are implemented, but the
  sales offer must describe them only when GeoVision has validated delivery
  capability for the intended customer and region. Indústria, Energia &
  Utilities is a distinct expanding sector with capability discovery and
  source-dependent operational KPIs; it is not proof of a connected energy,
  industrial-control, compliance, or utility provider. Oil-and-gas-specific
  offers remain outside the current promise.
- LiDAR, advanced thermal/multispectral, spraying, very-high-precision surveying, and
  other specialised flights until a paid project justifies rental, partnership, or purchase.
- Advanced predictive AI before sufficient field data exists.
- Energy and power monitoring may be described only as a scoped
  Indústria, Energia & Utilities project after its sensors, sources,
  integration, safety, and delivery requirements are validated. It must not be
  presented as provisioned, automated, or live from the sector label alone.
- The tenant integration registry, rollout controls, and named construction,
  asset-management, GIS, and maritime provider scaffolds. These are internal
  platform capabilities, not a promise that any customer-owned provider is
  connected; each named provider remains blocked pending its own approved
  account, credentials, sandbox, contract, and live verification.

## Add or complete

- Deployment-derived KPIs rather than generic or imagined metrics: data freshness,
  uptime/completeness, time in range, device/battery/signal health, open incidents,
  MTTA/MTTR, maintenance due, and the monitored outcome for the selected site.
- Home/property signals supported by the current scope: temperature/humidity comfort,
  air quality, water level, and leak events. Home is an onboarding/site experience, not
  a separate GeoVision brand.
- GeoVision catalogue recommendations tied to the active account/site and monitored problem.
- Supply categories introduced through partners first: soil probes, irrigation parts,
  valves, pump accessories, weather equipment, replacement probes, cables/connectors,
  batteries, small tools, and selected seeds. Fertilisers and regulated crop-protection
  products only through qualified suppliers and after demand/legal validation.
- RFID/NFC animal identity first; GPS collar/tag development remains a prototype path.

## Decision rule

An assistant suggestion is not a product requirement. A capability moves into the public
offer only when the user has explicitly accepted it or a current paid/validated use case
supports it. Otherwise, preserve reusable architecture and keep the capability hidden.
