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

The authenticated web portal also renders its validated GeoJSON layers over a
configured HTTPS base map. The default is OpenStreetMap with visible
attribution. Runtime tile configuration is restricted to known provider hosts,
required XYZ placeholders and provider zoom limits; invalid configuration fails
closed instead of loading an arbitrary tile origin.

Point features in that portal expose an allowlisted Google Maps directions link
and an explicit route-estimate action. Browser location is requested only when
the customer presses that action; the resulting coordinates are sent to the
authenticated GeoVision route endpoint and are not inserted into a provider
URL by the portal.

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

The backend now includes an authenticated provider boundary for Places API New
autocomplete, Place Details resolution, Routes API driving estimates and
Geocoding API v4 reverse address lookup. It
uses a deterministic local provider by contract test and a Google adapter with
mocked official HTTP responses. Live Google calls remain disabled until a
server-only key, billing, API restrictions, quotas, EEA terms and Spain/Angola
coverage are approved.

The site location picker consumes this boundary through the authenticated
GeoVision API. It debounces input, reuses one autocomplete session token through
place resolution, biases suggestions around the current point and sends the
site country as a region hint. Selecting a suggestion moves the marker, while
manual map taps and device GPS remain available. Demo mode uses deterministic
Luanda and Madrid entries without an external request.

After a manual map tap or GPS selection, the mobile picker offers an explicit
“identify this point” action. It performs reverse geocoding only on demand,
shows the returned address and keeps the original coordinate as the selected
site position, avoiding paid calls while the marker is being adjusted.

The asset map can also request a driving estimate from the device's current
position. Distance and duration come through the same server boundary and are
labelled as simulated, traffic-aware or non-traffic-aware. The estimate does
not replace the explicit Google Maps and Apple Maps navigation handoff.

## Production acceptance gate

Before enabling a live provider, record the account owner, billing limits,
allowed applications and APIs, licence/attribution review, privacy impact,
Spain and Angola coverage test, degraded/offline behavior, monitoring and
rollback to the demo provider. No empty or invalid credential may silently
claim that live maps are active.

GeoVision also applies per-client, per-minute API ceilings before a request can
reach the paid provider: 60 autocomplete calls, 30 place resolutions, 20 route
computations and 30 reverse-geocoding calls. These application limits reduce
accidental or abusive spend, but do not replace hard quotas, alerts and budgets
in the Google Cloud project.
