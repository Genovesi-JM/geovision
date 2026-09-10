"""Synthetic repeated-inspection fixture for Ports and Industrial demos."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any

from app.sectors.ports.services import ANALYSIS_SCHEMA


def _inspection(
    *,
    asset_id: str,
    reference: str,
    modality: str,
    capture_mode: str | None = None,
) -> dict[str, Any]:
    return {
        "reviewed": True,
        "asset_id": asset_id,
        "inspection_reference": reference,
        "modality": modality,
        "capture_mode": capture_mode or modality,
        "crs": "EPSG:25830",
        "method": "geovision.ports.documented_inspection",
        "method_version": "1.0.0",
        "registration_reference": "gantry-control-grid-v1",
        "registration_method": "geovision.ports.control_registration",
        "registration_version": "1.0.0",
    }


def _analysis(*, inspection: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "schema": ANALYSIS_SCHEMA,
        "validation_status": "VALIDATED",
        "algorithm": "geovision.ports.synthetic_inspection",
        "algorithm_version": "1.0.0",
        "confidence": 0.9,
        "metrics": {},
        "inspection_evidence": inspection,
        **extra,
    }


def _comparison(
    *,
    current: str,
    previous: str,
    current_reference: str,
    previous_reference: str,
) -> dict[str, Any]:
    return {
        "reviewed": True,
        "current_dataset_id": current,
        "previous_dataset_id": previous,
        "current_inspection_reference": current_reference,
        "previous_inspection_reference": previous_reference,
        "aligned": True,
        "crs": "EPSG:25830",
        "registration_reference": "gantry-control-grid-v1",
        "method": "geovision.ports.registered_change_review",
        "method_version": "1.0.0",
    }


def _inventory(
    *,
    asset_id: str,
    modality: str,
    reference: str,
    scope: str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "reviewed": True,
        "complete_for_dataset": True,
        "asset_id": asset_id,
        "modality": modality,
        "inventory_reference": reference,
        "inventory_scope": scope,
        "method": "geovision.ports.candidate_inventory",
        "method_version": "1.0.0",
        "candidates": candidates,
    }


def demo_ports_bundle(
    *,
    asset_id: str,
    measured_at: datetime | None = None,
) -> dict[str, Any]:
    current_at = measured_at or datetime(2026, 9, 10, 8, 0, 0)
    boundary = {
        "type": "Polygon",
        "coordinates": [
            [
                [-8.881, 37.952],
                [-8.878, 37.952],
                [-8.878, 37.955],
                [-8.881, 37.955],
                [-8.881, 37.952],
            ]
        ],
    }
    visual_zone = {
        "type": "Polygon",
        "coordinates": [
            [
                [-8.8805, 37.9530],
                [-8.8799, 37.9530],
                [-8.8799, 37.9536],
                [-8.8805, 37.9536],
                [-8.8805, 37.9530],
            ]
        ],
    }
    thermal_zone = {
        "type": "Polygon",
        "coordinates": [
            [
                [-8.8797, 37.9538],
                [-8.8792, 37.9538],
                [-8.8792, 37.9543],
                [-8.8797, 37.9543],
                [-8.8797, 37.9538],
            ]
        ],
    }
    previous_reference = "gantry-inspection-baseline"
    current_reference = "gantry-inspection-current"
    return deepcopy(
        {
            "asset": {
                "sector": "PORTS_INDUSTRIAL",
                "asset_type": "GANTRY",
                "name": "Synthetic terminal gantry",
                "location_label": "Synthetic demo terminal, Sines",
                "geometry": boundary,
                "metadata": {
                    "demo_fixture": True,
                    "synthetic": True,
                    "inspection_cadence_days": 30,
                },
            },
            "datasets": [
                {
                    "name": "Previous gantry visual inspection",
                    "inspection": "previous",
                    "dataset_type": "RGB_IMAGES",
                    "capture_date": current_at - timedelta(days=35),
                    "processing_level": "PROCESSED",
                    "crs": "EPSG:25830",
                    "provenance": {
                        "source_name": "GeoVision synthetic inspection",
                        "acquisition_method": "RGB_ZOOM",
                    },
                    "metadata": {
                        "ports_analysis": _analysis(
                            inspection=_inspection(
                                asset_id=asset_id,
                                reference=previous_reference,
                                modality="RGB",
                            ),
                            candidate_inventory=_inventory(
                                asset_id=asset_id,
                                modality="VISUAL",
                                reference="visual-inventory-baseline",
                                scope="BASELINE",
                                candidates=[
                                    {
                                        "candidate_reference": "baseline-visual-area",
                                        "new": False,
                                        "label": "Previously documented visual review area",
                                        "severity": "WATCH",
                                        "confidence": 0.82,
                                        "geometry": visual_zone,
                                    }
                                ],
                            ),
                        )
                    },
                },
                {
                    "name": "Previous gantry thermal inspection",
                    "inspection": "previous",
                    "dataset_type": "THERMAL_IMAGES",
                    "capture_date": current_at - timedelta(days=35),
                    "processing_level": "PROCESSED",
                    "crs": "EPSG:25830",
                    "provenance": {
                        "source_name": "GeoVision synthetic thermal inspection",
                        "acquisition_method": "CALIBRATED_THERMAL",
                    },
                    "metadata": {
                        "ports_analysis": _analysis(
                            inspection=_inspection(
                                asset_id=asset_id,
                                reference=previous_reference,
                                modality="THERMAL",
                            ),
                            thermal_evidence={
                                "reviewed": True,
                                "calibrated": True,
                                "calibration_reference": "thermal-calibration-v1",
                                "environmental_conditions_reference": "field-log-baseline",
                                "temperature_unit": "C",
                                "emissivity": 0.95,
                                "method": "geovision.ports.calibrated_thermal_review",
                                "method_version": "1.0.0",
                            },
                            candidate_inventory=_inventory(
                                asset_id=asset_id,
                                modality="THERMAL",
                                reference="thermal-inventory-baseline",
                                scope="BASELINE",
                                candidates=[],
                            ),
                        )
                    },
                },
                {
                    "name": "Previous gantry reality mesh",
                    "inspection": "previous",
                    "dataset_type": "MESH_3D",
                    "capture_date": current_at - timedelta(days=35),
                    "processing_level": "DERIVED",
                    "crs": "EPSG:25830",
                    "provenance": {
                        "source_name": "GeoVision synthetic reality capture",
                        "processor": "portable-processing-provider",
                        "processor_version": "1.0.0",
                    },
                    "metadata": {
                        "ports_analysis": _analysis(
                            inspection=_inspection(
                                asset_id=asset_id,
                                reference=previous_reference,
                                modality="SURFACE_3D",
                            )
                        )
                    },
                },
                {
                    "name": "Current gantry zoom inspection",
                    "inspection": "current",
                    "dataset_type": "RGB_IMAGES",
                    "capture_date": current_at - timedelta(days=5),
                    "processing_level": "PROCESSED",
                    "crs": "EPSG:25830",
                    "provenance": {
                        "source_name": "GeoVision synthetic inspection",
                        "acquisition_method": "RGB_ZOOM",
                    },
                    "metadata": {
                        "ports_analysis": _analysis(
                            inspection=_inspection(
                                asset_id=asset_id,
                                reference=current_reference,
                                modality="RGB",
                                capture_mode="ZOOM_RGB",
                            ),
                            comparison_evidence=_comparison(
                                current="$self",
                                previous="$dataset:Previous gantry visual inspection",
                                current_reference=current_reference,
                                previous_reference=previous_reference,
                            ),
                            candidate_inventory=_inventory(
                                asset_id=asset_id,
                                modality="VISUAL",
                                reference="visual-inventory-current",
                                scope="COMPARISON",
                                candidates=[
                                    {
                                        "candidate_reference": "new-visual-area",
                                        "new": True,
                                        "label": "New visual change candidate",
                                        "severity": "WATCH",
                                        "confidence": 0.86,
                                        "geometry": visual_zone,
                                    }
                                ],
                            ),
                            specialist_condition_evidence={
                                "specialist_validated": True,
                                "review_authority": "AUTHORIZED_SPECIALIST",
                                "review_reference": "specialist-review-current",
                                "summary_code": "REVIEW_REQUIRED",
                                "method": "geovision.ports.specialist_condition_screening",
                                "method_version": "1.0.0",
                            },
                        )
                    },
                },
                {
                    "name": "Current gantry thermal inspection",
                    "inspection": "current",
                    "dataset_type": "THERMAL_IMAGES",
                    "capture_date": current_at - timedelta(days=5),
                    "processing_level": "PROCESSED",
                    "crs": "EPSG:25830",
                    "provenance": {
                        "source_name": "GeoVision synthetic thermal inspection",
                        "acquisition_method": "CALIBRATED_THERMAL",
                    },
                    "metadata": {
                        "ports_analysis": _analysis(
                            inspection=_inspection(
                                asset_id=asset_id,
                                reference=current_reference,
                                modality="THERMAL",
                            ),
                            comparison_evidence=_comparison(
                                current="$self",
                                previous="$dataset:Previous gantry thermal inspection",
                                current_reference=current_reference,
                                previous_reference=previous_reference,
                            ),
                            thermal_evidence={
                                "reviewed": True,
                                "calibrated": True,
                                "calibration_reference": "thermal-calibration-v1",
                                "environmental_conditions_reference": "field-log-current",
                                "temperature_unit": "C",
                                "emissivity": 0.95,
                                "method": "geovision.ports.calibrated_thermal_review",
                                "method_version": "1.0.0",
                            },
                            candidate_inventory=_inventory(
                                asset_id=asset_id,
                                modality="THERMAL",
                                reference="thermal-inventory-current",
                                scope="COMPARISON",
                                candidates=[
                                    {
                                        "candidate_reference": "new-thermal-area",
                                        "new": True,
                                        "label": "New thermal response candidate",
                                        "severity": "WARNING",
                                        "confidence": 0.84,
                                        "geometry": thermal_zone,
                                    }
                                ],
                            ),
                        )
                    },
                },
                {
                    "name": "Current gantry reality mesh",
                    "inspection": "current",
                    "dataset_type": "MESH_3D",
                    "capture_date": current_at - timedelta(days=5),
                    "processing_level": "DERIVED",
                    "crs": "EPSG:25830",
                    "provenance": {
                        "source_name": "GeoVision synthetic reality capture",
                        "processor": "portable-processing-provider",
                        "processor_version": "1.0.0",
                    },
                    "metadata": {
                        "ports_analysis": _analysis(
                            inspection=_inspection(
                                asset_id=asset_id,
                                reference=current_reference,
                                modality="SURFACE_3D",
                            ),
                            comparison_evidence=_comparison(
                                current="$self",
                                previous="$dataset:Previous gantry reality mesh",
                                current_reference=current_reference,
                                previous_reference=previous_reference,
                            ),
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


__all__ = ["demo_ports_bundle", "resolve_demo_dataset_references"]
