# GeoVision current product scope

This register separates the current customer offer from ideas retained for later. It is
based on the accepted direction in the ChatGPT discussions **Business Failure Analysis**,
**Find missing Geovision page items**, **Next steps after ESP32**, and the subsequent
website/app implementation discussion.

## Platform capability now

- Agriculture, Infrastructure, Environmental, Mining, and Ports/Industrial are
  implemented backend sector modules on one shared platform. Their availability
  in a customer workspace remains controlled by entitlement, modules, and
  rollout flags.
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

- Mining and Ports/Industrial backend workflows are implemented, but the public
  website and sales offer must describe them only when GeoVision has validated
  delivery capability for the intended customer and region. Utilities and
  oil-and-gas-specific offers remain outside the current promise.
- LiDAR, advanced thermal/multispectral, spraying, very-high-precision surveying, and
  other specialised flights until a paid project justifies rental, partnership, or purchase.
- Advanced predictive AI before sufficient field data exists.
- Energy and power monitoring. The prototype definition may remain on standby, but it is
  not listed, provisionable, recommended, or sold as part of the current offer.
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
