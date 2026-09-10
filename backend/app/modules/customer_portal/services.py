"""Tenant-safe customer web portal projections.

This module deliberately does not import internal Operations services.  It
combines customer-owned domain records into read-only navigation and dashboard
contracts after re-checking the selected workspace boundary.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
import json
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Query, Session

from app.core.time import utc_now
from app.models import (
    Account,
    AccountMember,
    Action,
    Asset,
    CatalogItem,
    Company,
    CompanyEntitlement,
    IotDevice,
    KpiDefinition,
    KpiValue,
    MobileServiceRequest,
    Observation,
    Order,
    Report,
    User,
)
from app.modules.analytics.domain import KpiStatus, worst_kpi_status
from app.modules.analytics.services import kpi_payload
from app.modules.assets.domain import (
    AssetValidationError,
    geometry_bounds,
    geometry_display_center,
    normalize_geometry,
    point_geometry,
)
from app.modules.customer_portal.schemas import (
    PortalAssetSummaryOut,
    PortalCapability,
    PortalExperienceOut,
    PortalMapLayersOut,
    PortalWorkspaceOut,
)
from app.modules.identity.domain import AuthorizationContext
from app.modules.organizations.domain import (
    MembershipStatus,
    WorkspaceStatus,
    permission_granted,
)
from app.modules.organizations.services import (
    OrganizationAccessError,
    resolve_workspace_access,
)
from app.sector_taxonomy import normalize_capability_modules, public_sector_values


class CustomerPortalError(RuntimeError):
    """Stable customer-portal error that does not disclose another tenant."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


_CAPABILITY_ORDER: tuple[PortalCapability, ...] = (
    "overview",
    "assets",
    "actions",
    "monitoring",
    "services",
    "map",
    "analytics",
    "reports",
    "catalog",
    "orders",
    "billing",
    "team",
    "integrations",
    "settings",
)

_NAVIGATION = (
    (
        "overview",
        "Overview",
        (("overview", "Overview", "/dashboard.html"),),
    ),
    (
        "operations",
        "Operations",
        (
            ("assets", "Assets", "/dashboard.html?view=assets"),
            ("actions", "Actions", "/dashboard.html?view=actions"),
            ("monitoring", "Monitoring", "/dashboard.html?view=monitoring"),
            ("services", "Services", "/dashboard.html?view=services"),
        ),
    ),
    (
        "intelligence",
        "Intelligence",
        (
            ("map", "Map", "/dashboard.html?view=map"),
            ("analytics", "Analytics", "/dashboard.html?view=analytics"),
            ("reports", "Reports", "/dashboard.html?view=reports"),
        ),
    ),
    (
        "commercial",
        "Commercial",
        (
            ("catalog", "Products & Services", "/loja.html"),
            ("orders", "Orders", "/minhas-compras.html"),
            ("billing", "Billing", "/dashboard.html?view=billing"),
        ),
    ),
    (
        "management",
        "Management",
        (
            ("team", "Team", "/dashboard.html?view=team"),
            (
                "integrations",
                "Integrations",
                "/dashboard.html?view=integrations",
            ),
            ("settings", "Settings", "/dashboard.html?view=settings"),
        ),
    ),
)

_DESTINATIONS = (
    (
        "WORKSPACE",
        "/dashboard.html?view=overview&workspace_id={workspace_id}",
        "overview",
    ),
    ("ASSET", "/dashboard.html?view=asset&target_id={target_id}", "assets"),
    ("ACTION", "/dashboard.html?view=action&target_id={target_id}", "actions"),
    ("SERVICE", "/dashboard.html?view=service&target_id={target_id}", "services"),
    (
        "SERVICE_RESULT",
        "/dashboard.html?view=service-result&target_id={target_id}",
        "services",
    ),
    ("ORDER", "/dashboard.html?view=order&target_id={target_id}", "orders"),
    ("REPORT", "/dashboard.html?view=report&target_id={target_id}", "reports"),
)

