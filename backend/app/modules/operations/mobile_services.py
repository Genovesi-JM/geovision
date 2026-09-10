"""Tenant-safe read models for the customer mobile experience."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import and_, func, or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Query, Session

from app.core.time import utc_now
from app.models import (
    Account,
    AccountMember,
    Acquisition,
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
from app.modules.assets.services import synchronize_legacy_site
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
from app.modules.operations.domain import (
    OperationsResourceError,
    ServiceRequestStatus,
    require_service_request_transition,
)
from app.modules.operations.schemas import ServiceRequestLinkUpdate
from app.modules.reports.domain import ReportStatus
from app.services.erp_sync import publish_account_event


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
_SERVICE_RESULT_STATES = frozenset(
    {
        ServiceRequestStatus.RESULTS_READY.value,
        ServiceRequestStatus.COMPLETED.value,
        ServiceRequestStatus.DELIVERED.value,
    }
)


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
        raise MobileExperienceError(
            "workspace_required", "An active workspace is required"
        )
    # Platform staff have their own Operations surface.  A customer projection
    # requires an actual customer membership role, even for platform admins.
    if not context.workspace_role and not context.organization_role:
        raise MobileExperienceError(
            "customer_workspace_required", "Customer workspace access denied"
        )
    if not permission_granted(context.permissions, permission):
        raise MobileExperienceError(
            "capability_denied", "Mobile capability access denied"
        )
    workspace = db.get(Account, context.active_workspace_id)
    organization = db.get(Company, context.active_organization_id)
    if (
        workspace is None
        or organization is None
        or workspace.organization_id != organization.id
        or workspace.status != WorkspaceStatus.ACTIVE.value
        or organization.status == "suspended"
    ):
        raise MobileExperienceError(
            "workspace_not_found", "Workspace is not accessible"
        )
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
        return (
            bucket_rank[bucket],
            -(action.updated_at or action.created_at).timestamp(),
        )
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
        .outerjoin(Site, Site.id == MobileServiceRequest.site_id)
        .outerjoin(
            Asset,
            and_(
                Asset.legacy_source == "site",
                Asset.legacy_source_id == Site.id,
                Asset.organization_id == Site.company_id,
            ),
        )
    )
    canonical = and_(
        MobileServiceRequest.organization_id == context.active_organization_id,
        MobileServiceRequest.workspace_id == context.active_workspace_id,
    )
    legacy_owner = and_(
        MobileServiceRequest.workspace_id.is_(None),
        or_(
            MobileServiceRequest.organization_id.is_(None),
            MobileServiceRequest.organization_id == context.active_organization_id,
        ),
        Site.company_id == context.active_organization_id,
    )
    if _selected_is_only_active_workspace(db, context):
        legacy_scope = and_(
            legacy_owner,
            or_(
                and_(
                    Asset.workspace_id == context.active_workspace_id,
                    Asset.status != "archived",
                ),
                and_(
                    Asset.workspace_id.is_(None),
                    Asset.status != "archived",
                ),
                Asset.id.is_(None),
            ),
        )
    else:
        legacy_scope = and_(
            legacy_owner,
            Asset.workspace_id == context.active_workspace_id,
            Asset.status != "archived",
        )
    return query.filter(
        or_(canonical, legacy_scope),
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
                and_(
                    Asset.workspace_id.is_(None),
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
                and_(
                    Asset.workspace_id.is_(None),
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


def _service_request_digest(
    *,
    site_id: str,
    request_type: str,
    urgency: str,
    description: str,
    attachments: list[str],
) -> str:
    canonical = json.dumps(
        {
            "attachments": attachments,
            "description": description,
            "request_type": request_type,
            "site_id": site_id,
            "urgency": urgency,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _idempotent_service_request(
    db: Session,
    *,
    organization_id: str,
    workspace_id: str,
    user_id: str,
    idempotency_key: str,
) -> MobileServiceRequest | None:
    """Load a keyed request using every column in its tenant-scoped identity."""

    return (
        db.query(MobileServiceRequest)
        .filter(
            MobileServiceRequest.organization_id == organization_id,
            MobileServiceRequest.workspace_id == workspace_id,
            MobileServiceRequest.user_id == user_id,
            MobileServiceRequest.idempotency_key == idempotency_key,
        )
        .one_or_none()
    )


def _resolve_service_request_replay(
    existing: MobileServiceRequest,
    *,
    digest: str,
) -> tuple[MobileServiceRequest, bool]:
    if existing.request_sha256 != digest:
        raise MobileExperienceError(
            "idempotency_conflict",
            "Idempotency key was already used for a different service request",
        )
    return existing, True


def create_mobile_service_request(
    db: Session,
    *,
    actor: User,
    context: AuthorizationContext,
    site_id: str,
    request_type: str,
    urgency: str,
    description: str,
    attachments: list[str],
    idempotency_key: str | None = None,
) -> tuple[MobileServiceRequest, bool]:
    """Create one canonical request, replaying an identical keyed request."""

    workspace, organization = _customer_workspace(
        db,
        context,
        permission="workspace:contribute",
    )
    normalized_key = idempotency_key.strip() if idempotency_key else None
    if idempotency_key is not None and not normalized_key:
        raise MobileExperienceError(
            "idempotency_conflict", "Idempotency key cannot be blank"
        )
    digest = _service_request_digest(
        site_id=site_id,
        request_type=request_type,
        urgency=urgency,
        description=description,
        attachments=attachments,
    )
    if normalized_key:
        existing = _idempotent_service_request(
            db,
            organization_id=organization.id,
            workspace_id=workspace.id,
            user_id=actor.id,
            idempotency_key=normalized_key,
        )
        if existing is not None:
            return _resolve_service_request_replay(existing, digest=digest)

    # Resolve the mutable Site only for a genuinely new request. A committed
    # keyed request remains replayable after the legacy Site is renamed,
    # archived, or deleted and its foreign key is set to NULL.
    site = get_mobile_site(
        db,
        context=context,
        site_id=site_id,
        permission="workspace:contribute",
    )

    asset = synchronize_legacy_site(
        db,
        site,
        actor_user_id=actor.id,
        workspace_id=workspace.id,
    )
    if (
        asset.organization_id != organization.id
        or asset.workspace_id != workspace.id
        or asset.status == "archived"
    ):
        raise MobileExperienceError("asset_not_found", "Asset was not found")
    item = MobileServiceRequest(
        user_id=actor.id,
        organization_id=organization.id,
        workspace_id=workspace.id,
        asset_id=asset.id,
        site_id=site.id,
        site_name=site.name,
        request_type=request_type,
        urgency=urgency,
        description=description,
        attachments_json=json.dumps(attachments),
        idempotency_key=normalized_key,
        request_sha256=digest if normalized_key else None,
        lifecycle_version=1,
    )
    if normalized_key:
        try:
            # Keep the unique insert inside a savepoint: another request may
            # win after the initial lookup, and rolling back the whole caller
            # transaction would discard unrelated request-scoped work.
            with db.begin_nested():
                db.add(item)
                db.flush([item])
        except IntegrityError as exc:
            db.expire_all()
            winner = _idempotent_service_request(
                db,
                organization_id=organization.id,
                workspace_id=workspace.id,
                user_id=actor.id,
                idempotency_key=normalized_key,
            )
            if winner is None:
                raise MobileExperienceError(
                    "idempotency_conflict",
                    "Concurrent service request could not be safely replayed",
                ) from exc
            return _resolve_service_request_replay(winner, digest=digest)
    else:
        db.add(item)
        db.flush()
    publish_account_event(
        db,
        company_id=organization.id,
        workspace_id=workspace.id,
        event_type="service_request.created",
        resource_type="service_request",
        resource_id=item.id,
        title=f"Pedido de serviço recebido: {site.name}",
        payload={
            "asset_id": asset.id,
            "workspace_id": workspace.id,
            "status": item.status,
            "urgency": item.urgency,
        },
    )
    return item, False


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
    """Resolve only an explicitly linked, published report in this workspace."""

    if (
        not request.report_id
        or not request.asset_id
        or not request.order_id
        or request.status not in _SERVICE_RESULT_STATES
        or request.organization_id != context.active_organization_id
        or request.workspace_id != context.active_workspace_id
    ):
        return None
    asset = db.get(Asset, request.asset_id)
    order = db.get(Order, request.order_id)
    if (
        asset is None
        or asset.organization_id != request.organization_id
        or asset.workspace_id != request.workspace_id
        or asset.status == "archived"
        or order is None
        or (order.organization_id or order.company_id) != request.organization_id
        or order.workspace_id != request.workspace_id
        or (order.user_id is not None and order.user_id != request.user_id)
    ):
        return None
    report = db.get(Report, request.report_id)
    if (
        report is None
        or report.organization_id != request.organization_id
        or report.workspace_id != request.workspace_id
        or report.asset_id != request.asset_id
        or report.status != ReportStatus.PUBLISHED.value
        or report.published_at is None
    ):
        return None
    acquisition = (
        db.get(Acquisition, report.acquisition_id) if report.acquisition_id else None
    )
    if (
        acquisition is None
        or acquisition.organization_id != request.organization_id
        or acquisition.workspace_id != request.workspace_id
        or acquisition.asset_id != request.asset_id
        or acquisition.order_id != request.order_id
    ):
        return None
    summary = f"{report.report_type.replace('_', ' ').title()} report is ready."
    try:
        narrative = json.loads(report.narrative_json or "{}")
    except (TypeError, ValueError):
        narrative = {}
    if isinstance(narrative, dict):
        candidate = narrative.get("executive_summary") or narrative.get("summary")
        if isinstance(candidate, str) and candidate.strip():
            summary = candidate.strip()[:500]
    return MobileServiceResultOut(
        title=report.title,
        summary=summary,
        report_id=report.id,
        asset_id=report.asset_id,
        published_at=report.published_at,
    )


def _request_matches_scope(
    db: Session,
    *,
    request: MobileServiceRequest,
    organization_id: str,
    workspace_id: str,
) -> bool:
    if (
        request.organization_id is not None
        and request.organization_id != organization_id
    ):
        return False
    if request.workspace_id is not None and request.workspace_id != workspace_id:
        return False
    if (
        request.organization_id == organization_id
        and request.workspace_id == workspace_id
    ):
        return True
    if not request.site_id:
        return False
    return (
        db.query(Asset.id)
        .filter(
            Asset.organization_id == organization_id,
            Asset.workspace_id == workspace_id,
            Asset.legacy_source == "site",
            Asset.legacy_source_id == request.site_id,
            Asset.status != "archived",
        )
        .first()
        is not None
    )


def link_mobile_service_request(
    db: Session,
    *,
    actor: User,
    request_id: str,
    data: ServiceRequestLinkUpdate,
) -> MobileServiceRequest:
    """Atomically attach canonical journey IDs after tenant validation."""

    del actor  # Authorization happens at the Operations transport boundary.
    workspace = db.get(Account, data.workspace_id)
    if (
        workspace is None
        or workspace.organization_id != data.organization_id
        or workspace.status != WorkspaceStatus.ACTIVE.value
    ):
        raise OperationsResourceError("workspace_not_found", "Workspace was not found")
    request = db.get(MobileServiceRequest, request_id)
    if request is None or not _request_matches_scope(
        db,
        request=request,
        organization_id=data.organization_id,
        workspace_id=data.workspace_id,
    ):
        raise OperationsResourceError(
            "service_request_not_found", "Service request was not found"
        )

    fields_set = data.model_fields_set
    asset_id = data.asset_id if "asset_id" in fields_set else request.asset_id
    order_id = data.order_id if "order_id" in fields_set else request.order_id
    report_id = data.report_id if "report_id" in fields_set else request.report_id
    if not asset_id:
        raise OperationsResourceError("asset_not_found", "Asset was not found")
    asset = db.get(Asset, asset_id)
    if (
        asset is None
        or asset.organization_id != data.organization_id
        or asset.workspace_id != data.workspace_id
        or asset.status == "archived"
        or (request.asset_id is not None and request.asset_id != asset.id)
    ):
        raise OperationsResourceError("asset_not_found", "Asset was not found")

    if order_id:
        order = db.get(Order, order_id)
        if (
            order is None
            or (order.organization_id or order.company_id) != data.organization_id
            or order.workspace_id != data.workspace_id
            or (order.user_id is not None and order.user_id != request.user_id)
        ):
            raise OperationsResourceError("order_not_found", "Order was not found")
    report = None
    if report_id:
        report = db.get(Report, report_id)
        if (
            report is None
            or report.organization_id != data.organization_id
            or report.workspace_id != data.workspace_id
            or report.asset_id != asset.id
        ):
            raise OperationsResourceError("report_not_found", "Report was not found")
    if order_id and report is not None:
        acquisition = (
            db.get(Acquisition, report.acquisition_id)
            if report.acquisition_id
            else None
        )
        if (
            acquisition is None
            or acquisition.organization_id != data.organization_id
            or acquisition.workspace_id != data.workspace_id
            or acquisition.asset_id != asset.id
            or acquisition.order_id != order_id
        ):
            raise OperationsResourceError(
                "service_request_link_mismatch",
                "Order and report do not belong to one acquisition journey",
            )

    target_status = data.status.value if data.status else request.status
    require_service_request_transition(request.status, target_status)
    target_progress = (
        data.progress_percent
        if "progress_percent" in fields_set
        else request.progress_percent
    )
    if target_progress is None:
        raise OperationsResourceError(
            "invalid_service_request_progress",
            "Service request progress cannot be null",
        )
    if target_progress < request.progress_percent:
        raise OperationsResourceError(
            "invalid_service_request_progress",
            "Service request progress cannot decrease",
        )
    if target_status in _SERVICE_RESULT_STATES:
        linked_report = db.get(Report, report_id) if report_id else None
        if (
            linked_report is None
            or linked_report.status != ReportStatus.PUBLISHED.value
            or linked_report.published_at is None
        ):
            raise OperationsResourceError(
                "report_not_ready",
                "A published report is required for result-ready status",
            )
        if not order_id:
            raise OperationsResourceError(
                "service_request_link_mismatch",
                "A result-ready service request requires its acquisition order",
            )
        target_progress = 100

    values: dict[str, object] = {
        "organization_id": data.organization_id,
        "workspace_id": data.workspace_id,
        "asset_id": asset.id,
        "order_id": order_id,
        "report_id": report_id,
        "status": target_status,
        "progress_percent": target_progress,
        "lifecycle_version": data.expected_version + 1,
        "updated_at": utc_now(),
    }
    if "assigned_team" in fields_set:
        values["assigned_team"] = (
            data.assigned_team.strip() if data.assigned_team else None
        )
    result = db.execute(
        update(MobileServiceRequest)
        .where(
            MobileServiceRequest.id == request.id,
            MobileServiceRequest.lifecycle_version == data.expected_version,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise OperationsResourceError(
            "version_conflict", "Service request was updated by another actor"
        )
    db.flush()
    db.refresh(request)
    publish_account_event(
        db,
        company_id=data.organization_id,
        workspace_id=data.workspace_id,
        event_type="service_request.updated",
        resource_type="service_request",
        resource_id=request.id,
        title=f"Pedido de serviço atualizado: {request.site_name}",
        payload={
            "workspace_id": data.workspace_id,
            "asset_id": request.asset_id,
            "order_id": request.order_id,
            "report_id": request.report_id,
            "status": request.status,
            "lifecycle_version": request.lifecycle_version,
        },
    )
    return request


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
        .filter(
            func.upper(MobileServiceRequest.status).notin_(_CLOSED_SERVICE_STATUSES)
        )
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
    priority_rows = (buckets["critical"] + buckets["attention"] + buckets["scheduled"])[
        :priority_limit
    ]
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
    "create_mobile_service_request",
    "get_mobile_site",
    "get_mobile_service_request",
    "list_mobile_service_requests",
    "list_mobile_sites",
    "link_mobile_service_request",
    "mobile_action_buckets",
    "mobile_experience",
    "mobile_home",
    "mobile_service_result",
    "require_mobile_workspace",
]
