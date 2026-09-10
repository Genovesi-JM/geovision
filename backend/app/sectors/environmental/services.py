"""Validated source fusion and application services for Environmental monitoring."""

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
from app.models import (
    Account,
    Action,
    Asset,
    Dataset,
    IotDevice,
    SatelliteScene,
    TelemetryReading,
    WeatherObservation,
)
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
from app.sectors.environmental.domain import (
    ALGORITHM_VERSION,
    EnvironmentalError,
    EnvironmentalSourceContext,
    KPI_DEFINITIONS,
    SECTOR,
    SUPPORTED_ASSET_TYPES,
    SUPPORTED_DATASET_TYPES,
)


ANALYSIS_SCHEMA = "geovision.environmental.analysis.v1"
_MODULE_KEYS = frozenset({"environmental", "environment", "ambiental"})
_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,159}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,39}$")
_DRONE_TYPES = frozenset(
    {"RGB_IMAGES", "MULTISPECTRAL_IMAGES", "ORTHOMOSAIC", "THERMAL_IMAGES"}
)
_SURFACE_TYPES = frozenset({"DSM", "DTM"})
_CLASSIFICATION_TYPES = frozenset(
    {
        "LAND_COVER_CLASSIFICATION",
        "MULTISPECTRAL_IMAGES",
        "NDVI",
        "ORTHOMOSAIC",
        "SATELLITE_IMAGE",
    }
)
_CHANGE_TYPES = _CLASSIFICATION_TYPES
_METRIC_DATASET_TYPES = {
    "vegetation_cover": frozenset(
        {
            "LAND_COVER_CLASSIFICATION",
            "MULTISPECTRAL_IMAGES",
            "NDVI",
            "ORTHOMOSAIC",
            "SATELLITE_IMAGE",
        }
    ),
    "vegetation_cover_change": frozenset(
        {
            "LAND_COVER_CLASSIFICATION",
            "MULTISPECTRAL_IMAGES",
            "NDVI",
            "ORTHOMOSAIC",
            "SATELLITE_IMAGE",
        }
    ),
    "land_cover_change_area": frozenset(
        {
            "LAND_COVER_CLASSIFICATION",
            "MULTISPECTRAL_IMAGES",
            "ORTHOMOSAIC",
            "SATELLITE_IMAGE",
        }
    ),
    "reforestation_cover": frozenset(
        {
            "LAND_COVER_CLASSIFICATION",
            "MULTISPECTRAL_IMAGES",
            "NDVI",
            "ORTHOMOSAIC",
            "SATELLITE_IMAGE",
        }
    ),
    "reforestation_change": frozenset(
        {
            "LAND_COVER_CLASSIFICATION",
            "MULTISPECTRAL_IMAGES",
            "NDVI",
            "ORTHOMOSAIC",
            "SATELLITE_IMAGE",
        }
    ),
    "ndvi_mean": frozenset({"MULTISPECTRAL_IMAGES", "NDVI", "SATELLITE_IMAGE"}),
    "ndvi_change": frozenset({"MULTISPECTRAL_IMAGES", "NDVI", "SATELLITE_IMAGE"}),
}
_FINDING_DATASET_TYPES = {
    "vegetation_change": _METRIC_DATASET_TYPES["vegetation_cover_change"],
    "land_cover_change": _METRIC_DATASET_TYPES["land_cover_change_area"],
    "reforestation_change": _METRIC_DATASET_TYPES["reforestation_change"],
    "terrain_change": _SURFACE_TYPES,
}
_CLASSIFICATION_BASES = frozenset(
    {
        "SIGNED_FIELD_ASSESSMENT",
        "VALIDATED_LAND_COVER_CLASSIFICATION",
        "VALIDATED_VEGETATION_CLASSIFICATION",
    }
)
_PUBLIC_PROVENANCE_KEYS = frozenset(
    {
        "adapter_version",
        "attribution",
        "catalog_record_id",
        "catalog_record_url",
        "collection",
        "collection_id",
        "dataset_updated_at",
        "fetched_at",
        "license",
        "license_id",
        "license_url",
        "official_source",
        "context_only",
        "diagnostic_authority",
        "geographic_scope",
        "measurements_authoritative",
        "no_endorsement",
        "protocol",
        "provider_response_timestamp",
        "provider_updated_at",
        "reuse_notice_url",
        "source_name",
        "source_url",
    }
)


@dataclass(frozen=True, slots=True)
class EnvironmentalEvaluation:
    sources: EnvironmentalSourceContext
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
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


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


