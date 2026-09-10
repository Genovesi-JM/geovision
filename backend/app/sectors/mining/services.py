"""Validated survey fusion and application services for Mining/Quarry."""

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
from app.sectors.mining.domain import (
    ALGORITHM_VERSION,
    KPI_DEFINITIONS,
    SECTOR,
    SUPPORTED_ASSET_TYPES,
    SUPPORTED_DATASET_TYPES,
    MiningError,
    MiningSourceContext,
)


ANALYSIS_SCHEMA = "geovision.mining.analysis.v1"
_MODULE_KEYS = frozenset({"mining", "quarry"})
_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,159}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,39}$")
_SURVEY_TYPES = frozenset(
    {
        "DSM",
        "DTM",
        "LIDAR_POINT_CLOUD",
        "MESH_3D",
        "ORTHOMOSAIC",
        "POINT_CLOUD",
        "RGB_IMAGES",
    }
)
_SURFACE_TYPES = frozenset(
    {"DSM", "DTM", "LIDAR_POINT_CLOUD", "MESH_3D", "POINT_CLOUD"}
)
_POINT_CLOUD_FAMILY = frozenset({"LIDAR_POINT_CLOUD", "POINT_CLOUD"})
_VOLUME_METHODS = frozenset({"LIDAR", "RTK_PPK_PHOTOGRAMMETRY"})
_PLATFORM_TOLERANCE_LIMITS = {
    "max_horizontal_rmse_cm": 10.0,
    "max_vertical_rmse_cm": 15.0,
    "max_ground_sample_distance_cm": 5.0,
    "min_control_point_count": 3,
    "min_checkpoint_count": 3,
    "min_point_density_per_m2": 4.0,
}
_PUBLIC_PROVENANCE_KEYS = frozenset(
    {
        "adapter_version",
        "acquisition_method",
        "attribution",
        "collection",
        "dataset_updated_at",
        "fetched_at",
        "license_id",
        "license_url",
        "processor",
        "processor_version",
        "source_name",
        "survey_reference",
    }
)


@dataclass(frozen=True, slots=True)
class MiningEvaluation:
    sources: MiningSourceContext
    result: EvaluationResult
    actions: tuple[Action, ...]


