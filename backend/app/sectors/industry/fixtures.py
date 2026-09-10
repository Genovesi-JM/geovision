"""Deterministic Industry, Energy and Utilities demonstration fixture."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.core.time import utc_now


def demo_industry_bundle(*, measured_at: datetime | None = None) -> dict[str, Any]:
    current_at = measured_at or utc_now()
    baseline_at = current_at - timedelta(days=30)
    geometry = {
        "type": "Polygon",
        "coordinates": [
            [
                [13.205, -8.842],
                [13.211, -8.842],
                [13.211, -8.837],
                [13.205, -8.837],
                [13.205, -8.842],
            ]
        ],
    }

    def dataset(name: str, captured_at: datetime, count: int) -> dict[str, Any]:
        return {
            "name": name,
            "dataset_type": "INSPECTION_RECORD",
            "capture_date": captured_at,
            "processing_level": "DERIVED",
            "quality_status": "PASSED",
            "provenance": {
                "method": "geovision.industry.synthetic_documented_inspection",
                "source_reference": name.lower().replace(" ", "-"),
                "reviewed": True,
            },
            "metadata": {
                "industry_analysis": {
                    "schema": "geovision.industry.analysis.v1",
                    "equipment_attention_count": count,
                    "interpretation": "synthetic review candidates only",
                }
            },
        }

    return {
        "asset": {
            "asset_type": "FACILITY",
            "name": "Industry and Utilities Facility",
            "location_label": "Luanda industrial area",
            "geometry": geometry,
            "metadata": {
                "facility_kind": "multi-utility",
                "evidence_limit": "synthetic operational demonstration only",
            },
        },
        "datasets": [
            dataset("Industry baseline inspection", baseline_at, 1),
            dataset("Industry current inspection", current_at, 4),
        ],
    }


__all__ = ["demo_industry_bundle"]