_MODULES = {
    "assets": frozenset({"assets", "projects"}),
    "actions": frozenset({"actions", "alerts", "intelligence"}),
    "monitoring": frozenset({"monitoring", "iot", "devices", "sensors"}),
    "services": frozenset({"services", "store", "projects", "orders"}),
    "map": frozenset({"map", "maps", "gis"}),
    "analytics": frozenset({"kpi", "analytics", "intelligence"}),
    "reports": frozenset({"reports", "kpi", "analytics", "intelligence"}),
    "catalog": frozenset({"store", "catalog", "products", "services"}),
    "orders": frozenset({"store", "orders", "commercial", "services"}),
    "integrations": frozenset({"integrations", "erp"}),
}


def _json_list(value: str | None) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    result: list[str] = []
    for item in parsed:
        normalized = str(item).strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _synthetic_label(
    value: str | Mapping[str, Any] | None,
    *,
    source: str | None = None,
) -> dict[str, Any]:
    if isinstance(value, Mapping):
        parsed: Mapping[str, Any] = value
    else:
        try:
            candidate = json.loads(value or "{}")
        except (TypeError, ValueError):
            candidate = {}
        parsed = candidate if isinstance(candidate, Mapping) else {}
    marker = parsed.get("demo_seed")
    if not isinstance(marker, Mapping) or marker.get("synthetic") is not True:
        return {
            "synthetic": False,
            "synthetic_marker": None,
            "synthetic_notice": None,
            "source": source,
        }
    return {
        "synthetic": True,
        "synthetic_marker": str(marker.get("marker") or "") or None,
        "synthetic_notice": str(marker.get("notice") or "") or None,
        "source": source,
    }


def _customer_workspace(
    db: Session,
    context: AuthorizationContext,
) -> tuple[Account, Company]:
    if not context.active_workspace_id or not context.active_organization_id:
        raise CustomerPortalError(
            "workspace_required", "Select an active customer workspace"
        )
    # Platform roles do not grant access to the customer portal. Staff must
    # also hold a real customer membership when testing this surface.
    if not context.workspace_role and not context.organization_role:
        raise CustomerPortalError(
            "customer_workspace_required", "Customer workspace access denied"
        )
    if not permission_granted(context.permissions, "workspace:read"):
        raise CustomerPortalError("portal_access_denied", "Portal access denied")
    workspace = db.get(Account, context.active_workspace_id)
    organization = db.get(Company, context.active_organization_id)
    if (
        workspace is None
        or organization is None
        or workspace.organization_id != organization.id
        or workspace.status != WorkspaceStatus.ACTIVE.value
        or organization.status == "suspended"
    ):
        raise CustomerPortalError("workspace_not_found", "Workspace was not found")
    return workspace, organization


def _workspace_out(
    workspace: Account,
    organization: Company,
    role: str,
) -> PortalWorkspaceOut:
    sectors = public_sector_values(workspace.sector_focus)
    return PortalWorkspaceOut(
        id=workspace.id,
        organization_id=organization.id,
        name=workspace.name,
        organization_name=organization.name,
        role=role,
        # Keep the historical singular field as a primary-sector projection.
        # The complete selection is exposed separately and never encoded as a
        # comma-delimited pseudo identifier.
        sector=sectors[0] if sectors else "",
        sectors=sectors,
        modules_enabled=normalize_capability_modules(
            _json_list(workspace.modules_enabled)
        ),
    )


def _accessible_workspaces(db: Session, user: User) -> list[PortalWorkspaceOut]:
    rows = (
        db.query(Account, AccountMember, Company)
        .join(AccountMember, AccountMember.account_id == Account.id)
        .join(Company, Company.id == Account.organization_id)
        .filter(
            AccountMember.user_id == user.id,
            AccountMember.status == MembershipStatus.ACTIVE.value,
            Account.status == WorkspaceStatus.ACTIVE.value,
            Company.status != "suspended",
        )
        .order_by(Company.name.asc(), Account.name.asc(), Account.id.asc())
        .all()
    )
    result: list[PortalWorkspaceOut] = []
    for workspace, _, organization in rows:
        try:
            access = resolve_workspace_access(
                db,
                user,
                requested_workspace_id=workspace.id,
            )
        except OrganizationAccessError:
            # A stale AccountMember must not reveal workspace metadata after
            # the canonical organization membership has been revoked.
            continue
        if access.workspace is None or access.workspace_membership is None:
            continue
        result.append(
            _workspace_out(workspace, organization, access.workspace_membership.role)
        )
    return result