def _object(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _array(value: str | None) -> list[Any]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _number(value: Any) -> float | None:
    if isinstance(value, Mapping):
        value = value.get("value")
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _integer(value: Any) -> int | None:
    number = _number(value)
    if number is None or number < 0 or not number.is_integer():
        return None
    return int(number)


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _json_list(value: str | None) -> list[str]:
    return [str(item).strip() for item in _array(value) if str(item).strip()]


def _workspace_enabled(workspace: Account | None) -> bool:
    if workspace is None or workspace.status != "active":
        return False
    modules = {item.casefold() for item in _json_list(workspace.modules_enabled)}
    return bool(modules & _MODULE_KEYS)


def mining_enabled_for_context(
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


def _assert_mining_asset(asset: Asset) -> None:
    if asset.sector != SECTOR:
        raise MiningError(
            "sector_mismatch",
            "Mining intelligence is available only for Mining assets",
        )
    if asset.asset_type not in SUPPORTED_ASSET_TYPES:
        raise MiningError(
            "asset_type_unsupported",
            f"Mining does not support asset type {asset.asset_type}",
        )


def _require_feature(db: Session, asset: Asset) -> Account:
    workspace = db.get(Account, asset.workspace_id) if asset.workspace_id else None
    if (
        workspace is None
        or workspace.organization_id != asset.organization_id
        or not _workspace_enabled(workspace)
    ):
        raise MiningError(
            "feature_disabled", "Mining is not enabled for this workspace"
        )
    return workspace


def sync_kpi_definitions(db: Session) -> None:
    for definition in KPI_DEFINITIONS:
        ensure_kpi_definition(db, definition)


def _accepted_analysis(row: Dataset) -> Mapping[str, Any] | None:
    if row.status != "ready" or row.quality_status != "PASSED":
        return None
    metadata = _object(row.metadata_json)
    analysis = metadata.get("mining_analysis")
    if not isinstance(analysis, Mapping):
        return None
    if analysis.get("schema") != ANALYSIS_SCHEMA:
        return None
    if str(analysis.get("validation_status", "")).upper() != "VALIDATED":
        return None
    algorithm = str(analysis.get("algorithm", "")).strip()
    version = str(analysis.get("algorithm_version", "")).strip()
    if not _IDENTIFIER.fullmatch(algorithm) or not _VERSION.fullmatch(version):
        return None
    if not isinstance(analysis.get("metrics", {}), Mapping):
        return None
    return analysis


def _confidence(analysis: Mapping[str, Any]) -> float:
    value = _number(analysis.get("confidence"))
    return max(0.0, min(1.0, value if value is not None else 0.5))


def _reviewed_survey_valid(row: Dataset, value: Any) -> bool:
    if row.dataset_type not in _SURVEY_TYPES or not isinstance(value, Mapping):
        return False
    crs = str(value.get("crs", "")).strip().upper()
    return bool(
        value.get("reviewed") is True
        and str(value.get("survey_reference", "")).strip()
        and _IDENTIFIER.fullmatch(str(value.get("method", "")).strip())
        and _VERSION.fullmatch(str(value.get("method_version", "")).strip())
        and crs
        and crs == str(row.crs or "").strip().upper()
    )


def _quality_summary(
    row: Dataset,
    analysis: Mapping[str, Any] | None,
    datasets: Mapping[str, Dataset],
) -> dict[str, Any] | None:
    if row.dataset_type not in _SURFACE_TYPES or analysis is None:
        return None
    value = analysis.get("volume_quality_evidence")
    if not isinstance(value, Mapping):
        return None
    acquisition_method = str(value.get("acquisition_method", "")).strip().upper()
    horizontal_rmse = _number(value.get("horizontal_rmse_cm"))
    vertical_rmse = _number(value.get("vertical_rmse_cm"))
    checkpoint_count = _integer(value.get("checkpoint_count"))
    thresholds = value.get("project_tolerances")
    if not isinstance(thresholds, Mapping):
        return None
    max_horizontal = _number(thresholds.get("max_horizontal_rmse_cm"))
    max_vertical = _number(thresholds.get("max_vertical_rmse_cm"))
    min_checkpoints = _integer(thresholds.get("min_checkpoint_count"))
    if (
        value.get("reviewed") is not True
        or value.get("project_tolerance_approved") is not True
        or acquisition_method not in _VOLUME_METHODS
        or not str(value.get("tolerance_reference", "")).strip()
        or not _IDENTIFIER.fullmatch(str(value.get("method", "")).strip())
        or not _VERSION.fullmatch(str(value.get("method_version", "")).strip())
        or horizontal_rmse is None
        or horizontal_rmse < 0
        or vertical_rmse is None
        or vertical_rmse < 0
        or checkpoint_count is None
        or max_horizontal is None
        or max_horizontal <= 0
        or max_horizontal > _PLATFORM_TOLERANCE_LIMITS["max_horizontal_rmse_cm"]
        or max_vertical is None
        or max_vertical <= 0
        or max_vertical > _PLATFORM_TOLERANCE_LIMITS["max_vertical_rmse_cm"]
        or min_checkpoints is None
        or min_checkpoints < _PLATFORM_TOLERANCE_LIMITS["min_checkpoint_count"]
        or horizontal_rmse > max_horizontal
        or vertical_rmse > max_vertical
        or checkpoint_count < min_checkpoints
    ):
        return None
    crs = str(value.get("crs", "")).strip().upper()
    vertical_datum = str(value.get("vertical_datum", "")).strip().upper()
    if not crs or crs != str(row.crs or "").strip().upper() or not vertical_datum:
        return None

    result: dict[str, Any] = {
        "reviewed": True,
        "tolerance_reference": str(value["tolerance_reference"]),
        "method": str(value["method"]),
        "method_version": str(value["method_version"]),
        "acquisition_method": acquisition_method,
        "horizontal_rmse_cm": horizontal_rmse,
        "vertical_rmse_cm": vertical_rmse,
        "checkpoint_count": checkpoint_count,
        "crs": crs,
        "vertical_datum": vertical_datum,
        "project_tolerances": {
            "max_horizontal_rmse_cm": max_horizontal,
            "max_vertical_rmse_cm": max_vertical,
            "min_checkpoint_count": min_checkpoints,
        },
    }
    if acquisition_method == "RTK_PPK_PHOTOGRAMMETRY":
        ground_sample_distance = _number(value.get("ground_sample_distance_cm"))
        control_point_count = _integer(value.get("control_point_count"))
        max_gsd = _number(thresholds.get("max_ground_sample_distance_cm"))
        min_controls = _integer(thresholds.get("min_control_point_count"))
        control_dataset_id = str(value.get("control_dataset_id", "")).strip()
        control_dataset = datasets.get(control_dataset_id)
        if (
            ground_sample_distance is None
            or ground_sample_distance <= 0
            or control_point_count is None
            or max_gsd is None
            or max_gsd <= 0
            or max_gsd > _PLATFORM_TOLERANCE_LIMITS["max_ground_sample_distance_cm"]
            or min_controls is None
            or min_controls < _PLATFORM_TOLERANCE_LIMITS["min_control_point_count"]
            or ground_sample_distance > max_gsd
            or control_point_count < min_controls
            or control_dataset is None
            or control_dataset.dataset_type != "RTK_OBSERVATIONS"
            or control_dataset.company_id != row.company_id
            or control_dataset.workspace_id != row.workspace_id
            or control_dataset.asset_id != row.asset_id
            or control_dataset.status != "ready"
            or control_dataset.quality_status != "PASSED"
            or (control_dataset.capture_date or control_dataset.created_at)
            > (row.capture_date or row.created_at)
        ):
            return None
        result.update(
            {
                "ground_sample_distance_cm": ground_sample_distance,
                "control_point_count": control_point_count,
                "control_dataset_id": control_dataset_id,
            }
        )
        result["project_tolerances"].update(
            {
                "max_ground_sample_distance_cm": max_gsd,
                "min_control_point_count": min_controls,
            }
        )
    else:
        point_density = _number(value.get("point_density_per_m2"))
        min_density = _number(thresholds.get("min_point_density_per_m2"))
        if (
            point_density is None
            or point_density <= 0
            or min_density is None
            or min_density < _PLATFORM_TOLERANCE_LIMITS["min_point_density_per_m2"]
            or point_density < min_density
        ):
            return None
        result["point_density_per_m2"] = point_density
        result["project_tolerances"]["min_point_density_per_m2"] = min_density
    return result


def _surface_reference(
    row: Dataset,
    analysis: Mapping[str, Any] | None,
) -> dict[str, str] | None:
    if row.dataset_type not in _SURFACE_TYPES or analysis is None:
        return None
    value = analysis.get("surface_reference_evidence")
    if not isinstance(value, Mapping):
        return None
    crs = str(value.get("crs", "")).strip().upper()
    vertical_datum = str(value.get("vertical_datum", "")).strip().upper()
    method = str(value.get("method", "")).strip()
    method_version = str(value.get("method_version", "")).strip()
    reference = str(value.get("surface_reference", "")).strip()
    if not (
        value.get("reviewed") is True
        and reference
        and crs
        and crs == str(row.crs or "").strip().upper()
        and vertical_datum
        and _IDENTIFIER.fullmatch(method)
        and _VERSION.fullmatch(method_version)
    ):
        return None
    return {
        "surface_reference": reference,
        "crs": crs,
        "vertical_datum": vertical_datum,
        "method": method,
        "method_version": method_version,
    }


def _paired_surface(
    row: Dataset,
    value: Any,
    datasets: Mapping[str, Dataset],
) -> Dataset | None:
    if row.dataset_type not in _SURFACE_TYPES or not isinstance(value, Mapping):
        return None
    current_id = str(value.get("current_dataset_id", "")).strip()
    previous_id = str(value.get("previous_dataset_id", "")).strip()
    previous = datasets.get(previous_id)
    if (
        current_id != row.id
        or previous is None
        or previous.id == row.id
        or previous.dataset_type not in _SURFACE_TYPES
        or previous.company_id != row.company_id
        or previous.workspace_id != row.workspace_id
        or previous.asset_id != row.asset_id
    ):
        return None
    same_type = previous.dataset_type == row.dataset_type
    compatible_point_clouds = bool(
        not same_type
        and {previous.dataset_type, row.dataset_type}.issubset(_POINT_CLOUD_FAMILY)
        and value.get("compatibility_reviewed") is True
        and str(value.get("surface_family", "")).upper() == "POINT_CLOUD_SURFACE"
        and str(value.get("compatibility_reference", "")).strip()
    )
    if not same_type and not compatible_point_clouds:
        return None
    current_at = row.capture_date or row.processed_at or row.created_at
    previous_at = previous.capture_date or previous.processed_at or previous.created_at
    current_crs = str(row.crs or "").strip().upper()
    previous_crs = str(previous.crs or "").strip().upper()
    current_reference = _surface_reference(row, _accepted_analysis(row))
    previous_reference = _surface_reference(previous, _accepted_analysis(previous))
    if (
        previous_at >= current_at
        or value.get("reviewed") is not True
        or value.get("aligned") is not True
        or value.get("same_crs") is not True
        or value.get("same_vertical_datum") is not True
        or not current_crs
        or current_crs != previous_crs
        or not str(value.get("vertical_datum", "")).strip()
        or not _IDENTIFIER.fullmatch(str(value.get("method", "")).strip())
        or not _VERSION.fullmatch(str(value.get("method_version", "")).strip())
        or current_reference is None
        or previous_reference is None
        or current_reference["vertical_datum"] != previous_reference["vertical_datum"]
        or current_reference["vertical_datum"]
        != str(value.get("vertical_datum", "")).strip().upper()
        or current_reference["method"] != previous_reference["method"]
        or current_reference["method_version"] != previous_reference["method_version"]
    ):
        return None
    return previous


def _quality_pair(
    current: Dataset,
    previous: Dataset,
    current_analysis: Mapping[str, Any],
    datasets: Mapping[str, Dataset],
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    previous_analysis = _accepted_analysis(previous)
    current_quality = _quality_summary(current, current_analysis, datasets)
    previous_quality = _quality_summary(previous, previous_analysis, datasets)
    if current_quality is None or previous_quality is None:
        return None
    if (
        current_quality["vertical_datum"] != previous_quality["vertical_datum"]
        or current_quality["crs"] != previous_quality["crs"]
        or current_quality["method"] != previous_quality["method"]
        or current_quality["method_version"] != previous_quality["method_version"]
        or current_quality["tolerance_reference"]
        != previous_quality["tolerance_reference"]
        or current_quality["project_tolerances"]
        != previous_quality["project_tolerances"]
    ):
        return None
    return current_quality, previous_quality


def _detail(
    row: Dataset,
    analysis: Mapping[str, Any],
    *,
    gate: str,
    quality: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "source": f"validated:mining:{row.dataset_type.lower()}",
        "confidence": _confidence(analysis),
        "measured_at": row.capture_date or row.processed_at or row.created_at,
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
            **({"quality": dict(quality)} if quality else {}),
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
        candidate = f"candidate-{candidate or fallback}"
    return candidate[:100]


def _candidate_gate(value: Any, *, scope: str) -> bool:
    return bool(
        isinstance(value, Mapping)
        and value.get("reviewed") is True
        and str(value.get("interpretation_scope", "")).upper()
        == "GEOMETRIC_CHANGE_ONLY"
        and str(value.get("source_reference", "")).strip()
        and _IDENTIFIER.fullmatch(str(value.get("method", "")).strip())
        and _VERSION.fullmatch(str(value.get("method_version", "")).strip())
        and str(value.get("asset_scope", "")).upper() == scope
    )


def _candidate_recommendation(value: Any) -> str:
    if not isinstance(value, Mapping):
        return "progress"
    if (
        str(value.get("recommended_method", "")).strip().upper() == "LIDAR"
        and str(value.get("lidar_justification", "")).strip()
    ):
        return "lidar"
    return "progress"


def _extract_findings(
    asset: Asset,
    row: Dataset,
    analysis: Mapping[str, Any],
    *,
    paired_surface: bool,
) -> tuple[list[dict[str, Any]], set[str]]:
    candidates = analysis.get("review_candidates")
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        return [], set()
    evidence_by_kind = {
        "surface": analysis.get("surface_review_evidence"),
        "slope": analysis.get("slope_evidence"),
        "haul_road": analysis.get("haul_road_evidence"),
    }
    gates = {
        "surface": paired_surface
        and _candidate_gate(evidence_by_kind["surface"], scope="SURFACE"),
        "slope": asset.asset_type in {"SLOPE", "TALUS"}
        and paired_surface
        and _candidate_gate(evidence_by_kind["slope"], scope="SLOPE"),
        "haul_road": asset.asset_type == "HAUL_ROAD"
        and paired_surface
        and _candidate_gate(evidence_by_kind["haul_road"], scope="HAUL_ROAD"),
    }
    assessed = {kind for kind, valid in gates.items() if valid}
    measured_at = row.capture_date or row.processed_at or row.created_at
    provenance = {
        "analysis_schema": ANALYSIS_SCHEMA,
        "algorithm": analysis["algorithm"],
        "algorithm_version": analysis["algorithm_version"],
        "dataset_type": row.dataset_type,
        "interpretation": "geometric change candidate; cause and condition not assessed",
    }
    findings: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping) or candidate.get("new") is not True:
            continue
        kind = str(candidate.get("kind", "")).strip().lower()
        if kind not in assessed:
            continue
        area = _number(candidate.get("area_m2"))
        if area is not None and area < 0:
            area = None
        declared = _number(candidate.get("confidence"))
        confidence = min(
            _confidence(analysis),
            max(0.0, min(1.0, declared if declared is not None else 0.5)),
        )
        findings.append(
            {
                "key": _finding_key(candidate.get("id"), f"{kind}-{index + 1}"),
                "kind": kind,
                "label": str(
                    candidate.get("label") or "Mapped surface-change candidate"
                )[:200],
                "severity": str(candidate.get("severity") or "WATCH").upper(),
                "confidence": confidence,
                "area_m2": area,
                "geometry": _safe_geometry(candidate.get("geometry")),
                "source": f"validated:mining:{row.dataset_type.lower()}",
                "detected_at": measured_at,
                "dataset_id": row.id,
                "mission_id": row.mission_id,
                "recommendation_kind": _candidate_recommendation(
                    evidence_by_kind[kind]
                ),
                "provenance": provenance,
            }
        )
    return findings, assessed


def _eligible_datasets(
    db: Session,
    *,
    asset: Asset,
    as_of: datetime | None = None,
) -> list[Dataset]:
    rows = (
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
    if as_of is None:
        return rows
    return [row for row in rows if (row.capture_date or row.created_at) <= as_of]


def build_source_context(
    db: Session,
    *,
    asset: Asset,
    as_of: datetime | None = None,
) -> MiningSourceContext:
    """Promote only tenant-owned, reviewed, tolerance-compliant survey evidence."""

    _assert_mining_asset(asset)
    _require_feature(db, asset)
    evaluated_at = _utc_naive(as_of or utc_now())
    datasets = _eligible_datasets(db, asset=asset, as_of=evaluated_at)
    datasets_by_id = {row.id: row for row in datasets}
    histories: dict[str, list[tuple[datetime, float, dict[str, Any]]]] = {}
    accepted_ids: list[str] = []
    reviewed_survey_ids: set[str] = set()
    precise_volume_ids: set[str] = set()
    paired_surface_ids: set[str] = set()
    rtk_ppk_volume_ids: set[str] = set()
    lidar_volume_ids: set[str] = set()
    assessment_batches: dict[
        str,
        tuple[datetime, str, list[dict[str, Any]], dict[str, Any]],
    ] = {}

    for row in datasets:
        analysis = _accepted_analysis(row)
        if analysis is None:
            continue
        accepted_ids.append(row.id)
        measured_at = row.capture_date or row.processed_at or row.created_at
        survey_valid = _reviewed_survey_valid(row, analysis.get("survey_evidence"))
        quality = _quality_summary(row, analysis, datasets_by_id)
        if survey_valid:
            reviewed_survey_ids.add(row.id)
            age_days = max(0.0, (evaluated_at - measured_at).total_seconds() / 86_400)
            freshness_detail = _detail(row, analysis, gate="reviewed_survey_timestamp")
            freshness_detail["measured_at"] = evaluated_at
            freshness_detail["provenance"] = {
                **freshness_detail["provenance"],
                "survey_captured_at": measured_at.isoformat(),
                "calculation": "evaluation_time_minus_reviewed_survey_capture_time",
            }
            histories.setdefault("survey_freshness_days", []).append(
                (
                    measured_at,
                    age_days,
                    freshness_detail,
                )
            )

        metrics = analysis.get("metrics", {})
        if quality is not None:
            precise_volume_ids.add(row.id)
            if quality["acquisition_method"] == "RTK_PPK_PHOTOGRAMMETRY":
                rtk_ppk_volume_ids.add(row.id)
            else:
                lidar_volume_ids.add(row.id)
            stockpile_volume = _number(metrics.get("stockpile_volume"))
            if (
                asset.asset_type == "STOCKPILE_ZONE"
                and stockpile_volume is not None
                and stockpile_volume >= 0
            ):
                histories.setdefault("stockpile_volume", []).append(
                    (
                        measured_at,
                        stockpile_volume,
                        _detail(
                            row,
                            analysis,
                            gate="reviewed_project_tolerance",
                            quality=quality,
                        ),
                    )
                )

        previous = _paired_surface(
            row, analysis.get("surface_comparison_evidence"), datasets_by_id
        )
        if previous is not None:
            paired_surface_ids.add(row.id)
            surface_area = _number(metrics.get("surface_change_area"))
            if surface_area is not None and surface_area >= 0:
                histories.setdefault("surface_change_area", []).append(
                    (
                        measured_at,
                        surface_area,
                        _detail(row, analysis, gate="reviewed_aligned_surface_pair"),
                    )
                )
            quality_pair = _quality_pair(row, previous, analysis, datasets_by_id)
            volume_change = _number(metrics.get("terrain_volume_change"))
            if quality_pair is not None and volume_change is not None:
                current_quality, previous_quality = quality_pair
                histories.setdefault("terrain_volume_change", []).append(
                    (
                        measured_at,
                        volume_change,
                        {
                            **_detail(
                                row,
                                analysis,
                                gate="tolerance_compliant_surface_pair",
                                quality=current_quality,
                            ),
                            "provenance": {
                                **_detail(
                                    row,
                                    analysis,
                                    gate="tolerance_compliant_surface_pair",
                                    quality=current_quality,
                                )["provenance"],
                                "previous_dataset_id": previous.id,
                                "previous_quality": previous_quality,
                            },
                        },
                    )
                )

        extracted, assessed = _extract_findings(
            asset,
            row,
            analysis,
            paired_surface=previous is not None,
        )
        detail = _detail(row, analysis, gate="reviewed_geometric_candidate_inventory")
        for kind in assessed:
            batch = (
                measured_at,
                row.id,
                [item for item in extracted if item["kind"] == kind],
                detail,
            )
            current = assessment_batches.get(kind)
            if current is None or (batch[0], batch[1]) > (current[0], current[1]):
                assessment_batches[kind] = batch

    measurements: dict[str, float] = {}
    details: dict[str, dict[str, Any]] = {}
    for key, history in histories.items():
        history.sort(
            key=lambda item: (item[0], str(item[2].get("dataset_id"))), reverse=True
        )
        measurements[key] = history[0][1]
        details[key] = history[0][2]

    findings = [
        item for _, _, batch, _ in assessment_batches.values() for item in batch
    ]
    for kind, metric_key in (
        ("slope", "slope_review_candidate_count"),
        ("haul_road", "haul_road_review_candidate_count"),
    ):
        batch = assessment_batches.get(kind)
        if batch is None:
            continue
        matching = batch[2]
        measurements[metric_key] = float(len(matching))
        details[metric_key] = {
            **batch[3],
            "source": "mining.reviewed_geometric_candidate_inventory",
            "confidence": min(
                (float(item["confidence"]) for item in matching),
                default=float(batch[3]["confidence"]),
            ),
            "provenance": {
                **dict(batch[3]["provenance"]),
                "candidate_kind": kind,
                "derived_from": "reviewed_explicit_candidate_list",
            },
        }

    comparisons = mining_comparisons(db, asset=asset, enforce_feature=False)
    availability = {
        "validated_analysis": bool(accepted_ids),
        "reviewed_survey": bool(reviewed_survey_ids),
        "precise_volume": "stockpile_volume" in measurements,
        "paired_surface": bool(paired_surface_ids),
        "historical_comparison": any(
            item["availability"] == "AVAILABLE" for item in comparisons
        ),
        "rtk_ppk_photogrammetry": bool(rtk_ppk_volume_ids),
        "lidar": bool(lidar_volume_ids),
        "slope_assessment": "slope" in assessment_batches,
        "haul_road_assessment": "haul_road" in assessment_batches,
        "supported_dataset_count": len(datasets),
        "validated_analysis_count": len(accepted_ids),
        "limitations": [
            message
            for condition, message in (
                (not accepted_ids, "No validated Mining analysis is available."),
                (
                    not reviewed_survey_ids,
                    "Survey age is unknown without an explicitly reviewed survey reference.",
                ),
                (
                    asset.asset_type == "STOCKPILE_ZONE"
                    and "stockpile_volume" not in measurements,
                    "Precise stockpile volume is unavailable until measured project tolerances pass.",
                ),
                (
                    not paired_surface_ids,
                    "Terrain change is unavailable without a compatible aligned surface pair.",
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
        "reviewed_survey_dataset_ids": sorted(reviewed_survey_ids),
        "precise_volume_dataset_ids": sorted(precise_volume_ids),
        "paired_surface_dataset_ids": sorted(paired_surface_ids),
        "rtk_ppk_volume_dataset_ids": sorted(rtk_ppk_volume_ids),
        "lidar_volume_dataset_ids": sorted(lidar_volume_ids),
    }
    return MiningSourceContext(
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
                "asset_type": asset.asset_type,
                "measurement_details": details,
                "source_availability": availability,
                "evidence": evidence,
                "findings": tuple(findings),
            },
        ),
        availability=availability,
        evidence=evidence,
    )


def evaluate_mining(
    db: Session,
    *,
    asset: Asset,
    actor=None,
    as_of: datetime | None = None,
) -> MiningEvaluation:
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
    return MiningEvaluation(sources, result, actions)


def _comparison_vertical_datum(row: Dataset) -> str | None:
    analysis = _accepted_analysis(row)
    reference = _surface_reference(row, analysis)
    return reference["vertical_datum"] if reference else None


def mining_comparisons(
    db: Session,
    *,
    asset: Asset,
    enforce_feature: bool = True,
) -> list[dict[str, Any]]:
    _assert_mining_asset(asset)
    if enforce_feature:
        _require_feature(db, asset)
    datasets = _eligible_datasets(db, asset=asset)
    specifications = (
        (
            "SURVEY_2D",
            "Historical mining orthomosaic comparison",
            "2D",
            "SWIPE_2D",
            ("ORTHOMOSAIC",),
            False,
        ),
        (
            "SURFACE_3D",
            "Historical mining surface comparison",
            "3D",
            "MODEL_COMPARE_3D",
            ("POINT_CLOUD", "LIDAR_POINT_CLOUD", "DSM", "DTM", "MESH_3D"),
            True,
        ),
    )
    result: list[dict[str, Any]] = []
    for (
        kind,
        title,
        dimension,
        render_mode,
        preferred_types,
        require_vertical,
    ) in specifications:
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
        current_at = current.capture_date or current.created_at if current else None
        previous_at = previous.capture_date or previous.created_at if previous else None
        current_datum = _comparison_vertical_datum(current) if current else None
        previous_datum = _comparison_vertical_datum(previous) if previous else None
        compatible = bool(
            current
            and previous
            and current_at
            and previous_at
            and previous_at < current_at
            and str(current.crs or "").strip()
            and str(current.crs or "").strip().upper()
            == str(previous.crs or "").strip().upper()
            and (
                not require_vertical
                or (current_datum and current_datum == previous_datum)
            )
        )
        availability = "AVAILABLE" if compatible else "UNKNOWN" if pair else "NO_DATA"
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
                        "captured_at": current_at,
                        "data_ref": f"/datasets/{current.id}",
                    }
                    if current
                    else None
                ),
                "previous": (
                    {
                        "dataset_id": previous.id,
                        "captured_at": previous_at,
                        "data_ref": f"/datasets/{previous.id}",
                    }
                    if previous
                    else None
                ),
                "crs": current.crs if compatible and current else None,
                "vertical_datum": current_datum
                if compatible and require_vertical
                else None,
                "limitation": (
                    None
                    if compatible
                    else "Reference systems, vertical datum, or capture order are incompatible."
                    if pair
                    else "A compatible earlier dataset is required."
                ),
                "interpretation": (
                    "visual survey comparison only; no reserve, grade, geotechnical, safety, "
                    "or defect conclusion"
                ),
            }
        )
    return result


_LAYER_MODES = {
    "DSM": ("2D", "MAP_RASTER"),
    "DTM": ("2D", "MAP_RASTER"),
    "LIDAR_POINT_CLOUD": ("3D", "POINT_CLOUD_3D"),
    "MESH_3D": ("3D", "MESH_3D"),
    "ORTHOMOSAIC": ("2D", "MAP_RASTER"),
    "POINT_CLOUD": ("3D", "POINT_CLOUD_3D"),
    "RGB_IMAGES": ("REFERENCE", "REFERENCE_ONLY"),
    "RTK_OBSERVATIONS": ("REFERENCE", "REFERENCE_ONLY"),
}


def _public_provenance(row: Dataset) -> dict[str, Any]:
    raw = _object(row.provenance_json)
    return {
        str(key): value
        for key, value in raw.items()
        if str(key) in _PUBLIC_PROVENANCE_KEYS
        and value is not None
        and isinstance(value, (str, int, float, bool))
    }


def mining_map_layers(db: Session, *, asset: Asset) -> list[dict[str, Any]]:
    _assert_mining_asset(asset)
    _require_feature(db, asset)
    geometry = _safe_geometry(
        _object(asset.geometry_geojson) if asset.geometry_geojson else None
    )
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
    rows = (
        db.query(Dataset)
        .filter(
            Dataset.company_id == asset.organization_id,
            Dataset.workspace_id == asset.workspace_id,
            Dataset.asset_id == asset.id,
            Dataset.dataset_type.in_(tuple(SUPPORTED_DATASET_TYPES)),
        )
        .order_by(Dataset.capture_date.desc(), Dataset.created_at.desc())
        .all()
    )
    datasets_by_id = {row.id: row for row in rows}
    for row in rows:
        dimension, render_mode = _LAYER_MODES[row.dataset_type]
        analysis = _accepted_analysis(row)
        quality = _quality_summary(row, analysis, datasets_by_id)
        availability = (
            "NO_DATA"
            if row.status not in {"ready", "processing"}
            or row.quality_status == "FAILED"
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
                "confidence": _confidence(analysis) if analysis else None,
                "quality": {
                    "dataset_status": row.quality_status,
                    "volume_tolerance": "PASSED" if quality else "NOT_ESTABLISHED",
                },
                "crs": row.crs,
                "resolution": (
                    {"value": row.resolution, "unit": row.resolution_unit}
                    if row.resolution is not None
                    else None
                ),
                "provenance": {
                    "dataset_type": row.dataset_type,
                    "processing_level": row.processing_level,
                    **_public_provenance(row),
                },
            }
        )
    for row in list_asset_observations(db, asset=asset, limit=500):
        observation_geometry = (
            _safe_geometry(_object(row.geometry_geojson))
            if row.geometry_geojson
            else None
        )
        if not observation_geometry:
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
                "geometry": observation_geometry,
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
                    "causation_assessed": False,
                    "specialist_review_required": row.validation_status != "VALIDATED",
                },
            }
        )
    return layers


