# Satellite and weather intelligence

Phase 15 adds reusable, provider-neutral remote intelligence to the monitoring,
acquisition and dataset foundations. It does not embed agriculture rules in the
provider adapters, so later sectors can consume the same normalized records.

## Data flow

```text
tenant-owned Asset geometry
        |
        v
intelligence request or weekly schedule
        |
        v
durable acquisition -> injected provider -> normalized result
        |                                  |
        v                                  v
canonical Acquisition/Dataset       scene or weather records
        |
        v
domain events and downstream sector analytics
```

Every request records its provider, status, attempt count, retry state, cache
fingerprint, source time and safe failure details. Equivalent requests reuse a
completed result until its configured cache expiry. Provider references remain
opaque and never replace GeoVision UUIDs.

## Satellite provider

`SATELLITE_PROVIDER=copernicus` selects the Copernicus Data Space STAC adapter.
It searches by the asset's EPSG:4326 geometry and requested time range, then
normalizes collection, acquisition/publish time, cloud cover, ground
resolution, CRS, bands, coverage, source link and advertised assets. The
adapter follows the official [Copernicus Data Space STAC
contract](https://documentation.dataspace.copernicus.eu/APIs/STAC.html).

Metadata-only discovery is the default. Optional imagery or thumbnail download
must be enabled explicitly and is limited by requested asset keys, response
size, HTTPS and a configured host allowlist. Query strings and fragments are
removed before source links are stored so signed credentials do not enter the
database. Downloaded bytes use the configured object-storage adapter and are
registered as ordinary Dataset files.

## Weather provider

`WEATHER_PROVIDER=aemet` selects AEMET OpenData for assets in Spain. It follows
the official two-step response: the authenticated API response supplies a
short-lived data URL, which is accepted only on the configured AEMET host. The
adapter selects the nearest reporting station within the configured radius and
normalizes each supported metric with observation time, numeric value, unit,
quality, station reference/name, coordinates, distance and provenance. See the
official [AEMET OpenData documentation](https://opendata.aemet.es/dist/).

Azure Maps Weather has an explicit unavailable adapter so configuration cannot
silently pretend that a future integration is live. Its future implementation
should follow the official [Azure Maps Weather REST
contract](https://learn.microsoft.com/en-us/rest/api/maps/weather?view=rest-maps-2026-01-01).

## API and scheduling

- `POST /intelligence/satellite/search` discovers scenes for an owned asset.
- `POST /intelligence/weather/observations` acquires nearby observations.
- `GET /intelligence/assets/{asset_id}/satellite` lists normalized scenes.
- `GET /intelligence/assets/{asset_id}/weather` lists observations.
- `GET /intelligence/acquisitions/{acquisition_id}` exposes safe status.
- `/intelligence/schedules` lets operations staff create, list and update
  recurring acquisitions. The default cadence is weekly.

Run scheduled and retry work outside API replicas:

```bash
python -m app.workers.intelligence_worker
```

`--once` processes one due batch. Database claims, stale-claim recovery and
bounded backoff make restarts safe. In-process execution exists only for an
explicit local demonstration and should not be enabled on horizontally scaled
API replicas.

## Activation gate

The deterministic fake providers support local and automated tests only and
are rejected in staging/production. Before enabling live providers, review
credentials, quotas, licence/attribution, geographic and temporal coverage,
station/scene quality, download/storage costs, failure monitoring and customer
interpretation. A successful provider response is source data, not proof of an
agronomic or engineering conclusion. The human gate is recorded in
`HUMAN_GATES.md`.
