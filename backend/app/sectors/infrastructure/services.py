"""Evidence fusion and application services for the Infrastructure sector."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models import Account, Action, Asset, Dataset
from app.modules.actions.services import action_payload, materialize_evaluation_actions
from app.modules.analytics.domain import EvaluationContext
from app.modules.analytics.services import (
    EvaluationResult,
    asset_kpi_payloads,
    ensure_kpi_definition,
    evaluate_asset,
    list_asset_observations,
    observation_payload,
)
from app.modules.assets.domain import normalize_geometry
from app.modules.identity.domain import AuthorizationContext
from app.sectors.infrastructure.domain import (
    ALGORITHM_VERSION,
    InfrastructureError,
    InfrastructureSourceContext,
    KPI_DEFINITIONS,
    SECTOR,
    SUPPORTED_ASSET_TYPES,
    SUPPORTED_DATASET_TYPES,
)


ANALYSIS_SCHEMA = "geovision.infrastructure.analysis.v1"
_MODULE_KEYS = frozenset({"infrastructure", "construction"})
_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,159}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,39}$")
_SURFACE_TYPES = frozenset({"DSM", "DTM", "POINT_CLOUD", "LIDAR_POINT_CLOUD"})
_PROGRESS_BASES = frozenset(
    {"VALIDATED_SURVEY_CLASSIFICATION", "SIGNED_QUANTITY_SURVEY", "BIM_4D_COMPARISON"}
)
_SCHEDULE_KINDS = frozenset({"SIGNED_BASELINE", "BIM_4D", "PROJECT_SYSTEM"})
_SCHEDULE_DATASET_TYPES = frozenset({"BIM_MODEL", "PROJECT_REFERENCE"})
_SCHEDULE_SOURCES = frozenset(
    {
        "AUTODESK_CONSTRUCTION_CLOUD",
        "BIM_4D",
        "GEOVISION_PROJECT_SYSTEM",
        "MICROSOFT_PROJECT",
        "PRIMAVERA_P6",
        "PROCORE",
        "SIGNED_MANUAL",
    }
)


@dataclass(frozen=True, slots=True)
class InfrastructureEvaluation:
    sources: InfrastructureSourceContext
    result: EvaluationResult
    actions: tuple[Action, ...]


def _object(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _number(value: Any) -> float | None:
    if isinstance(value, Mapping):
        value = value.get("value")
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _json_list(value: str | None) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def _workspace_enabled(workspace: Account | None) -> bool:
    if workspace is None or workspace.status != "active":
        return False
    modules = {item.casefold() for item in _json_list(workspace.modules_enabled)}
    return bool(modules & _MODULE_KEYS)


def infrastructure_enabled_for_context(
    db: Session,
    *,
    context: AuthorizationContext,
) -> bool:
    if not context.active_workspace_id or not context.active_organization_id:
        return False
    workspace = db.get(Account, context.active_workspace_id)
    return bool(
        workspace
        and workspace.organization_id == context.active_organization_id
        and _workspace_enabled(workspace)
    )


def _assert_infrastructure_asset(asset: Asset) -> None:
    if asset.sector != SECTOR:
        raise InfrastructureError(
            "sector_mismatch",
            "Infrastructure intelligence is available only for Infrastructure assets",
        )
    if asset.asset_type not in SUPPORTED_ASSET_TYPES:
        raise InfrastructureError(
            "asset_type_unsupported",
            f"Infrastructure does not support asset type {asset.asset_type}",
        )


def _require_feature(db: Session, asset: Asset) -> Account:
    workspace = db.get(Account, asset.workspace_id) if asset.workspace_id else None
    if (
        workspace is None
        or workspace.organization_id != asset.organization_id
        or not _workspace_enabled(workspace)
    ):
        raise InfrastructureError(
            "feature_disabled",
            "Infrastructure is not enabled for this workspace",
        )
    return workspace


def sync_kpi_definitions(db: Session) -> None:
    for definition in KPI_DEFINITIONS:
        ensure_kpi_definition(db, definition)


def _accepted_analysis(row: Dataset) -> Mapping[str, Any] | None:
    metadata = _object(row.metadata_json)
    analysis = metadata.get("infrastructure_analysis")
    if not isinstance(analysis, Mapping):
        return None
    if analysis.get("schema") != ANALYSIS_SCHEMA:
        return None
    if str(analysis.get("validation_status", "")).upper() != "VALIDATED":
        return None
    algorithm = str(analysis.get("algorithm", "")).strip()
    algorithm_version = str(analysis.get("algorithm_version", "")).strip()
    if not _IDENTIFIER.fullmatch(algorithm) or not _VERSION.fullmatch(algorithm_version):
        return None
    if not isinstance(analysis.get("metrics", {}), Mapping):
        return None
    return analysis


def _confidence(analysis: Mapping[str, Any]) -> float:
    value = _number(analysis.get("confidence"))
    return max(0.0, min(1.0, value if value is not None else 0.5))


def _progress_evidence_valid(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    return bool(
        value.get("reviewed") is True
        and str(value.get("basis", "")).upper() in _PROGRESS_BASES
        and str(value.get("source_reference", "")).strip()
        and str(value.get("reference_version", "")).strip()
    )


def _schedule_evidence_valid(row: Dataset, value: Any) -> bool:
    if row.dataset_type not in _SCHEDULE_DATASET_TYPES or not isinstance(value, Mapping):
        return False
    return bool(
        value.get("trusted") is True
        and str(value.get("kind", "")).upper() in _SCHEDULE_KINDS
        and str(value.get("source_system", "")).upper() in _SCHEDULE_SOURCES
        and str(value.get("source_reference", "")).strip()
        and str(value.get("baseline_version", "")).strip()
    )


def _paired_evidence_valid(
    row: Dataset,
    value: Any,
    datasets: Mapping[str, Dataset],
    *,
    surface: bool,
) -> bool:
    if not isinstance(value, Mapping):
        return False
    previous_id = str(value.get("previous_dataset_id", "")).strip()
    current_id = str(value.get("current_dataset_id", "")).strip()
    previous = datasets.get(previous_id)
    if (
        current_id != row.id
        or not previous
        or previous.id == row.id
        or previous.dataset_type != row.dataset_type
    ):
        return False
    current_at = row.capture_date or row.processed_at or row.created_at
    previous_at = previous.capture_date or previous.processed_at or previous.created_at
    if previous_at >= current_at:
        return False
    if value.get("aligned") is not True or value.get("same_crs") is not True:
        return False
    method = str(value.get("method", "")).strip()
    method_version = str(value.get("method_version", "")).strip()
    if not _IDENTIFIER.fullmatch(method) or not _VERSION.fullmatch(method_version):
        return False
    current_crs = str(row.crs or "").strip().upper()
    previous_crs = str(previous.crs or "").strip().upper()
    if not current_crs or current_crs != previous_crs:
        return False
    if surface:
        if row.dataset_type not in _SURFACE_TYPES or previous.dataset_type not in _SURFACE_TYPES:
            return False
        if not str(value.get("vertical_datum", "")).strip():
            return False
    return True


def _detail(row: Dataset, analysis: Mapping[str, Any], *, gate: str) -> dict[str, Any]:
    measured_at = row.capture_date or row.processed_at or row.created_at
    return {
        "source": f"validated:{row.dataset_type.lower()}",
        "confidence": _confidence(analysis),
        "measured_at": measured_at,
        "dataset_id": row.id,
        "mission_id": row.mission_id,
        "provenance": {
            "analysis_schema": ANALYSIS_SCHEMA,
            "algorithm": analysis["algorithm"],
            "algorithm_version": analysis["algorithm_version"],
            "dataset_type": row.dataset_type,
            "processing_level": row.processing_level,
            "quality_status": row.quality_status,
            "evidence_gate": gate,
        },
    }


def _safe_geometry(value: Any) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    try:
        return normalize_geometry(value)
    except ValueError:
        return None


def _finding_key(value: Any, fallback: str) -> str:
    candidate = re.sub(r"[^A-Za-z0-9_.:-]+", "-", str(value or fallback)).strip("-.")
    if not candidate or not candidate[0].isalpha():
        candidate = f"finding-{candidate or fallback}"
    return candidate[:100]


def _candidate_confidence(candidate: Mapping[str, Any], analysis: Mapping[str, Any]) -> float:
    declared = _number(candidate.get("confidence"))
    normalized = 0.5 if declared is None else max(0.0, min(1.0, declared))
    return min(_confidence(analysis), normalized)


def _extract_findings(
    row: Dataset,
    analysis: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, bool]]:
    findings: list[dict[str, Any]] = []
    assessed = {"visual": False, "thermal": False, "review_area": False}
    measured_at = row.capture_date or row.processed_at or row.created_at
    provenance = {
        "analysis_schema": ANALYSIS_SCHEMA,
        "algorithm": analysis["algorithm"],
        "algorithm_version": analysis["algorithm_version"],
        "dataset_type": row.dataset_type,
    }
    anomalies = analysis.get("anomalies")
    if isinstance(anomalies, Sequence) and not isinstance(anomalies, (str, bytes)):
        if row.dataset_type in {"RGB_IMAGES", "ORTHOMOSAIC", "MESH_3D", "POINT_CLOUD"}:
            assessed["visual"] = True
        if row.dataset_type == "THERMAL_IMAGES":
            assessed["thermal"] = True
        for index, candidate in enumerate(anomalies):
            if not isinstance(candidate, Mapping) or candidate.get("new") is not True:
                continue
            kind = str(candidate.get("kind", "")).strip().lower()
            if kind == "visual" and not assessed["visual"]:
                continue
            if kind == "thermal" and not assessed["thermal"]:
                continue
            if kind not in {"visual", "thermal"}:
                continue
            findings.append(
                {
                    "key": _finding_key(candidate.get("id"), f"{kind}-{index + 1}"),
                    "kind": kind,
                    "label": str(candidate.get("label") or f"{kind.title()} review candidate"),
                    "severity": str(candidate.get("severity") or "WATCH").upper(),
                    "confidence": _candidate_confidence(candidate, analysis),
                    "geometry": _safe_geometry(candidate.get("geometry")),
                    "source": f"validated:{row.dataset_type.lower()}",
                    "detected_at": measured_at,
                    "dataset_id": row.id,
                    "mission_id": row.mission_id,
                    "provenance": provenance,
                }
            )
    review_areas = analysis.get("review_areas")
    if isinstance(review_areas, Sequence) and not isinstance(review_areas, (str, bytes)):
        assessed["review_area"] = True
        for index, candidate in enumerate(review_areas):
            if not isinstance(candidate, Mapping):
                continue
            findings.append(
                {
                    "key": _finding_key(candidate.get("id"), f"review-area-{index + 1}"),
                    "kind": "review_area",
                    "label": str(candidate.get("label") or "Mapped review area"),
                    "severity": str(candidate.get("severity") or "WATCH").upper(),
                    "confidence": _candidate_confidence(candidate, analysis),
                    "geometry": _safe_geometry(candidate.get("geometry")),
                    "source": f"validated:{row.dataset_type.lower()}",
                    "detected_at": measured_at,
                    "dataset_id": row.id,
                    "mission_id": row.mission_id,
                    "provenance": provenance,
                }
            )
    return findings, assessed


def build_source_context(
    db: Session,
    *,
    asset: Asset,
    as_of: datetime | None = None,
) -> InfrastructureSourceContext:
    """Load only validated, tenant-owned evidence; missing proof stays missing."""

    _assert_infrastructure_asset(asset)
    _require_feature(db, asset)
    evaluated_at = _utc_naive(as_of or utc_now())
    query = db.query(Dataset).filter(
        Dataset.company_id == asset.organization_id,
        Dataset.asset_id == asset.id,
        Dataset.workspace_id == asset.workspace_id,
        Dataset.dataset_type.in_(tuple(SUPPORTED_DATASET_TYPES)),
        Dataset.status == "ready",
        Dataset.quality_status == "PASSED",
    )
    datasets = [
        row
        for row in query.order_by(Dataset.capture_date.desc(), Dataset.created_at.desc()).all()
        if (row.capture_date or row.created_at) <= evaluated_at
    ]
    datasets_by_id = {row.id: row for row in datasets}

    histories: dict[str, list[tuple[datetime, float, dict[str, Any]]]] = {}
    assessment_batches: dict[
        str,
        tuple[datetime, str, dict[str, Any], list[dict[str, Any]]],
    ] = {}
    accepted_ids: list[str] = []
    paired_surface_ids: set[str] = set()
    paired_change_ids: set[str] = set()
    trusted_schedule_ids: set[str] = set()

    for row in datasets:
        analysis = _accepted_analysis(row)
        if analysis is None:
            continue
        accepted_ids.append(row.id)
        measured_at = row.capture_date or row.processed_at or row.created_at
        metrics = analysis.get("metrics", {})
        progress = _number(metrics.get("overall_progress"))
        if progress is not None and 0 <= progress <= 100 and _progress_evidence_valid(
            analysis.get("progress_evidence")
        ):
            histories.setdefault("overall_progress", []).append(
                (measured_at, progress, _detail(row, analysis, gate="reviewed_progress"))
            )

        if _paired_evidence_valid(
            row, analysis.get("comparison_evidence"), datasets_by_id, surface=False
        ):
            area_change = _number(metrics.get("area_change"))
            if area_change is not None:
                histories.setdefault("area_change", []).append(
                    (measured_at, area_change, _detail(row, analysis, gate="aligned_2d_pair"))
                )
                paired_change_ids.add(row.id)

        if _paired_evidence_valid(
            row, analysis.get("surface_evidence"), datasets_by_id, surface=True
        ):
            found_surface_metric = False
            for key in ("volume_change", "cut_volume", "fill_volume"):
                value = _number(metrics.get(key))
                if value is None or (key in {"cut_volume", "fill_volume"} and value < 0):
                    continue
                histories.setdefault(key, []).append(
                    (measured_at, value, _detail(row, analysis, gate="validated_surface_pair"))
                )
                found_surface_metric = True
            if found_surface_metric:
                paired_surface_ids.add(row.id)

        schedule = _number(metrics.get("schedule_variance"))
        if (
            schedule is not None
            and -36500 <= schedule <= 36500
            and _schedule_evidence_valid(row, analysis.get("schedule_evidence"))
        ):
            histories.setdefault("schedule_variance", []).append(
                (measured_at, schedule, _detail(row, analysis, gate="trusted_schedule"))
            )
            trusted_schedule_ids.add(row.id)

        extracted, dataset_assessed = _extract_findings(row, analysis)
        for key, is_assessed in dataset_assessed.items():
            if not is_assessed:
                continue
            batch = (
                measured_at,
                row.id,
                _detail(row, analysis, gate=f"validated_{key}_candidate_inventory"),
                [item for item in extracted if item["kind"] == key],
            )
            current = assessment_batches.get(key)
            if current is None or (batch[0], batch[1]) > (current[0], current[1]):
                assessment_batches[key] = batch

    measurements: dict[str, float] = {}
    details: dict[str, dict[str, Any]] = {}
    for key, history in histories.items():
        history.sort(key=lambda item: item[0], reverse=True)
        measurements[key] = history[0][1]
        details[key] = history[0][2]
    progress_history = histories.get("overall_progress", [])
    if progress_history:
        current_at, current, current_detail = progress_history[0]
        previous_entry = next(
            (item for item in progress_history[1:] if item[0] < current_at),
            None,
        )
    else:
        previous_entry = None
    if previous_entry is not None:
        previous_at, previous, previous_detail = previous_entry
        measurements["progress_change"] = current - previous
        details["progress_change"] = {
            **current_detail,
            "confidence": min(current_detail["confidence"], previous_detail["confidence"]),
            "measured_at": current_at,
            "provenance": {
                **dict(current_detail["provenance"]),
                "previous_dataset_id": previous_detail["dataset_id"],
                "previous_measured_at": previous_at.isoformat(),
                "calculation": "current_reviewed_progress_minus_previous_reviewed_progress",
            },
        }

    latest_findings = [
        item
        for _, _, _, batch_findings in assessment_batches.values()
        for item in batch_findings
    ]
    unique_findings: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in latest_findings:
        unique_findings[(str(item["dataset_id"]), str(item["kind"]), str(item["key"]))] = item
    findings = list(unique_findings.values())
    finding_counts = {
        "visual": sum(item["kind"] == "visual" for item in findings),
        "thermal": sum(item["kind"] == "thermal" for item in findings),
        "review_area": sum(item["kind"] == "review_area" for item in findings),
    }
    for kind, metric_key in (
        ("visual", "visual_anomaly_count"),
        ("thermal", "thermal_anomaly_count"),
        ("review_area", "review_area_count"),
    ):
        batch = assessment_batches.get(kind)
        if batch is None:
            continue
        batch_at, _, assessment_detail, _ = batch
        matching = [item for item in findings if item["kind"] == kind]
        measurements[metric_key] = float(finding_counts[kind])
        details[metric_key] = {
            **assessment_detail,
            "source": "infrastructure.validated_candidate_inventory",
            "confidence": min(
                (float(item["confidence"]) for item in matching),
                default=float(assessment_detail["confidence"]),
            ),
            "measured_at": batch_at,
            "provenance": {
                **dict(assessment_detail["provenance"]),
                "derived_from": "validated_explicit_candidate_list",
                "candidate_kind": kind,
                "dataset_ids": sorted(
                    {str(item["dataset_id"]) for item in matching}
                ),
            },
        }

    comparisons = infrastructure_comparisons(db, asset=asset, enforce_feature=False)
    historical_comparison = any(item["availability"] == "AVAILABLE" for item in comparisons)
    availability = {
        "validated_analysis": bool(accepted_ids),
        "validated_progress": "overall_progress" in measurements,
        "historical_comparison": historical_comparison,
        "paired_2d_change": bool(paired_change_ids),
        "paired_surface": bool(paired_surface_ids),
        "trusted_schedule": bool(trusted_schedule_ids),
        "visual_assessment": "visual" in assessment_batches,
        "thermal_assessment": "thermal" in assessment_batches,
        "review_area_assessment": "review_area" in assessment_batches,
        "supported_dataset_count": len(datasets),
        "validated_analysis_count": len(accepted_ids),
        "limitations": [
            message
            for condition, message in (
                (not accepted_ids, "No validated Infrastructure analysis is available."),
                (
                    "overall_progress" not in measurements,
                    "Overall progress is unknown without reviewed survey or trusted project evidence.",
                ),
                (
                    not paired_surface_ids,
                    "Volume and cut/fill are unavailable without a validated co-registered surface pair.",
                ),
                (
                    not trusted_schedule_ids,
                    "Schedule variance is unknown without a trusted, versioned schedule baseline.",
                ),
            )
            if condition
        ],
    }
    evidence = {
        "analysis_schema": ANALYSIS_SCHEMA,
        "algorithm_bundle_version": ALGORITHM_VERSION,
        "dataset_ids": [row.id for row in datasets],
        "validated_analysis_dataset_ids": accepted_ids,
        "paired_2d_dataset_ids": sorted(paired_change_ids),
        "paired_surface_dataset_ids": sorted(paired_surface_ids),
        "trusted_schedule_dataset_ids": sorted(trusted_schedule_ids),
    }
    return InfrastructureSourceContext(
        evaluation=EvaluationContext(
            asset_id=asset.id,
            sector=SECTOR,
            measured_at=evaluated_at,
            measurements=measurements,
            datasets=tuple(
                {
                    "id": row.id,
                    "dataset_type": row.dataset_type,
                    "capture_date": row.capture_date,
                    "quality_status": row.quality_status,
                }
                for row in datasets
            ),
            metadata={
                "measurement_details": details,
                "source_availability": availability,
                "evidence": evidence,
                "findings": tuple(findings),
            },
        ),
        availability=availability,
        evidence=evidence,
    )


def evaluate_infrastructure(
    db: Session,
    *,
    asset: Asset,
    actor=None,
    as_of: datetime | None = None,
) -> InfrastructureEvaluation:
    sync_kpi_definitions(db)
    sources = build_source_context(db, asset=asset, as_of=as_of)
    result = evaluate_asset(
        db,
        asset=asset,
        context=sources.evaluation,
        workspace_id=asset.workspace_id,
    )
    actions = materialize_evaluation_actions(
        db,
        asset=asset,
        evaluation=result,
        actor=actor,
    )
    db.flush()
    return InfrastructureEvaluation(sources, result, actions)


def _eligible_comparison_rows(db: Session, asset: Asset) -> list[Dataset]:
    return (
        db.query(Dataset)
        .filter(
            Dataset.company_id == asset.organization_id,
            Dataset.workspace_id == asset.workspace_id,
            Dataset.asset_id == asset.id,
            Dataset.dataset_type.in_(tuple(SUPPORTED_DATASET_TYPES)),
            Dataset.status == "ready",
            Dataset.quality_status == "PASSED",
        )
        .order_by(Dataset.capture_date.desc(), Dataset.created_at.desc())
        .all()
    )


def infrastructure_comparisons(
    db: Session,
    *,
    asset: Asset,
    enforce_feature: bool = True,
) -> list[dict[str, Any]]:
    _assert_infrastructure_asset(asset)
    if enforce_feature:
        _require_feature(db, asset)
    datasets = _eligible_comparison_rows(db, asset)
    specifications = (
        ("SURVEY_2D", "Historical 2D survey comparison", "2D", "SWIPE_2D", ("ORTHOMOSAIC",)),
        (
            "SURFACE_3D",
            "Historical 3D surface comparison",
            "3D",
            "MODEL_COMPARE_3D",
            ("DSM", "DTM", "POINT_CLOUD", "LIDAR_POINT_CLOUD", "MESH_3D"),
        ),
        ("THERMAL_2D", "Historical thermal comparison", "2D", "THERMAL_COMPARE_2D", ("THERMAL_IMAGES",)),
    )
    result: list[dict[str, Any]] = []
    for kind, title, dimension, render_mode, preferred_types in specifications:
        pair: tuple[Dataset, Dataset] | None = None
        fallback: Dataset | None = None
        for dataset_type in preferred_types:
            candidates = [row for row in datasets if row.dataset_type == dataset_type]
            if candidates and fallback is None:
                fallback = candidates[0]
            if len(candidates) >= 2:
                pair = (candidates[0], candidates[1])
                break
        current = pair[0] if pair else fallback
        previous = pair[1] if pair else None
        compatible = bool(
            current
            and previous
            and str(current.crs or "").strip()
            and str(current.crs or "").strip().upper()
            == str(previous.crs or "").strip().upper()
        )
        availability = "AVAILABLE" if compatible else "UNKNOWN" if pair else "NO_DATA"
        limitation = (
            None
            if compatible
            else "Coordinate reference systems are missing or incompatible."
            if pair
            else "A compatible earlier dataset is required."
        )
        result.append(
            {
                "id": kind.lower(),
                "kind": kind,
                "title": title,
                "dimension": dimension,
                "render_mode": render_mode,
                "availability": availability,
                "dataset_type": current.dataset_type if current else preferred_types[0],
                "current": (
                    {
                        "dataset_id": current.id,
                        "captured_at": current.capture_date or current.created_at,
                        "data_ref": f"/datasets/{current.id}",
                    }
                    if current
                    else None
                ),
                "previous": (
                    {
                        "dataset_id": previous.id,
                        "captured_at": previous.capture_date or previous.created_at,
                        "data_ref": f"/datasets/{previous.id}",
                    }
                    if previous
                    else None
                ),
                "crs": current.crs if compatible and current else None,
                "limitation": limitation,
                "interpretation": "visual comparison only; no engineering conclusion",
            }
        )
    return result


_LAYER_MODES = {
    "ORTHOMOSAIC": ("2D", "MAP_RASTER"),
    "DSM": ("2D", "MAP_RASTER"),
    "DTM": ("2D", "MAP_RASTER"),
    "THERMAL_IMAGES": ("2D", "MAP_RASTER"),
    "POINT_CLOUD": ("3D", "POINT_CLOUD_3D"),
    "LIDAR_POINT_CLOUD": ("3D", "POINT_CLOUD_3D"),
    "MESH_3D": ("3D", "MESH_3D"),
    "BIM_MODEL": ("3D", "REFERENCE_3D"),
    "RGB_IMAGES": ("REFERENCE", "REFERENCE_ONLY"),
    "RTK_OBSERVATIONS": ("REFERENCE", "REFERENCE_ONLY"),
    "PROJECT_REFERENCE": ("REFERENCE", "REFERENCE_ONLY"),
}


def infrastructure_map_layers(db: Session, *, asset: Asset) -> list[dict[str, Any]]:
    _assert_infrastructure_asset(asset)
    _require_feature(db, asset)
    geometry = _safe_geometry(_object(asset.geometry_geojson) if asset.geometry_geojson else None)
    layers: list[dict[str, Any]] = [
        {
            "id": f"asset:{asset.id}",
            "kind": "ASSET_BOUNDARY",
            "title": asset.name,
            "dimension": "2D",
            "render_mode": "VECTOR",
            "availability": "AVAILABLE" if geometry else "NO_DATA",
            "geometry": geometry,
            "data_ref": f"/assets/{asset.id}",
            "dataset_id": None,
            "observation_id": None,
            "captured_at": None,
            "confidence": 1.0 if geometry else None,
            "quality": "canonical" if geometry else "missing",
            "crs": "EPSG:4326" if geometry else None,
            "resolution": None,
            "provenance": {"source": "asset.geometry_geojson"},
        }
    ]
    for row in (
        db.query(Dataset)
        .filter(
            Dataset.company_id == asset.organization_id,
            Dataset.workspace_id == asset.workspace_id,
            Dataset.asset_id == asset.id,
            Dataset.dataset_type.in_(tuple(SUPPORTED_DATASET_TYPES)),
        )
        .order_by(Dataset.capture_date.desc(), Dataset.created_at.desc())
        .all()
    ):
        dimension, render_mode = _LAYER_MODES[row.dataset_type]
        accepted_analysis = _accepted_analysis(row)
        availability = (
            "NO_DATA"
            if row.status not in {"ready", "processing"} or row.quality_status == "FAILED"
            else "PROCESSING"
            if row.status == "processing"
            else "NOT_RENDERABLE"
            if render_mode == "REFERENCE_ONLY"
            else "AVAILABLE"
        )
        layers.append(
            {
                "id": f"dataset:{row.id}",
                "kind": row.dataset_type,
                "title": row.name,
                "dimension": dimension,
                "render_mode": render_mode,
                "availability": availability,
                "geometry": None,
                "data_ref": f"/datasets/{row.id}",
                "dataset_id": row.id,
                "observation_id": None,
                "captured_at": row.capture_date or row.created_at,
                "confidence": _confidence(accepted_analysis) if accepted_analysis else None,
                "quality": row.quality_status,
                "crs": row.crs,
                "resolution": (
                    {"value": row.resolution, "unit": row.resolution_unit}
                    if row.resolution is not None
                    else None
                ),
                "provenance": {
                    "dataset_type": row.dataset_type,
                    "processing_level": row.processing_level,
                },
            }
        )
    for row in list_asset_observations(db, asset=asset, limit=500):
        geometry = _safe_geometry(_object(row.geometry_geojson)) if row.geometry_geojson else None
        if not geometry:
            continue
        layers.append(
            {
                "id": f"observation:{row.id}",
                "kind": "OBSERVATION_ZONE",
                "title": row.observation_type.replace("_", " ").title(),
                "dimension": "2D",
                "render_mode": "VECTOR",
                "availability": (
                    "AVAILABLE" if row.validation_status == "VALIDATED" else "UNKNOWN"
                ),
                "geometry": geometry,
                "data_ref": f"/assets/{asset.id}/observations",
                "dataset_id": row.dataset_id,
                "observation_id": row.id,
                "captured_at": row.detected_at,
                "confidence": row.confidence,
                "quality": row.validation_status,
                "crs": "EPSG:4326",
                "resolution": None,
                "provenance": {
                    "algorithm": row.algorithm_key,
                    "algorithm_version": row.algorithm_version,
                    "specialist_review_required": row.validation_status != "VALIDATED",
                },
            }
        )
    return layers


def infrastructure_report_context(db: Session, *, asset: Asset) -> dict[str, Any]:
    """Return structured evidence for the common report engine."""

    sources = build_source_context(db, asset=asset)
    observations = list_asset_observations(db, asset=asset, limit=500)
    action_query = db.query(Action).filter(
        Action.organization_id == asset.organization_id,
        Action.workspace_id == asset.workspace_id,
        Action.asset_id == asset.id,
        Action.status.in_(("OPEN", "IN_PROGRESS")),
    )
    actions = action_query.order_by(Action.due_date, Action.created_at.desc()).limit(500).all()
    return {
        "schema": "geovision.infrastructure.report-context.v1",
        "algorithm_bundle_version": ALGORITHM_VERSION,
        "asset": {
            "id": asset.id,
            "name": asset.name,
            "asset_type": asset.asset_type,
            "sector": asset.sector,
            "location_label": asset.location_label,
        },
        "as_of": sources.evaluation.measured_at,
        "source_availability": dict(sources.availability),
        "evidence": dict(sources.evidence),
        "kpis": asset_kpi_payloads(db, asset),
        "observations": [observation_payload(row) for row in observations],
        "open_actions": [action_payload(row) for row in actions],
        "comparisons": infrastructure_comparisons(db, asset=asset),
        "map_layers": infrastructure_map_layers(db, asset=asset),
        "limitations": [
            *sources.availability.get("limitations", []),
            "Progress indicators are evidence summaries, not certification of completed work.",
            "Cut/fill values are indicative and require a validated co-registered surface pair.",
            "Visual, thermal, and mapped review candidates require authorized specialist review.",
            "No structural, safety, compliance, or engineering conclusion is generated.",
        ],
    }


__all__ = [
    "ANALYSIS_SCHEMA",
    "InfrastructureEvaluation",
    "build_source_context",
    "evaluate_infrastructure",
    "infrastructure_comparisons",
    "infrastructure_enabled_for_context",
    "infrastructure_map_layers",
    "infrastructure_report_context",
    "sync_kpi_definitions",
]
