"""Tenant-safe read models for the customer mobile experience."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Query, Session

from app.core.time import utc_now
from app.models import (
    Account,
    AccountMember,
    Action,
    Asset,
    Company,
    IotDevice,
    MobileServiceRequest,
    Order,
    Report,
    Site,
    User,
)
from app.modules.actions.schemas import ActionOut
from app.modules.actions.services import action_payload
from app.modules.identity.domain import AuthorizationContext
from app.modules.operations.mobile_schemas import (
    MobileActionBucketsOut,
    MobileAttentionOut,
    MobileExperienceOut,
    MobileHomeOut,
    MobileLatestResultOut,
    MobilePriorityItemOut,
    MobileServiceResultOut,
    MobileWorkspaceOut,
)
from app.modules.organizations.domain import (
    MembershipStatus,
    WorkspaceStatus,
    permission_granted,
)
from app.modules.organizations.services import (
    OrganizationAccessError,
    resolve_workspace_access,
)
from app.modules.reports.domain import ReportStatus


ActionBucket = Literal["critical", "attention", "scheduled", "completed"]

_CAPABILITY_RULES: tuple[tuple[str, str], ...] = (
    ("assets", "asset:read"),
    ("actions", "asset:read"),
    ("services", "workspace:read"),
    ("reports", "report:read"),
    ("devices", "asset:read"),
    ("team", "organization:manage_members"),
    ("billing", "billing:read"),
    ("settings", "profile:read"),
    ("support", "profile:read"),
)
_HIDDEN_ACTION_STATUSES = frozenset({"DISMISSED", "CANCELLED"})
_CRITICAL_PRIORITIES = frozenset({"CRITICAL", "URGENT"})
_CLOSED_SERVICE_STATUSES = frozenset(
    {"COMPLETED", "CANCELLED", "REJECTED", "DELIVERED"}
)
_RESULT_SERVICE_STATUSES = frozenset({"COMPLETED", "DELIVERED", "RESULTS_READY"})
_ACTIVE_ORDER_END_STATES = frozenset({"DELIVERED", "COMPLETED", "CANCELLED", "FAILED"})
_RESULT_ORDER_STATES = frozenset({"RESULTS_READY", "DELIVERED", "COMPLETED"})
_PRIORITY_RANK = {"CRITICAL": 0, "URGENT": 1, "HIGH": 2, "MEDIUM": 3, "LOW": 4}


class MobileExperienceError(RuntimeError):
    """Stable mobile read-model failure that does not disclose tenant data."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _json_list(value: object) -> list[str]:
    parsed: object = value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
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


def _customer_workspace(
    db: Session,
    context: AuthorizationContext,
    *,
    permission: str,
) -> tuple[Account, Company]:
    """Re-check selected customer context at the projection boundary."""

    if not context.active_workspace_id or not context.active_organization_id:
        raise MobileExperienceError("workspace_required", "An active workspace is required")
    # Platform staff have their own Operations surface.  A customer projection
    # requires an actual customer membership role, even for platform admins.
    if not context.workspace_role and not context.organization_role:
        raise MobileExperienceError("customer_workspace_required", "Customer workspace access denied")
    if not permission_granted(context.permissions, permission):
        raise MobileExperienceError("capability_denied", "Mobile capability access denied")
    workspace = db.get(Account, context.active_workspace_id)
    organization = db.get(Company, context.active_organization_id)
    if (
        workspace is None
        or organization is None
        or workspace.organization_id != organization.id
        or workspace.status != WorkspaceStatus.ACTIVE.value
        or organization.status == "suspended"
    ):
        raise MobileExperienceError("workspace_not_found", "Workspace is not accessible")
    return workspace, organization


def require_mobile_workspace(
    db: Session,
    *,
    context: AuthorizationContext,
    permission: str,
) -> tuple[Account, Company]:
    """Public boundary for mobile write routes that need selected context."""

    return _customer_workspace(db, context, permission=permission)


