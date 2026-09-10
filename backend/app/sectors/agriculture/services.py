"""Source fusion and application services for the Agriculture sector."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models import (
    Action,
    Asset,
    Dataset,
    IotDevice,
    SatelliteScene,
    TelemetryReading,
    WeatherObservation,
)
from app.modules.actions.services import (
    action_payload,
    materialize_evaluation_actions,
)
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
from app.sectors.agriculture.domain import (
    ALGORITHM_VERSION,
    AgricultureError,
    AgricultureSourceContext,
    KPI_DEFINITIONS,
    SECTOR,
    SUPPORTED_ASSET_TYPES,
    SUPPORTED_DATASET_TYPES,
)


ANALYSIS_SCHEMA = "geovision.agriculture.analysis.v1"
_IMAGERY_TYPES = {
    "RGB_IMAGES",
    "MULTISPECTRAL_IMAGES",
    "THERMAL_IMAGES",
    "ORTHOMOSAIC",
    "NDVI",
    "NDRE",
    "GNDVI",
}
_INDEX_KEYS = {"ndvi_mean", "ndre_mean", "gndvi_mean"}
_PERCENT_KEYS = {
    "crop_condition_percent",
    "water_stress",
    "soil_moisture",
    "vegetation_coverage",
}
_AREA_KEYS = {"area_needing_attention", "affected_area"}
_ALIASES = {
    "crop_condition": "crop_condition_percent",
    "crop_condition_pct": "crop_condition_percent",
    "crop_condition_percent": "crop_condition_percent",
    "mean_ndvi": "ndvi_mean",
    "average_ndvi": "ndvi_mean",
    "ndvi": "ndvi_mean",
    "ndvi_mean": "ndvi_mean",
    "mean_ndre": "ndre_mean",
    "ndre": "ndre_mean",
    "ndre_mean": "ndre_mean",
    "mean_gndvi": "gndvi_mean",
    "gndvi": "gndvi_mean",
    "gndvi_mean": "gndvi_mean",
    "water_stress_indicator": "water_stress",
    "water_stress_percent": "water_stress",
    "water_stress_pct": "water_stress",
    "water_stress": "water_stress",
    "soil_moisture_percent": "soil_moisture",
    "soil_moisture_pct": "soil_moisture",
    "soil_moisture": "soil_moisture",
    "attention_area_ha": "area_needing_attention",
    "area_needing_attention_ha": "area_needing_attention",
    "area_needing_attention": "area_needing_attention",
    "affected_hectares": "affected_area",
    "affected_area_ha": "affected_area",
    "affected_area": "affected_area",
    "vegetation_coverage_percent": "vegetation_coverage",
    "vegetation_coverage_pct": "vegetation_coverage",
    "vegetation_coverage": "vegetation_coverage",
    "rainfall_24h_mm": "rainfall_24h",
    "precipitation_24h": "rainfall_24h",
    "rainfall_24h": "rainfall_24h",
    "air_temperature_c": "air_temperature",
    "temperature_c": "air_temperature",
    "temperature": "air_temperature",
    "air_temperature": "air_temperature",
    "relative_humidity_percent": "relative_humidity",
    "relative_humidity_pct": "relative_humidity",
    "humidity": "relative_humidity",
    "relative_humidity": "relative_humidity",
}


@dataclass(frozen=True, slots=True)
class AgricultureEvaluation:
    sources: AgricultureSourceContext
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
        value = value.get("value", value.get("mean"))
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


def _valid_metric(key: str, value: float) -> bool:
    if key in _INDEX_KEYS:
        return -1 <= value <= 1
    if key in _PERCENT_KEYS:
        return 0 <= value <= 100
    if key in _AREA_KEYS or key == "rainfall_24h":
        return value >= 0
    if key == "air_temperature":
        return -90 <= value <= 70
    if key == "relative_humidity":
        return 0 <= value <= 100
    return True


def _dataset_confidence(row: Dataset, analysis: Mapping[str, Any]) -> float:
    quality = {
        "PASSED": 0.9,
        "WARNING": 0.65,
        "UNREVIEWED": 0.55,
        "FAILED": 0.0,
    }.get(str(row.quality_status or "").upper(), 0.5)
    declared = _number(analysis.get("confidence"))
    return max(0.0, min(1.0, min(quality, declared if declared is not None else quality)))


def _dataset_analysis(row: Dataset) -> Mapping[str, Any] | None:
    metadata = _object(row.metadata_json)
    candidate = metadata.get("agriculture_analysis", metadata)
    if not isinstance(candidate, Mapping) or candidate.get("schema") != ANALYSIS_SCHEMA:
        return None
    metrics = candidate.get("metrics")
    if not isinstance(metrics, Mapping):
        return None
    return candidate


def _source_kind(row: Dataset, satellite_dataset_ids: set[str]) -> str:
    if row.id in satellite_dataset_ids or row.dataset_type == "SATELLITE_IMAGE":
        return "satellite"
    if row.dataset_type == "WEATHER_DATA":
        return "weather"
    if row.dataset_type == "TELEMETRY":
        return "iot"
    return "drone" if row.dataset_type in _IMAGERY_TYPES else "other"


def _metric_detail(
    *,
    source: str,
    confidence: float,
    measured_at: datetime,
    dataset: Dataset | None = None,
    provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "source": source[:160],
        "confidence": confidence,
        "measured_at": measured_at,
        "dataset_id": dataset.id if dataset else None,
        "mission_id": dataset.mission_id if dataset else None,
        "provenance": dict(provenance or {}),
    }


def _assert_agriculture_asset(asset: Asset) -> None:
    if asset.sector != SECTOR:
        raise AgricultureError(
            "sector_mismatch", "Agriculture intelligence is available only for Agriculture assets"
        )
    if asset.asset_type not in SUPPORTED_ASSET_TYPES:
        raise AgricultureError(
            "asset_type_unsupported",
            f"Agriculture does not support asset type {asset.asset_type}",
        )


def sync_kpi_definitions(db: Session) -> None:
    for definition in KPI_DEFINITIONS:
        ensure_kpi_definition(db, definition)


def build_source_context(
    db: Session,
    *,
    asset: Asset,
    as_of: datetime | None = None,
) -> AgricultureSourceContext:
    """Load only canonical tenant-owned evidence and normalize safe numeric inputs."""

    _assert_agriculture_asset(asset)
    evaluated_at = _utc_naive(as_of or utc_now())
    datasets = (
        db.query(Dataset)
        .filter(
            Dataset.company_id == asset.organization_id,
            Dataset.asset_id == asset.id,
            Dataset.dataset_type.in_(tuple(SUPPORTED_DATASET_TYPES)),
            Dataset.status == "ready",
            or_(
                Dataset.capture_date <= evaluated_at,
                and_(
                    Dataset.capture_date.is_(None),
                    Dataset.created_at <= evaluated_at,
                ),
            ),
        )
        .order_by(Dataset.capture_date.desc(), Dataset.created_at.desc())
        .all()
    )
    satellite_scenes = (
        db.query(SatelliteScene)
        .filter(
            SatelliteScene.organization_id == asset.organization_id,
            SatelliteScene.asset_id == asset.id,
            SatelliteScene.acquired_at <= evaluated_at,
        )
        .order_by(SatelliteScene.acquired_at.desc())
        .all()
    )
    satellite_dataset_ids = {row.dataset_id for row in satellite_scenes}

    measurements: dict[str, float] = {}
    details: dict[str, dict[str, Any]] = {}
    metric_history: dict[str, list[tuple[datetime, float, dict[str, Any]]]] = {}
    attention_zone_geometry: Mapping[str, Any] | None = None
    source_counts = {"drone": 0, "satellite": 0, "iot": 0, "weather": 0}

    for dataset in datasets:
        source_kind = _source_kind(dataset, satellite_dataset_ids)
        if source_kind in source_counts:
            source_counts[source_kind] += 1
        analysis = _dataset_analysis(dataset)
        if analysis is None or str(dataset.quality_status).upper() == "FAILED":
            continue
        confidence = _dataset_confidence(dataset, analysis)
        measured_at = dataset.capture_date or dataset.processed_at or dataset.created_at
        metrics = analysis["metrics"]
        for raw_key, raw_value in metrics.items():
            key = _ALIASES.get(str(raw_key).strip().lower())
            value = _number(raw_value)
            if key is None or value is None or not _valid_metric(key, value):
                continue
            metric_confidence = confidence
            if isinstance(raw_value, Mapping):
                declared = _number(raw_value.get("confidence"))
                if declared is not None:
                    metric_confidence = min(metric_confidence, max(0.0, min(1.0, declared)))
            detail = _metric_detail(
                source=f"{source_kind}:{dataset.dataset_type.lower()}",
                confidence=metric_confidence,
                measured_at=measured_at,
                dataset=dataset,
                provenance={
                    "analysis_schema": ANALYSIS_SCHEMA,
                    "algorithm": analysis.get("algorithm"),
                    "algorithm_version": analysis.get("algorithm_version"),
                    "dataset_type": dataset.dataset_type,
                    "processing_level": dataset.processing_level,
                    "quality_status": dataset.quality_status,
                },
            )
            metric_history.setdefault(key, []).append((measured_at, value, detail))

        zones = analysis.get("zones", ())
        if isinstance(zones, Sequence) and not isinstance(zones, (str, bytes)):
            attention_total = 0.0
            zone_confidence = confidence
            for zone in zones:
                if not isinstance(zone, Mapping):
                    continue
                if str(zone.get("kind", "")).lower() not in {
                    "attention",
                    "crop_attention",
                    "water_stress",
                }:
                    continue
                area = _number(zone.get("area_ha"))
                if area is not None and area >= 0:
                    attention_total += area
                declared = _number(zone.get("confidence"))
                if declared is not None:
                    zone_confidence = min(zone_confidence, max(0.0, min(1.0, declared)))
                if attention_zone_geometry is None and isinstance(zone.get("geometry"), Mapping):
                    try:
                        attention_zone_geometry = normalize_geometry(zone["geometry"])
                    except ValueError:
                        pass
            if attention_total > 0:
                metric_history.setdefault("area_needing_attention", []).append(
                    (
                        measured_at,
                        attention_total,
                        _metric_detail(
                            source=f"{source_kind}:{dataset.dataset_type.lower()}",
                            confidence=zone_confidence,
                            measured_at=measured_at,
                            dataset=dataset,
                            provenance={
                                "analysis_schema": ANALYSIS_SCHEMA,
                                "derived_from": "validated_zone_areas",
                            },
                        ),
                    )
                )

    for key, history in metric_history.items():
        history.sort(key=lambda item: item[0], reverse=True)
        measurements[key] = history[0][1]
        details[key] = history[0][2]
    ndvi_history = metric_history.get("ndvi_mean", [])
    if len(ndvi_history) > 1:
        current_at, current, current_detail = ndvi_history[0]
        previous_at, previous, previous_detail = ndvi_history[1]
        measurements["ndvi_change"] = current - previous
        details["ndvi_change"] = {
            **current_detail,
            "confidence": min(
                float(current_detail["confidence"]),
                float(previous_detail["confidence"]),
            ),
            "measured_at": current_at,
            "provenance": {
                **dict(current_detail.get("provenance", {})),
                "previous_dataset_id": previous_detail.get("dataset_id"),
                "previous_measured_at": previous_at.isoformat(),
                "calculation": "current_ndvi_minus_previous_ndvi",
            },
        }

    telemetry = (
        db.query(TelemetryReading)
        .filter(
            TelemetryReading.company_id == asset.organization_id,
            TelemetryReading.core_asset_id == asset.id,
            TelemetryReading.numeric_value.isnot(None),
            TelemetryReading.recorded_at <= evaluated_at,
        )
        .order_by(TelemetryReading.recorded_at.desc())
        .limit(1000)
        .all()
    )
    selected_telemetry: list[str] = []
    for reading in telemetry:
        key = _ALIASES.get(str(reading.channel).strip().lower())
        value = _number(reading.numeric_value)
        if key not in {"soil_moisture", "rainfall_24h", "air_temperature", "relative_humidity"}:
            continue
        if value is None or not _valid_metric(key, value) or key in details:
            continue
        confidence = 0.85 if str(reading.quality).lower() == "good" else 0.55
        measurements[key] = value
        details[key] = _metric_detail(
            source="iot:telemetry",
            confidence=confidence,
            measured_at=reading.recorded_at,
            provenance={
                "telemetry_reading_id": reading.id,
                "device_id": reading.device_id,
                "channel": reading.channel,
                "quality": reading.quality,
                "unit": reading.unit,
            },
        )
        selected_telemetry.append(reading.id)
    if selected_telemetry:
        source_counts["iot"] = len(selected_telemetry)

    weather = (
        db.query(WeatherObservation)
        .filter(
            WeatherObservation.organization_id == asset.organization_id,
            WeatherObservation.asset_id == asset.id,
            WeatherObservation.observed_at <= evaluated_at,
        )
        .order_by(WeatherObservation.observed_at.desc())
        .limit(1000)
        .all()
    )
    selected_weather: list[str] = []
    for reading in weather:
        key = _ALIASES.get(str(reading.metric).strip().lower())
        value = _number(reading.value)
        if key not in {"rainfall_24h", "air_temperature", "relative_humidity"}:
            continue
        if value is None or not _valid_metric(key, value) or key in details:
            continue
        confidence = 0.85 if str(reading.quality).lower() == "observed" else 0.6
        measurements[key] = value
        dataset = next((item for item in datasets if item.id == reading.dataset_id), None)
        details[key] = _metric_detail(
            source=f"weather:{reading.provider_code}",
            confidence=confidence,
            measured_at=reading.observed_at,
            dataset=dataset,
            provenance={
                "weather_observation_id": reading.id,
                "provider": reading.provider_code,
                "source_reference": reading.source_reference,
                "quality": reading.quality,
                "distance_km": reading.distance_km,
            },
        )
        selected_weather.append(reading.id)
    if selected_weather:
        source_counts["weather"] = len(selected_weather)

    availability = {
        "drone": source_counts["drone"] > 0,
        "satellite": bool(satellite_scenes) or source_counts["satellite"] > 0,
        "iot": source_counts["iot"] > 0,
        "weather": source_counts["weather"] > 0,
        "multispectral": any(row.dataset_type == "MULTISPECTRAL_IMAGES" for row in datasets),
        "orthomosaic": any(row.dataset_type == "ORTHOMOSAIC" for row in datasets),
        "thermal": any(row.dataset_type == "THERMAL_IMAGES" for row in datasets),
        "analysis_dataset_count": sum(
            _dataset_analysis(row) is not None for row in datasets
        ),
        "source_counts": source_counts,
        "limitations": [
            message
            for condition, message in (
                (
                    not metric_history,
                    "No validated agriculture-analysis dataset is available.",
                ),
                (
                    not selected_telemetry,
                    "No current canonical IoT measurement is available.",
                ),
                (
                    not selected_weather,
                    "No normalized weather observation is available.",
                ),
            )
            if condition
        ],
    }
    evidence = {
        "analysis_schema": ANALYSIS_SCHEMA,
        "algorithm_bundle_version": ALGORITHM_VERSION,
        "dataset_ids": [row.id for row in datasets],
        "satellite_scene_ids": [row.id for row in satellite_scenes],
        "telemetry_reading_ids": selected_telemetry,
        "weather_observation_ids": selected_weather,
    }
    return AgricultureSourceContext(
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
            telemetry=tuple(
                {
                    "id": row.id,
                    "channel": row.channel,
                    "recorded_at": row.recorded_at,
                    "quality": row.quality,
                }
                for row in telemetry
                if row.id in selected_telemetry
            ),
            metadata={
                "measurement_details": details,
                "source_availability": availability,
                "attention_zone_geometry": attention_zone_geometry,
                "evidence": evidence,
            },
        ),
        availability=availability,
        evidence=evidence,
    )


def evaluate_agriculture(
    db: Session,
    *,
    asset: Asset,
    actor=None,
    as_of: datetime | None = None,
) -> AgricultureEvaluation:
    sync_kpi_definitions(db)
    sources = build_source_context(db, asset=asset, as_of=as_of)
    result = evaluate_asset(db, asset=asset, context=sources.evaluation)
    actions = materialize_evaluation_actions(
        db,
        asset=asset,
        evaluation=result,
        actor=actor,
    )
    db.flush()
    return AgricultureEvaluation(sources, result, actions)


def agriculture_map_layers(db: Session, *, asset: Asset) -> list[dict[str, Any]]:
    _assert_agriculture_asset(asset)
    layers: list[dict[str, Any]] = []
    geometry = None
    try:
        geometry = normalize_geometry(asset.geometry_geojson)
    except ValueError:
        pass
    layers.append(
        {
            "id": f"asset:{asset.id}",
            "kind": "ASSET_BOUNDARY",
            "title": asset.name,
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
    )
    datasets = (
        db.query(Dataset)
        .filter(
            Dataset.company_id == asset.organization_id,
            Dataset.asset_id == asset.id,
            Dataset.dataset_type.in_(tuple(SUPPORTED_DATASET_TYPES)),
        )
        .order_by(Dataset.capture_date.desc(), Dataset.created_at.desc())
        .all()
    )
    renderable = {
        "ORTHOMOSAIC",
        "NDVI",
        "NDRE",
        "GNDVI",
        "THERMAL_IMAGES",
        "SATELLITE_IMAGE",
    }
    for row in datasets:
        availability = (
            "NO_DATA"
            if row.status not in {"ready", "processing"}
            else "NOT_RENDERABLE"
            if row.dataset_type not in renderable
            else "AVAILABLE"
        )
        layers.append(
            {
                "id": f"dataset:{row.id}",
                "kind": row.dataset_type,
                "title": row.name,
                "availability": availability,
                "geometry": None,
                "data_ref": f"/datasets/{row.id}",
                "dataset_id": row.id,
                "observation_id": None,
                "captured_at": row.capture_date or row.created_at,
                "confidence": _dataset_confidence(row, _dataset_analysis(row) or {}),
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
                    "provider": row.provider_code,
                },
            }
        )
    observations = list_asset_observations(db, asset=asset, limit=500)
    for row in observations:
        geometry = _object(row.geometry_geojson) if row.geometry_geojson else None
        if not geometry:
            continue
        layers.append(
            {
                "id": f"observation:{row.id}",
                "kind": "OBSERVATION_ZONE",
                "title": row.observation_type.replace("_", " ").title(),
                "availability": (
                    "AVAILABLE" if row.validation_status != "REJECTED" else "NO_DATA"
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
                },
            }
        )
    devices = (
        db.query(IotDevice)
        .filter(
            IotDevice.company_id == asset.organization_id,
            IotDevice.core_asset_id == asset.id,
        )
        .all()
    )
    for row in devices:
        point = None
        if row.last_latitude is not None and row.last_longitude is not None:
            try:
                point = normalize_geometry(
                    {
                        "type": "Point",
                        "coordinates": [row.last_longitude, row.last_latitude],
                    }
                )
            except ValueError:
                pass
        layers.append(
            {
                "id": f"device:{row.id}",
                "kind": "SENSOR_POINT",
                "title": row.name,
                "availability": "AVAILABLE" if point else "NO_DATA",
                "geometry": point,
                "data_ref": f"/iot/devices/{row.id}",
                "dataset_id": None,
                "observation_id": None,
                "captured_at": row.last_seen_at,
                "confidence": None,
                "quality": row.health_status,
                "crs": "EPSG:4326" if point else None,
                "resolution": None,
                "provenance": {"provider": row.provider_code, "device_id": row.id},
            }
        )
    return layers


def agriculture_report_context(db: Session, *, asset: Asset) -> dict[str, Any]:
    """Return structured evidence only; Phase 19 owns narrative generation."""

    sources = build_source_context(db, asset=asset)
    kpis = asset_kpi_payloads(db, asset)
    observations = list_asset_observations(db, asset=asset, limit=500)
    actions = (
        db.query(Action)
        .filter(
            Action.organization_id == asset.organization_id,
            Action.asset_id == asset.id,
            Action.status.in_(("OPEN", "IN_PROGRESS")),
        )
        .order_by(Action.due_date, Action.created_at.desc())
        .limit(500)
        .all()
    )
    return {
        "schema": "geovision.agriculture.report-context.v1",
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
        "kpis": kpis,
        "observations": [observation_payload(row) for row in observations],
        "open_actions": [action_payload(row) for row in actions],
        "map_layers": agriculture_map_layers(db, asset=asset),
        "limitations": [
            *sources.availability.get("limitations", []),
            "Indicators require crop-, season-, soil-, and sensor-specific validation.",
            "No chemical, pest, disease, nutrient, or yield diagnosis is generated.",
        ],
    }


__all__ = [
    "ANALYSIS_SCHEMA",
    "AgricultureEvaluation",
    "agriculture_map_layers",
    "agriculture_report_context",
    "build_source_context",
    "evaluate_agriculture",
    "sync_kpi_definitions",
]