def _assets_query(
    db: Session,
    *,
    organization_id: str,
    workspace_id: str,
) -> Query:
    # Unlike compatibility endpoints, the portal is exact-scope only. A NULL
    # workspace cannot be assigned safely once an organization has a portfolio.
    return db.query(Asset).filter(
        Asset.organization_id == organization_id,
        Asset.workspace_id == workspace_id,
        Asset.status != "archived",
    )


def _selected_assets(
    db: Session,
    *,
    organization_id: str,
    workspace_id: str,
    asset_id: str | None = None,
) -> list[Asset]:
    assets = (
        _assets_query(
            db,
            organization_id=organization_id,
            workspace_id=workspace_id,
        )
        .order_by(Asset.created_at.asc(), Asset.id.asc())
        .all()
    )
    if asset_id is None:
        return assets
    by_id = {asset.id: asset for asset in assets}
    if asset_id not in by_id:
        raise CustomerPortalError("asset_not_found", "Asset was not found")
    selected = {asset_id}
    changed = True
    while changed:
        changed = False
        for asset in assets:
            if asset.parent_asset_id in selected and asset.id not in selected:
                selected.add(asset.id)
                changed = True
    return [asset for asset in assets if asset.id in selected]


def _asset_tree(assets: Iterable[Asset]) -> list[dict[str, Any]]:
    ordered = list(assets)
    visible_ids = {asset.id for asset in ordered}
    children: dict[str | None, list[Asset]] = defaultdict(list)
    for asset in ordered:
        parent = asset.parent_asset_id if asset.parent_asset_id in visible_ids else None
        children[parent].append(asset)

    def node(asset: Asset, ancestors: frozenset[str]) -> dict[str, Any]:
        # Persisted constraints prevent a direct self-cycle. The ancestor guard
        # also keeps corrupt legacy graphs from recursing indefinitely.
        nested = []
        if asset.id not in ancestors:
            nested = [
                node(child, ancestors | {asset.id})
                for child in children.get(asset.id, ())
                if child.id not in ancestors
            ]
        return {
            "id": asset.id,
            "parent_asset_id": asset.parent_asset_id,
            "name": asset.name,
            "sector": asset.sector,
            "asset_type": asset.asset_type,
            "status": asset.status,
            **_synthetic_label(
                asset.metadata_json,
                source=asset.legacy_source,
            ),
            "children": nested,
        }

    return [node(asset, frozenset()) for asset in children.get(None, ())]


def _workspace_devices_query(
    db: Session,
    *,
    organization_id: str,
    workspace_id: str,
    asset_ids: Iterable[str] | None = None,
) -> Query:
    scoped_assets = _assets_query(
        db,
        organization_id=organization_id,
        workspace_id=workspace_id,
    )
    if asset_ids is not None:
        values = tuple(asset_ids)
        if not values:
            return db.query(IotDevice).filter(False)
        scoped_assets = scoped_assets.filter(Asset.id.in_(values))
    core_asset_ids = scoped_assets.with_entities(Asset.id)
    site_ids = scoped_assets.filter(
        Asset.legacy_source == "site",
        Asset.legacy_source_id.is_not(None),
    ).with_entities(Asset.legacy_source_id)
    return db.query(IotDevice).filter(
        IotDevice.company_id == organization_id,
        or_(
            IotDevice.core_asset_id.in_(core_asset_ids),
            IotDevice.site_id.in_(site_ids),
        ),
    )


