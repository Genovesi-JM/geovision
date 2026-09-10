"""Deterministic, credential-free Infrastructure evidence fixture."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any

from app.sectors.infrastructure.services import ANALYSIS_SCHEMA


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
        "confidence": 0.88,
        "metrics": metrics or {},
        **extra,
    }


def demo_infrastructure_bundle(
    *,
    measured_at: datetime | None = None,
) -> dict[str, Any]:
    current_at = measured_at or datetime(2026, 9, 10, 8, 0, 0)
    boundary = {
        "type": "Polygon",
        "coordinates": [
            [
                [13.10, -8.90],
                [13.14, -8.90],
                [13.14, -8.86],
                [13.10, -8.86],
                [13.10, -8.90],
            ]
        ],
    }
    visual_zone = {
        "type": "Polygon",
        "coordinates": [
            [
                [13.112, -8.888],
                [13.118, -8.888],
                [13.118, -8.882],
                [13.112, -8.882],
                [13.112, -8.888],
            ]
        ],
    }
    thermal_zone = {
        "type": "Polygon",
        "coordinates": [
            [
                [13.125, -8.878],
                [13.130, -8.878],
                [13.130, -8.873],
                [13.125, -8.873],
                [13.125, -8.878],
            ]
        ],
    }
    return deepcopy(
        {
            "asset": {
                "sector": "INFRASTRUCTURE",
                "asset_type": "ROAD",
                "name": "Kwanza corridor section A",
                "location_label": "Cuanza Sul, Angola",
                "geometry": boundary,
                "metadata": {"project_code": "DEMO-INFRA-01", "demo_fixture": True},
            },
            "datasets": [
                {
                    "name": "Previous reviewed orthomosaic",
                    "dataset_type": "ORTHOMOSAIC",
                    "capture_date": current_at - timedelta(days=21),
                    "crs": "EPSG:32733",
                    "processing_level": "DERIVED",
                    "metadata": {
                        "infrastructure_analysis": _analysis(
                            algorithm="geovision.infrastructure.progress",
                            metrics={"overall_progress": 42.0},
                            progress_evidence={
                                "reviewed": True,
                                "basis": "VALIDATED_SURVEY_CLASSIFICATION",
                                "source_reference": "orthomosaic-review-A",
                                "reference_version": "survey-review-1",
                            },
                            anomalies=[],
                            review_areas=[],
                        )
                    },
                },
                {
                    "name": "Current reviewed orthomosaic",
                    "dataset_type": "ORTHOMOSAIC",
                    "capture_date": current_at,
                    "crs": "EPSG:32733",
                    "processing_level": "DERIVED",
                    "metadata": {
                        "infrastructure_analysis": _analysis(
                            algorithm="geovision.infrastructure.progress",
                            metrics={"overall_progress": 57.0, "area_change": 1200.0},
                            progress_evidence={
                                "reviewed": True,
                                "basis": "VALIDATED_SURVEY_CLASSIFICATION",
                                "source_reference": "orthomosaic-review-A",
                                "reference_version": "survey-review-2",
                            },
                            comparison_evidence={
                                "current_dataset_id": "$self",
                                "previous_dataset_id": "$dataset:Previous reviewed orthomosaic",
                                "aligned": True,
                                "same_crs": True,
                                "method": "geovision.orthomosaic_change",
                                "method_version": "1.0.0",
                            },
                            anomalies=[
                                {
                                    "id": "visual-candidate-1",
                                    "kind": "visual",
                                    "new": True,
                                    "label": "Surface appearance change",
                                    "severity": "WATCH",
                                    "confidence": 0.82,
                                    "geometry": visual_zone,
                                }
                            ],
                            review_areas=[
                                {
                                    "id": "review-area-1",
                                    "label": "Survey classification review area",
                                    "severity": "WATCH",
                                    "confidence": 0.8,
                                    "geometry": visual_zone,
                                }
                            ],
                        )
                    },
                },
                {
                    "name": "Previous DSM",
                    "dataset_type": "DSM",
                    "capture_date": current_at - timedelta(days=21),
                    "crs": "EPSG:32733",
                    "processing_level": "DERIVED",
                    "metadata": {},
                },
                {
                    "name": "Current DSM",
                    "dataset_type": "DSM",
                    "capture_date": current_at,
                    "crs": "EPSG:32733",
                    "processing_level": "DERIVED",
                    "metadata": {
                        "infrastructure_analysis": _analysis(
                            algorithm="geovision.infrastructure.surface_change",
                            metrics={
                                "volume_change": 2250.0,
                                "cut_volume": 180.0,
                                "fill_volume": 2430.0,
                            },
                            surface_evidence={
                                "current_dataset_id": "$self",
                                "previous_dataset_id": "$dataset:Previous DSM",
                                "aligned": True,
                                "same_crs": True,
                                "vertical_datum": "EGM2008",
                                "method": "geovision.surface_difference",
                                "method_version": "1.0.0",
                            },
                        )
                    },
                },
                {
                    "name": "Current thermal review",
                    "dataset_type": "THERMAL_IMAGES",
                    "capture_date": current_at,
                    "crs": "EPSG:32733",
                    "processing_level": "DERIVED",
                    "metadata": {
                        "infrastructure_analysis": _analysis(
                            algorithm="geovision.infrastructure.thermal_candidates",
                            anomalies=[
                                {
                                    "id": "thermal-candidate-1",
                                    "kind": "thermal",
                                    "new": True,
                                    "label": "Thermal contrast candidate",
                                    "severity": "WARNING",
                                    "confidence": 0.84,
                                    "geometry": thermal_zone,
                                }
                            ],
                        )
                    },
                },
                {
                    "name": "Trusted project schedule",
                    "dataset_type": "PROJECT_REFERENCE",
                    "capture_date": current_at,
                    "crs": "EPSG:32733",
                    "processing_level": "DERIVED",
                    "metadata": {
                        "infrastructure_analysis": _analysis(
                            algorithm="geovision.infrastructure.schedule",
                            metrics={"schedule_variance": 5.0},
                            schedule_evidence={
                                "trusted": True,
                                "kind": "SIGNED_BASELINE",
                                "source_system": "SIGNED_MANUAL",
                                "source_reference": "baseline-programme-A",
                                "baseline_version": "3",
                            },
                        )
                    },
                },
                {
                    "name": "Current point cloud",
                    "dataset_type": "POINT_CLOUD",
                    "capture_date": current_at,
                    "crs": "EPSG:32733",
                    "processing_level": "PROCESSED",
                    "metadata": {},
                },
                {
                    "name": "Current 3D mesh",
                    "dataset_type": "MESH_3D",
                    "capture_date": current_at,
                    "crs": "EPSG:32733",
                    "processing_level": "PROCESSED",
                    "metadata": {},
                },
                {
                    "name": "Current BIM reference",
                    "dataset_type": "BIM_MODEL",
                    "capture_date": current_at,
                    "crs": "EPSG:32733",
                    "processing_level": "PROCESSED",
                    "metadata": {},
                },
            ],
        }
    )


def resolve_demo_dataset_references(
    bundle: dict[str, Any],
    dataset_ids_by_name: dict[str, str],
) -> dict[str, Any]:
    """Replace fixture-only dataset tokens after deterministic rows are flushed."""

    resolved = deepcopy(bundle)

    def replace(value: Any, *, current_id: str) -> Any:
        if value == "$self":
            return current_id
        if isinstance(value, str) and value.startswith("$dataset:"):
            return dataset_ids_by_name[value.removeprefix("$dataset:")]
        if isinstance(value, dict):
            return {key: replace(item, current_id=current_id) for key, item in value.items()}
        if isinstance(value, list):
            return [replace(item, current_id=current_id) for item in value]
        return value

    for item in resolved.get("datasets", []):
        current_id = dataset_ids_by_name[item["name"]]
        item["metadata"] = replace(item.get("metadata", {}), current_id=current_id)
    return resolved


__all__ = ["demo_infrastructure_bundle", "resolve_demo_dataset_references"]