def environmental_enabled_for_context(
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


def _assert_environmental_asset(asset: Asset) -> None:
    if asset.sector != SECTOR:
        raise EnvironmentalError(
            "sector_mismatch",
            "Environmental intelligence is available only for Environmental assets",
        )
    if asset.asset_type not in SUPPORTED_ASSET_TYPES:
        raise EnvironmentalError(
            "asset_type_unsupported",
            f"Environmental does not support asset type {asset.asset_type}",
        )


def _require_feature(db: Session, asset: Asset) -> Account:
    workspace = db.get(Account, asset.workspace_id) if asset.workspace_id else None
    if (
        workspace is None
        or workspace.organization_id != asset.organization_id
        or not _workspace_enabled(workspace)
    ):
        raise EnvironmentalError(
            "feature_disabled",
            "Environmental is not enabled for this workspace",
        )
    return workspace


def sync_kpi_definitions(db: Session) -> None:
    for definition in KPI_DEFINITIONS:
        ensure_kpi_definition(db, definition)


def _accepted_analysis(row: Dataset) -> Mapping[str, Any] | None:
    # Official/public reference layers are contextual evidence only. A caller
    # cannot promote them into GeoVision measurements by injecting metadata.
    if (
        row.dataset_type in {"ENVIRONMENTAL_REFERENCE", "TELEMETRY", "WEATHER_DATA"}
        or str(row.provider_code or "").lower() == "miteco"
    ):
        return None
    metadata = _object(row.metadata_json)
    analysis = metadata.get("environmental_analysis")
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


def _classification_evidence_valid(value: Any) -> bool:
    return bool(
        isinstance(value, Mapping)
        and value.get("reviewed") is True
        and str(value.get("basis", "")).upper() in _CLASSIFICATION_BASES
        and str(value.get("source_reference", "")).strip()
        and str(value.get("reference_version", "")).strip()
        and _VERSION.fullmatch(str(value.get("class_schema_version", "")).strip())
    )


def _thermal_evidence_valid(value: Any) -> bool:
    return bool(
        isinstance(value, Mapping)
        and value.get("reviewed") is True
        and value.get("calibrated") is True
        and str(value.get("sensor_reference", "")).strip()
        and str(value.get("calibration_reference", "")).strip()
        and _IDENTIFIER.fullmatch(str(value.get("method", "")).strip())
        and _VERSION.fullmatch(str(value.get("method_version", "")).strip())
    )


def _affected_area_inventory(
    value: Any,
    findings: Sequence[Mapping[str, Any]],
) -> tuple[float, tuple[str, ...]] | None:
    if not isinstance(value, Mapping):
        return None
    candidate_ids = value.get("candidate_ids")
    if not isinstance(candidate_ids, Sequence) or isinstance(
        candidate_ids, (str, bytes)
    ):
        return None
    normalized_ids = tuple(
        str(item).strip() for item in candidate_ids if str(item).strip()
    )
    if not normalized_ids or len(normalized_ids) != len(set(normalized_ids)):
        return None
    if not (
        value.get("reviewed") is True
        and value.get("non_overlapping") is True
        and str(value.get("inventory_reference", "")).strip()
        and _IDENTIFIER.fullmatch(str(value.get("method", "")).strip())
        and _VERSION.fullmatch(str(value.get("method_version", "")).strip())
    ):
        return None
    by_key = {str(item.get("key")): item for item in findings}
    selected = [by_key.get(candidate_id) for candidate_id in normalized_ids]
    if any(item is None or _number(item.get("area_ha")) is None for item in selected):
        return None
    area = sum(float(item["area_ha"]) for item in selected if item is not None)
    return (area, normalized_ids) if area >= 0 else None


def _drone_verifies_satellite(
    analysis: Mapping[str, Any],
    *,
    satellite_dataset_ids: set[str],
    satellite_candidate_ids: set[str],
) -> bool:
    evidence = analysis.get("verification_evidence")
    if not isinstance(evidence, Mapping) or evidence.get("reviewed") is not True:
        return False
    linked_datasets = (
        {
            str(item).strip()
            for item in evidence.get("satellite_dataset_ids", ())
            if str(item).strip()
        }
        if isinstance(evidence.get("satellite_dataset_ids"), Sequence)
        and not isinstance(evidence.get("satellite_dataset_ids"), (str, bytes))
        else set()
    )
    linked_candidates = (
        {
            str(item).strip()
            for item in evidence.get("candidate_ids", ())
            if str(item).strip()
        }
        if isinstance(evidence.get("candidate_ids"), Sequence)
        and not isinstance(evidence.get("candidate_ids"), (str, bytes))
        else set()
    )
    return bool(
        linked_datasets.intersection(satellite_dataset_ids)
        or linked_candidates.intersection(satellite_candidate_ids)
    )


def _paired_evidence_valid(
    row: Dataset,
    value: Any,
    datasets: Mapping[str, Dataset],
    *,
    surface: bool = False,
) -> bool:
    if not isinstance(value, Mapping):
        return False
    previous_id = str(value.get("previous_dataset_id", "")).strip()
    current_id = str(value.get("current_dataset_id", "")).strip()
    previous = datasets.get(previous_id)
    if (
        current_id != row.id
        or previous is None
        or previous.id == row.id
        or previous.dataset_type != row.dataset_type
        or previous.company_id != row.company_id
        or previous.workspace_id != row.workspace_id
        or previous.asset_id != row.asset_id
    ):
        return False
    current_at = row.capture_date or row.processed_at or row.created_at
    previous_at = previous.capture_date or previous.processed_at or previous.created_at
    if previous_at >= current_at:
        return False
    current_crs = str(row.crs or "").strip().upper()
    previous_crs = str(previous.crs or "").strip().upper()
    if (
        value.get("aligned") is not True
        or value.get("same_crs") is not True
        or not current_crs
        or current_crs != previous_crs
    ):
        return False
    method = str(value.get("method", "")).strip()
    method_version = str(value.get("method_version", "")).strip()
    if not _IDENTIFIER.fullmatch(method) or not _VERSION.fullmatch(method_version):
        return False
    if surface and (
        row.dataset_type not in _SURFACE_TYPES
        or previous.dataset_type not in _SURFACE_TYPES
        or not str(value.get("vertical_datum", "")).strip()
    ):
        return False
    return True


def _source_kind(row: Dataset, satellite_dataset_ids: set[str]) -> str:
    if row.id in satellite_dataset_ids or row.dataset_type == "SATELLITE_IMAGE":
        return "satellite"
    if str(row.provider_code or "").lower() == "copernicus":
        return "satellite"
    if row.dataset_type == "WEATHER_DATA":
        return "weather"
    if row.dataset_type == "TELEMETRY":
        return "iot"
    if row.dataset_type == "ENVIRONMENTAL_REFERENCE":
        return "official_context"
    return "drone" if row.dataset_type in _DRONE_TYPES else "other"


def _detail(
    row: Dataset,
    analysis: Mapping[str, Any],
    *,
    gate: str,
) -> dict[str, Any]:
    return {
        "source": f"validated:{_source_kind(row, set())}:{row.dataset_type.lower()}",
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


def _public_provenance(row: Dataset) -> dict[str, Any]:
    raw = _object(row.provenance_json)
    source = raw.get("source") if isinstance(raw.get("source"), Mapping) else raw
    result = {
        str(key): value
        for key, value in source.items()
        if str(key) in _PUBLIC_PROVENANCE_KEYS
        and value is not None
        and isinstance(value, (str, int, float, bool))
    }
    if row.dataset_type == "ENVIRONMENTAL_REFERENCE":
        result.setdefault(
            "official_source", str(row.provider_code or "").lower() == "miteco"
        )
    return result


def _extract_findings(
    row: Dataset,
    analysis: Mapping[str, Any],
    *,
    source_kind: str,
    comparison_valid: bool,
    surface_valid: bool,
    reforestation_valid: bool,
    thermal_valid: bool,
) -> tuple[list[dict[str, Any]], set[str]]:
    findings: list[dict[str, Any]] = []
    assessed: set[str] = set()
    measured_at = row.capture_date or row.processed_at or row.created_at
    provenance = {
        "analysis_schema": ANALYSIS_SCHEMA,
        "algorithm": analysis["algorithm"],
        "algorithm_version": analysis["algorithm_version"],
        "dataset_type": row.dataset_type,
        "interpretation": "change candidate; causation not assessed",
    }
    candidates = analysis.get("change_candidates")
    if isinstance(candidates, Sequence) and not isinstance(candidates, (str, bytes)):
        for index, candidate in enumerate(candidates):
            if not isinstance(candidate, Mapping) or candidate.get("new") is not True:
                continue
            kind = str(candidate.get("kind", "")).strip().lower()
            if kind not in {
                "vegetation_change",
                "land_cover_change",
                "terrain_change",
                "reforestation_change",
            }:
                continue
            if row.dataset_type not in _FINDING_DATASET_TYPES[kind]:
                continue
            if kind == "terrain_change" and not surface_valid:
                continue
            if kind == "reforestation_change" and not reforestation_valid:
                continue
            if (
                kind in {"vegetation_change", "land_cover_change"}
                and not comparison_valid
            ):
                continue
            assessed.add(kind)
            area = _number(candidate.get("area_ha"))
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
                    "label": str(candidate.get("label") or "Mapped change candidate")[
                        :200
                    ],
                    "severity": str(candidate.get("severity") or "WATCH").upper(),
                    "confidence": confidence,
                    "area_ha": area,
                    "geometry": _safe_geometry(candidate.get("geometry")),
                    "source": f"validated:{source_kind}:{row.dataset_type.lower()}",
                    "source_kind": source_kind,
                    "detected_at": measured_at,
                    "dataset_id": row.id,
                    "mission_id": row.mission_id,
                    "provenance": provenance,
                }
            )

    hotspots = analysis.get("thermal_hotspots")
    if (
        row.dataset_type == "THERMAL_IMAGES"
        and thermal_valid
        and isinstance(hotspots, Sequence)
        and not isinstance(hotspots, (str, bytes))
    ):
        assessed.add("thermal_hotspot")
        for index, candidate in enumerate(hotspots):
            if not isinstance(candidate, Mapping) or candidate.get("new") is not True:
                continue
            declared = _number(candidate.get("confidence"))
            confidence = min(
                _confidence(analysis),
                max(0.0, min(1.0, declared if declared is not None else 0.5)),
            )
            findings.append(
                {
                    "key": _finding_key(candidate.get("id"), f"thermal-{index + 1}"),
                    "kind": "thermal_hotspot",
                    "label": str(
                        candidate.get("label") or "Thermal contrast candidate"
                    )[:200],
                    "severity": str(candidate.get("severity") or "WATCH").upper(),
                    "confidence": confidence,
                    "area_ha": _number(candidate.get("area_ha")),
                    "geometry": _safe_geometry(candidate.get("geometry")),
                    "source": f"validated:{source_kind}:thermal_images",
                    "source_kind": source_kind,
                    "detected_at": measured_at,
                    "dataset_id": row.id,
                    "mission_id": row.mission_id,
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
    query = db.query(Dataset).filter(
        Dataset.company_id == asset.organization_id,
        Dataset.workspace_id == asset.workspace_id,
        Dataset.asset_id == asset.id,
        Dataset.dataset_type.in_(tuple(SUPPORTED_DATASET_TYPES)),
        Dataset.status == "ready",
        Dataset.quality_status == "PASSED",
    )
    rows = query.order_by(Dataset.capture_date.desc(), Dataset.created_at.desc()).all()
    if as_of is None:
        return rows
    return [row for row in rows if (row.capture_date or row.created_at) <= as_of]


def build_source_context(
    db: Session,
    *,
    asset: Asset,
    as_of: datetime | None = None,
) -> EnvironmentalSourceContext:
    """Load tenant-owned evidence and promote only validated, technically gated facts."""

    _assert_environmental_asset(asset)
    _require_feature(db, asset)
    evaluated_at = _utc_naive(as_of or utc_now())
    datasets = _eligible_datasets(db, asset=asset, as_of=evaluated_at)
    datasets_by_id = {row.id: row for row in datasets}
    dataset_ids = set(datasets_by_id)
    satellite_scenes = (
        db.query(SatelliteScene)
        .filter(
            SatelliteScene.organization_id == asset.organization_id,
            SatelliteScene.asset_id == asset.id,
            SatelliteScene.dataset_id.in_(dataset_ids),
            SatelliteScene.acquired_at <= evaluated_at,
        )
        .order_by(SatelliteScene.acquired_at.desc())
        .all()
        if dataset_ids
        else []
    )
    satellite_dataset_ids = {row.dataset_id for row in satellite_scenes}
    weather_rows = (
        db.query(WeatherObservation)
        .filter(
            WeatherObservation.organization_id == asset.organization_id,
            WeatherObservation.asset_id == asset.id,
            WeatherObservation.dataset_id.in_(dataset_ids),
            WeatherObservation.observed_at <= evaluated_at,
        )
        .order_by(WeatherObservation.observed_at.desc())
        .all()
        if dataset_ids
        else []
    )
    devices = (
        db.query(IotDevice)
        .filter(
            IotDevice.company_id == asset.organization_id,
            IotDevice.core_asset_id == asset.id,
            IotDevice.status == "active",
        )
        .all()
    )
    device_ids = [row.id for row in devices]
    telemetry_rows = (
        db.query(TelemetryReading)
        .filter(
            TelemetryReading.company_id == asset.organization_id,
            TelemetryReading.core_asset_id == asset.id,
            TelemetryReading.device_id.in_(device_ids),
            TelemetryReading.recorded_at <= evaluated_at,
        )
        .order_by(TelemetryReading.recorded_at.desc())
        .limit(200)
        .all()
        if device_ids
        else []
    )

    histories: dict[str, list[tuple[datetime, float, dict[str, Any]]]] = {}
    finding_batches: dict[
        str,
        tuple[datetime, str, list[dict[str, Any]], dict[str, Any]],
    ] = {}
    accepted_ids: list[str] = []
    paired_change_ids: set[str] = set()
    paired_surface_ids: set[str] = set()
    classification_ids: set[str] = set()
    affected_area_batches: list[
        tuple[datetime, str, float, tuple[str, ...], dict[str, Any]]
    ] = []

    for row in datasets:
        analysis = _accepted_analysis(row)
        if analysis is None:
            continue
        accepted_ids.append(row.id)
        measured_at = row.capture_date or row.processed_at or row.created_at
        source_kind = _source_kind(row, satellite_dataset_ids)
        classification_valid = bool(
            row.dataset_type in _CLASSIFICATION_TYPES
            and _classification_evidence_valid(analysis.get("classification_evidence"))
        )
        comparison_valid = bool(
            row.dataset_type in _CHANGE_TYPES
            and _paired_evidence_valid(
                row,
                analysis.get("comparison_evidence"),
                datasets_by_id,
            )
        )
        surface_valid = _paired_evidence_valid(
            row,
            analysis.get("surface_evidence"),
            datasets_by_id,
            surface=True,
        )
        reforestation_evidence = analysis.get("reforestation_evidence")
        reforestation_valid = bool(
            asset.asset_type == "RESTORATION_SITE"
            and classification_valid
            and isinstance(reforestation_evidence, Mapping)
            and reforestation_evidence.get("reviewed") is True
            and str(reforestation_evidence.get("programme_reference", "")).strip()
            and str(reforestation_evidence.get("baseline_version", "")).strip()
        )
        thermal_valid = _thermal_evidence_valid(analysis.get("thermal_evidence"))
        if classification_valid:
            classification_ids.add(row.id)
        if comparison_valid:
            paired_change_ids.add(row.id)
        if surface_valid:
            paired_surface_ids.add(row.id)

        metrics = analysis.get("metrics", {})
        if classification_valid:
            vegetation_cover = _number(metrics.get("vegetation_cover"))
            if (
                row.dataset_type in _METRIC_DATASET_TYPES["vegetation_cover"]
                and vegetation_cover is not None
                and 0 <= vegetation_cover <= 100
            ):
                histories.setdefault("vegetation_cover", []).append(
                    (
                        measured_at,
                        vegetation_cover,
                        _detail(
                            row, analysis, gate="reviewed_vegetation_classification"
                        ),
                    )
                )
            ndvi = _number(metrics.get("ndvi_mean"))
            if (
                row.dataset_type in _METRIC_DATASET_TYPES["ndvi_mean"]
                and ndvi is not None
                and -1 <= ndvi <= 1
            ):
                histories.setdefault("ndvi_mean", []).append(
                    (measured_at, ndvi, _detail(row, analysis, gate="reviewed_index"))
                )
            if reforestation_valid:
                reforestation_cover = _number(metrics.get("reforestation_cover"))
                if (
                    row.dataset_type in _METRIC_DATASET_TYPES["reforestation_cover"]
                    and reforestation_cover is not None
                    and 0 <= reforestation_cover <= 100
                ):
                    histories.setdefault("reforestation_cover", []).append(
                        (
                            measured_at,
                            reforestation_cover,
                            _detail(
                                row, analysis, gate="reviewed_reforestation_programme"
                            ),
                        )
                    )

        if comparison_valid:
            for key, minimum, maximum in (
                ("vegetation_cover_change", -100.0, 100.0),
                ("land_cover_change_area", 0.0, None),
                ("ndvi_change", -2.0, 2.0),
                ("reforestation_change", -100.0, 100.0),
            ):
                if key.startswith("reforestation") and not reforestation_valid:
                    continue
                if row.dataset_type not in _METRIC_DATASET_TYPES[key]:
                    continue
                value = _number(metrics.get(key))
                if (
                    value is None
                    or value < minimum
                    or (maximum is not None and value > maximum)
                ):
                    continue
                histories.setdefault(key, []).append(
                    (
                        measured_at,
                        value,
                        _detail(row, analysis, gate="aligned_reviewed_pair"),
                    )
                )
        if surface_valid:
            terrain_area = _number(metrics.get("terrain_change_area"))
            if terrain_area is not None and terrain_area >= 0:
                histories.setdefault("terrain_change_area", []).append(
                    (
                        measured_at,
                        terrain_area,
                        _detail(row, analysis, gate="aligned_surface_change_pair"),
                    )
                )

        extracted, assessed = _extract_findings(
            row,
            analysis,
            source_kind=source_kind,
            comparison_valid=comparison_valid,
            surface_valid=surface_valid,
            reforestation_valid=reforestation_valid,
            thermal_valid=thermal_valid,
        )
        area_inventory = _affected_area_inventory(
            analysis.get("affected_area_evidence"), extracted
        )
        if area_inventory is not None:
            area, candidate_ids = area_inventory
            affected_area_batches.append(
                (
                    measured_at,
                    row.id,
                    area,
                    candidate_ids,
                    _detail(
                        row,
                        analysis,
                        gate="reviewed_non_overlapping_candidate_inventory",
                    ),
                )
            )
        detail = _detail(row, analysis, gate="validated_candidate_inventory")
        for kind in assessed:
            batch = (
                measured_at,
                row.id,
                [item for item in extracted if item["kind"] == kind],
                detail,
            )
            current = finding_batches.get(kind)
            if current is None or (batch[0], batch[1]) > (current[0], current[1]):
                finding_batches[kind] = batch

    measurements: dict[str, float] = {}
    details: dict[str, dict[str, Any]] = {}
    for key, history in histories.items():
        history.sort(
            key=lambda item: (item[0], str(item[2].get("dataset_id"))), reverse=True
        )
        measurements[key] = history[0][1]
        details[key] = history[0][2]

    findings = [item for _, _, batch, _ in finding_batches.values() for item in batch]
    if affected_area_batches:
        newest_area = max(affected_area_batches, key=lambda item: (item[0], item[1]))
        measurements["affected_area"] = newest_area[2]
        details["affected_area"] = {
            **newest_area[4],
            "source": "environmental.reviewed_non_overlapping_inventory",
            "provenance": {
                **dict(newest_area[4]["provenance"]),
                "derived_from": "reviewed_non_overlapping_candidate_inventory",
                "candidate_ids": list(newest_area[3]),
            },
        }
    thermal_batch = finding_batches.get("thermal_hotspot")
    if thermal_batch is not None:
        measurements["thermal_hotspot_count"] = float(len(thermal_batch[2]))
        details["thermal_hotspot_count"] = {
            **thermal_batch[3],
            "source": "environmental.validated_thermal_candidate_inventory",
            "confidence": min(
                (float(item["confidence"]) for item in thermal_batch[2]),
                default=float(thermal_batch[3]["confidence"]),
            ),
            "provenance": {
                **dict(thermal_batch[3]["provenance"]),
                "derived_from": "explicit_thermal_candidate_list",
            },
        }

    comparisons = environmental_comparisons(db, asset=asset, enforce_feature=False)
    historical_comparison = any(
        item["availability"] == "AVAILABLE" for item in comparisons
    )
    latest_satellite_change = max(
        (
            item["detected_at"]
            for item in findings
            if item["source_kind"] == "satellite"
            and item["kind"] in {"vegetation_change", "land_cover_change"}
        ),
        default=None,
    )
    relevant_satellite_dataset_ids = {
        str(item["dataset_id"])
        for item in findings
        if item["source_kind"] == "satellite"
        and item["kind"] in {"vegetation_change", "land_cover_change"}
    }
    relevant_satellite_candidate_ids = {
        str(item["key"])
        for item in findings
        if item["source_kind"] == "satellite"
        and item["kind"] in {"vegetation_change", "land_cover_change"}
    }
    current_drone_verification = bool(
        latest_satellite_change
        and any(
            _source_kind(row, satellite_dataset_ids) == "drone"
            and (analysis := _accepted_analysis(row)) is not None
            and (row.capture_date or row.processed_at or row.created_at)
            >= latest_satellite_change
            and _drone_verifies_satellite(
                analysis,
                satellite_dataset_ids=relevant_satellite_dataset_ids,
                satellite_candidate_ids=relevant_satellite_candidate_ids,
            )
            for row in datasets
        )
    )
    official_rows = [
        row
        for row in datasets
        if row.dataset_type == "ENVIRONMENTAL_REFERENCE"
        or str(row.provider_code or "").lower() == "miteco"
    ]
    availability = {
        "validated_analysis": bool(accepted_ids),
        "satellite": bool(satellite_scenes)
        or any(
            _source_kind(row, satellite_dataset_ids) == "satellite" for row in datasets
        ),
        "current_drone_verification": current_drone_verification,
        "weather": bool(weather_rows),
        "iot": bool(telemetry_rows),
        "official_environmental_context": bool(official_rows),
        "historical_comparison": historical_comparison,
        "paired_change": bool(paired_change_ids),
        "paired_surface": bool(paired_surface_ids),
        "reviewed_classification": bool(classification_ids),
        "supported_dataset_count": len(datasets),
        "validated_analysis_count": len(accepted_ids),
        "limitations": [
            message
            for condition, message in (
                (not accepted_ids, "No validated Environmental analysis is available."),
                (
                    not paired_change_ids,
                    "Vegetation and land-cover change are unknown without a compatible aligned pair.",
                ),
                (
                    not paired_surface_ids,
                    "Terrain-change indicators are unavailable without a validated surface pair.",
                ),
                (
                    not official_rows,
                    "No applicable official environmental reference layer is attached.",
                ),
            )
            if condition
        ],
    }

    latest_weather: dict[str, dict[str, Any]] = {}
    for row in weather_rows:
        if row.metric not in latest_weather:
            latest_weather[row.metric] = {
                "metric": row.metric,
                "value": row.value,
                "unit": row.unit,
                "quality": row.quality,
                "observed_at": row.observed_at,
                "dataset_id": row.dataset_id,
            }
    latest_telemetry: dict[str, dict[str, Any]] = {}
    for row in telemetry_rows:
        if row.channel not in latest_telemetry:
            latest_telemetry[row.channel] = {
                "channel": row.channel,
                "value": row.numeric_value,
                "unit": row.unit,
                "quality": row.quality,
                "recorded_at": row.recorded_at,
            }
    environmental_context = {
        "satellite": {
            "scene_count": len(satellite_scenes),
            "latest_acquired_at": satellite_scenes[0].acquired_at
            if satellite_scenes
            else None,
            "latest_cloud_cover_percent": (
                satellite_scenes[0].cloud_cover_percent if satellite_scenes else None
            ),
            "latest_resolution_meters": (
                satellite_scenes[0].resolution_meters if satellite_scenes else None
            ),
            "collections": sorted({row.collection for row in satellite_scenes}),
        },
        "weather": list(latest_weather.values()),
        "telemetry": list(latest_telemetry.values()),
        "official_layers": [
            {
                "dataset_id": row.id,
                "name": row.name,
                "captured_at": row.capture_date or row.created_at,
                "provenance": _public_provenance(row),
            }
            for row in official_rows
        ],
        "interpretation": (
            "Context supports review but does not establish causation, compliance, or impact."
        ),
    }
    evidence = {
        "analysis_schema": ANALYSIS_SCHEMA,
        "algorithm_bundle_version": ALGORITHM_VERSION,
        "dataset_ids": [row.id for row in datasets],
        "validated_analysis_dataset_ids": accepted_ids,
        "reviewed_classification_dataset_ids": sorted(classification_ids),
        "paired_change_dataset_ids": sorted(paired_change_ids),
        "paired_surface_dataset_ids": sorted(paired_surface_ids),
        "satellite_scene_ids": [row.id for row in satellite_scenes],
        "official_context_dataset_ids": [row.id for row in official_rows],
    }
    return EnvironmentalSourceContext(
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
            telemetry=tuple(latest_telemetry.values()),
            metadata={
                "measurement_details": details,
                "source_availability": availability,
                "evidence": evidence,
                "environmental_context": environmental_context,
                "findings": tuple(findings),
            },
        ),
        availability=availability,
        evidence=evidence,
        context=environmental_context,
    )


def evaluate_environmental(
    db: Session,
    *,
    asset: Asset,
    actor=None,
    as_of: datetime | None = None,
) -> EnvironmentalEvaluation:
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
    return EnvironmentalEvaluation(sources, result, actions)


def environmental_comparisons(
    db: Session,
    *,
    asset: Asset,
    enforce_feature: bool = True,
) -> list[dict[str, Any]]:
    _assert_environmental_asset(asset)
    if enforce_feature:
        _require_feature(db, asset)
    datasets = _eligible_datasets(db, asset=asset)
    specifications = (
        (
            "SATELLITE_2D",
            "Multi-date satellite comparison",
            "2D",
            "SWIPE_2D",
            ("SATELLITE_IMAGE", "NDVI", "LAND_COVER_CLASSIFICATION"),
        ),
        (
            "DRONE_2D",
            "Multi-date drone comparison",
            "2D",
            "SWIPE_2D",
            ("ORTHOMOSAIC", "MULTISPECTRAL_IMAGES", "RGB_IMAGES"),
        ),
        (
            "THERMAL_2D",
            "Multi-date thermal comparison",
            "2D",
            "THERMAL_COMPARE_2D",
            ("THERMAL_IMAGES",),
        ),
        (
            "TERRAIN_3D",
            "Multi-date terrain comparison",
            "3D",
            "SURFACE_COMPARE_3D",
            ("DSM", "DTM"),
        ),
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
            and (previous.capture_date or previous.created_at)
            < (current.capture_date or current.created_at)
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
                "limitation": (
                    None
                    if compatible
                    else "Coordinate reference systems or capture order are incompatible."
                    if pair
                    else "A compatible earlier dataset is required."
                ),
                "interpretation": (
                    "visual and contextual comparison only; no causal or impact conclusion"
                ),
            }
        )
    return result


