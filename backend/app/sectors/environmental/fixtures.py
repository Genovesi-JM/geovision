"""Deterministic Environmental satellite/drone comparison fixture."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any

from app.sectors.environmental.services import ANALYSIS_SCHEMA


def _analysis(
    *,
    algorithm: str,
    metrics: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "schema": ANALYSIS_SCHEMA,
        "validation_status": "VALIDATED",
        "algorithm": algorithm,
        "algorithm_version": "1.0.0",
        "confidence": 0.87,
        "metrics": metrics or {},
        **extra,
    }


def _classification(reference: str, version: str) -> dict[str, Any]:
    return {
        "reviewed": True,
        "basis": "VALIDATED_LAND_COVER_CLASSIFICATION",
        "source_reference": reference,
        "reference_version": version,
        "class_schema_version": "1.0.0",
    }


def demo_environmental_bundle(
    *,
    measured_at: datetime | None = None,
) -> dict[str, Any]:
    current_at = measured_at or datetime(2026, 9, 10, 8, 0, 0)
    boundary = {
        "type": "Polygon",
        "coordinates": [
            [
                [-3.72, 40.40],
                [-3.68, 40.40],
                [-3.68, 40.44],
                [-3.72, 40.44],
                [-3.72, 40.40],
            ]
        ],
    }
    change_zone = {
        "type": "Polygon",
        "coordinates": [
            [
                [-3.708, 40.410],
                [-3.696, 40.410],
                [-3.696, 40.420],
                [-3.708, 40.420],
                [-3.708, 40.410],
            ]
        ],
    }
    terrain_zone = {
        "type": "Polygon",
        "coordinates": [
            [
                [-3.693, 40.425],
                [-3.687, 40.425],
                [-3.687, 40.431],
                [-3.693, 40.431],
                [-3.693, 40.425],
            ]
        ],
    }
    thermal_zone = {
        "type": "Polygon",
        "coordinates": [
            [
                [-3.713, 40.429],
                [-3.709, 40.429],
                [-3.709, 40.433],
                [-3.713, 40.433],
                [-3.713, 40.429],
            ]
        ],
    }
    return deepcopy(
        {
            "asset": {
                "sector": "ENVIRONMENTAL",
                "asset_type": "RESTORATION_SITE",
                "name": "Guadarrama restoration monitoring area",
                "location_label": "Community of Madrid, Spain",
                "geometry": boundary,
                "metadata": {
                    "monitoring_program": "reforestation",
                    "demo_fixture": True,
                },
            },
            "datasets": [
                {
                    "name": "Previous Copernicus land-cover scene",
                    "dataset_type": "SATELLITE_IMAGE",
                    "provider_code": "copernicus",
                    "capture_date": current_at - timedelta(days=35),
                    "crs": "EPSG:4326",
                    "processing_level": "DERIVED",
                    "provenance": {
                        "source_name": "Copernicus Sentinel-2",
                        "collection": "sentinel-2-l2a",
                        "license_id": "copernicus-data-space-ecosystem",
                    },
                    "metadata": {
                        "environmental_analysis": _analysis(
                            algorithm="geovision.environmental.land_cover",
                            metrics={
                                "vegetation_cover": 72.0,
                                "ndvi_mean": 0.61,
                            },
                            classification_evidence=_classification(
                                "copernicus-land-cover-review", "baseline-1"
                            ),
                            change_candidates=[],
                        )
                    },
                },
                {
                    "name": "Current Copernicus change scene",
                    "dataset_type": "SATELLITE_IMAGE",
                    "provider_code": "copernicus",
                    "capture_date": current_at - timedelta(days=5),
                    "crs": "EPSG:4326",
                    "processing_level": "DERIVED",
                    "provenance": {
                        "source_name": "Copernicus Sentinel-2",
                        "collection": "sentinel-2-l2a",
                        "license_id": "copernicus-data-space-ecosystem",
                    },
                    "metadata": {
                        "environmental_analysis": _analysis(
                            algorithm="geovision.environmental.land_cover_change",
                            metrics={
                                "vegetation_cover": 63.0,
                                "vegetation_cover_change": -9.0,
                                "land_cover_change_area": 4.2,
                                "reforestation_cover": 63.0,
                                "reforestation_change": -9.0,
                                "ndvi_mean": 0.52,
                                "ndvi_change": -0.09,
                            },
                            classification_evidence=_classification(
                                "copernicus-land-cover-review", "current-2"
                            ),
                            comparison_evidence={
                                "current_dataset_id": "$self",
                                "previous_dataset_id": "$dataset:Previous Copernicus land-cover scene",
                                "aligned": True,
                                "same_crs": True,
                                "method": "geovision.environmental.aligned_land_cover_change",
                                "method_version": "1.0.0",
                            },
                            reforestation_evidence={
                                "reviewed": True,
                                "programme_reference": "restoration-programme-demo",
                                "baseline_version": "1",
                            },
                            change_candidates=[
                                {
                                    "id": "land-cover-zone-1",
                                    "kind": "land_cover_change",
                                    "new": True,
                                    "label": "Land-cover change candidate",
                                    "area_ha": 4.2,
                                    "severity": "WARNING",
                                    "confidence": 0.82,
                                    "geometry": change_zone,
                                },
                                {
                                    "id": "reforestation-zone-1",
                                    "kind": "reforestation_change",
                                    "new": True,
                                    "label": "Reforestation cover change candidate",
                                    "area_ha": 4.2,
                                    "severity": "WATCH",
                                    "confidence": 0.79,
                                    "geometry": change_zone,
                                },
                            ],
                            affected_area_evidence={
                                "reviewed": True,
                                "non_overlapping": True,
                                "inventory_reference": "reviewed-change-inventory-2",
                                "method": "geovision.environmental.candidate_area_inventory",
                                "method_version": "1.0.0",
                                "candidate_ids": ["land-cover-zone-1"],
                            },
                        )
                    },
                },
                {
                    "name": "Previous drone orthomosaic",
                    "dataset_type": "ORTHOMOSAIC",
                    "provider_code": "geovision",
                    "capture_date": current_at - timedelta(days=30),
                    "crs": "EPSG:25830",
                    "processing_level": "PROCESSED",
                    "provenance": {"source_name": "GeoVision drone survey"},
                    "metadata": {},
                },
                {
                    "name": "Current targeted drone orthomosaic",
                    "dataset_type": "ORTHOMOSAIC",
                    "provider_code": "geovision",
                    "capture_date": current_at - timedelta(days=2),
                    "crs": "EPSG:25830",
                    "processing_level": "DERIVED",
                    "provenance": {"source_name": "GeoVision drone survey"},
                    "metadata": {
                        "environmental_analysis": _analysis(
                            algorithm="geovision.environmental.drone_verification",
                            metrics={"vegetation_cover": 64.0, "ndvi_mean": 0.53},
                            classification_evidence=_classification(
                                "targeted-drone-classification", "verification-1"
                            ),
                            comparison_evidence={
                                "current_dataset_id": "$self",
                                "previous_dataset_id": "$dataset:Previous drone orthomosaic",
                                "aligned": True,
                                "same_crs": True,
                                "method": "geovision.environmental.orthomosaic_change",
                                "method_version": "1.0.0",
                            },
                            verification_evidence={
                                "reviewed": True,
                                "satellite_dataset_ids": [
                                    "$dataset:Current Copernicus change scene"
                                ],
                                "candidate_ids": ["land-cover-zone-1"],
                            },
                            change_candidates=[],
                        )
                    },
                },
                {
                    "name": "Previous terrain model",
                    "dataset_type": "DTM",
                    "provider_code": "geovision",
                    "capture_date": current_at - timedelta(days=60),
                    "crs": "EPSG:25830",
                    "processing_level": "DERIVED",
                    "provenance": {"source_name": "GeoVision terrain survey"},
                    "metadata": {},
                },
                {
                    "name": "Current terrain model",
                    "dataset_type": "DTM",
                    "provider_code": "geovision",
                    "capture_date": current_at - timedelta(days=1),
                    "crs": "EPSG:25830",
                    "processing_level": "DERIVED",
                    "provenance": {"source_name": "GeoVision terrain survey"},
                    "metadata": {
                        "environmental_analysis": _analysis(
                            algorithm="geovision.environmental.terrain_change",
                            metrics={"terrain_change_area": 0.7},
                            surface_evidence={
                                "current_dataset_id": "$self",
                                "previous_dataset_id": "$dataset:Previous terrain model",
                                "aligned": True,
                                "same_crs": True,
                                "vertical_datum": "EVRF2019",
                                "method": "geovision.environmental.surface_difference",
                                "method_version": "1.0.0",
                            },
                            change_candidates=[
                                {
                                    "id": "terrain-zone-1",
                                    "kind": "terrain_change",
                                    "new": True,
                                    "label": "Terrain-surface change candidate",
                                    "area_ha": 0.7,
                                    "severity": "WATCH",
                                    "confidence": 0.78,
                                    "geometry": terrain_zone,
                                }
                            ],
                        )
                    },
                },
                {
                    "name": "Reviewed thermal survey",
                    "dataset_type": "THERMAL_IMAGES",
                    "provider_code": "geovision",
                    "capture_date": current_at,
                    "crs": "EPSG:25830",
                    "processing_level": "DERIVED",
                    "provenance": {
                        "source_name": "GeoVision calibrated thermal survey"
                    },
                    "metadata": {
                        "environmental_analysis": _analysis(
                            algorithm="geovision.environmental.thermal_candidates",
                            thermal_evidence={
                                "reviewed": True,
                                "calibrated": True,
                                "sensor_reference": "thermal-payload-demo",
                                "calibration_reference": "calibration-record-demo",
                                "method": "geovision.environmental.thermal_contrast",
                                "method_version": "1.0.0",
                            },
                            thermal_hotspots=[
                                {
                                    "id": "thermal-zone-1",
                                    "new": True,
                                    "label": "Thermal contrast candidate",
                                    "severity": "WARNING",
                                    "confidence": 0.8,
                                    "geometry": thermal_zone,
                                }
                            ],
                        )
                    },
                },
                {
                    "name": "MITECO biodiversity context",
                    "dataset_type": "ENVIRONMENTAL_REFERENCE",
                    "provider_code": "miteco",
                    "capture_date": current_at - timedelta(days=1),
                    "crs": "EPSG:4326",
                    "processing_level": "PROCESSED",
                    "provenance": {
                        "official_source": True,
                        "source_name": "Ministerio para la Transición Ecológica y el Reto Demográfico",
                        "collection_id": "costas:poem_uso_prio_biodiv_zupbd",
                        "source_url": "https://gis.miteco.gob.es/geoserver/ogc/features/v1/",
                        "license_id": "MITECO-GENERAL-REUSE-CONDITIONS",
                        "license_url": "https://www.datosabiertos.miteco.gob.es/es/aviso-legal.html",
                        "reuse_notice_url": "https://www.datosabiertos.miteco.gob.es/es/aviso-legal.html",
                        "attribution": "Origen de los datos: Ministerio para la Transición ecológica y el Reto Demográfico",
                        "no_endorsement": True,
                        "context_only": True,
                        "measurements_authoritative": False,
                        "diagnostic_authority": False,
                        "geographic_scope": "Spain",
                        "dataset_updated_at": "2026-08-01",
                        "adapter_version": "miteco-ogc-features-v1",
                    },
                    "metadata": {},
                },
                {
                    "name": "AEMET observed weather context",
                    "dataset_type": "WEATHER_DATA",
                    "provider_code": "aemet",
                    "capture_date": current_at,
                    "crs": "EPSG:4326",
                    "processing_level": "RAW",
                    "provenance": {
                        "source_name": "AEMET OpenData",
                        "adapter_version": "aemet-opendata-v1",
                    },
                    "metadata": {},
                },
            ],
            "satellite_scenes": [
                {
                    "dataset_name": "Previous Copernicus land-cover scene",
                    "provider_code": "copernicus",
                    "provider_reference": "S2-ENV-DEMO-BASELINE",
                    "collection": "sentinel-2-l2a",
                    "acquired_at": current_at - timedelta(days=35),
                    "cloud_cover_percent": 8.0,
                    "resolution_meters": 10.0,
                    "coverage": boundary,
                },
                {
                    "dataset_name": "Current Copernicus change scene",
                    "provider_code": "copernicus",
                    "provider_reference": "S2-ENV-DEMO-CURRENT",
                    "collection": "sentinel-2-l2a",
                    "acquired_at": current_at - timedelta(days=5),
                    "cloud_cover_percent": 6.0,
                    "resolution_meters": 10.0,
                    "coverage": boundary,
                },
            ],
            "weather": [
                {"metric": "precipitation_24h_mm", "value": 2.4, "unit": "mm"},
                {"metric": "air_temperature_c", "value": 26.1, "unit": "°C"},
                {"metric": "relative_humidity_percent", "value": 58.0, "unit": "%"},
            ],
        }
    )


def resolve_demo_dataset_references(
    bundle: dict[str, Any],
    dataset_ids_by_name: dict[str, str],
) -> dict[str, Any]:
    """Replace fixture-only dataset tokens after canonical rows are flushed."""

    resolved = deepcopy(bundle)

    def replace(value: Any, *, current_id: str) -> Any:
        if value == "$self":
            return current_id
        if isinstance(value, str) and value.startswith("$dataset:"):
            return dataset_ids_by_name[value.removeprefix("$dataset:")]
        if isinstance(value, dict):
            return {
                key: replace(item, current_id=current_id) for key, item in value.items()
            }
        if isinstance(value, list):
            return [replace(item, current_id=current_id) for item in value]
        return value

    for item in resolved.get("datasets", []):
        current_id = dataset_ids_by_name[item["name"]]
        item["metadata"] = replace(item.get("metadata", {}), current_id=current_id)
    return resolved


__all__ = ["demo_environmental_bundle", "resolve_demo_dataset_references"]
