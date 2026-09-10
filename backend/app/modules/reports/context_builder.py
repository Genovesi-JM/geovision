"""Build immutable, tenant-safe report facts from canonical persistence."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
import math
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models import (
    Acquisition,
    Action,
    Asset,
    Dataset,
    DatasetFile,
    KpiDefinition,
    KpiValue,
    Observation,
)
from app.modules.reports.domain import ReportError
from app.modules.reports.ports import ReportContextRegistry, report_context_registry


CONTEXT_SCHEMA_VERSION = "geovision.report-context.v1"
_SENSITIVE_KEY = re.compile(
    r"(^|_)(password|passwd|secret|token|api_key|authorization|credential|private_key|storage_key|storage_uri|object_prefix|file_path)($|_)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class BuiltReportContext:
    context: dict[str, Any]
    canonical_json: str
    sha256: str
    evidence_ids: frozenset[str]
    exclusions: dict[str, int]


def _json_object(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_array(value: str | None) -> list[Any]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _safe_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 12:
        return None
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for raw_key, nested in value.items():
            key = str(raw_key)[:160]
            normalized = re.sub(r"[^A-Za-z0-9]+", "_", key).strip("_")
            if _SENSITIVE_KEY.search(normalized):
                continue
            result[key] = _safe_value(nested, depth=depth + 1)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_safe_value(item, depth=depth + 1) for item in list(value)[:1_000]]
    return str(value)[:2_000]


def _dataset_is_eligible(dataset: Dataset | None, asset: Asset) -> bool:
    return bool(
        dataset is not None
        and dataset.company_id == asset.organization_id
        and dataset.asset_id == asset.id
        and dataset.status == "ready"
        and str(dataset.quality_status).upper() == "PASSED"
    )


def _kpi_is_eligible(db: Session, asset: Asset, row: KpiValue) -> bool:
    if row.confidence < 0.5:
        return False
    if str(row.source or "").strip().lower() in {"", "legacy"}:
        return False
    if str(row.algorithm_version or "").strip().lower() in {"", "legacy-1"}:
        return False
    if row.numeric_value is not None and not math.isfinite(float(row.numeric_value)):
        return False
    if row.dataset_id and not _dataset_is_eligible(db.get(Dataset, row.dataset_id), asset):
        return False
    return True


def _observation_is_eligible(db: Session, asset: Asset, row: Observation) -> bool:
    if row.validation_status != "VALIDATED" or row.confidence < 0.5:
        return False
    if row.dataset_id and not _dataset_is_eligible(db.get(Dataset, row.dataset_id), asset):
        return False
    return True


class ReportContextBuilder:
    """Select only validated facts and remove transport/storage secrets."""

    def __init__(self, registry: ReportContextRegistry = report_context_registry) -> None:
        self.registry = registry

    def build(
        self,
        db: Session,
        *,
        asset: Asset,
        acquisition: Acquisition | None = None,
    ) -> BuiltReportContext:
        if acquisition is not None and (
            acquisition.organization_id != asset.organization_id
            or acquisition.asset_id != asset.id
        ):
            raise ReportError(
                "acquisition_not_found",
                "Acquisition was not found for this asset",
            )

        exclusions = {
            "kpi_values": 0,
            "observations": 0,
            "actions": 0,
            "map_layers": 0,
        }
        kpi_rows = (
            db.query(KpiValue, KpiDefinition)
            .join(KpiDefinition, KpiDefinition.id == KpiValue.kpi_definition_id)
            .filter(
                KpiValue.organization_id == asset.organization_id,
                KpiValue.asset_id == asset.id,
                KpiValue.is_baseline.is_(False),
                KpiDefinition.is_active.is_(True),
            )
            .order_by(KpiValue.measured_at.desc(), KpiValue.id.asc())
            .all()
        )
        histories: dict[str, list[dict[str, Any]]] = defaultdict(list)
        current_kpis: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        eligible_dataset_ids: set[str] = set()
        evidence_ids: set[str] = set()
        timestamps: list[datetime] = []
        for row, definition in kpi_rows:
            if acquisition is not None and row.mission_id != acquisition.id:
                exclusions["kpi_values"] += 1
                continue
            if not _kpi_is_eligible(db, asset, row):
                exclusions["kpi_values"] += 1
                continue
            evidence_id = f"kpi:{row.id}"
            item = {
                "evidence_id": evidence_id,
                "id": row.id,
                "definition_id": definition.id,
                "key": definition.key,
                "name": definition.name or definition.label,
                "unit": definition.unit,
                "importance": definition.importance,
                "value": row.value,
                "numeric_value": (
                    float(row.numeric_value) if row.numeric_value is not None else None
                ),
                "status": row.status,
                "confidence": float(row.confidence),
                "measured_at": row.measured_at,
                "source": row.source,
                "algorithm_version": row.algorithm_version,
                "dataset_id": row.dataset_id,
                "acquisition_id": row.mission_id,
                "provenance": _json_object(row.provenance_json),
            }
            histories[definition.key].append(item)
            if definition.key not in seen_keys:
                current_kpis.append(item)
                seen_keys.add(definition.key)
                evidence_ids.add(evidence_id)
                timestamps.append(row.measured_at)
                if row.dataset_id:
                    eligible_dataset_ids.add(row.dataset_id)

        current_kpis.sort(
            key=lambda item: (
                {"PRIMARY": 0, "SECONDARY": 1, "TECHNICAL": 2}.get(
                    str(item["importance"]), 3
                ),
                str(item["key"]),
            )
        )
        history_payload = {
            key: values[:5]
            for key, values in sorted(histories.items())
            if values
        }

        observation_rows = (
            db.query(Observation)
            .filter(
                Observation.organization_id == asset.organization_id,
                Observation.asset_id == asset.id,
            )
            .order_by(Observation.detected_at.desc(), Observation.id.asc())
            .limit(1_000)
            .all()
        )
        observations: list[dict[str, Any]] = []
        validated_observation_ids: set[str] = set()
        for row in observation_rows:
            if acquisition is not None and row.mission_id != acquisition.id:
                exclusions["observations"] += 1
                continue
            if not _observation_is_eligible(db, asset, row):
                exclusions["observations"] += 1
                continue
            evidence_id = f"observation:{row.id}"
            observations.append(
                {
                    "evidence_id": evidence_id,
                    "id": row.id,
                    "type": row.observation_type,
                    "severity": row.severity,
                    "geometry": _json_object(row.geometry_geojson),
                    "value": _json_object(row.value_json),
                    "numeric_value": row.numeric_value,
                    "unit": row.unit,
                    "confidence": float(row.confidence),
                    "source": row.source,
                    "algorithm": row.algorithm_key,
                    "algorithm_version": row.algorithm_version,
                    "dataset_id": row.dataset_id,
                    "acquisition_id": row.mission_id,
                    "validated_at": row.validated_at,
                    "detected_at": row.detected_at,
                    "provenance": _json_object(row.provenance_json),
                }
            )
            evidence_ids.add(evidence_id)
            validated_observation_ids.add(row.id)
            timestamps.append(row.detected_at)
            if row.dataset_id:
                eligible_dataset_ids.add(row.dataset_id)

        action_rows = (
            db.query(Action)
            .filter(
                Action.organization_id == asset.organization_id,
                Action.asset_id == asset.id,
                Action.status.in_(("OPEN", "IN_PROGRESS")),
            )
            .order_by(Action.due_date.asc(), Action.created_at.desc())
            .limit(1_000)
            .all()
        )
        actions: list[dict[str, Any]] = []
        for row in action_rows:
            trusted_manual = str(row.source_rule_key).lower().startswith(
                ("manual.", "manual_", "human.")
            ) and bool(row.created_by_user_id)
            if row.source_observation_id not in validated_observation_ids and not trusted_manual:
                exclusions["actions"] += 1
                continue
            evidence_id = f"action:{row.id}"
            actions.append(
                {
                    "evidence_id": evidence_id,
                    "id": row.id,
                    "source_observation_id": row.source_observation_id,
                    "source_rule": row.source_rule_key,
                    "source_rule_version": row.source_rule_version,
                    "priority": row.priority,
                    "title": row.title,
                    "description": row.description,
                    "status": row.status,
                    "due_date": row.due_date,
                    "recommendation_refs": _json_array(row.recommendation_refs_json),
                    "created_at": row.created_at,
                }
            )
            evidence_ids.add(evidence_id)
            timestamps.append(row.created_at)

        datasets: list[dict[str, Any]] = []
        files: list[dict[str, Any]] = []
        if eligible_dataset_ids:
            dataset_rows = (
                db.query(Dataset)
                .filter(
                    Dataset.id.in_(tuple(eligible_dataset_ids)),
                    Dataset.company_id == asset.organization_id,
                    Dataset.asset_id == asset.id,
                )
                .order_by(Dataset.capture_date.desc(), Dataset.id.asc())
                .all()
            )
            for row in dataset_rows:
                datasets.append(
                    {
                        "id": row.id,
                        "name": row.name,
                        "dataset_type": row.dataset_type,
                        "processing_level": row.processing_level,
                        "quality_status": row.quality_status,
                        "status": row.status,
                        "provider": row.provider_code,
                        "capture_date": row.capture_date,
                        "acquisition_id": row.mission_id,
                        "crs": row.crs,
                        "resolution": row.resolution,
                        "resolution_unit": row.resolution_unit,
                        "provenance": _json_object(row.provenance_json),
                    }
                )
            file_rows = (
                db.query(DatasetFile)
                .filter(
                    DatasetFile.dataset_id.in_(tuple(eligible_dataset_ids)),
                    DatasetFile.deleted_at.is_(None),
                    DatasetFile.status == "uploaded",
                )
                .order_by(DatasetFile.created_at.asc(), DatasetFile.id.asc())
                .all()
            )
            files = [
                {
                    "id": row.id,
                    "dataset_id": row.dataset_id,
                    "filename": row.filename,
                    "mime_type": row.mime_type,
                    "size_bytes": row.file_size,
                    "sha256": row.sha256_hash,
                }
                for row in file_rows
            ]

        sector_context: Mapping[str, Any] = {}
        sector_limitations: list[str] = []
        provider = self.registry.get(asset.sector)
        if provider is not None:
            try:
                sector_context = provider.build(db, asset)
            except (ValueError, RuntimeError):
                sector_limitations.append(
                    "Sector enrichment was unavailable; canonical validated facts remain included."
                )
        raw_layers = sector_context.get("map_layers", [])
        map_layers: list[Any] = []
        if isinstance(raw_layers, Sequence) and not isinstance(raw_layers, (str, bytes)):
            for layer in raw_layers[:1_000]:
                if not isinstance(layer, Mapping):
                    exclusions["map_layers"] += 1
                    continue
                dataset_id = layer.get("dataset_id")
                observation_id = layer.get("observation_id")
                if dataset_id and dataset_id not in eligible_dataset_ids:
                    exclusions["map_layers"] += 1
                    continue
                if observation_id and observation_id not in validated_observation_ids:
                    exclusions["map_layers"] += 1
                    continue
                map_layers.append(_safe_value(layer))

        raw_limitations = sector_context.get("limitations", [])
        if isinstance(raw_limitations, Sequence) and not isinstance(
            raw_limitations, (str, bytes)
        ):
            sector_limitations.extend(
                str(item).strip()[:1_000] for item in raw_limitations if str(item).strip()
            )

        as_of = max(timestamps) if timestamps else (
            acquisition.completed_at
            if acquisition is not None and acquisition.completed_at is not None
            else asset.updated_at
        )
        context = _safe_value(
            {
                "schema_version": CONTEXT_SCHEMA_VERSION,
                "as_of": as_of,
                "organization_id": asset.organization_id,
                "workspace_id": asset.workspace_id,
                "asset": {
                    "id": asset.id,
                    "name": asset.name,
                    "sector": asset.sector,
                    "asset_type": asset.asset_type,
                    "location_label": asset.location_label,
                    "geometry": _json_object(asset.geometry_geojson),
                },
                "acquisition": (
                    {
                        "id": acquisition.id,
                        "number": acquisition.acquisition_number,
                        "type": acquisition.acquisition_type,
                        "title": acquisition.title,
                        "state": acquisition.state,
                        "captured_at": acquisition.captured_at,
                        "completed_at": acquisition.completed_at,
                    }
                    if acquisition is not None
                    else None
                ),
                "kpis": current_kpis,
                "kpi_history": history_payload,
                "observations": observations,
                "actions": actions,
                "datasets": datasets,
                "files": files,
                "map_layers": map_layers,
                "source_availability": sector_context.get("source_availability", {}),
                "limitations": list(dict.fromkeys(sector_limitations)),
                "selection": {
                    "kpi_minimum_confidence": 0.5,
                    "observation_validation": "VALIDATED",
                    "dataset_status": "ready",
                    "dataset_quality": "PASSED",
                    "exclusions": exclusions,
                },
            }
        )
        canonical_json = json.dumps(
            context,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        if len(canonical_json.encode("utf-8")) > 2 * 1024 * 1024:
            raise ReportError(
                "context_too_large",
                "Validated report context exceeds the supported size",
            )
        return BuiltReportContext(
            context=context,
            canonical_json=canonical_json,
            sha256=hashlib.sha256(canonical_json.encode()).hexdigest(),
            evidence_ids=frozenset(evidence_ids),
            exclusions=exclusions,
        )


__all__ = [
    "BuiltReportContext",
    "CONTEXT_SCHEMA_VERSION",
    "ReportContextBuilder",
]
