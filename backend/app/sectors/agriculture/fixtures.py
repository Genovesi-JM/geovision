"""Deterministic, credential-free Agriculture fusion fixture for demos and tests."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any

from app.sectors.agriculture.services import ANALYSIS_SCHEMA


def demo_fusion_bundle(
    *,
    measured_at: datetime | None = None,
) -> dict[str, Any]:
    current_at = measured_at or datetime(2026, 9, 10, 8, 0, 0)
    polygon = {
        "type": "Polygon",
        "coordinates": [
            [
                [13.10, -8.90],
                [13.13, -8.90],
                [13.13, -8.87],
                [13.10, -8.87],
                [13.10, -8.90],
            ]
        ],
    }
    attention_zone = {
        "type": "Polygon",
        "coordinates": [
            [
                [13.112, -8.888],
                [13.119, -8.888],
                [13.119, -8.881],
                [13.112, -8.881],
                [13.112, -8.888],
            ]
        ],
    }
    return deepcopy(
        {
            "asset": {
                "sector": "AGRICULTURE",
                "asset_type": "FIELD",
                "name": "Kwanza maize block A",
                "location_label": "Cuanza Sul, Angola",
                "geometry": polygon,
                "metadata": {
                    "crop": "maize",
                    "area_hectares": 48.0,
                    "growth_stage": "vegetative",
                    "demo_fixture": True,
                },
            },
            "datasets": [
                {
                    "name": "Previous multispectral campaign",
                    "dataset_type": "NDVI",
                    "capture_date": current_at - timedelta(days=14),
                    "quality_status": "PASSED",
                    "processing_level": "DERIVED",
                    "metadata": {
                        "agriculture_analysis": {
                            "schema": ANALYSIS_SCHEMA,
                            "algorithm": "geovision.vegetation_indices",
                            "algorithm_version": "1.0.0",
                            "confidence": 0.9,
                            "metrics": {
                                "ndvi_mean": 0.68,
                                "vegetation_coverage_percent": 82.0,
                            },
                            "zones": [],
                        }
                    },
                },
                {
                    "name": "Current drone multispectral campaign",
                    "dataset_type": "NDVI",
                    "capture_date": current_at,
                    "quality_status": "PASSED",
                    "processing_level": "DERIVED",
                    "metadata": {
                        "agriculture_analysis": {
                            "schema": ANALYSIS_SCHEMA,
                            "algorithm": "geovision.vegetation_indices",
                            "algorithm_version": "1.0.0",
                            "confidence": 0.88,
                            "metrics": {
                                "ndvi_mean": {"value": 0.57, "confidence": 0.88},
                                "ndre_mean": 0.31,
                                "gndvi_mean": 0.52,
                                "vegetation_coverage_percent": 74.0,
                                "water_stress_percent": 36.0,
                                "affected_area_ha": 3.4,
                            },
                            "zones": [
                                {
                                    "kind": "attention",
                                    "area_ha": 3.4,
                                    "confidence": 0.81,
                                    "geometry": attention_zone,
                                }
                            ],
                        }
                    },
                },
                {
                    "name": "Current orthomosaic",
                    "dataset_type": "ORTHOMOSAIC",
                    "capture_date": current_at,
                    "quality_status": "PASSED",
                    "processing_level": "PROCESSED",
                    "metadata": {},
                },
                {
                    "name": "Sentinel-2 context scene",
                    "dataset_type": "SATELLITE_IMAGE",
                    "capture_date": current_at - timedelta(days=2),
                    "quality_status": "PASSED",
                    "processing_level": "RAW",
                    "metadata": {},
                },
                {
                    "name": "Nearby observed weather",
                    "dataset_type": "WEATHER_DATA",
                    "capture_date": current_at,
                    "quality_status": "PASSED",
                    "processing_level": "RAW",
                    "metadata": {},
                },
            ],
            "satellite_scene": {
                "provider_code": "copernicus",
                "provider_reference": "S2-DEMO-20260908",
                "collection": "sentinel-2-l2a",
                "acquired_at": current_at - timedelta(days=2),
                "bands": ["B02", "B03", "B04", "B08"],
                "cloud_cover_percent": 7.2,
                "resolution_meters": 10.0,
                "coverage": polygon,
            },
            "weather": [
                {
                    "metric": "rainfall_24h_mm",
                    "value": 1.8,
                    "unit": "mm",
                    "quality": "observed",
                },
                {
                    "metric": "air_temperature_c",
                    "value": 29.4,
                    "unit": "°C",
                    "quality": "observed",
                },
                {
                    "metric": "relative_humidity_percent",
                    "value": 63.0,
                    "unit": "%",
                    "quality": "observed",
                },
            ],
            "telemetry": {
                "channel": "soil_moisture_percent",
                "value": 21.5,
                "unit": "%",
                "quality": "good",
                "recorded_at": current_at - timedelta(minutes=10),
            },
        }
    )


__all__ = ["demo_fusion_bundle"]
