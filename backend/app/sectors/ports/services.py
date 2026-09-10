"""Asset-centric inspection intelligence for Ports and Industrial workspaces."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
    DeviceAssignment,
    IotAlert,
    IotDevice,
    TelemetryReading,
    TelemetryReceipt,
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
from app.sectors.ports.domain import (
    ALGORITHM_VERSION,
    KPI_DEFINITIONS,
    SECTOR,
    SUPPORTED_ASSET_TYPES,
    SUPPORTED_DATASET_TYPES,
    PortsError,
    PortsSourceContext,
)


ANALYSIS_SCHEMA = "geovision.ports.analysis.v1"
_MODULE_KEYS = frozenset({"ports", "industrial", "industry", "ports_industrial"})
_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,159}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,39}$")
_PARENT_TYPES = frozenset({"PORT", "TERMINAL"})
_INSPECTION_TYPES = frozenset(
    {
        "DSM",
        "DTM",
        "MESH_3D",
        "ORTHOMOSAIC",
        "POINT_CLOUD",
        "RGB_IMAGES",
        "THERMAL_IMAGES",
    }
)
_CONTEXT_TYPES = frozenset({"AIS_DATA", "WEATHER_DATA"})
_VISUAL_TYPES = frozenset({"ORTHOMOSAIC", "RGB_IMAGES"})
_SURFACE_TYPES = frozenset({"DSM", "DTM", "MESH_3D", "POINT_CLOUD"})
_MODALITY_BY_TYPE = {
    "DSM": "SURFACE_3D",
    "DTM": "SURFACE_3D",
    "MESH_3D": "SURFACE_3D",
    "ORTHOMOSAIC": "ORTHOMOSAIC",
    "POINT_CLOUD": "SURFACE_3D",
    "RGB_IMAGES": "RGB",
    "THERMAL_IMAGES": "THERMAL",
}
_CONDITION_CODES = frozenset(
    {
        "MONITOR",
        "NO_MATERIAL_CHANGE_REPORTED",
        "REVIEW_REQUIRED",
        "SPECIALIST_FOLLOW_UP_REQUIRED",
    }
)
_ENVIRONMENTAL_CHANNELS = frozenset(
    {
        "air_quality",
        "ambient_temperature",
        "humidity",
        "rainfall",
        "water_level",
        "wave_height",
        "wind_speed",
    }
)
_OPERATIONAL_CHANNELS = frozenset(
    {
        "current",
        "load",
        "power",
        "pressure",
        "tank_level",
        "temperature",
        "vibration",
    }
)
_PUBLIC_PROVENANCE_KEYS = frozenset(
    {
        "acquisition_method",
        "adapter_version",
        "attribution",
        "dataset_updated_at",
        "fetched_at",
        "license_id",
        "license_url",
        "processor",
        "processor_version",
        "source_name",
        "source_reference",
        "terms_reference",
    }
)


@dataclass(frozen=True, slots=True)
class PortsEvaluation:
    sources: PortsSourceContext
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
    parsed = _number(value)
    if parsed is None or parsed < 0 or not parsed.is_integer():
        return None
    return int(parsed)


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _utc_naive(value)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return _utc_naive(parsed)


def _json_list(value: str | None) -> list[str]:
    return [str(item).strip() for item in _array(value) if str(item).strip()]


def _workspace_enabled(workspace: Account | None) -> bool:
    if workspace is None or workspace.status != "active":
        return False
    modules = {item.casefold() for item in _json_list(workspace.modules_enabled)}
    return bool(modules & _MODULE_KEYS)


def ports_enabled_for_context(
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


def _assert_ports_asset(asset: Asset) -> None:
    if asset.sector != SECTOR:
        raise PortsError(
            "sector_mismatch",
            "Ports intelligence is available only for Ports/Industrial assets",
        )
    if asset.asset_type not in SUPPORTED_ASSET_TYPES:
        raise PortsError(
            "asset_type_unsupported",
            f"Ports intelligence does not support asset type {asset.asset_type}",
        )


def _require_feature(db: Session, asset: Asset) -> Account:
    workspace = db.get(Account, asset.workspace_id) if asset.workspace_id else None
    if (
        workspace is None
        or workspace.organization_id != asset.organization_id
        or not _workspace_enabled(workspace)
    ):
        raise PortsError(
            "feature_disabled", "Ports/Industrial is not enabled for this workspace"
        )
    return workspace


def sync_kpi_definitions(db: Session) -> None:
    for definition in KPI_DEFINITIONS:
        ensure_kpi_definition(db, definition)


def _accepted_analysis(row: Dataset) -> Mapping[str, Any] | None:
    if row.status != "ready" or row.quality_status != "PASSED":
        return None
    metadata = _object(row.metadata_json)
    analysis = metadata.get("ports_analysis")
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


def _inspection_evidence(
    row: Dataset,
    analysis: Mapping[str, Any] | None,
) -> dict[str, str] | None:
    if row.dataset_type not in _INSPECTION_TYPES or analysis is None:
        return None
    value = analysis.get("inspection_evidence")
    if not isinstance(value, Mapping):
        return None
    expected_modality = _MODALITY_BY_TYPE[row.dataset_type]
    declared_modality = str(value.get("modality", "")).strip().upper()
    capture_mode = str(value.get("capture_mode", declared_modality)).strip().upper()
    allowed_capture_modes = (
        {"RGB", "ZOOM_RGB"} if row.dataset_type == "RGB_IMAGES" else {expected_modality}
    )
    crs = str(value.get("crs", "")).strip().upper()
    row_crs = str(row.crs or "").strip().upper()
    method = str(value.get("method", "")).strip()
    method_version = str(value.get("method_version", "")).strip()
    registration_method = str(value.get("registration_method", "")).strip()
    registration_version = str(value.get("registration_version", "")).strip()
    reference = str(value.get("inspection_reference", "")).strip()
    registration_reference = str(value.get("registration_reference", "")).strip()
    if not (
        value.get("reviewed") is True
        and str(value.get("asset_id", "")).strip() == row.asset_id
        and reference
        and declared_modality == expected_modality
        and capture_mode in allowed_capture_modes
        and crs
        and row_crs
        and crs == row_crs
        and registration_reference
        and _IDENTIFIER.fullmatch(method)
        and _VERSION.fullmatch(method_version)
        and _IDENTIFIER.fullmatch(registration_method)
        and _VERSION.fullmatch(registration_version)
    ):
        return None
    return {
        "inspection_reference": reference,
        "modality": declared_modality,
        "capture_mode": capture_mode,
        "crs": crs,
        "method": method,
        "method_version": method_version,
        "registration_reference": registration_reference,
        "registration_method": registration_method,
        "registration_version": registration_version,
    }


def _thermal_evidence(analysis: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if analysis is None:
        return None
    value = analysis.get("thermal_evidence")
    if not isinstance(value, Mapping):
        return None
    emissivity = _number(value.get("emissivity"))
    method = str(value.get("method", "")).strip()
    version = str(value.get("method_version", "")).strip()
    if not (
        value.get("reviewed") is True
        and value.get("calibrated") is True
        and str(value.get("calibration_reference", "")).strip()
        and str(value.get("environmental_conditions_reference", "")).strip()
        and str(value.get("temperature_unit", "")).strip().upper() in {"C", "CELSIUS"}
        and emissivity is not None
        and 0 < emissivity <= 1
        and _IDENTIFIER.fullmatch(method)
        and _VERSION.fullmatch(version)
    ):
        return None
    return {
        "calibration_reference": str(value["calibration_reference"]),
        "environmental_conditions_reference": str(
            value["environmental_conditions_reference"]
        ),
        "emissivity": emissivity,
        "method": method,
        "method_version": version,
    }


def _specialist_condition(
    row: Dataset,
    analysis: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if analysis is None or _inspection_evidence(row, analysis) is None:
        return None
    value = analysis.get("specialist_condition_evidence")
    if not isinstance(value, Mapping):
        return None
    summary = str(value.get("summary_code", "")).strip().upper()
    method = str(value.get("method", "")).strip()
    version = str(value.get("method_version", "")).strip()
    if not (
        value.get("specialist_validated") is True
        and str(value.get("review_authority", "")).strip().upper()
        == "AUTHORIZED_SPECIALIST"
        and str(value.get("review_reference", "")).strip()
        and summary in _CONDITION_CODES
        and _IDENTIFIER.fullmatch(method)
        and _VERSION.fullmatch(version)
    ):
        return None
    return {
        "summary_code": summary,
        "review_reference": str(value["review_reference"]),
        "method": method,
        "method_version": version,
    }


def _compatible_pair(
    row: Dataset,
    analysis: Mapping[str, Any],
    datasets: Mapping[str, Dataset],
) -> Dataset | None:
    value = analysis.get("comparison_evidence")
    if not isinstance(value, Mapping):
        return None
    current_id = str(value.get("current_dataset_id", "")).strip()
    previous_id = str(value.get("previous_dataset_id", "")).strip()
    previous = datasets.get(previous_id)
    if (
        current_id != row.id
        or previous is None
        or previous.id == row.id
        or previous.company_id != row.company_id
        or previous.workspace_id != row.workspace_id
        or previous.asset_id != row.asset_id
        or previous.dataset_type not in _INSPECTION_TYPES
    ):
        return None
    previous_analysis = _accepted_analysis(previous)
    current_evidence = _inspection_evidence(row, analysis)
    previous_evidence = _inspection_evidence(previous, previous_analysis)
    if current_evidence is None or previous_evidence is None:
        return None
    same_type = previous.dataset_type == row.dataset_type
    visual_compatible = bool(
        not same_type
        and {previous.dataset_type, row.dataset_type}.issubset(_VISUAL_TYPES)
        and value.get("modality_compatibility_reviewed") is True
        and str(value.get("modality_family", "")).strip().upper()
        == "REGISTERED_VISUAL_2D"
    )
    surface_compatible = bool(
        not same_type
        and {previous.dataset_type, row.dataset_type}.issubset(_SURFACE_TYPES)
        and value.get("modality_compatibility_reviewed") is True
        and str(value.get("modality_family", "")).strip().upper()
        == "REGISTERED_SURFACE_3D"
    )
    if not same_type and not visual_compatible and not surface_compatible:
        return None
    current_at = row.capture_date or row.processed_at or row.created_at
    previous_at = previous.capture_date or previous.processed_at or previous.created_at
    crs = str(row.crs or "").strip().upper()
    previous_crs = str(previous.crs or "").strip().upper()
    method = str(value.get("method", "")).strip()
    version = str(value.get("method_version", "")).strip()
    if not (
        previous_at < current_at
        and value.get("reviewed") is True
        and value.get("aligned") is True
        and crs
        and crs == previous_crs
        and str(value.get("crs", "")).strip().upper() == crs
        and str(value.get("registration_reference", "")).strip()
        == current_evidence["registration_reference"]
        == previous_evidence["registration_reference"]
        and str(value.get("current_inspection_reference", "")).strip()
        == current_evidence["inspection_reference"]
        and str(value.get("previous_inspection_reference", "")).strip()
        == previous_evidence["inspection_reference"]
        and current_evidence["registration_method"]
        == previous_evidence["registration_method"]
        and current_evidence["registration_version"]
        == previous_evidence["registration_version"]
        and _IDENTIFIER.fullmatch(method)
        and _VERSION.fullmatch(version)
    ):
        return None
    return previous


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


def _inventory(
    row: Dataset,
    analysis: Mapping[str, Any],
    *,
    kind: str,
    pair_valid: bool,
) -> tuple[list[dict[str, Any]], bool]:
    value = analysis.get("candidate_inventory")
    expected_modality = "THERMAL" if kind == "thermal" else "VISUAL"
    if not isinstance(value, Mapping):
        return [], False
    if not (
        value.get("reviewed") is True
        and value.get("complete_for_dataset") is True
        and str(value.get("asset_id", "")).strip() == row.asset_id
        and str(value.get("modality", "")).strip().upper() == expected_modality
        and str(value.get("inventory_reference", "")).strip()
        and _IDENTIFIER.fullmatch(str(value.get("method", "")).strip())
        and _VERSION.fullmatch(str(value.get("method_version", "")).strip())
    ):
        return [], False
    if kind == "thermal" and _thermal_evidence(analysis) is None:
        return [], False
    candidates = value.get("candidates")
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        return [], False
    baseline = value.get("inventory_scope") == "BASELINE"
    # A candidate may be labelled new only against a validated, registered pair.
    publish_new = pair_valid and not baseline
    if not publish_new:
        return [], False
    result: list[dict[str, Any]] = []
    measured_at = row.capture_date or row.processed_at or row.created_at
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            continue
        if candidate.get("new") is not True or not publish_new:
            continue
        declared_confidence = _number(candidate.get("confidence"))
        confidence = min(
            _confidence(analysis),
            max(
                0.0,
                min(
                    1.0, declared_confidence if declared_confidence is not None else 0.5
                ),
            ),
        )
        result.append(
            {
                "key": _finding_key(
                    candidate.get("candidate_reference"), f"{kind}-{index + 1}"
                ),
                "kind": kind,
                "label": str(
                    candidate.get("label") or f"{kind.title()} review candidate"
                )[:200],
                "severity": str(candidate.get("severity") or "WATCH").upper(),
                "confidence": confidence,
                "geometry": _safe_geometry(candidate.get("geometry")),
                "source": f"validated:ports:{row.dataset_type.lower()}",
                "detected_at": measured_at,
                "dataset_id": row.id,
                "mission_id": row.mission_id,
                "provenance": {
                    "analysis_schema": ANALYSIS_SCHEMA,
                    "algorithm": analysis["algorithm"],
                    "algorithm_version": analysis["algorithm_version"],
                    "inventory_reference": value["inventory_reference"],
                    "comparison_required": True,
                    "interpretation": "candidate only; cause and condition not assessed",
                },
            }
        )
    return result, True


def _context_alerts(
    row: Dataset,
    analysis: Mapping[str, Any],
    *,
    evaluated_at: datetime,
) -> tuple[str, list[dict[str, Any]]] | None:
    if row.dataset_type not in _CONTEXT_TYPES:
        return None
    evidence = analysis.get("context_evidence")
    if not isinstance(evidence, Mapping):
        return None
    category = "environmental" if row.dataset_type == "WEATHER_DATA" else "operational"
    allowed_sources = (
        {"CUSTOMER_ENVIRONMENTAL_FEED", "OFFICIAL_ENVIRONMENTAL_FEED"}
        if category == "environmental"
        else {"CUSTOMER_OPERATIONAL_FEED", "OFFICIAL_MARITIME_FEED"}
    )
    retrieved_at = _parse_datetime(evidence.get("retrieved_at"))
    if not (
        evidence.get("reviewed") is True
        and str(evidence.get("source_kind", "")).strip().upper() in allowed_sources
        and str(evidence.get("source_reference", "")).strip()
        and str(evidence.get("terms_reference", "")).strip()
        and retrieved_at is not None
        and retrieved_at <= evaluated_at
        and _IDENTIFIER.fullmatch(str(evidence.get("method", "")).strip())
        and _VERSION.fullmatch(str(evidence.get("method_version", "")).strip())
    ):
        return None
    values = analysis.get("context_alerts")
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return None
    result: list[dict[str, Any]] = []
    for index, item in enumerate(values):
        if not isinstance(item, Mapping):
            continue
        event_at = _parse_datetime(item.get("event_at"))
        if (
            str(item.get("category", "")).strip().lower() != category
            or str(item.get("status", "")).strip().upper() != "ACTIVE"
            or event_at is None
            or event_at > evaluated_at
        ):
            continue
        result.append(
            {
                "key": _finding_key(
                    item.get("alert_reference"), f"{category}-{index + 1}"
                ),
                "kind": f"{category}_alert",
                "label": str(item.get("label") or f"Sourced {category} alert")[:200],
                "severity": str(item.get("severity") or "WATCH").upper(),
                "confidence": _confidence(analysis),
                "geometry": _safe_geometry(item.get("geometry")),
                "source": f"validated:ports:{row.dataset_type.lower()}",
                "detected_at": event_at,
                "dataset_id": row.id,
                "mission_id": row.mission_id,
                "provenance": {
                    "analysis_schema": ANALYSIS_SCHEMA,
                    "source_kind": evidence["source_kind"],
                    "source_reference": evidence["source_reference"],
                    "terms_reference": evidence["terms_reference"],
                    "context_only": True,
                },
            }
        )
    return category, result


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
        )
        .order_by(
            Dataset.capture_date.desc(), Dataset.created_at.desc(), Dataset.id.desc()
        )
        .all()
    )
    if as_of is None:
        return rows
    return [row for row in rows if (row.capture_date or row.created_at) <= as_of]


def _asset_scope(db: Session, *, asset: Asset) -> list[Asset]:
    """Return one tenant-bounded canonical subtree, capped against corrupt cycles."""

    result = [asset]
    if asset.asset_type not in _PARENT_TYPES:
        return result
    seen = {asset.id}
    frontier = [asset.id]
    while frontier and len(result) < 500:
        children = (
            db.query(Asset)
            .filter(
                Asset.organization_id == asset.organization_id,
                Asset.workspace_id == asset.workspace_id,
                Asset.parent_asset_id.in_(frontier),
            )
            .order_by(Asset.created_at, Asset.id)
            .limit(500 - len(result))
            .all()
        )
        frontier = []
        for child in children:
            if child.id in seen:
                continue
            seen.add(child.id)
            result.append(child)
            frontier.append(child.id)
    return result


def _valid_reading(
    row: TelemetryReading,
    receipts: Mapping[str, TelemetryReceipt],
) -> bool:
    if row.quality.lower() != "good":
        return False
    metadata = _object(row.metadata_json)
    if metadata.get("offline_replay") is True or metadata.get("duplicate") is True:
        return False
    if row.source and row.source.lower() in {"offline", "offline_replay", "duplicate"}:
        return False
    if row.receipt_id:
        receipt = receipts.get(row.receipt_id)
        if receipt is None or receipt.out_of_order or receipt.replayed_from_edge:
            return False
    return True


def _sensor_context(
    db: Session,
    *,
    asset: Asset,
    evaluated_at: datetime,
) -> dict[str, Any]:
    scoped_assets = _asset_scope(db, asset=asset)
    scoped_ids = {row.id for row in scoped_assets}
    assignments = (
        db.query(DeviceAssignment)
        .filter(
            DeviceAssignment.company_id == asset.organization_id,
            DeviceAssignment.asset_id.in_(tuple(scoped_ids)),
            DeviceAssignment.status == "active",
            DeviceAssignment.ended_at.is_(None),
            DeviceAssignment.assigned_at <= evaluated_at,
        )
        .order_by(DeviceAssignment.assigned_at.desc(), DeviceAssignment.id.desc())
        .all()
    )
    assignments_by_device: dict[str, DeviceAssignment] = {}
    for assignment in assignments:
        assignments_by_device.setdefault(assignment.device_id, assignment)
    devices = (
        db.query(IotDevice)
        .filter(
            IotDevice.id.in_(tuple(assignments_by_device)),
            IotDevice.company_id == asset.organization_id,
        )
        .all()
        if assignments_by_device
        else []
    )
    eligible_devices: dict[str, IotDevice] = {}
    for device in devices:
        assignment = assignments_by_device[device.id]
        assigned_asset = next(
            (item for item in scoped_assets if item.id == assignment.asset_id), None
        )
        if (
            assigned_asset is not None
            and assigned_asset.organization_id == asset.organization_id
            and assigned_asset.workspace_id == asset.workspace_id
            and device.core_asset_id == assignment.asset_id
            and device.status not in {"disabled", "quarantined"}
        ):
            eligible_devices[device.id] = device

    historical_rows = (
        db.query(TelemetryReading)
        .filter(
            TelemetryReading.company_id == asset.organization_id,
            TelemetryReading.core_asset_id.in_(tuple(scoped_ids)),
            TelemetryReading.recorded_at <= evaluated_at,
        )
        .order_by(TelemetryReading.recorded_at.desc(), TelemetryReading.id.desc())
        .limit(1000)
        .all()
    )
    receipt_ids = {row.receipt_id for row in historical_rows if row.receipt_id}
    receipts = {
        row.id: row
        for row in (
            db.query(TelemetryReceipt)
            .filter(
                TelemetryReceipt.id.in_(tuple(receipt_ids)),
                TelemetryReceipt.company_id == asset.organization_id,
                TelemetryReceipt.core_asset_id.in_(tuple(scoped_ids)),
            )
            .all()
            if receipt_ids
            else []
        )
    }
    valid_historical = [row for row in historical_rows if _valid_reading(row, receipts)]
    latest_by_device: dict[str, TelemetryReading] = {}
    categories: set[str] = set()
    for row in valid_historical:
        assignment = assignments_by_device.get(row.device_id)
        device = eligible_devices.get(row.device_id)
        if (
            assignment is None
            or device is None
            or device.connectivity_status != "online"
            or row.core_asset_id != assignment.asset_id
            or row.recorded_at < assignment.assigned_at
        ):
            continue
        latest_by_device.setdefault(row.device_id, row)
        channel = row.channel.strip().lower()
        if channel in _ENVIRONMENTAL_CHANNELS:
            categories.add("environmental")
        if channel in _OPERATIONAL_CHANNELS:
            categories.add("operational")

    online_ids = {
        device_id
        for device_id, device in eligible_devices.items()
        if device.connectivity_status == "online"
    }
    coverage_complete = bool(eligible_devices) and online_ids == set(eligible_devices)
    coverage_complete = coverage_complete and set(latest_by_device) == set(
        eligible_devices
    )
    freshness_minutes = None
    if coverage_complete:
        freshness_minutes = max(
            max(0.0, (evaluated_at - row.recorded_at).total_seconds() / 60)
            for row in latest_by_device.values()
        )

    active_alerts: list[IotAlert] = []
    if eligible_devices:
        active_alerts = (
            db.query(IotAlert)
            .filter(
                IotAlert.company_id == asset.organization_id,
                IotAlert.device_id.in_(tuple(eligible_devices)),
                IotAlert.status.in_(("open", "acknowledged")),
                IotAlert.opened_at <= evaluated_at,
            )
            .order_by(IotAlert.opened_at.desc(), IotAlert.id.desc())
            .limit(500)
            .all()
        )
        active_alerts = [
            row
            for row in active_alerts
            if row.opened_at >= assignments_by_device[row.device_id].assigned_at
            and eligible_devices[row.device_id].connectivity_status == "online"
        ]
    alert_counts = {
        "environmental": sum(
            1
            for row in active_alerts
            if row.channel.strip().lower() in _ENVIRONMENTAL_CHANNELS
        ),
        "operational": sum(
            1
            for row in active_alerts
            if row.channel.strip().lower() in _OPERATIONAL_CHANNELS
        ),
    }
    status = (
        "NOT_CONFIGURED"
        if not eligible_devices
        else "AVAILABLE"
        if coverage_complete
        else "UNKNOWN"
    )
    alert_findings: list[dict[str, Any]] = []
    if coverage_complete:
        for row in active_alerts:
            channel = row.channel.strip().lower()
            category = (
                "environmental"
                if channel in _ENVIRONMENTAL_CHANNELS
                else "operational"
                if channel in _OPERATIONAL_CHANNELS
                else None
            )
            if category is None or category not in categories:
                continue
            alert_findings.append(
                {
                    "key": _finding_key(row.id, f"{category}-sensor-alert"),
                    "kind": f"{category}_alert",
                    "label": f"Assigned sensor {category} alert",
                    "severity": str(row.severity or "WATCH").upper(),
                    "confidence": 1.0,
                    "geometry": None,
                    "source": "ports.iot_alert",
                    "detected_at": row.opened_at.isoformat(),
                    "dataset_id": None,
                    "mission_id": None,
                    "provenance": {
                        "alert_id": row.id,
                        "assignment_id": assignments_by_device[row.device_id].id,
                        "asset_id": assignments_by_device[row.device_id].asset_id,
                        "channel": channel,
                        "context_only": True,
                    },
                }
            )
    return {
        "status": status,
        "assignment_count": len(eligible_devices),
        "online_count": len(online_ids),
        "offline_or_unknown_count": len(eligible_devices) - len(online_ids),
        "freshness_minutes": freshness_minutes,
        "available_alert_categories": sorted(categories) if coverage_complete else [],
        "alert_counts": alert_counts,
        "alert_findings": alert_findings,
        "historical_reading_count": len(valid_historical),
        "latest_historical_reading_at": (
            valid_historical[0].recorded_at.isoformat() if valid_historical else None
        ),
        "devices": [
            {
                "device_id": device_id,
                "asset_id": assignments_by_device[device_id].asset_id,
                "connectivity": device.connectivity_status,
                "last_valid_reading_at": (
                    latest_by_device[device_id].recorded_at.isoformat()
                    if device_id in latest_by_device
                    else None
                ),
            }
            for device_id, device in sorted(eligible_devices.items())
        ],
    }


def _detail(
    row: Dataset,
    analysis: Mapping[str, Any],
    *,
    gate: str,
) -> dict[str, Any]:
    return {
        "source": f"validated:ports:{row.dataset_type.lower()}",
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


def _cadence(asset: Asset) -> int | None:
    value = _integer(_object(asset.metadata_json).get("inspection_cadence_days"))
    return value if value is not None and 1 <= value <= 3650 else None


def build_source_context(
    db: Session,
    *,
    asset: Asset,
    as_of: datetime | None = None,
) -> PortsSourceContext:
    """Load only reviewed exact-asset evidence and current bounded sensor context."""

    _assert_ports_asset(asset)
    _require_feature(db, asset)
    evaluated_at = _utc_naive(as_of or utc_now())
    datasets = _eligible_datasets(db, asset=asset, as_of=evaluated_at)
    datasets_by_id = {row.id: row for row in datasets}
    accepted_ids: list[str] = []
    reviewed_inspections: list[tuple[datetime, Dataset, Mapping[str, Any]]] = []
    valid_pairs: dict[str, str] = {}
    candidate_batches: dict[
        str, tuple[datetime, str, list[dict[str, Any]], dict[str, Any]]
    ] = {}
    latest_candidate_inspection_seen: set[str] = set()
    context_batches: dict[str, tuple[datetime, str, list[dict[str, Any]]]] = {}
    specialist_batches: list[
        tuple[datetime, Dataset, Mapping[str, Any], dict[str, Any]]
    ] = []

    for row in datasets:
        analysis = _accepted_analysis(row)
        if analysis is None:
            continue
        accepted_ids.append(row.id)
        measured_at = row.capture_date or row.processed_at or row.created_at
        inspection = _inspection_evidence(row, analysis)
        if inspection is not None:
            reviewed_inspections.append((measured_at, row, analysis))
        previous = _compatible_pair(row, analysis, datasets_by_id)
        if previous is not None:
            valid_pairs[row.id] = previous.id
        for kind, allowed in (
            ("visual", row.dataset_type in _VISUAL_TYPES),
            ("thermal", row.dataset_type == "THERMAL_IMAGES"),
        ):
            if (
                not allowed
                or inspection is None
                or kind in latest_candidate_inspection_seen
            ):
                continue
            latest_candidate_inspection_seen.add(kind)
            pair_valid = previous is not None
            if kind == "thermal" and previous is not None:
                pair_valid = _thermal_evidence(_accepted_analysis(previous)) is not None
            findings, assessed = _inventory(
                row, analysis, kind=kind, pair_valid=pair_valid
            )
            if assessed:
                detail = _detail(
                    row, analysis, gate="reviewed_registered_candidate_inventory"
                )
                batch = (measured_at, row.id, findings, detail)
                current = candidate_batches.get(kind)
                if current is None or (batch[0], batch[1]) > (current[0], current[1]):
                    candidate_batches[kind] = batch
        condition = _specialist_condition(row, analysis)
        if condition is not None:
            specialist_batches.append((measured_at, row, analysis, condition))
        context_batch = _context_alerts(row, analysis, evaluated_at=evaluated_at)
        if context_batch is not None:
            category, alerts = context_batch
            batch = (measured_at, row.id, alerts)
            current = context_batches.get(category)
            if current is None or (batch[0], batch[1]) > (current[0], current[1]):
                context_batches[category] = batch

    reviewed_inspections.sort(key=lambda item: (item[0], item[1].id), reverse=True)
    specialist_batches.sort(key=lambda item: (item[0], item[1].id), reverse=True)
    measurements: dict[str, float | str] = {}
    details: dict[str, dict[str, Any]] = {}
    findings = [item for _, _, batch, _ in candidate_batches.values() for item in batch]
    findings.extend(item for _, _, batch in context_batches.values() for item in batch)

    latest_inspection_at: datetime | None = None
    if reviewed_inspections:
        latest_inspection_at, latest_row, latest_analysis = reviewed_inspections[0]
        latest_candidates = sum(
            len(batch[2])
            for batch in candidate_batches.values()
            if batch[0] == latest_inspection_at
        )
        measurements["inspection_status"] = (
            "CANDIDATES_REQUIRE_REVIEW" if latest_candidates else "REVIEWED"
        )
        details["inspection_status"] = {
            **_detail(latest_row, latest_analysis, gate="reviewed_inspection_identity"),
            "status": "UNKNOWN",
        }
        measurements["inspection_freshness_days"] = max(
            0.0, (evaluated_at - latest_inspection_at).total_seconds() / 86_400
        )
        freshness_detail = _detail(
            latest_row, latest_analysis, gate="reviewed_inspection_timestamp"
        )
        freshness_detail["measured_at"] = evaluated_at
        freshness_detail["provenance"] = {
            **freshness_detail["provenance"],
            "inspection_captured_at": latest_inspection_at.isoformat(),
            "calculation": "evaluation_time_minus_reviewed_inspection_capture_time",
        }
        details["inspection_freshness_days"] = freshness_detail

    if specialist_batches:
        measured_at, row, analysis, condition = specialist_batches[0]
        measurements["condition_summary"] = condition["summary_code"]
        details["condition_summary"] = {
            **_detail(row, analysis, gate="authorized_specialist_condition_review"),
            "measured_at": measured_at,
            "status": "UNKNOWN",
            "provenance": {
                **_detail(row, analysis, gate="authorized_specialist_condition_review")[
                    "provenance"
                ],
                "review_reference": condition["review_reference"],
                "review_method": condition["method"],
                "review_method_version": condition["method_version"],
            },
        }

    for kind, key in (
        ("visual", "new_visual_candidate_count"),
        ("thermal", "new_thermal_candidate_count"),
    ):
        batch = candidate_batches.get(kind)
        if batch is None:
            continue
        measurements[key] = float(len(batch[2]))
        details[key] = {
            **batch[3],
            "source": "ports.reviewed_registered_candidate_inventory",
            "confidence": min(
                (float(item["confidence"]) for item in batch[2]),
                default=float(batch[3]["confidence"]),
            ),
            "provenance": {
                **dict(batch[3]["provenance"]),
                "candidate_kind": kind,
                "latest_inventory_only": True,
            },
        }

    cadence_days = _cadence(asset)
    reinspection = "NOT_CONFIGURED" if cadence_days is None else "UNKNOWN"
    due_at = None
    if cadence_days is not None and latest_inspection_at is not None:
        due_at = latest_inspection_at + timedelta(days=cadence_days)
        warning_window = min(14, max(1, round(cadence_days * 0.1)))
        if evaluated_at > due_at:
            reinspection = "OVERDUE"
            status = "CRITICAL"
        elif evaluated_at >= due_at - timedelta(days=warning_window):
            reinspection = "DUE"
            status = "WATCH"
        else:
            reinspection = "NOT_DUE"
            status = "GOOD"
        measurements["reinspection_state"] = reinspection
        details["reinspection_state"] = {
            "source": "ports.asset_inspection_cadence",
            "confidence": 1.0,
            "measured_at": evaluated_at,
            "dataset_id": reviewed_inspections[0][1].id,
            "mission_id": reviewed_inspections[0][1].mission_id,
            "status": status,
            "provenance": {
                "cadence_days": cadence_days,
                "latest_inspection_at": latest_inspection_at.isoformat(),
                "due_at": due_at.isoformat(),
            },
        }

    sensor = _sensor_context(db, asset=asset, evaluated_at=evaluated_at)
    findings.extend(
        {
            **item,
            "detected_at": _parse_datetime(item.get("detected_at")) or evaluated_at,
        }
        for item in sensor["alert_findings"]
    )
    if sensor["freshness_minutes"] is not None:
        measurements["assigned_sensor_freshness_minutes"] = sensor["freshness_minutes"]
        details["assigned_sensor_freshness_minutes"] = {
            "source": "ports.iot_assignment_snapshot",
            "confidence": 1.0,
            "measured_at": evaluated_at,
            "provenance": {
                "assignment_count": sensor["assignment_count"],
                "coverage_complete": True,
                "offline_replay_excluded": True,
            },
        }

    for category, key in (
        ("environmental", "environmental_alert_count"),
        ("operational", "operational_alert_count"),
    ):
        context_batch = context_batches.get(category)
        sensor_available = category in sensor["available_alert_categories"]
        if context_batch is None and not sensor_available:
            continue
        context_count = len(context_batch[2]) if context_batch else 0
        sensor_count = sensor["alert_counts"][category] if sensor_available else 0
        measurements[key] = float(context_count + sensor_count)
        details[key] = {
            "source": "ports.sourced_context_alerts",
            "confidence": 0.85,
            "measured_at": evaluated_at,
            "dataset_id": context_batch[1] if context_batch else None,
            "provenance": {
                "context_alert_count": context_count,
                "iot_alert_count": sensor_count,
                "context_only": True,
                "no_operational_or_compliance_conclusion": True,
            },
        }

    comparisons = ports_comparisons(db, asset=asset, enforce_feature=False)
    availability = {
        "inspection_evidence": "AVAILABLE" if reviewed_inspections else "UNKNOWN",
        "condition_summary": "AVAILABLE" if specialist_batches else "UNKNOWN",
        "visual_inventory": (
            "AVAILABLE" if "visual" in candidate_batches else "UNKNOWN"
        ),
        "thermal_inventory": (
            "AVAILABLE" if "thermal" in candidate_batches else "UNKNOWN"
        ),
        "reinspection": reinspection,
        "inspection_cadence": (
            "CONFIGURED" if cadence_days is not None else "NOT_CONFIGURED"
        ),
        "sensor_assignment": sensor["status"],
        "environmental_alert_source": (
            "AVAILABLE"
            if "environmental" in context_batches
            or "environmental" in sensor["available_alert_categories"]
            else "UNKNOWN"
        ),
        "operational_alert_source": (
            "AVAILABLE"
            if "operational" in context_batches
            or "operational" in sensor["available_alert_categories"]
            else "UNKNOWN"
        ),
        "historical_comparison": (
            "AVAILABLE"
            if any(item["availability"] == "AVAILABLE" for item in comparisons)
            else "UNKNOWN"
        ),
        "comparison_3d": next(
            (
                item["availability"]
                for item in comparisons
                if item["kind"] == "REALITY_3D"
            ),
            "NO_DATA",
        ),
        "supported_dataset_count": len(datasets),
        "validated_analysis_count": len(accepted_ids),
        "limitations": [
            message
            for condition, message in (
                (
                    not reviewed_inspections,
                    "Inspection state and age are unknown without reviewed exact-asset evidence.",
                ),
                (
                    not candidate_batches,
                    "New candidate counts are unknown without a registered chronological comparison.",
                ),
                (
                    cadence_days is None,
                    "Reinspection cadence is not configured for this asset.",
                ),
                (
                    sensor["status"] == "UNKNOWN",
                    "Assigned sensor freshness is unknown while any current device is offline or lacks valid telemetry.",
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
        "reviewed_inspection_dataset_ids": [
            item[1].id for item in reviewed_inspections
        ],
        "comparison_pairs": [
            {"current_dataset_id": current, "previous_dataset_id": previous}
            for current, previous in sorted(valid_pairs.items())
        ],
        "sensor_context": sensor,
    }
    return PortsSourceContext(
        evaluation=EvaluationContext(
            asset_id=asset.id,
            sector=SECTOR,
            measured_at=evaluated_at,
            measurements=measurements,
            datasets=tuple(
                {
                    "id": row.id,
                    "asset_id": row.asset_id,
                    "dataset_type": row.dataset_type,
                    "capture_date": row.capture_date,
                    "quality_status": row.quality_status,
                }
                for row in datasets
            ),
            telemetry=tuple(sensor["devices"]),
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


def evaluate_ports(
    db: Session,
    *,
    asset: Asset,
    actor=None,
    as_of: datetime | None = None,
) -> PortsEvaluation:
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
    return PortsEvaluation(sources, result, actions)


def _comparison_descriptor(
    rows: list[Dataset],
    *,
    kind: str,
    title: str,
    dimension: str,
    render_mode: str,
) -> dict[str, Any]:
    current = rows[0] if rows else None
    previous = None
    limitation = "A reviewed current and earlier inspection are required."
    if current is not None:
        analysis = _accepted_analysis(current)
        lookup = {row.id: row for row in rows}
        if analysis is not None:
            previous = _compatible_pair(current, analysis, lookup)
            if kind == "THERMAL_2D" and previous is not None:
                if (
                    _thermal_evidence(analysis) is None
                    or _thermal_evidence(_accepted_analysis(previous)) is None
                ):
                    previous = None
        if (
            previous is None
            and analysis is not None
            and analysis.get("comparison_evidence")
        ):
            limitation = (
                "The declared pair failed asset, tenant, modality, CRS, registration, quality, "
                "version, or chronology checks."
            )
    available = current is not None and previous is not None
    current_at = current.capture_date or current.created_at if current else None
    previous_at = previous.capture_date or previous.created_at if previous else None
    inspection = (
        _inspection_evidence(current, _accepted_analysis(current)) if current else None
    )
    return {
        "id": kind.lower(),
        "kind": kind,
        "title": title,
        "dimension": dimension,
        "render_mode": render_mode,
        "availability": "AVAILABLE"
        if available
        else "UNKNOWN"
        if current
        else "NO_DATA",
        "asset_id": current.asset_id if current else None,
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
        "crs": current.crs if available and current else None,
        "registration_reference": (
            inspection["registration_reference"] if available and inspection else None
        ),
        "limitation": None if available else limitation,
        "interpretation": (
            "registered inspection comparison only; no defect, structural-integrity, safety, "
            "navigation, or compliance conclusion"
        ),
    }


def ports_comparisons(
    db: Session,
    *,
    asset: Asset,
    enforce_feature: bool = True,
) -> list[dict[str, Any]]:
    _assert_ports_asset(asset)
    if enforce_feature:
        _require_feature(db, asset)
    datasets = [
        row for row in _eligible_datasets(db, asset=asset) if _accepted_analysis(row)
    ]
    return [
        _comparison_descriptor(
            [row for row in datasets if row.dataset_type in _VISUAL_TYPES],
            kind="VISUAL_2D",
            title="Registered visual inspection comparison",
            dimension="2D",
            render_mode="SWIPE_2D",
        ),
        _comparison_descriptor(
            [row for row in datasets if row.dataset_type == "THERMAL_IMAGES"],
            kind="THERMAL_2D",
            title="Calibrated thermal inspection comparison",
            dimension="2D",
            render_mode="THERMAL_COMPARE_2D",
        ),
        _comparison_descriptor(
            [row for row in datasets if row.dataset_type in _SURFACE_TYPES],
            kind="REALITY_3D",
            title="Registered 3D reality comparison",
            dimension="3D",
            render_mode="MODEL_COMPARE_3D",
        ),
    ]


def ports_inspection_history(db: Session, *, asset: Asset) -> list[dict[str, Any]]:
    _assert_ports_asset(asset)
    _require_feature(db, asset)
    scope = _asset_scope(db, asset=asset)
    scope_by_id = {row.id: row for row in scope}
    rows = (
        db.query(Dataset)
        .filter(
            Dataset.company_id == asset.organization_id,
            Dataset.workspace_id == asset.workspace_id,
            Dataset.asset_id.in_(tuple(scope_by_id)),
            Dataset.dataset_type.in_(tuple(_INSPECTION_TYPES)),
        )
        .order_by(
            Dataset.capture_date.desc(), Dataset.created_at.desc(), Dataset.id.desc()
        )
        .limit(1000)
        .all()
    )
    lookup = {row.id: row for row in rows}
    result: list[dict[str, Any]] = []
    for row in rows:
        analysis = _accepted_analysis(row)
        inspection = _inspection_evidence(row, analysis)
        pair = _compatible_pair(row, analysis, lookup) if analysis is not None else None
        condition = _specialist_condition(row, analysis)
        visual_items, visual_assessed = (
            _inventory(row, analysis, kind="visual", pair_valid=pair is not None)
            if analysis is not None and row.dataset_type in _VISUAL_TYPES
            else ([], False)
        )
        thermal_items, thermal_assessed = (
            _inventory(row, analysis, kind="thermal", pair_valid=pair is not None)
            if analysis is not None and row.dataset_type == "THERMAL_IMAGES"
            else ([], False)
        )
        result.append(
            {
                "dataset_id": row.id,
                "mission_id": row.mission_id,
                "asset_id": row.asset_id,
                "asset_name": scope_by_id[row.asset_id].name,
                "asset_type": scope_by_id[row.asset_id].asset_type,
                "dataset_type": row.dataset_type,
                "captured_at": row.capture_date or row.created_at,
                "quality_status": row.quality_status,
                "inspection_status": "REVIEWED" if inspection else "UNKNOWN",
                "inspection_reference": (
                    inspection["inspection_reference"] if inspection else None
                ),
                "capture_mode": inspection["capture_mode"] if inspection else None,
                "comparison_previous_dataset_id": pair.id if pair else None,
                "new_visual_candidate_count": (
                    len(visual_items) if visual_assessed and pair else None
                ),
                "new_thermal_candidate_count": (
                    len(thermal_items) if thermal_assessed and pair else None
                ),
                "condition_summary": condition["summary_code"]
                if condition
                else "UNKNOWN",
                "interpretation": "review evidence only; no automatic condition conclusion",
            }
        )
    return result


_LAYER_MODES = {
    "AIS_DATA": ("REFERENCE", "REFERENCE_ONLY"),
    "DSM": ("2D", "MAP_RASTER"),
    "DTM": ("2D", "MAP_RASTER"),
    "MESH_3D": ("3D", "MESH_3D"),
    "ORTHOMOSAIC": ("2D", "MAP_RASTER"),
    "POINT_CLOUD": ("3D", "POINT_CLOUD_3D"),
    "RGB_IMAGES": ("REFERENCE", "REFERENCE_ONLY"),
    "THERMAL_IMAGES": ("2D", "MAP_RASTER"),
    "WEATHER_DATA": ("REFERENCE", "REFERENCE_ONLY"),
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


def ports_map_layers(db: Session, *, asset: Asset) -> list[dict[str, Any]]:
    _assert_ports_asset(asset)
    _require_feature(db, asset)
    scope = _asset_scope(db, asset=asset)
    scope_ids = {row.id for row in scope}
    layers: list[dict[str, Any]] = []
    for scoped_asset in scope:
        geometry = _safe_geometry(
            _object(scoped_asset.geometry_geojson)
            if scoped_asset.geometry_geojson
            else None
        )
        layers.append(
            {
                "id": f"asset:{scoped_asset.id}",
                "kind": "ASSET_BOUNDARY",
                "title": scoped_asset.name,
                "asset_id": scoped_asset.id,
                "dimension": "2D",
                "render_mode": "VECTOR",
                "availability": "AVAILABLE" if geometry else "NO_DATA",
                "geometry": geometry,
                "data_ref": f"/assets/{scoped_asset.id}",
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
    rows = (
        db.query(Dataset)
        .filter(
            Dataset.company_id == asset.organization_id,
            Dataset.workspace_id == asset.workspace_id,
            Dataset.asset_id.in_(tuple(scope_ids)),
            Dataset.dataset_type.in_(tuple(SUPPORTED_DATASET_TYPES)),
        )
        .order_by(Dataset.capture_date.desc(), Dataset.created_at.desc())
        .limit(1000)
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
        layers.append(
            {
                "id": f"dataset:{row.id}",
                "kind": row.dataset_type,
                "title": row.name,
                "asset_id": row.asset_id,
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
                "provenance": {
                    "dataset_type": row.dataset_type,
                    "processing_level": row.processing_level,
                    **_public_provenance(row),
                },
            }
        )
    for scoped_asset in scope:
        for row in list_asset_observations(db, asset=scoped_asset, limit=500):
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
                    "asset_id": row.asset_id,
                    "dimension": "2D",
                    "render_mode": "VECTOR",
                    "availability": (
                        "AVAILABLE"
                        if row.validation_status == "VALIDATED"
                        else "UNKNOWN"
                    ),
                    "geometry": geometry,
                    "data_ref": f"/assets/{row.asset_id}/observations",
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
                        "cause_assessed": False,
                        "specialist_review_required": row.validation_status
                        != "VALIDATED",
                    },
                }
            )
    return layers


def ports_report_context(db: Session, *, asset: Asset) -> dict[str, Any]:
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
        "schema": "geovision.ports.report-context.v1",
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
        "inspection_history": ports_inspection_history(db, asset=asset),
        "comparisons": ports_comparisons(db, asset=asset),
        "map_layers": ports_map_layers(db, asset=asset),
        "limitations": [
            *sources.availability.get("limitations", []),
            "Inspection and sensor history remains attached to canonical asset and zone UUIDs.",
            "Potential visual and thermal anomalies remain NEEDS_REVIEW candidates.",
            "AIS, environmental, operational, and enterprise context is optional and context-only.",
            "No defect, structural-integrity, safety, navigation, compliance, or engineering conclusion is generated automatically.",
        ],
    }


__all__ = [
    "ANALYSIS_SCHEMA",
    "PortsEvaluation",
    "build_source_context",
    "evaluate_ports",
    "ports_comparisons",
    "ports_enabled_for_context",
    "ports_inspection_history",
    "ports_map_layers",
    "ports_report_context",
    "sync_kpi_definitions",
]