def _content_facts(
    db: Session,
    *,
    workspace: Account,
    organization: Company,
    assets: list[Asset],
) -> dict[str, int]:
    asset_ids = tuple(asset.id for asset in assets)
    site_ids = tuple(
        asset.legacy_source_id
        for asset in assets
        if asset.legacy_source == "site" and asset.legacy_source_id
    )

    def count_for(model, *filters) -> int:
        if not asset_ids and model in {KpiValue, Observation}:
            return 0
        return db.query(model).filter(*filters).count()

    return {
        "assets": len(assets),
        "spatial_assets": sum(
            _safe_geometry(asset.geometry_geojson) is not None for asset in assets
        ),
        "actions": count_for(
            Action,
            Action.organization_id == organization.id,
            Action.workspace_id == workspace.id,
        ),
        "kpis": count_for(
            KpiValue,
            KpiValue.organization_id == organization.id,
            KpiValue.workspace_id == workspace.id,
            KpiValue.asset_id.in_(asset_ids) if asset_ids else False,
        ),
        "observations": count_for(
            Observation,
            Observation.organization_id == organization.id,
            Observation.workspace_id == workspace.id,
            Observation.asset_id.in_(asset_ids) if asset_ids else False,
            Observation.validation_status == "VALIDATED",
        ),
        "reports": count_for(
            Report,
            Report.organization_id == organization.id,
            Report.workspace_id == workspace.id,
            Report.status == "PUBLISHED",
        ),
        "devices": _workspace_devices_query(
            db,
            organization_id=organization.id,
            workspace_id=workspace.id,
        ).count(),
        "services": (
            db.query(MobileServiceRequest)
            .filter(MobileServiceRequest.site_id.in_(site_ids))
            .count()
            if site_ids
            else 0
        ),
        "orders": db.query(Order)
        .filter(
            Order.workspace_id == workspace.id,
            or_(
                Order.organization_id == organization.id,
                Order.company_id == organization.id,
            ),
        )
        .count(),
        "catalog": db.query(CatalogItem)
        .filter(CatalogItem.status == "PUBLISHED")
        .count(),
    }


def _subscription(db: Session, organization: Company) -> dict[str, Any]:
    entitlement = (
        db.query(CompanyEntitlement)
        .filter(CompanyEntitlement.company_id == organization.id)
        .one_or_none()
    )
    now = utc_now()
    if entitlement is None:
        status = "pending" if organization.status == "pending" else "active"
        return {
            "plan": organization.subscription_plan or "trial",
            "status": status,
            "tier": organization.subscription_plan or "trial",
            "valid_until": None,
            "source": "organization_plan",
        }
    valid_until = entitlement.valid_until
    days = (valid_until.date() - now.date()).days if valid_until else None
    if days is not None and days < 0:
        status = "expired"
    elif days is not None and days <= 30:
        status = "expiring"
    else:
        status = "active"
    return {
        "plan": organization.subscription_plan or entitlement.tier,
        "status": status,
        "tier": entitlement.tier,
        "valid_until": valid_until,
        "source": "entitlement",
    }


def _capability_flags(
    *,
    context: AuthorizationContext,
    modules: set[str],
    content: dict[str, int],
    subscription: dict[str, Any],
) -> dict[PortalCapability, bool]:
    def can(permission: str) -> bool:
        return permission_granted(context.permissions, permission)

    def module(capability: PortalCapability) -> bool:
        return bool(modules.intersection(_MODULES.get(capability, ())))

    advanced_active = subscription["status"] != "expired"
    plan = str(subscription["tier"] or subscription["plan"]).casefold()
    integration_plan = plan in {
        "professional",
        "growth",
        "scale",
        "enterprise",
        "custom",
    }
    flags: dict[PortalCapability, bool] = {
        "overview": can("workspace:read"),
        "assets": can("asset:read") and (module("assets") or content["assets"] > 0),
        "actions": can("asset:read") and (module("actions") or content["actions"] > 0),
        "monitoring": can("asset:read")
        and advanced_active
        and (module("monitoring") or content["devices"] > 0),
        "services": can("workspace:read")
        and (module("services") or content["services"] > 0 or content["orders"] > 0),
        "map": can("asset:read") and (module("map") or content["spatial_assets"] > 0),
        "analytics": can("asset:read")
        and advanced_active
        and (module("analytics") or content["kpis"] > 0 or content["observations"] > 0),
        "reports": can("report:read") and (module("reports") or content["reports"] > 0),
        "catalog": can("workspace:read")
        and module("catalog")
        and content["catalog"] > 0,
        "orders": can("workspace:read") and (module("orders") or content["orders"] > 0),
        "billing": can("billing:read"),
        "team": can("organization:manage_members"),
        "integrations": can("organization:manage")
        and advanced_active
        and integration_plan
        # Legacy Integration rows are organization-wide and cannot safely
        # enable an arbitrary workspace. Phase 32 can add exact-scope content.
        and module("integrations"),
        "settings": can("workspace:manage") or can("organization:manage"),
    }
    return flags