def _capabilities(
    db: Session,
    context: AuthorizationContext,
    workspace: Account | None,
) -> list[str]:
    if (
        not context.active_workspace_id
        or not context.active_organization_id
        or (not context.workspace_role and not context.organization_role)
    ):
        return []
    if workspace is None:
        return []
    modules = {item.casefold() for item in _json_list(workspace.modules_enabled)}
    feature_available = {
        "reports": bool(
            modules.intersection({"reports", "kpi", "analytics", "intelligence"})
            or db.query(Report.id)
            .filter(
                Report.organization_id == context.active_organization_id,
                Report.workspace_id == context.active_workspace_id,
                Report.status == ReportStatus.PUBLISHED.value,
            )
            .first()
        ),
        "devices": bool(
            modules.intersection({"devices", "iot", "monitoring", "sensors"})
            or _workspace_devices_query(db, context).first()
        ),
    }
    result: list[str] = []
    for capability, required in _CAPABILITY_RULES:
        if not permission_granted(context.permissions, required):
            continue
        if capability in feature_available and not feature_available[capability]:
            continue
        result.append(capability)
    return result


def mobile_experience(
    db: Session,
    *,
    user: User,
    context: AuthorizationContext,
) -> MobileExperienceOut:
    """Return selected context and every explicitly accessible workspace."""

    candidates = (
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
    workspaces: list[MobileWorkspaceOut] = []
    for workspace, _, organization in candidates:
        try:
            access = resolve_workspace_access(
                db,
                user,
                requested_workspace_id=workspace.id,
            )
        except OrganizationAccessError:
            # A stale workspace membership must never re-enable a suspended or
            # revoked organization membership.
            continue
        if access.workspace is None or access.workspace_membership is None:
            continue
        workspaces.append(
            MobileWorkspaceOut(
                id=workspace.id,
                organization_id=organization.id,
                name=workspace.name,
                organization_name=organization.name,
                role=access.workspace_membership.role,
                sector=workspace.sector_focus,
                modules_enabled=_json_list(workspace.modules_enabled),
            )
        )
    selected_workspace = next(
        (row for row, _, _ in candidates if row.id == context.active_workspace_id),
        None,
    )
    return MobileExperienceOut(
        active_workspace_id=context.active_workspace_id,
        active_organization_id=context.active_organization_id,
        permissions=sorted(context.permissions),
        capabilities=_capabilities(db, context, selected_workspace),
        workspaces=workspaces,
    )


def action_bucket(
    action: Action,
    *,
    now: datetime | None = None,
) -> ActionBucket | None:
    current = now or utc_now()
    if action.status == "COMPLETED":
        return "completed"
    if action.status in _HIDDEN_ACTION_STATUSES:
        return None
    if action.priority in _CRITICAL_PRIORITIES:
        return "critical"
    if action.due_date is not None and action.due_date > current:
        return "scheduled"
    return "attention"


def _action_sort_key(action: Action, *, now: datetime) -> tuple[object, ...]:
    bucket_rank = {"critical": 0, "attention": 1, "scheduled": 2, "completed": 3}
    bucket = action_bucket(action, now=now)
    if bucket is None:
        return (4, -(action.updated_at or action.created_at).timestamp())
    if bucket == "completed":
        return (bucket_rank[bucket], -(action.updated_at or action.created_at).timestamp())
    return (
        bucket_rank[bucket],
        _PRIORITY_RANK.get(action.priority, 5),
        action.due_date or datetime.max,
        action.created_at,
        action.id,
    )


def _workspace_action_rows(
    db: Session,
    context: AuthorizationContext,
    *,
    asset_id: str | None = None,
) -> list[Action]:
    _customer_workspace(db, context, permission="asset:read")
    if asset_id is not None:
        asset = db.get(Asset, asset_id)
        if (
            asset is None
            or asset.organization_id != context.active_organization_id
            or asset.workspace_id != context.active_workspace_id
            or asset.status == "archived"
        ):
            raise MobileExperienceError("asset_not_found", "Asset was not found")
    now = utc_now()
    query = db.query(Action).filter(
        Action.organization_id == context.active_organization_id,
        Action.workspace_id == context.active_workspace_id,
    )
    if asset_id is not None:
        query = query.filter(Action.asset_id == asset_id)
    rows = query.all()
    return sorted(rows, key=lambda row: _action_sort_key(row, now=now))


def mobile_action_buckets(
    db: Session,
    *,
    context: AuthorizationContext,
    per_bucket_limit: int = 100,
    asset_id: str | None = None,
) -> MobileActionBucketsOut:
    now = utc_now()
    grouped: dict[ActionBucket, list[ActionOut]] = {
        "critical": [],
        "attention": [],
        "scheduled": [],
        "completed": [],
    }
    for row in _workspace_action_rows(db, context, asset_id=asset_id):
        bucket = action_bucket(row, now=now)
        if bucket is None:
            continue
        if len(grouped[bucket]) < per_bucket_limit:
            grouped[bucket].append(ActionOut(**action_payload(row)))
    return MobileActionBucketsOut(**grouped)


def _workspace_service_requests_query(
    db: Session,
    context: AuthorizationContext,
) -> Query:
    query = (
        db.query(MobileServiceRequest)
        .join(Site, Site.id == MobileServiceRequest.site_id)
        .outerjoin(
            Asset,
            and_(
                Asset.legacy_source == "site",
                Asset.legacy_source_id == Site.id,
                Asset.organization_id == Site.company_id,
            ),
        )
        .filter(
            Site.company_id == context.active_organization_id,
        )
    )
    if _selected_is_only_active_workspace(db, context):
        return query.filter(
            or_(
                and_(
                    Asset.workspace_id == context.active_workspace_id,
                    Asset.status != "archived",
                ),
                Asset.id.is_(None),
            )
        )
    return query.filter(
        Asset.workspace_id == context.active_workspace_id,
        Asset.status != "archived",
    )


def _selected_is_only_active_workspace(
    db: Session,
    context: AuthorizationContext,
) -> bool:
    workspace_ids = [
        row[0]
        for row in db.query(Account.id)
        .filter(
            Account.organization_id == context.active_organization_id,
            Account.status == WorkspaceStatus.ACTIVE.value,
        )
        .limit(2)
        .all()
    ]
    return workspace_ids == [context.active_workspace_id]


def list_mobile_sites(
    db: Session,
    *,
    context: AuthorizationContext,
) -> list[Site]:
    """List only legacy sites mapped into the selected canonical workspace."""

    _customer_workspace(db, context, permission="asset:read")
    query = (
        db.query(Site)
        .outerjoin(
            Asset,
            and_(
                Asset.legacy_source == "site",
                Asset.legacy_source_id == Site.id,
                Asset.organization_id == Site.company_id,
            ),
        )
        .filter(
            Site.company_id == context.active_organization_id,
        )
    )
    if _selected_is_only_active_workspace(db, context):
        query = query.filter(
            or_(
                and_(
                    Asset.workspace_id == context.active_workspace_id,
                    Asset.status != "archived",
                ),
                Asset.id.is_(None),
            )
        )
    else:
        query = query.filter(
            Asset.workspace_id == context.active_workspace_id,
            Asset.status != "archived",
        )
    return query.order_by(Site.updated_at.desc(), Site.id.asc()).all()


def get_mobile_site(
    db: Session,
    *,
    context: AuthorizationContext,
    site_id: str,
    permission: str = "asset:read",
) -> Site:
    _customer_workspace(db, context, permission=permission)
    query = (
        db.query(Site)
        .outerjoin(
            Asset,
            and_(
                Asset.legacy_source == "site",
                Asset.legacy_source_id == Site.id,
                Asset.organization_id == Site.company_id,
            ),
        )
        .filter(
            Site.id == site_id,
            Site.company_id == context.active_organization_id,
        )
    )
    if _selected_is_only_active_workspace(db, context):
        query = query.filter(
            or_(
                and_(
                    Asset.workspace_id == context.active_workspace_id,
                    Asset.status != "archived",
                ),
                Asset.id.is_(None),
            )
        )
    else:
        query = query.filter(
            Asset.workspace_id == context.active_workspace_id,
            Asset.status != "archived",
        )
    row = query.one_or_none()
    if row is None:
        raise MobileExperienceError("site_not_found", "Site was not found")
    return row


def list_mobile_service_requests(
    db: Session,
    *,
    context: AuthorizationContext,
) -> list[MobileServiceRequest]:
    _customer_workspace(db, context, permission="workspace:read")
    return (
        _workspace_service_requests_query(db, context)
        .order_by(MobileServiceRequest.created_at.desc(), MobileServiceRequest.id.asc())
        .all()
    )


def get_mobile_service_request(
    db: Session,
    *,
    context: AuthorizationContext,
    request_id: str,
) -> MobileServiceRequest:
    _customer_workspace(db, context, permission="workspace:read")
    row = (
        _workspace_service_requests_query(db, context)
        .filter(MobileServiceRequest.id == request_id)
        .one_or_none()
    )
    if row is None:
        raise MobileExperienceError(
            "service_request_not_found",
            "Service request was not found",
        )
    return row


def mobile_service_result(
    db: Session,
    *,
    context: AuthorizationContext,
    request: MobileServiceRequest,
) -> MobileServiceResultOut | None:
    """Return a result only when a durable request-to-report link exists.

    ``MobileServiceRequest`` does not currently store such a link.  A report
    on the same asset is only correlated context and may belong to unrelated
    work, so the customer projection must fail closed until the model records
    an explicit report identifier.
    """

    del db, context, request
    return None


def _workspace_orders_query(db: Session, context: AuthorizationContext) -> Query:
    return db.query(Order).filter(
        or_(
            Order.organization_id == context.active_organization_id,
            and_(
                Order.organization_id.is_(None),
                Order.company_id == context.active_organization_id,
            ),
        ),
        Order.workspace_id == context.active_workspace_id,
    )


def _active_service_count(db: Session, context: AuthorizationContext) -> int:
    service_requests = (
        _workspace_service_requests_query(db, context)
        .filter(func.upper(MobileServiceRequest.status).notin_(_CLOSED_SERVICE_STATUSES))
        .count()
    )
    service_orders = (
        _workspace_orders_query(db, context)
        .filter(
            Order.order_type.in_({"SERVICE", "MONITORING"}),
            Order.fulfilment_status.notin_(_ACTIVE_ORDER_END_STATES),
        )
        .count()
    )
    return service_requests + service_orders


def _workspace_devices_query(db: Session, context: AuthorizationContext) -> Query:
    asset_ids = db.query(Asset.id).filter(
        Asset.organization_id == context.active_organization_id,
        Asset.workspace_id == context.active_workspace_id,
        Asset.status != "archived",
    )
    site_ids = db.query(Asset.legacy_source_id).filter(
        Asset.organization_id == context.active_organization_id,
        Asset.workspace_id == context.active_workspace_id,
        Asset.legacy_source == "site",
        Asset.legacy_source_id.is_not(None),
        Asset.status != "archived",
    )
    return db.query(IotDevice).filter(
        IotDevice.company_id == context.active_organization_id,
        or_(
            IotDevice.core_asset_id.in_(asset_ids),
            IotDevice.site_id.in_(site_ids),
        ),
    )


def _offline_device_count(db: Session, context: AuthorizationContext) -> int:
    return (
        _workspace_devices_query(db, context)
        .filter(
            or_(
                IotDevice.connectivity_status == "offline",
                IotDevice.status == "offline",
            ),
        )
        .count()
    )


def _latest_result(
    db: Session,
    context: AuthorizationContext,
) -> MobileLatestResultOut | None:
    candidates: list[MobileLatestResultOut] = []
    report = (
        db.query(Report)
        .filter(
            Report.organization_id == context.active_organization_id,
            Report.workspace_id == context.active_workspace_id,
            Report.status == ReportStatus.PUBLISHED.value,
        )
        .order_by(Report.published_at.desc(), Report.updated_at.desc())
        .first()
    )
    if report is not None:
        completed_at = report.published_at or report.updated_at
        candidates.append(
            MobileLatestResultOut(
                target_type="REPORT",
                target_id=report.id,
                title=report.title,
                summary=f"{report.report_type.replace('_', ' ').title()} report is ready.",
                completed_at=completed_at,
            )
        )

    service = (
        _workspace_service_requests_query(db, context)
        .filter(func.upper(MobileServiceRequest.status).in_(_RESULT_SERVICE_STATUSES))
        .order_by(MobileServiceRequest.updated_at.desc())
        .first()
    )
    if service is not None:
        candidates.append(
            MobileLatestResultOut(
                target_type="SERVICE_RESULT",
                target_id=service.id,
                title=service.site_name,
                summary=service.description,
                completed_at=service.updated_at,
            )
        )

    order = (
        _workspace_orders_query(db, context)
        .filter(Order.fulfilment_status.in_(_RESULT_ORDER_STATES))
        .order_by(Order.updated_at.desc())
        .first()
    )
    if order is not None:
        completed_at = order.completed_at or order.actual_end or order.updated_at
        candidates.append(
            MobileLatestResultOut(
                target_type="ORDER",
                target_id=order.id,
                title=order.order_number or f"GeoVision order {order.id[:8]}",
                summary=f"{order.order_type.title()} order {order.fulfilment_status.replace('_', ' ').lower()}.",
                completed_at=completed_at,
            )
        )
    return max(candidates, key=lambda item: item.completed_at) if candidates else None


def mobile_home(
    db: Session,
    *,
    context: AuthorizationContext,
    priority_limit: int = 20,
) -> MobileHomeOut:
    workspace, organization = _customer_workspace(db, context, permission="asset:read")
    now = utc_now()
    rows = _workspace_action_rows(db, context)
    buckets: dict[ActionBucket, list[Action]] = {
        "critical": [],
        "attention": [],
        "scheduled": [],
        "completed": [],
    }
    for row in rows:
        bucket = action_bucket(row, now=now)
        if bucket is not None:
            buckets[bucket].append(row)
    recent_cutoff = now - timedelta(days=30)
    completed_recent = sum(
        1
        for row in buckets["completed"]
        if row.status == "COMPLETED"
        and row.completed_at is not None
        and row.completed_at >= recent_cutoff
    )
    priority_rows = (
        buckets["critical"] + buckets["attention"] + buckets["scheduled"]
    )[:priority_limit]
    return MobileHomeOut(
        workspace_id=workspace.id,
        organization_name=organization.name,
        workspace_name=workspace.name,
        attention=MobileAttentionOut(
            critical=len(buckets["critical"]),
            attention=len(buckets["attention"]),
            scheduled=len(buckets["scheduled"]),
            completed_recent=completed_recent,
            active_services=_active_service_count(db, context),
            offline_devices=_offline_device_count(db, context),
        ),
        priority_items=[
            MobilePriorityItemOut(
                id=row.id,
                target_type="ACTION",
                target_id=row.id,
                title=row.title,
                summary=row.description,
                severity=row.priority,
                due_at=row.due_date,
            )
            for row in priority_rows
        ],
        latest_result=_latest_result(db, context),
        updated_at=now,
    )


__all__ = [
    "MobileExperienceError",
    "action_bucket",
    "get_mobile_site",
    "get_mobile_service_request",
    "list_mobile_service_requests",
    "list_mobile_sites",
    "mobile_action_buckets",
    "mobile_experience",
    "mobile_home",
    "mobile_service_result",
    "require_mobile_workspace",
]
