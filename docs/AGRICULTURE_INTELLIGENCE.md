# Agriculture intelligence bundle 1.0.0

Phase 18 activates Agriculture as GeoVision's first complete sector package.
It composes the common Asset, Mission, Dataset, satellite/weather, IoT, KPI,
Observation and Action contracts; it adds no agriculture-only database column
or table.

## Supported vocabulary

The package declares `FARM`, `FIELD`, `SITE`, `ORCHARD`, `VINEYARD`, `PASTURE`,
`GREENHOUSE` and `IRRIGATION_ZONE` as supported asset identifiers. Dataset
inputs include RGB/multispectral/thermal imagery, orthomosaics, NDVI/NDRE/GNDVI,
satellite scenes, normalized weather and canonical telemetry. The generic
schemas remain extensible and do not import these vertical identifiers.

## Evidence contract and source fusion

Raster-derived measurements are accepted only from an explicit
`geovision.agriculture.analysis.v1` object in Dataset metadata. It contains an
algorithm/version, confidence, finite/ranged metric values and optional GeoJSON
zones. A satellite scene with red/NIR bands is useful context but does not, by
itself, become an NDVI value. Invalid ranges, failed datasets and unrecognized
free-form metadata are ignored rather than converted into facts.

The source loader combines the newest eligible dataset measurements with
canonical IoT readings and normalized weather observations. Every selected
value retains its own timestamp, Dataset/Mission when applicable, source,
confidence and provenance. A current/previous NDVI pair produces a transparent
delta; missing sources return explicit availability limitations and do not
crash evaluation.

## KPI and rule behavior

Primary KPIs cover crop condition, area needing attention and a water-stress
indicator. Secondary values cover NDVI/change, soil moisture, affected hectares
and vegetation coverage. NDRE, GNDVI, rainfall, temperature and humidity remain
technical context. Definitions without evidence are returned as `NO_DATA` with
`UNKNOWN` status. NDRE/GNDVI and descriptive weather carry no generic safety
classification.

Crop condition may use a clearly labelled NDVI vegetation-vigour proxy when no
explicit condition score exists. It is not a disease or yield diagnosis.
Derived zones and water-stress findings remain `NEEDS_REVIEW`; actions request
field inspection, a detailed survey, monitoring assessment or GeoVision
specialist review. The bundle never prescribes chemicals, irrigation volume,
nutrients, pest/disease treatment or yield expectations.

## APIs and downstream context

- `GET /sectors/agriculture/capabilities`
- `POST /assets/{asset_id}/agriculture/evaluate`
- `GET /assets/{asset_id}/agriculture/map-layers`
- `GET /assets/{asset_id}/agriculture/report-context`

Evaluation requires Asset update permission; contextual reads require Asset
read permission and exact tenant/workspace ownership. Map layers expose only
GeoVision-controlled references, never provider or signed storage URLs. Report
context is structured evidence only; Phase 19 owns narrative generation,
quality review and publication.

## Demo and activation gate

`app/sectors/agriculture/fixtures.py` supplies a deterministic credential-free
field example with two drone campaigns, an orthomosaic, a Copernicus scene,
observed weather, a calibrated field node and a spatial attention zone. It is a
test/demo fixture, not production evidence.

The initial thresholds are screening defaults. Gate 14a requires an accountable
agronomist to approve exact crops, regions, seasons, soil/sensor calibration,
confidence behavior, zone-area methods and wording before customer decision
claims are enabled.
