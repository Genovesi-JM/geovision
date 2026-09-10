"""Application services for tenant-scoped generic spatial assets."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models import Account, Asset, AuditLog, IotAsset, Site, User
from app.modules.assets.domain import (
    AssetStatus,
    AssetValidationError,
    geometry_bounds,
    geometry_display_center,
    normalize_asset_type,
    normalize_geometry,
    normalize_sector,
    point_geometry,
)
from app.modules.identity.domain import AuthorizationContext
from app.modules.organizations.domain import permission_granted
from app.modules.organizations.services import sole_active_workspace_id


class AssetAccessError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


_SENSITIVE_METADATA_KEY = re.compile(
    r"(^|_)(password|passwd|secret|token|api_key|authorization|credential|private_key)($|_)",
    re.IGNORECASE,
)


def _validate_metadata_keys(value: Any, *, path: str = "metadata") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized_key = re.sub(r"[^A-Za-z0-9]+", "_", str(key)).strip("_")
            if _SENSITIVE_METADATA_KEY.search(normalized_key):
                raise AssetAccessError(
                    "invalid_metadata",
                    f"{path} must not contain credential or secret fields",
                )
            _validate_metadata_keys(nested, path=f"{path}.{key}")
    elif isinstance(value, list):
        for nested in value:
            _validate_metadata_keys(nested, path=path)


def _json_object(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_dump(value: Mapping[str, Any]) -> str:
    _validate_metadata_keys(value)
    try:
        encoded = json.dumps(
            dict(value),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise AssetAccessError(
            "invalid_metadata",
            "metadata must contain JSON-compatible values",
        ) from exc
    if len(encoded.encode("utf-8")) > 65_536:
        raise AssetAccessError(
            "invalid_metadata",
            "metadata must not exceed 64 KiB",
        )
    return encoded


def _require_context(
    context: AuthorizationContext,
    permission: str,
) -> tuple[str, str]:
    if not context.active_organization_id or not context.active_workspace_id:
        raise AssetAccessError(
            "workspace_required",
            "Select an active workspace before accessing assets",
        )
    if not permission_granted(context.permissions, permission):
        raise AssetAccessError("asset_access_denied", "Asset access denied")
    return context.active_organization_id, context.active_workspace_id


def _workspace_scope_matches(
    db: Session,
    *,
    organization_id: str,
    row_workspace_id: str | None,
    selected_workspace_id: str,
) -> bool:
    """Resolve legacy NULL scope only when the organization has one workspace."""

    return row_workspace_id == selected_workspace_id or (
        row_workspace_id is None
        and sole_active_workspace_id(db, organization_id) == selected_workspace_id
    )


def _apply_geometry(asset: Asset, geometry: Mapping[str, Any] | None) -> None:
    normalized = normalize_geometry(geometry)
    asset.geometry_geojson = (
        json.dumps(normalized, separators=(",", ":"), sort_keys=True)
        if normalized is not None
        else None
    )
    bounds = geometry_bounds(normalized)
    center = geometry_display_center(normalized)
    if bounds is None:
        asset.bbox_min_x = None
        asset.bbox_min_y = None
        asset.bbox_max_x = None
        asset.bbox_max_y = None
        asset.centroid_latitude = None
        asset.centroid_longitude = None
        return
    asset.bbox_min_x, asset.bbox_min_y, asset.bbox_max_x, asset.bbox_max_y = bounds
    if center is not None:
        asset.centroid_latitude, asset.centroid_longitude = center


def _validate_parent(
    db: Session,
    *,
    parent_asset_id: str | None,
    organization_id: str,
    workspace_id: str,
    asset_id: str | None = None,
) -> Asset | None:
    if parent_asset_id is None:
        return None
    if parent_asset_id == asset_id:
        raise AssetAccessError("invalid_parent", "An asset cannot be its own parent")
    parent = db.get(Asset, parent_asset_id)
    if (
        parent is None
        or parent.organization_id != organization_id
        or not _workspace_scope_matches(
            db,
            organization_id=organization_id,
            row_workspace_id=parent.workspace_id,
            selected_workspace_id=workspace_id,
        )
        or parent.status == AssetStatus.ARCHIVED.value
    ):
        raise AssetAccessError("parent_not_found", "Parent asset was not found")

    seen = {asset_id} if asset_id else set()
    cursor = parent
    while cursor is not None:
        if cursor.id in seen:
            raise AssetAccessError(
                "hierarchy_cycle", "Asset hierarchy cannot contain a cycle"
            )
        seen.add(cursor.id)
        cursor = (
            db.get(Asset, cursor.parent_asset_id) if cursor.parent_asset_id else None
        )
    return parent


def _audit(
    db: Session,
    *,
    actor: User,
    action: str,
    asset: Asset,
    details: Mapping[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=actor.id,
            user_email=actor.email,
            action=action,
            resource_type="asset",
            resource_id=asset.id,
            details=_json_dump(
                {
                    "organization_id": asset.organization_id,
                    "workspace_id": asset.workspace_id,
                    **dict(details or {}),
                }
            ),
        )
    )


def create_asset(
    db: Session,
    *,
    actor: User,
    context: AuthorizationContext,
    values: Mapping[str, Any],
) -> Asset:
    organization_id, workspace_id = _require_context(context, "asset:create")
    parent_asset_id = values.get("parent_asset_id")
    _validate_parent(
        db,
        parent_asset_id=parent_asset_id,
        organization_id=organization_id,
        workspace_id=workspace_id,
    )
    status = values.get("status", AssetStatus.ACTIVE)
    status_value = status.value if isinstance(status, AssetStatus) else str(status)
    if status_value == AssetStatus.ARCHIVED.value:
        raise AssetAccessError(
            "invalid_status",
            "Create the asset before archiving it",
        )
    asset = Asset(
        id=str(uuid.uuid4()),
        organization_id=organization_id,
        workspace_id=workspace_id,
        parent_asset_id=parent_asset_id,
        sector=normalize_sector(str(values["sector"])),
        asset_type=normalize_asset_type(str(values["asset_type"])),
        name=str(values["name"]).strip(),
        description=values.get("description"),
        status=status_value,
        external_reference=values.get("external_reference"),
        location_label=values.get("location_label"),
        metadata_json=_json_dump(values.get("metadata") or {}),
        created_by_user_id=actor.id,
        updated_by_user_id=actor.id,
    )
    _apply_geometry(asset, values.get("geometry"))
    db.add(asset)
    db.flush()
    _audit(
        db,
        actor=actor,
        action="asset.created",
        asset=asset,
        details={"sector": asset.sector, "asset_type": asset.asset_type},
    )
    return asset


def get_asset(
    db: Session,
    *,
    context: AuthorizationContext,
    asset_id: str,
    permission: str = "asset:read",
) -> Asset:
    organization_id, workspace_id = _require_context(context, permission)
    asset = db.get(Asset, asset_id)
    if (
        asset is None
        or asset.organization_id != organization_id
        or not _workspace_scope_matches(
            db,
            organization_id=organization_id,
            row_workspace_id=asset.workspace_id,
            selected_workspace_id=workspace_id,
        )
    ):
        raise AssetAccessError("asset_not_found", "Asset was not found")
    return asset


def list_assets(
    db: Session,
    *,
    context: AuthorizationContext,
    organization_id: str | None = None,
    workspace_id: str | None = None,
    parent_asset_id: str | None = None,
    root_only: bool = False,
    sector: str | None = None,
    asset_type: str | None = None,
    status: str | None = None,
    include_archived: bool = False,
    bbox: tuple[float, float, float, float] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Asset]:
    active_organization_id, active_workspace_id = _require_context(
        context, "asset:read"
    )
    if organization_id is not None and organization_id != active_organization_id:
        raise AssetAccessError("asset_access_denied", "Asset access denied")
    if workspace_id is not None and workspace_id != active_workspace_id:
        raise AssetAccessError("asset_access_denied", "Asset access denied")

    workspace_filters = [Asset.workspace_id == active_workspace_id]
    if sole_active_workspace_id(db, active_organization_id) == active_workspace_id:
        workspace_filters.append(Asset.workspace_id.is_(None))
    query = db.query(Asset).filter(
        Asset.organization_id == active_organization_id,
        or_(*workspace_filters),
    )
    if parent_asset_id is not None:
        query = query.filter(Asset.parent_asset_id == parent_asset_id)
    elif root_only:
        query = query.filter(Asset.parent_asset_id.is_(None))
    if sector:
        query = query.filter(Asset.sector == normalize_sector(sector))
    if asset_type:
        query = query.filter(Asset.asset_type == normalize_asset_type(asset_type))
    if status:
        query = query.filter(Asset.status == AssetStatus(status).value)
    elif not include_archived:
        query = query.filter(Asset.status != AssetStatus.ARCHIVED.value)
    if bbox is not None:
        min_x, min_y, max_x, max_y = bbox
        if min_x > max_x or min_y > max_y:
            raise AssetAccessError(
                "invalid_bbox",
                "bbox minimum coordinates must not exceed maximum coordinates",
            )
        query = query.filter(
            Asset.bbox_max_x.is_not(None),
            Asset.bbox_max_y.is_not(None),
            Asset.bbox_min_x <= max_x,
            Asset.bbox_max_x >= min_x,
            Asset.bbox_min_y <= max_y,
            Asset.bbox_max_y >= min_y,
        )
    return (
        query.order_by(Asset.created_at.asc(), Asset.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def update_asset(
    db: Session,
    *,
    actor: User,
    context: AuthorizationContext,
    asset_id: str,
    values: Mapping[str, Any],
    changed_fields: set[str],
) -> Asset:
    asset = get_asset(
        db,
        context=context,
        asset_id=asset_id,
        permission="asset:update",
    )
    if asset.status == AssetStatus.ARCHIVED.value:
        raise AssetAccessError("asset_archived", "Archived assets cannot be edited")
    if "status" in changed_fields and values.get("status") == AssetStatus.ARCHIVED:
        raise AssetAccessError("invalid_status", "Use the archive endpoint")
    if "parent_asset_id" in changed_fields:
        _validate_parent(
            db,
            parent_asset_id=values.get("parent_asset_id"),
            organization_id=asset.organization_id,
            workspace_id=asset.workspace_id or context.active_workspace_id or "",
            asset_id=asset.id,
        )
        asset.parent_asset_id = values.get("parent_asset_id")
    if "sector" in changed_fields:
        asset.sector = normalize_sector(str(values["sector"]))
    if "asset_type" in changed_fields:
        asset.asset_type = normalize_asset_type(str(values["asset_type"]))
    for field in (
        "name",
        "description",
        "external_reference",
        "location_label",
    ):
        if field in changed_fields:
            value = values.get(field)
            setattr(asset, field, value.strip() if isinstance(value, str) else value)
    if "status" in changed_fields and values.get("status") is not None:
        status = values["status"]
        asset.status = status.value if isinstance(status, AssetStatus) else str(status)
    if "geometry" in changed_fields:
        _apply_geometry(asset, values.get("geometry"))
    if "metadata" in changed_fields:
        asset.metadata_json = _json_dump(values.get("metadata") or {})
    asset.updated_by_user_id = actor.id
    asset.updated_at = utc_now()
    db.add(asset)
    db.flush()
    _audit(
        db,
        actor=actor,
        action="asset.updated",
        asset=asset,
        details={"fields": sorted(changed_fields)},
    )
    return asset


def archive_asset(
    db: Session,
    *,
    actor: User,
    context: AuthorizationContext,
    asset_id: str,
) -> Asset:
    asset = get_asset(
        db,
        context=context,
        asset_id=asset_id,
        permission="asset:archive",
    )
    active_children = (
        db.query(Asset)
        .filter(
            Asset.parent_asset_id == asset.id,
            Asset.status != AssetStatus.ARCHIVED.value,
        )
        .count()
    )
    if active_children:
        raise AssetAccessError(
            "active_children",
            "Archive or move child assets before archiving this asset",
        )
    if asset.status != AssetStatus.ARCHIVED.value:
        asset.status = AssetStatus.ARCHIVED.value
        asset.archived_at = utc_now()
        asset.archived_by_user_id = actor.id
        asset.updated_by_user_id = actor.id
        asset.updated_at = asset.archived_at
        db.add(asset)
        db.flush()
        _audit(db, actor=actor, action="asset.archived", asset=asset)
    return asset


def asset_payload(db: Session, asset: Asset) -> dict[str, Any]:
    geometry = normalize_geometry(asset.geometry_geojson)
    bbox = None
    if asset.bbox_min_x is not None:
        bbox = [
            asset.bbox_min_x,
            asset.bbox_min_y,
            asset.bbox_max_x,
            asset.bbox_max_y,
        ]
    center = None
    if asset.centroid_latitude is not None and asset.centroid_longitude is not None:
        center = {
            "lat": asset.centroid_latitude,
            "lng": asset.centroid_longitude,
        }
    return {
        "id": asset.id,
        "organization_id": asset.organization_id,
        "workspace_id": asset.workspace_id,
        "parent_asset_id": asset.parent_asset_id,
        "sector": asset.sector,
        "asset_type": asset.asset_type,
        "name": asset.name,
        "description": asset.description,
        "status": asset.status,
        "external_reference": asset.external_reference,
        "location_label": asset.location_label,
        "geometry": geometry,
        "bbox": bbox,
        "center": center,
        "metadata": _json_object(asset.metadata_json),
        "children_count": db.query(Asset)
        .filter(Asset.parent_asset_id == asset.id)
        .count(),
        "legacy_source": asset.legacy_source,
        "legacy_source_id": asset.legacy_source_id,
        "archived_at": asset.archived_at,
        "created_at": asset.created_at,
        "updated_at": asset.updated_at,
    }


def _legacy_workspace_id(db: Session, organization_id: str) -> str | None:
    workspace = (
        db.query(Account)
        .filter(
            Account.organization_id == organization_id,
            Account.status == "active",
        )
        .order_by(Account.created_at.asc(), Account.id.asc())
        .first()
    )
    return workspace.id if workspace else None


def _legacy_asset(
    db: Session,
    *,
    source: str,
    source_id: str,
) -> Asset | None:
    return (
        db.query(Asset)
        .filter(
            Asset.legacy_source == source,
            Asset.legacy_source_id == source_id,
        )
        .one_or_none()
    )


def _compatible_asset_id(db: Session, source: str, source_id: str) -> str:
    if db.get(Asset, source_id) is None:
        return source_id
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"geovision:asset:{source}:{source_id}"))


def synchronize_legacy_site(
    db: Session,
    site: Site,
    *,
    actor_user_id: str | None = None,
    workspace_id: str | None = None,
) -> Asset:
    """Mirror the legacy Site facade into the generic Asset table."""

    asset = _legacy_asset(db, source="site", source_id=site.id)
    if asset is None:
        asset = Asset(
            id=_compatible_asset_id(db, "site", site.id),
            organization_id=site.company_id,
            workspace_id=workspace_id or _legacy_workspace_id(db, site.company_id),
            legacy_source="site",
            legacy_source_id=site.id,
            created_by_user_id=actor_user_id,
            created_at=site.created_at or utc_now(),
        )
    asset.organization_id = site.company_id
    if workspace_id is not None:
        asset.workspace_id = workspace_id
    if not site.sector:
        raise AssetValidationError(
            "Legacy site requires sector review before it can become an asset"
        )
    asset.sector = normalize_sector(site.sector)
    asset.asset_type = "SITE"
    asset.name = site.name
    asset.description = site.description
    asset.status = "active" if site.is_active else "inactive"
    asset.location_label = (
        ", ".join(
            part for part in (site.municipality, site.province, site.country) if part
        )
        or None
    )
    asset.metadata_json = _json_dump(
        {
            "legacy": {
                "source": "site",
                "country": site.country,
                "province": site.province,
                "municipality": site.municipality,
                "area_hectares": float(site.area_hectares)
                if site.area_hectares is not None
                else None,
            }
        }
    )
    asset.updated_by_user_id = actor_user_id
    asset.updated_at = site.updated_at or utc_now()
    _apply_geometry(asset, point_geometry(site.latitude, site.longitude))
    db.add(asset)
    db.flush()
    return asset


def synchronize_legacy_iot_asset(
    db: Session,
    legacy_asset: IotAsset,
    *,
    actor_user_id: str | None = None,
) -> Asset:
    """Mirror existing IoT/construction assets while preserving their IDs."""

    parent = _legacy_asset(db, source="site", source_id=legacy_asset.site_id)
    if parent is None:
        site = db.get(Site, legacy_asset.site_id)
        parent = synchronize_legacy_site(db, site) if site is not None else None
    asset = _legacy_asset(db, source="iot_asset", source_id=legacy_asset.id)
    if asset is None:
        asset = Asset(
            id=_compatible_asset_id(db, "iot_asset", legacy_asset.id),
            organization_id=legacy_asset.company_id,
            workspace_id=parent.workspace_id
            if parent
            else _legacy_workspace_id(db, legacy_asset.company_id),
            legacy_source="iot_asset",
            legacy_source_id=legacy_asset.id,
            created_by_user_id=actor_user_id,
            created_at=legacy_asset.created_at or utc_now(),
        )
    asset.parent_asset_id = parent.id if parent else None
    asset.sector = parent.sector if parent else "INFRASTRUCTURE"
    asset.asset_type = normalize_asset_type(legacy_asset.asset_type or "EQUIPMENT")
    asset.name = legacy_asset.name
    asset.status = "active"
    asset.external_reference = legacy_asset.external_reference
    metadata = _json_object(legacy_asset.metadata_json)
    metadata["legacy"] = {"source": "iot_asset", "site_id": legacy_asset.site_id}
    asset.metadata_json = _json_dump(metadata)
    asset.updated_by_user_id = actor_user_id
    asset.updated_at = utc_now()
    _apply_geometry(
        asset, point_geometry(legacy_asset.latitude, legacy_asset.longitude)
    )
    db.add(asset)
    db.flush()
    return asset


def archive_legacy_asset(db: Session, *, source: str, source_id: str) -> None:
    asset = _legacy_asset(db, source=source, source_id=source_id)
    if asset is not None and asset.status != AssetStatus.ARCHIVED.value:
        asset.status = AssetStatus.ARCHIVED.value
        asset.archived_at = utc_now()
        asset.updated_at = asset.archived_at
        db.add(asset)


__all__ = [
    "AssetAccessError",
    "archive_asset",
    "archive_legacy_asset",
    "asset_payload",
    "create_asset",
    "get_asset",
    "list_assets",
    "synchronize_legacy_iot_asset",
    "synchronize_legacy_site",
    "update_asset",
]
