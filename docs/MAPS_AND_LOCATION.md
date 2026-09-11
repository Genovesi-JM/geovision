# Maps and location architecture

GeoVision now renders customer asset locations through one mobile map-provider
boundary. The provider can change without changing canonical Asset identifiers,
workspace authorization, stored coordinates, or sector logic.

## Current capability

| Provider | Intended use | State |
|---|---|---|
| `demo` | Offline-safe demonstration with no network requests | Working |
| `openstreetmap` | Development, pilots and precise point selection | Working; attribution is rendered |
| `mapbox` | Satellite base tiles for approved deployments | Working behind `GV_MAPBOX_TOKEN`; live account review required |

`AssetMapScreen` uses the selected provider when it supplies XYZ tiles and
retains the local demonstration surface otherwise. The site-location picker
uses the same selected provider and falls back explicitly to OpenStreetMap when
the application is in demo mode. Individual screens no longer own hard-coded
tile URLs.

An asset with valid coordinates also offers Google Maps and Apple Maps driving
handoff. GeoVision constructs only allowlisted HTTPS universal links from
validated latitude/longitude values. This works without an API key and does not
give GeoVision access to the user's route or navigation history.

## Configuration and secrets

Select a provider with `GV_MAP_PROVIDER`. Mapbox uses `GV_MAPBOX_TOKEN` supplied
at build time. Mobile map tokens are client-visible by design, so they must be
restricted by the provider to the approved applications, origins, APIs and
quotas. Server credentials, signing secrets and customer-owned GIS credentials
must never be placed in Dart defines or shipped inside the application.

The checked-in production profile remains `demo` until the provider account,
licence, budget alerts, restrictions and staging evidence are approved. The
real-local profile uses OpenStreetMap so engineers can verify the real backend
journey without a commercial credential.

## Capabilities that remain separate

A visual base map does not provide all location services. Future integrations
must use explicit provider interfaces and capability flags for:

- address autocomplete and place search;
- forward and reverse geocoding;
- road routing, travel times and navigation;
- fleet, courier or emergency-vehicle position feeds;
- traffic, elevation, street imagery and offline regions;
- customer-owned ArcGIS or other enterprise GIS layers.

Google Maps Platform can later be added for Places, server-calculated Routes
and native turn-by-turn navigation without replacing GeoVision's canonical
coordinates or operational layer model. The current external-app handoff is
not a substitute for those APIs. Provider responses are external references
and cached evidence, never GeoVision primary identifiers.

## Production acceptance gate

Before enabling a live provider, record the account owner, billing limits,
allowed applications and APIs, licence/attribution review, privacy impact,
Spain and Angola coverage test, degraded/offline behavior, monitoring and
rollback to the demo provider. No empty or invalid credential may silently
claim that live maps are active.