def mining_report_context(db: Session, *, asset: Asset) -> dict[str, Any]:
    """Return provenance-bearing Mining evidence for the common report engine."""

    sources = build_source_context(db, asset=asset)
    observations = list_asset_observations(db, asset=asset, limit=500)
    actions = (
        db.query(Action)
        .filter(
            Action.organization_id == asset.organization_id,
            Action.workspace_id == asset.workspace_id,
            Action.asset_id == asset.id,
            Action.status.in_(("OPEN", "IN_PROGRESS")),
        )
        .order_by(Action.due_date, Action.created_at.desc())
        .limit(500)
        .all()
    )
    return {
        "schema": "geovision.mining.report-context.v1",
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
        "comparisons": mining_comparisons(db, asset=asset),
        "map_layers": mining_map_layers(db, asset=asset),
        "limitations": [
            *sources.availability.get("limitations", []),
            "Published volumes require reviewed project tolerances and measured accuracy evidence.",
            "RTK/PPK photogrammetry is supported without LiDAR when its tolerance evidence passes.",
            "Mapped slope, haul-road, and surface changes remain review candidates.",
            "No reserve, resource, ore-grade, geotechnical, defect, safety, or compliance conclusion is generated.",
        ],
    }


__all__ = [
    "ANALYSIS_SCHEMA",
    "MiningEvaluation",
    "build_source_context",
    "evaluate_mining",
    "mining_comparisons",
    "mining_enabled_for_context",
    "mining_map_layers",
    "mining_report_context",
    "sync_kpi_definitions",
]