def portal_experience(
    db: Session,
    *,
    user: User,
    context: AuthorizationContext,
) -> PortalExperienceOut:
    workspace, organization = _customer_workspace(db, context)
    assets = _selected_assets(
        db,
        organization_id=organization.id,
        workspace_id=workspace.id,
    )
    content = _content_facts(
        db,
        workspace=workspace,
        organization=organization,
        assets=assets,
    )
    subscription = _subscription(db, organization)
    modules = {item.casefold() for item in _json_list(workspace.modules_enabled)}
    flags = _capability_flags(
        context=context,
        modules=modules,
        content=content,
        subscription=subscription,
    )
    capabilities = [name for name in _CAPABILITY_ORDER if flags[name]]
    navigation = []
    for group_key, group_label, items in _NAVIGATION:
        visible = [
            {
                "key": key,
                "label": label,
                "route": route,
                "capability": key,
            }
            for key, label, route in items
            if flags[key]
        ]
        if visible:
            navigation.append(
                {"key": group_key, "label": group_label, "items": visible}
            )
    active_role = context.workspace_role or context.organization_role or "viewer"
    active_workspace = _workspace_out(workspace, organization, active_role)
    accessible = _accessible_workspaces(db, user)
    if active_workspace.id not in {item.id for item in accessible}:
        # Defensive fail-closed guard against platform-only contexts.
        raise CustomerPortalError(
            "customer_workspace_required", "Customer workspace access denied"
        )
    destinations = [
        {
            "target_type": target_type,
            "route_template": route_template,
            "capability": capability,
        }
        for target_type, route_template, capability in _DESTINATIONS
        if flags[capability]
    ]
    return PortalExperienceOut(
        active_workspace_id=workspace.id,
        active_organization_id=organization.id,
        organization_name=organization.name,
        active_workspace=active_workspace,
        permissions=sorted(context.permissions),
        capabilities=capabilities,
        feature_flags=flags,
        subscription=subscription,
        workspaces=accessible,
        navigation=navigation,
        asset_tree=_asset_tree(assets),
        deep_link_contract={"destinations": destinations},
    )


def _safe_geometry(value: str | dict[str, Any] | None) -> dict[str, Any] | None:
    try:
        return normalize_geometry(value)
    except (AssetValidationError, TypeError, ValueError):
        return None


def _safe_point(
    latitude: float | None, longitude: float | None
) -> dict[str, Any] | None:
    try:
        return point_geometry(latitude, longitude)
    except (AssetValidationError, TypeError, ValueError):
        # Historical device rows predate coordinate validation. One malformed
        # position must not make the entire customer map unavailable.
        return None


def _asset_center(asset: Asset) -> dict[str, float] | None:
    if asset.centroid_latitude is not None and asset.centroid_longitude is not None:
        return {
            "lat": float(asset.centroid_latitude),
            "lng": float(asset.centroid_longitude),
        }
    center = geometry_display_center(_safe_geometry(asset.geometry_geojson))
    return {"lat": center[0], "lng": center[1]} if center else None


