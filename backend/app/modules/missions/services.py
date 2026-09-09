"""Application services for provider-neutral acquisition missions."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models import (
    Acquisition,
    Asset,
    AssetInspection,
    AuditLog,
    DroneAcquisitionDetail,
    DroneAircraft,
    DroneMission,
    FulfilmentJob,
    OperationsContractor,
    Order,
    Site,
    User,
)
from app.modules.assets.domain import AssetValidationError, normalize_geometry
from app.modules.assets.services import synchronize_legacy_iot_asset, synchronize_legacy_site
from app.modules.missions.domain import (
    AcquisitionError,
    AcquisitionState,
    AcquisitionType,
    require_acquisition_transition,
)
from app.modules.missions.schemas import (
    AcquisitionCreate,
    AcquisitionStateUpdate,
    AcquisitionUpdate,
    DroneDetailsInput,
    InternalAcquisitionCreate,
    InternalAcquisitionUpdate,
)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


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


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _provider_code(value: str | None) -> str | None:
    if not value:
        return None
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return normalized[:80] or None


def _audit(
    db: Session,
    *,
    actor: User | None,
    action: str,
    acquisition: Acquisition,
    details: dict[str, Any],
) -> None:
    db.add(
        AuditLog(
            user_id=actor.id if actor else None,
            user_email=actor.email if actor else None,
            action=action,
            resource_type="acquisition",
            resource_id=acquisition.id,
            details=_json(
                {
                    "organization_id": acquisition.organization_id,
                    "asset_id": acquisition.asset_id,
                    **details,
                }
            ),
        )
    )


def _check_version(acquisition: Acquisition, expected: int | None) -> None:
    if expected is not None and acquisition.lifecycle_version != expected:
        raise AcquisitionError(
            "version_conflict", "Acquisition changed since it was last read"
        )


def _drone_detail(db: Session, acquisition_id: str) -> DroneAcquisitionDetail | None:
    return db.get(DroneAcquisitionDetail, acquisition_id)


def _normalize_capture_area(value: dict[str, Any] | None) -> str | None:
    if value is None:
        return None
    try:
        normalized = normalize_geometry(value)
    except AssetValidationError as exc:
        raise AcquisitionError("invalid_capture_area", str(exc)) from exc
    if normalized and normalized["type"] not in {"Polygon", "MultiPolygon"}:
        raise AcquisitionError(
            "invalid_capture_area", "Drone capture area must be a Polygon or MultiPolygon"
        )
    return _json(normalized) if normalized else None


def _validate_links(
    db: Session,
    *,
    asset: Asset,
    order_id: str | None,
    fulfilment_job_id: str | None,
) -> None:
    order = db.get(Order, order_id) if order_id else None
    if order_id and (
        order is None
        or (order.organization_id or order.company_id) != asset.organization_id
    ):
        raise AcquisitionError("order_not_found", "Order was not found for this asset")
    if fulfilment_job_id:
        job = db.get(FulfilmentJob, fulfilment_job_id)
        if job is None:
            raise AcquisitionError("job_not_found", "Fulfilment job was not found")
        linked_order = order or db.get(Order, job.order_id)
        if (
            linked_order is None
            or (linked_order.organization_id or linked_order.company_id)
            != asset.organization_id
            or (order_id and job.order_id != order_id)
            or (job.asset_id and job.asset_id != asset.id)
        ):
            raise AcquisitionError(
                "job_asset_mismatch", "Fulfilment job does not belong to this asset/order"
            )


def _upsert_drone_details(
    db: Session,
    *,
    acquisition: Acquisition,
    data: DroneDetailsInput,
) -> DroneAcquisitionDetail:
    if acquisition.acquisition_type != AcquisitionType.DRONE.value:
        raise AcquisitionError("invalid_modality", "Drone details require a DRONE acquisition")
    if data.aircraft_id:
        aircraft = db.get(DroneAircraft, data.aircraft_id)
        if aircraft is None or aircraft.company_id != acquisition.organization_id:
            raise AcquisitionError("aircraft_not_found", "Aircraft was not found")
    if data.operator_user_id:
        operator = db.get(User, data.operator_user_id)
        if operator is None or not operator.is_active:
            raise AcquisitionError("operator_not_found", "Operator is unavailable")
    if data.contractor_id:
        contractor = db.get(OperationsContractor, data.contractor_id)
        if contractor is None or contractor.status != "ACTIVE":
            raise AcquisitionError("contractor_not_found", "Contractor is unavailable")
    if data.reflight_of_acquisition_id:
        original = db.get(Acquisition, data.reflight_of_acquisition_id)
        if (
            original is None
            or original.acquisition_type != AcquisitionType.DRONE.value
            or original.asset_id != acquisition.asset_id
            or original.id == acquisition.id
        ):
            raise AcquisitionError("reflight_not_found", "Original drone acquisition was not found")
    detail = _drone_detail(db, acquisition.id)
    if detail is None:
        detail = DroneAcquisitionDetail(
            acquisition_id=acquisition.id,
            created_at=acquisition.created_at,
        )
    detail.aircraft_id = data.aircraft_id
    detail.payload_reference = data.payload_reference
    detail.operator_user_id = data.operator_user_id
    detail.contractor_id = data.contractor_id
    detail.mission_requirements_json = _json(data.mission_requirements)
    detail.capture_area_geojson = _normalize_capture_area(data.capture_area)
    detail.flight_metadata_json = _json(data.flight_metadata)
    detail.reflight_of_acquisition_id = data.reflight_of_acquisition_id
    detail.reflight_reason = data.reflight_reason
    detail.updated_at = utc_now()
    db.add(detail)
    return detail


def create_acquisition(
    db: Session,
    *,
    actor: User,
    asset: Asset,
    data: AcquisitionCreate | InternalAcquisitionCreate,
    internal: bool,
) -> Acquisition:
    order_id = getattr(data, "order_id", None) if internal else None
    job_id = getattr(data, "fulfilment_job_id", None) if internal else None
    if job_id and not order_id:
        linked_job = db.get(FulfilmentJob, job_id)
        order_id = linked_job.order_id if linked_job is not None else None
    _validate_links(db, asset=asset, order_id=order_id, fulfilment_job_id=job_id)
    now = utc_now()
    acquisition_id = str(uuid.uuid4())
    acquisition = Acquisition(
        id=acquisition_id,
        acquisition_number=f"GVAQ-{now.year}-{acquisition_id.split('-')[0].upper()}",
        organization_id=asset.organization_id,
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        order_id=order_id,
        fulfilment_job_id=job_id,
        acquisition_type=data.acquisition_type.value,
        title=data.title.strip(),
        description=data.description,
        state=AcquisitionState.DRAFT.value,
        provider_code=(
            _provider_code(getattr(data, "provider_code", None)) if internal else None
        ),
        provider_reference=(getattr(data, "provider_reference", None) if internal else None),
        provenance_json=_json(getattr(data, "provenance", {}) if internal else {}),
        metadata_json=_json(data.metadata),
        output_refs_json=_json(getattr(data, "output_refs", []) if internal else []),
        scheduled_start=data.scheduled_start,
        scheduled_end=data.scheduled_end,
        lifecycle_version=1,
        created_by_user_id=actor.id,
        updated_by_user_id=actor.id,
        created_at=now,
        updated_at=now,
    )
    db.add(acquisition)
    db.flush()
    if data.drone_details:
        details = data.drone_details
        if not internal and (details.operator_user_id or details.contractor_id):
            raise AcquisitionError(
                "assignment_forbidden", "Customers cannot assign internal acquisition resources"
            )
        _upsert_drone_details(db, acquisition=acquisition, data=details)
    _audit(
        db,
        actor=actor,
        action="acquisition.created",
        acquisition=acquisition,
        details={"type": acquisition.acquisition_type, "state": acquisition.state},
    )
    return acquisition


_PRIVATE_OUTPUT_KEY_PARTS = (
    "contractor",
    "cost",
    "credential",
    "internal",
    "margin",
    "operator",
    "provider_reference",
    "raw_path",
    "secret",
    "storage_key",
    "supplier",
    "token",
    "user_id",
)


def _public_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _public_value(nested)
            for key, nested in value.items()
            if not any(
                part in str(key).strip().lower() for part in _PRIVATE_OUTPUT_KEY_PARTS
            )
        }
    if isinstance(value, list):
        return [_public_value(item) for item in value]
    return value


def _drone_payload(db: Session, acquisition: Acquisition, *, internal: bool) -> dict | None:
    detail = _drone_detail(db, acquisition.id)
    if detail is None:
        return None
    payload = {
        "aircraft_id": detail.aircraft_id,
        "payload_reference": detail.payload_reference,
        "mission_requirements": _public_value(_object(detail.mission_requirements_json)),
        "capture_area": (
            _object(detail.capture_area_geojson) if detail.capture_area_geojson else None
        ),
        "flight_metadata": _public_value(_object(detail.flight_metadata_json)),
        "reflight_of_acquisition_id": detail.reflight_of_acquisition_id,
        "reflight_reason": detail.reflight_reason,
    }
    if internal:
        payload["operator_user_id"] = detail.operator_user_id
        payload["contractor_id"] = detail.contractor_id
        payload["mission_requirements"] = _object(detail.mission_requirements_json)
        payload["flight_metadata"] = _object(detail.flight_metadata_json)
    return payload


def acquisition_out(
    db: Session, acquisition: Acquisition, *, internal: bool = False
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": acquisition.id,
        "acquisition_number": acquisition.acquisition_number,
        "asset_id": acquisition.asset_id,
        "acquisition_type": acquisition.acquisition_type,
        "title": acquisition.title,
        "description": acquisition.description,
        "state": acquisition.state,
        "metadata": _public_value(_object(acquisition.metadata_json)),
        "output_refs": _public_value(_array(acquisition.output_refs_json)),
        "scheduled_start": _iso(acquisition.scheduled_start),
        "scheduled_end": _iso(acquisition.scheduled_end),
        "started_at": _iso(acquisition.started_at),
        "captured_at": _iso(acquisition.captured_at),
        "completed_at": _iso(acquisition.completed_at),
        "lifecycle_version": acquisition.lifecycle_version,
        "drone_details": _drone_payload(db, acquisition, internal=internal),
        "created_at": acquisition.created_at.isoformat(),
        "updated_at": acquisition.updated_at.isoformat(),
    }
    if internal:
        payload.update(
            {
                "organization_id": acquisition.organization_id,
                "workspace_id": acquisition.workspace_id,
                "order_id": acquisition.order_id,
                "fulfilment_job_id": acquisition.fulfilment_job_id,
                "provider_code": acquisition.provider_code,
                "provider_reference": acquisition.provider_reference,
                "provenance": _object(acquisition.provenance_json),
                "legacy_source": acquisition.legacy_source,
                "legacy_source_id": acquisition.legacy_source_id,
                "created_by_user_id": acquisition.created_by_user_id,
                "updated_by_user_id": acquisition.updated_by_user_id,
                "metadata": _object(acquisition.metadata_json),
                "output_refs": _array(acquisition.output_refs_json),
            }
        )
    return payload


def list_acquisitions(
    db: Session,
    *,
    organization_id: str | None = None,
    workspace_id: str | None = None,
    asset_id: str | None = None,
    acquisition_type: str | None = None,
    state: str | None = None,
    chronological: bool = False,
    limit: int = 200,
) -> list[Acquisition]:
    query = db.query(Acquisition)
    if organization_id:
        query = query.filter(Acquisition.organization_id == organization_id)
    if workspace_id:
        query = query.filter(
            (Acquisition.workspace_id == workspace_id) | (Acquisition.workspace_id.is_(None))
        )
    if asset_id:
        query = query.filter(Acquisition.asset_id == asset_id)
    if acquisition_type:
        query = query.filter(Acquisition.acquisition_type == acquisition_type.upper())
    if state:
        query = query.filter(Acquisition.state == state.upper())
    ordering = (
        (Acquisition.created_at.asc(), Acquisition.id.asc())
        if chronological
        else (Acquisition.created_at.desc(), Acquisition.id.desc())
    )
    return query.order_by(*ordering).limit(limit).all()


def update_acquisition(
    db: Session,
    *,
    actor: User,
    acquisition: Acquisition,
    data: AcquisitionUpdate | InternalAcquisitionUpdate,
    internal: bool,
) -> Acquisition:
    _check_version(acquisition, data.expected_version)
    if acquisition.state in {
        AcquisitionState.COMPLETED.value,
        AcquisitionState.CANCELLED.value,
        AcquisitionState.FAILED.value,
    }:
        raise AcquisitionError("acquisition_locked", "Terminal acquisition cannot be edited")
    if not internal and acquisition.state not in {
        AcquisitionState.DRAFT.value,
        AcquisitionState.PLANNED.value,
    }:
        raise AcquisitionError("acquisition_locked", "Acquisition can no longer be edited")
    changed = data.model_dump(exclude_unset=True, mode="json")
    changed.pop("expected_version", None)
    clear_schedule = bool(changed.pop("clear_schedule", False))
    drone_data = changed.pop("drone_details", None) if internal else None
    if "metadata" in changed:
        acquisition.metadata_json = _json(changed.pop("metadata") or {})
    if internal and "provenance" in changed:
        acquisition.provenance_json = _json(changed.pop("provenance") or {})
    if internal and "output_refs" in changed:
        acquisition.output_refs_json = _json(changed.pop("output_refs") or [])
    if internal and "provider_code" in changed:
        acquisition.provider_code = _provider_code(changed.pop("provider_code"))
    if internal and "provider_reference" in changed:
        acquisition.provider_reference = changed.pop("provider_reference")
    if clear_schedule:
        if acquisition.state == AcquisitionState.SCHEDULED.value:
            raise AcquisitionError("schedule_locked", "A scheduled acquisition needs a window")
        acquisition.scheduled_start = None
        acquisition.scheduled_end = None
    for field in ("title", "description", "scheduled_start", "scheduled_end"):
        if field in changed:
            setattr(acquisition, field, changed[field])
    if drone_data is not None:
        _upsert_drone_details(
            db,
            acquisition=acquisition,
            data=DroneDetailsInput.model_validate(drone_data),
        )
    acquisition.lifecycle_version = int(acquisition.lifecycle_version or 0) + 1
    acquisition.updated_by_user_id = actor.id
    acquisition.updated_at = utc_now()
    _audit(
        db,
        actor=actor,
        action="acquisition.updated",
        acquisition=acquisition,
        details={"fields": sorted(data.model_fields_set)},
    )
    return acquisition


def transition_acquisition(
    db: Session,
    *,
    actor: User,
    acquisition: Acquisition,
    data: AcquisitionStateUpdate,
    internal: bool,
) -> Acquisition:
    _check_version(acquisition, data.expected_version)
    current = AcquisitionState(acquisition.state)
    target = data.state
    if current == target:
        return acquisition
    if not internal and not (
        target in {AcquisitionState.PLANNED, AcquisitionState.CANCELLED}
        and current in {AcquisitionState.DRAFT, AcquisitionState.PLANNED}
    ):
        raise AcquisitionError(
            "state_forbidden", "GeoVision Operations controls this acquisition transition"
        )
    require_acquisition_transition(current.value, target.value)
    if target in {
        AcquisitionState.CANCELLED,
        AcquisitionState.FAILED,
        AcquisitionState.NEEDS_REFLIGHT,
    } and not (data.reason or "").strip():
        raise AcquisitionError("reason_required", f"{target.value} requires a reason")
    if target == AcquisitionState.SCHEDULED and not (
        acquisition.scheduled_start and acquisition.scheduled_end
    ):
        raise AcquisitionError("schedule_required", "A scheduled acquisition needs a window")
    if target == AcquisitionState.NEEDS_REFLIGHT and (
        acquisition.acquisition_type != AcquisitionType.DRONE.value
    ):
        raise AcquisitionError("invalid_reflight", "Only a drone acquisition can need reflight")
    now = utc_now()
    acquisition.state = target.value
    if target == AcquisitionState.IN_PROGRESS and acquisition.started_at is None:
        acquisition.started_at = now
    if target == AcquisitionState.DATA_CAPTURED and acquisition.captured_at is None:
        acquisition.captured_at = now
    if target == AcquisitionState.COMPLETED:
        acquisition.completed_at = now
        acquisition.captured_at = acquisition.captured_at or now
    if target == AcquisitionState.NEEDS_REFLIGHT:
        detail = _drone_detail(db, acquisition.id)
        if detail is None:
            detail = DroneAcquisitionDetail(acquisition_id=acquisition.id, created_at=now)
        detail.reflight_reason = data.reason
        detail.updated_at = now
        db.add(detail)
    metadata = _object(acquisition.metadata_json)
    if data.reason:
        metadata["last_transition_reason"] = data.reason
        acquisition.metadata_json = _json(metadata)
    acquisition.lifecycle_version = int(acquisition.lifecycle_version or 0) + 1
    acquisition.updated_by_user_id = actor.id
    acquisition.updated_at = now
    _audit(
        db,
        actor=actor,
        action="acquisition.state_changed",
        acquisition=acquisition,
        details={"from": current.value, "to": target.value, "reason": data.reason},
    )
    return acquisition


def _legacy_state(value: str) -> str:
    return {
        "draft": "DRAFT",
        "planned": "PLANNED",
        "approved": "PLANNED",
        "approved_for_provider_handoff": "PLANNED",
        "scheduled": "SCHEDULED",
        "in_progress": "IN_PROGRESS",
        "captured": "DATA_CAPTURED",
        "uploaded": "DATA_CAPTURED",
        "processing": "PROCESSING",
        "completed": "COMPLETED",
        "cancelled": "CANCELLED",
        "failed": "FAILED",
        "needs_reflight": "NEEDS_REFLIGHT",
    }.get(str(value or "").strip().lower(), "DRAFT")


def _legacy_boundary(value: str | None) -> dict[str, Any] | None:
    points = _array(value)
    coordinates: list[list[float]] = []
    for point in points:
        if not isinstance(point, dict):
            continue
        latitude = point.get("lat", point.get("latitude"))
        longitude = point.get("lng", point.get("longitude"))
        try:
            coordinates.append([float(longitude), float(latitude)])
        except (TypeError, ValueError):
            continue
    if len(coordinates) < 3:
        return None
    if coordinates[0] != coordinates[-1]:
        coordinates.append(coordinates[0])
    try:
        return normalize_geometry({"type": "Polygon", "coordinates": [coordinates]})
    except AssetValidationError:
        return None


def _legacy_asset_for_site(db: Session, site_id: str, actor_id: str | None) -> Asset:
    asset = (
        db.query(Asset)
        .filter(Asset.legacy_source == "site", Asset.legacy_source_id == site_id)
        .one_or_none()
    )
    if asset is not None:
        return asset
    site = db.get(Site, site_id)
    if site is None:
        raise AcquisitionError("asset_not_found", "Legacy site asset was not found")
    return synchronize_legacy_site(db, site, actor_user_id=actor_id)


def synchronize_legacy_drone_mission(
    db: Session, mission: DroneMission, *, actor: User | None = None
) -> Acquisition:
    asset = _legacy_asset_for_site(db, mission.site_id, actor.id if actor else mission.created_by)
    acquisition = (
        db.query(Acquisition)
        .filter(
            Acquisition.legacy_source == "drone_mission",
            Acquisition.legacy_source_id == mission.id,
        )
        .one_or_none()
    )
    now = utc_now()
    if acquisition is None:
        acquisition_id = str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"geovision:acquisition:drone_mission:{mission.id}")
        )
        acquisition = Acquisition(
            id=acquisition_id,
            acquisition_number=f"GVAQ-LEGACY-{acquisition_id[:12].upper()}",
            organization_id=mission.company_id,
            workspace_id=asset.workspace_id,
            asset_id=asset.id,
            acquisition_type=AcquisitionType.DRONE.value,
            title=mission.name,
            state=_legacy_state(mission.status),
            provenance_json="{}",
            metadata_json="{}",
            output_refs_json="[]",
            legacy_source="drone_mission",
            legacy_source_id=mission.id,
            created_by_user_id=mission.created_by,
            updated_by_user_id=actor.id if actor else mission.created_by,
            created_at=mission.created_at or now,
            updated_at=mission.updated_at or now,
        )
        db.add(acquisition)
        db.flush()
    previous_state = acquisition.state
    aircraft = db.get(DroneAircraft, mission.aircraft_id)
    acquisition.title = mission.name
    acquisition.state = _legacy_state(mission.status)
    acquisition.provider_code = _provider_code(aircraft.provider if aircraft else None)
    acquisition.provider_reference = mission.provider_reference
    acquisition.provenance_json = _json(
        {"source": "legacy_drone_mission", "source_id": mission.id}
    )
    acquisition.metadata_json = _json(
        {"legacy_mission_type": mission.mission_type, "route": _array(mission.route_json)}
    )
    acquisition.updated_at = mission.updated_at or now
    acquisition.updated_by_user_id = actor.id if actor else mission.created_by
    if previous_state != acquisition.state:
        acquisition.lifecycle_version = int(acquisition.lifecycle_version or 0) + 1
    detail = _drone_detail(db, acquisition.id)
    if detail is None:
        detail = DroneAcquisitionDetail(
            acquisition_id=acquisition.id,
            created_at=mission.created_at or now,
        )
    detail.aircraft_id = mission.aircraft_id
    detail.mission_requirements_json = _json(
        {
            "mission_type": mission.mission_type,
            "altitude_m": mission.altitude_m,
            "speed_mps": float(mission.speed_mps),
            "front_overlap_percent": mission.front_overlap_percent,
            "side_overlap_percent": mission.side_overlap_percent,
            "safety_checklist": _object(mission.checklist_json),
        }
    )
    boundary = _legacy_boundary(mission.boundary_json)
    detail.capture_area_geojson = _json(boundary) if boundary else None
    detail.flight_metadata_json = _json(
        {
            "legacy_route": _array(mission.route_json),
            "connection_mode": aircraft.connection_mode if aircraft else None,
        }
    )
    detail.updated_at = acquisition.updated_at
    db.add_all([acquisition, detail])
    db.flush()
    return acquisition


def synchronize_legacy_inspection(
    db: Session, inspection: AssetInspection, *, actor: User | None = None
) -> Acquisition:
    from app.models import IotAsset

    generic_asset = (
        db.query(Asset)
        .filter(
            Asset.legacy_source == "iot_asset",
            Asset.legacy_source_id == inspection.asset_id,
        )
        .one_or_none()
    )
    if generic_asset is None:
        legacy_asset = db.get(IotAsset, inspection.asset_id)
        if legacy_asset is None:
            raise AcquisitionError("asset_not_found", "Legacy inspection asset was not found")
        generic_asset = synchronize_legacy_iot_asset(
            db, legacy_asset, actor_user_id=actor.id if actor else inspection.inspected_by
        )
    acquisition = (
        db.query(Acquisition)
        .filter(
            Acquisition.legacy_source == "asset_inspection",
            Acquisition.legacy_source_id == inspection.id,
        )
        .one_or_none()
    )
    now = inspection.created_at or utc_now()
    if acquisition is None:
        acquisition_id = str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"geovision:acquisition:asset_inspection:{inspection.id}")
        )
        acquisition = Acquisition(
            id=acquisition_id,
            acquisition_number=f"GVAQ-LEGACY-{acquisition_id[:12].upper()}",
            organization_id=inspection.company_id,
            workspace_id=generic_asset.workspace_id,
            asset_id=generic_asset.id,
            acquisition_type=AcquisitionType.MANUAL_INSPECTION.value,
            title=f"{inspection.category.replace('_', ' ').title()} inspection",
            description=inspection.notes,
            state=AcquisitionState.COMPLETED.value,
            provider_code="geovision_manual",
            provenance_json=_json(
                {"source": "legacy_asset_inspection", "source_id": inspection.id}
            ),
            metadata_json=_json(
                {
                    "category": inspection.category,
                    "result": inspection.result,
                    "checklist": _object(inspection.checklist_json),
                    "location": {
                        "latitude": inspection.latitude,
                        "longitude": inspection.longitude,
                    },
                }
            ),
            output_refs_json=_json(
                [
                    {"type": "photo", "reference": reference}
                    for reference in _array(inspection.photos_json)
                ]
            ),
            started_at=now,
            captured_at=now,
            completed_at=now,
            legacy_source="asset_inspection",
            legacy_source_id=inspection.id,
            created_by_user_id=inspection.inspected_by,
            updated_by_user_id=actor.id if actor else inspection.inspected_by,
            created_at=now,
            updated_at=now,
        )
        db.add(acquisition)
        db.flush()
    return acquisition


def acquisition_for_legacy(
    db: Session, *, source: str, source_id: str
) -> Acquisition | None:
    return (
        db.query(Acquisition)
        .filter(Acquisition.legacy_source == source, Acquisition.legacy_source_id == source_id)
        .one_or_none()
    )


def asset_acquisition_outputs(db: Session, asset_id: str) -> list[dict[str, Any]]:
    """Common sector-facing output feed with no capture-resource dependency."""

    rows = list_acquisitions(db, asset_id=asset_id, chronological=True, limit=10_000)
    outputs: list[dict[str, Any]] = []
    for row in rows:
        references = _array(row.output_refs_json)
        if not references or row.state not in {
            "DATA_CAPTURED",
            "PROCESSING",
            "COMPLETED",
        }:
            continue
        outputs.append(
            {
                "acquisition_id": row.id,
                "acquisition_type": row.acquisition_type,
                "captured_at": _iso(row.captured_at),
                "state": row.state,
                "outputs": references,
            }
        )
    return outputs


__all__ = [
    "acquisition_for_legacy",
    "acquisition_out",
    "asset_acquisition_outputs",
    "create_acquisition",
    "list_acquisitions",
    "synchronize_legacy_drone_mission",
    "synchronize_legacy_inspection",
    "transition_acquisition",
    "update_acquisition",
]