_LAYER_MODES = {
    "DSM": ("2D", "MAP_RASTER"),
    "DTM": ("2D", "MAP_RASTER"),
    "ENVIRONMENTAL_REFERENCE": ("2D", "MAP_VECTOR"),
    "LAND_COVER_CLASSIFICATION": ("2D", "MAP_RASTER"),
    "MULTISPECTRAL_IMAGES": ("2D", "MAP_RASTER"),
    "NDVI": ("2D", "MAP_RASTER"),
    "ORTHOMOSAIC": ("2D", "MAP_RASTER"),
    "RGB_IMAGES": ("REFERENCE", "REFERENCE_ONLY"),
    "SATELLITE_IMAGE": ("2D", "MAP_RASTER"),
    "TELEMETRY": ("REFERENCE", "REFERENCE_ONLY"),
    "THERMAL_IMAGES": ("2D", "MAP_RASTER"),
    "WEATHER_DATA": ("REFERENCE", "REFERENCE_ONLY"),
}


def environmental_map_layers(db: Session, *, asset: Asset) -> list[dict[str, Any]]:
    _assert_environmental_asset(asset)
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
    for row in rows:
        dimension, render_mode = _LAYER_MODES[row.dataset_type]
        analysis = _accepted_analysis(row)
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
        provenance = {
            "dataset_type": row.dataset_type,
            "processing_level": row.processing_level,
            **_public_provenance(row),
        }
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
                "quality": row.quality_status,
                "crs": row.crs,
                "resolution": (
                    {"value": row.resolution, "unit": row.resolution_unit}
                    if row.resolution is not None
                    else None
                ),
                "provenance": provenance,
            }
        )
    for row in list_asset_observations(db, asset=asset, limit=500):
        geometry = (
            _safe_geometry(_object(row.geometry_geojson))
            if row.geometry_geojson
            else None
        )
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
                    "causation_assessed": False,
                    "specialist_review_required": row.validation_status != "VALIDATED",
                },
            }
        )
    return layers


def environmental_report_context(db: Session, *, asset: Asset) -> dict[str, Any]:
    """Return structured, provenance-bearing evidence for the common report engine."""

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
        "schema": "geovision.environmental.report-context.v1",
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
        "environmental_context": dict(sources.context),
        "kpis": asset_kpi_payloads(db, asset),
        "observations": [observation_payload(row) for row in observations],
        "open_actions": [action_payload(row) for row in actions],
        "comparisons": environmental_comparisons(db, asset=asset),
        "map_layers": environmental_map_layers(db, asset=asset),
        "limitations": [
            *sources.availability.get("limitations", []),
            "Mapped changes and thermal contrasts are candidates requiring authorized review.",
            "Weather, public GIS, satellite, and sensor data provide context, not causation.",
            "No ecological damage, fire, erosion cause, legal compliance, or remediation conclusion is generated.",
            "Official-source attribution and licence metadata must accompany reused public layers.",
        ],
    }


__all__ = [
    "ANALYSIS_SCHEMA",
    "EnvironmentalEvaluation",
    "build_source_context",
    "environmental_comparisons",
    "environmental_enabled_for_context",
    "environmental_map_layers",
    "environmental_report_context",
    "evaluate_environmental",
    "sync_kpi_definitions",
]