def _asset_kpis(
    db: Session,
    *,
    asset: Asset,
    workspace_id: str,
) -> list[dict[str, Any]]:
    values = (
        db.query(KpiValue)
        .filter(
            KpiValue.organization_id == asset.organization_id,
            KpiValue.workspace_id == workspace_id,
            KpiValue.asset_id == asset.id,
        )
        .order_by(KpiValue.measured_at.desc())
        .all()
    )
    grouped: dict[str, list[KpiValue]] = defaultdict(list)
    for value in values:
        grouped[value.kpi_definition_id].append(value)
    if not grouped:
        return []
    definitions = (
        db.query(KpiDefinition)
        .filter(
            KpiDefinition.is_active.is_(True),
            KpiDefinition.id.in_(tuple(grouped)),
        )
        .all()
    )
    importance_order = {"PRIMARY": 0, "SECONDARY": 1, "TECHNICAL": 2}
    return [
        kpi_payload(definition, grouped.get(definition.id, ()))
        for definition in sorted(
            definitions,
            key=lambda item: (
                importance_order.get(item.importance, 3),
                item.sort_order,
                item.key,
            ),
        )
    ]


def _kpi_card(item: dict[str, Any]) -> dict[str, Any]:
    definition = item["definition"]
    return {
        "key": definition["key"],
        "name": definition["name"],
        "value": item["current"],
        "display_value": item["display_value"],
        "unit": definition["unit"],
        "status": item["status"],
        "confidence": item["confidence"],
        "measured_at": item["measured_at"],
        "change_percent": item["change_percent"],
        **_synthetic_label(
            item.get("provenance"),
            source=item.get("source"),
        ),
    }


def _asset_summary_item(
    db: Session,
    *,
    asset: Asset,
    workspace_id: str,
    child_counts: dict[str, int],
) -> dict[str, Any]:
    kpis = _asset_kpis(db, asset=asset, workspace_id=workspace_id)
    primary = [item for item in kpis if item["definition"]["importance"] == "PRIMARY"]
    secondary = [
        item for item in kpis if item["definition"]["importance"] == "SECONDARY"
    ]
    decision_inputs = primary or secondary or kpis
    decision_status = (
        worst_kpi_status([item["status"] for item in decision_inputs]).value
        if decision_inputs
        else KpiStatus.UNKNOWN.value
    )
    confidence_values = [
        float(item["confidence"])
        for item in decision_inputs
        if item["confidence"] is not None
    ]
    measured_values = [
        item["measured_at"]
        for item in decision_inputs
        if item["measured_at"] is not None
    ]
    observations = (
        db.query(Observation)
        .filter(
            Observation.organization_id == asset.organization_id,
            Observation.workspace_id == workspace_id,
            Observation.asset_id == asset.id,
            Observation.validation_status != "REJECTED",
        )
        .order_by(Observation.detected_at.desc())
        .all()
    )
    open_actions = (
        db.query(Action)
        .filter(
            Action.organization_id == asset.organization_id,
            Action.workspace_id == workspace_id,
            Action.asset_id == asset.id,
            Action.status.in_(("OPEN", "IN_PROGRESS")),
        )
        .count()
    )
    return {
        "id": asset.id,
        "parent_asset_id": asset.parent_asset_id,
        "name": asset.name,
        "sector": asset.sector,
        "asset_type": asset.asset_type,
        "status": asset.status,
        "location_label": asset.location_label,
        "center": _asset_center(asset),
        "children_count": child_counts.get(asset.id, 0),
        "decision_status": decision_status,
        "confidence": (
            sum(confidence_values) / len(confidence_values)
            if confidence_values
            else None
        ),
        "measured_at": max(measured_values) if measured_values else None,
        "primary_kpis": [_kpi_card(item) for item in primary],
        "secondary_kpis": [_kpi_card(item) for item in secondary],
        "technical_metric_count": sum(
            item["definition"]["importance"] == "TECHNICAL" for item in kpis
        ),
        "technical_metrics_path": f"/assets/{asset.id}/kpis?importance=TECHNICAL",
        "open_action_count": open_actions,
        "critical_observation_count": sum(
            item.severity == "CRITICAL" for item in observations
        ),
        "warning_observation_count": sum(
            item.severity == "WARNING" for item in observations
        ),
        "unvalidated_observation_count": sum(
            item.validation_status in {"UNVALIDATED", "NEEDS_REVIEW"}
            for item in observations
        ),
        "latest_observation_at": observations[0].detected_at if observations else None,
        "destination": {"target_type": "ASSET", "target_id": asset.id},
        **_synthetic_label(
            asset.metadata_json,
            source=asset.legacy_source,
        ),
    }


