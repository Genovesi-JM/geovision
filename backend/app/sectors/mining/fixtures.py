"""Deterministic two-survey Mining stockpile fixture."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any

from app.sectors.mining.services import ANALYSIS_SCHEMA


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
        "confidence": 0.91,
        "metrics": metrics or {},
        **extra,
    }


def _survey(reference: str) -> dict[str, Any]:
    return {
        "reviewed": True,
        "survey_reference": reference,
        "method": "geovision.mining.rtk_ppk_survey",
        "method_version": "1.0.0",
        "crs": "EPSG:25830",
    }


def _quality(reference: str, control_dataset: str) -> dict[str, Any]:
    return {
        "reviewed": True,
        "project_tolerance_approved": True,
        "tolerance_reference": "stockpile-project-tolerance-v1",
        "method": "geovision.mining.rtk_ppk_photogrammetry",
        "method_version": "1.0.0",
        "acquisition_method": "RTK_PPK_PHOTOGRAMMETRY",
        "survey_reference": reference,
        "horizontal_rmse_cm": 2.4,
        "vertical_rmse_cm": 4.1,
        "ground_sample_distance_cm": 2.0,
        "control_point_count": 6,
        "checkpoint_count": 5,
        "control_dataset_id": control_dataset,
        "crs": "EPSG:25830",
        "vertical_datum": "EVRF2019",
        "project_tolerances": {
            "max_horizontal_rmse_cm": 5.0,
            "max_vertical_rmse_cm": 8.0,
            "max_ground_sample_distance_cm": 3.0,
            "min_control_point_count": 4,
            "min_checkpoint_count": 4,
        },
    }


def _surface_reference(reference: str) -> dict[str, Any]:
    return {
        "reviewed": True,
        "surface_reference": reference,
        "crs": "EPSG:25830",
        "vertical_datum": "EVRF2019",
        "method": "geovision.mining.normalized_surface",
        "method_version": "1.0.0",
    }


def demo_mining_bundle(*, measured_at: datetime | None = None) -> dict[str, Any]:
    current_at = measured_at or datetime(2026, 9, 10, 8, 0, 0)
    boundary = {
        "type": "Polygon",
        "coordinates": [
            [
                [14.90, -12.80],
                [14.94, -12.80],
                [14.94, -12.76],
                [14.90, -12.76],
                [14.90, -12.80],
            ]
        ],
    }
    review_zone = {
        "type": "Polygon",
        "coordinates": [
            [
                [14.913, -12.789],
                [14.921, -12.789],
                [14.921, -12.782],
                [14.913, -12.782],
                [14.913, -12.789],
            ]
        ],
    }
    return deepcopy(
        {
            "asset": {
                "sector": "MINING",
                "asset_type": "STOCKPILE_ZONE",
                "name": "Synthetic quarry stockpile zone",
                "location_label": "Synthetic demo site, Angola",
                "geometry": boundary,
                "metadata": {"demo_fixture": True, "synthetic": True},
            },
            "datasets": [
                {
                    "name": "Previous RTK control observations",
                    "dataset_type": "RTK_OBSERVATIONS",
                    "capture_date": current_at - timedelta(days=36),
                    "crs": "EPSG:25830",
                    "processing_level": "PROCESSED",
                    "provenance": {
                        "source_name": "GeoVision synthetic RTK controls",
                        "survey_reference": "stockpile-survey-baseline",
                        "acquisition_method": "RTK_PPK_PHOTOGRAMMETRY",
                    },
                    "metadata": {},
                },
                {
                    "name": "Previous stockpile point cloud",
                    "dataset_type": "POINT_CLOUD",
                    "capture_date": current_at - timedelta(days=35),
                    "crs": "EPSG:25830",
                    "processing_level": "DERIVED",
                    "provenance": {
                        "source_name": "GeoVision synthetic photogrammetry",
                        "processor": "portable-processing-provider",
                        "processor_version": "1.0.0",
                        "acquisition_method": "RTK_PPK_PHOTOGRAMMETRY",
                    },
                    "metadata": {
                        "mining_analysis": _analysis(
                            algorithm="geovision.mining.stockpile_surface",
                            metrics={"stockpile_volume": 12000.0},
                            survey_evidence=_survey("stockpile-survey-baseline"),
                            surface_reference_evidence=_surface_reference(
                                "stockpile-surface-baseline"
                            ),
                            volume_quality_evidence=_quality(
                                "stockpile-survey-baseline",
                                "$dataset:Previous RTK control observations",
                            ),
                            review_candidates=[],
                        )
                    },
                },
                {
                    "name": "Previous stockpile orthomosaic",
                    "dataset_type": "ORTHOMOSAIC",
                    "capture_date": current_at - timedelta(days=35),
                    "crs": "EPSG:25830",
                    "processing_level": "PROCESSED",
                    "provenance": {
                        "source_name": "GeoVision synthetic photogrammetry",
                        "acquisition_method": "RTK_PPK_PHOTOGRAMMETRY",
                    },
                    "metadata": {
                        "mining_analysis": _analysis(
                            algorithm="geovision.mining.orthomosaic_review",
                            survey_evidence=_survey("stockpile-survey-baseline"),
                        )
                    },
                },
                {
                    "name": "Current RTK control observations",
                    "dataset_type": "RTK_OBSERVATIONS",
                    "capture_date": current_at - timedelta(days=6),
                    "crs": "EPSG:25830",
                    "processing_level": "PROCESSED",
                    "provenance": {
                        "source_name": "GeoVision synthetic RTK controls",
                        "survey_reference": "stockpile-survey-current",
                        "acquisition_method": "RTK_PPK_PHOTOGRAMMETRY",
                    },
                    "metadata": {},
                },
                {
                    "name": "Current stockpile point cloud",
                    "dataset_type": "POINT_CLOUD",
                    "capture_date": current_at - timedelta(days=5),
                    "crs": "EPSG:25830",
                    "processing_level": "DERIVED",
                    "provenance": {
                        "source_name": "GeoVision synthetic photogrammetry",
                        "processor": "portable-processing-provider",
                        "processor_version": "1.0.0",
                        "acquisition_method": "RTK_PPK_PHOTOGRAMMETRY",
                    },
                    "metadata": {
                        "mining_analysis": _analysis(
                            algorithm="geovision.mining.stockpile_change",
                            metrics={
                                "stockpile_volume": 13250.0,
                                "terrain_volume_change": 1250.0,
                                "surface_change_area": 860.0,
                            },
                            survey_evidence=_survey("stockpile-survey-current"),
                            surface_reference_evidence=_surface_reference(
                                "stockpile-surface-current"
                            ),
                            volume_quality_evidence=_quality(
                                "stockpile-survey-current",
                                "$dataset:Current RTK control observations",
                            ),
                            surface_comparison_evidence={
                                "reviewed": True,
                                "current_dataset_id": "$self",
                                "previous_dataset_id": "$dataset:Previous stockpile point cloud",
                                "aligned": True,
                                "same_crs": True,
                                "same_vertical_datum": True,
                                "vertical_datum": "EVRF2019",
                                "method": "geovision.mining.surface_difference",
                                "method_version": "1.0.0",
                            },
                            surface_review_evidence={
                                "reviewed": True,
                                "interpretation_scope": "GEOMETRIC_CHANGE_ONLY",
                                "asset_scope": "SURFACE",
                                "source_reference": "stockpile-change-review-current",
                                "method": "geovision.mining.surface_candidate_inventory",
                                "method_version": "1.0.0",
                            },
                            review_candidates=[
                                {
                                    "id": "surface-change-zone-1",
                                    "kind": "surface",
                                    "new": True,
                                    "label": "Mapped stockpile surface-change candidate",
                                    "area_m2": 860.0,
                                    "severity": "WATCH",
                                    "confidence": 0.84,
                                    "geometry": review_zone,
                                }
                            ],
                        )
                    },
                },
                {
                    "name": "Current stockpile orthomosaic",
                    "dataset_type": "ORTHOMOSAIC",
                    "capture_date": current_at - timedelta(days=5),
                    "crs": "EPSG:25830",
                    "processing_level": "PROCESSED",
                    "provenance": {
                        "source_name": "GeoVision synthetic photogrammetry",
                        "acquisition_method": "RTK_PPK_PHOTOGRAMMETRY",
                    },
                    "metadata": {
                        "mining_analysis": _analysis(
                            algorithm="geovision.mining.orthomosaic_review",
                            survey_evidence=_survey("stockpile-survey-current"),
                        )
                    },
                },
            ],
        }
    )


def resolve_demo_dataset_references(
    bundle: dict[str, Any],
    dataset_ids_by_name: dict[str, str],
) -> dict[str, Any]:
    """Resolve fixture-only dataset tokens after canonical rows are flushed."""

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


__all__ = ["demo_mining_bundle", "resolve_demo_dataset_references"]