def portal_asset_summary(
    db: Session,
    *,
    context: AuthorizationContext,
    asset_id: str | None = None,
) -> PortalAssetSummaryOut:
    workspace, organization = _customer_workspace(db, context)
    if not permission_granted(context.permissions, "asset:read"):
        raise CustomerPortalError("portal_access_denied", "Asset access denied")
    assets = _selected_assets(
        db,
        organization_id=organization.id,
        workspace_id=workspace.id,
        asset_id=asset_id,
    )
    asset_ids = tuple(asset.id for asset in assets)
    child_counts: dict[str, int] = defaultdict(int)
    for asset in assets:
        if asset.parent_asset_id in asset_ids:
            child_counts[asset.parent_asset_id] += 1
    items = [
        _asset_summary_item(
            db,
            asset=asset,
            workspace_id=workspace.id,
            child_counts=child_counts,
        )
        for asset in assets
    ]
    published_reports = (
        db.query(Report)
        .filter(
            Report.organization_id == organization.id,
            Report.workspace_id == workspace.id,
            Report.status == "PUBLISHED",
            Report.asset_id.in_(asset_ids) if asset_ids else False,
        )
        .count()
    )
    devices = _workspace_devices_query(
        db,
        organization_id=organization.id,
        workspace_id=workspace.id,
        asset_ids=asset_ids,
    ).all()
    return PortalAssetSummaryOut(
        workspace_id=workspace.id,
        generated_at=utc_now(),
        totals={
            "assets": len(items),
            "active": sum(item["status"] == "active" for item in items),
            "attention": sum(
                item["decision_status"] in {"WATCH", "WARNING", "CRITICAL"}
                or item["open_action_count"] > 0
                or item["critical_observation_count"] > 0
                or item["warning_observation_count"] > 0
                for item in items
            ),
            "open_actions": sum(item["open_action_count"] for item in items),
            "published_reports": published_reports,
            "offline_devices": sum(
                str(device.connectivity_status).casefold() == "offline"
                for device in devices
            ),
        },
        items=items,
    )


def _feature(
    *,
    feature_id: str,
    geometry: dict[str, Any] | None,
    properties: dict[str, Any],
) -> dict[str, Any] | None:
    if geometry is None:
        return None
    return {
        "type": "Feature",
        "id": feature_id,
        "geometry": geometry,
        "properties": properties,
    }


def _map_bounds(features: Iterable[dict[str, Any]]) -> list[float] | None:
    bounds = [
        geometry_bounds(feature["geometry"])
        for feature in features
        if feature.get("geometry") is not None
    ]
    values = [value for value in bounds if value is not None]
    if not values:
        return None
    return [
        min(value[0] for value in values),
        min(value[1] for value in values),
        max(value[2] for value in values),
        max(value[3] for value in values),
    ]


def portal_map_layers(
    db: Session,
    *,
    context: AuthorizationContext,
    asset_id: str | None = None,
) -> PortalMapLayersOut:
    workspace, organization = _customer_workspace(db, context)
    if not permission_granted(context.permissions, "asset:read"):
        raise CustomerPortalError("portal_access_denied", "Map access denied")
    assets = _selected_assets(
        db,
        organization_id=organization.id,
        workspace_id=workspace.id,
        asset_id=asset_id,
    )
    asset_ids = tuple(asset.id for asset in assets)
    asset_by_id = {asset.id: asset for asset in assets}
    legacy_site_assets = {
        asset.legacy_source_id: asset.id
        for asset in assets
        if asset.legacy_source == "site" and asset.legacy_source_id
    }

    asset_features = []
    for asset in assets:
        feature = _feature(
            feature_id=asset.id,
            geometry=_safe_geometry(asset.geometry_geojson),
            properties={
                "target_type": "ASSET",
                "target_id": asset.id,
                "name": asset.name,
                "sector": asset.sector,
                "asset_type": asset.asset_type,
                "status": asset.status,
                "parent_asset_id": asset.parent_asset_id,
                **_synthetic_label(
                    asset.metadata_json,
                    source=asset.legacy_source,
                ),
            },
        )
        if feature:
            asset_features.append(feature)

    observations = (
        db.query(Observation)
        .filter(
            Observation.organization_id == organization.id,
            Observation.workspace_id == workspace.id,
            Observation.asset_id.in_(asset_ids) if asset_ids else False,
            Observation.validation_status == "VALIDATED",
            Observation.geometry_geojson.is_not(None),
        )
        .order_by(Observation.detected_at.desc(), Observation.id.asc())
        .all()
    )
    observation_features = []
    for observation in observations:
        feature = _feature(
            feature_id=observation.id,
            geometry=_safe_geometry(observation.geometry_geojson),
            properties={
                "target_type": "ASSET",
                "target_id": observation.asset_id,
                "observation_id": observation.id,
                "observation_type": observation.observation_type,
                "severity": observation.severity,
                "confidence": float(observation.confidence),
                "detected_at": observation.detected_at.isoformat(),
                **_synthetic_label(
                    observation.provenance_json,
                    source=observation.source,
                ),
            },
        )
        if feature:
            observation_features.append(feature)

    devices = (
        _workspace_devices_query(
            db,
            organization_id=organization.id,
            workspace_id=workspace.id,
            asset_ids=asset_ids,
        )
        .order_by(IotDevice.name.asc(), IotDevice.id.asc())
        .all()
    )
    device_features = []
    for device in devices:
        target_id = (
            device.core_asset_id
            if device.core_asset_id in asset_by_id
            else legacy_site_assets.get(device.site_id)
        )
        if not target_id:
            continue
        feature = _feature(
            feature_id=device.id,
            geometry=_safe_point(device.last_latitude, device.last_longitude),
            properties={
                "target_type": "ASSET",
                "target_id": target_id,
                "device_id": device.id,
                "name": device.name,
                "device_type": device.device_type,
                "status": device.status,
                "connectivity_status": device.connectivity_status,
                "last_seen_at": (
                    device.last_seen_at.isoformat() if device.last_seen_at else None
                ),
            },
        )
        if feature:
            device_features.append(feature)

    layers = [
        {
            "id": "assets",
            "label": "Assets",
            "kind": "ASSET",
            "default_visible": True,
            "geometry_types": sorted(
                {item["geometry"]["type"] for item in asset_features}
            ),
            "feature_collection": {
                "type": "FeatureCollection",
                "features": asset_features,
            },
        },
        {
            "id": "observations",
            "label": "Validated observations",
            "kind": "OBSERVATION",
            "default_visible": True,
            "geometry_types": sorted(
                {item["geometry"]["type"] for item in observation_features}
            ),
            "feature_collection": {
                "type": "FeatureCollection",
                "features": observation_features,
            },
        },
        {
            "id": "devices",
            "label": "Devices",
            "kind": "DEVICE",
            "default_visible": False,
            "geometry_types": sorted(
                {item["geometry"]["type"] for item in device_features}
            ),
            "feature_collection": {
                "type": "FeatureCollection",
                "features": device_features,
            },
        },
    ]
    all_features = [*asset_features, *observation_features, *device_features]
    return PortalMapLayersOut(
        workspace_id=workspace.id,
        generated_at=utc_now(),
        bounds=_map_bounds(all_features),
        layers=layers,
    )


__all__ = [
    "CustomerPortalError",
    "portal_asset_summary",
    "portal_experience",
    "portal_map_layers",
]
