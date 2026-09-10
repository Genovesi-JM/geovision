"""Recipient and contextual-target authorization for notification deep links."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import (
    Account,
    AccountMember,
    Action,
    Asset,
    CompanyUser,
    FulfilmentJob,
    Invitation,
    Notification,
    Order,
    Report,
    User,
)
from app.modules.identity.domain import AuthorizationContext
from app.modules.organizations.domain import (
    MembershipStatus,
    customer_permissions,
    permission_granted,
)
from app.modules.organizations.services import sole_active_workspace_id

from .domain import (
    NotificationError,
    NotificationTargetType,
    TARGET_REQUIRED_PERMISSION,
)


@dataclass(frozen=True, slots=True)
class ResolvedNotificationTarget:
    target_type: str
    target_id: str
    workspace_id: str | None
    app_path: str
    portal_path: str


_WORKSPACE_OWNED_TARGETS = frozenset(
    {
        NotificationTargetType.ASSET.value,
        NotificationTargetType.REPORT.value,
        NotificationTargetType.ACTION.value,
        NotificationTargetType.ORDER.value,
        NotificationTargetType.SHIPMENT.value,
        NotificationTargetType.SERVICE.value,
    }
)


def _workspace_owned_target_scope(
    db: Session,
    *,
    notification: Notification,
) -> tuple[bool, str | None]:
    """Validate and resolve the workspace for a workspace-owned notification."""

    target_type = str(notification.target_type or "NONE").upper()
    if target_type not in _WORKSPACE_OWNED_TARGETS:
        return True, notification.workspace_id
    if not notification.target_id:
        return False, None

    target_workspace_id: str | None
    target_organization_id: str | None
    if target_type == NotificationTargetType.ASSET.value:
        asset = db.get(Asset, notification.target_id)
        if asset is None:
            return False, None
        target_workspace_id = asset.workspace_id
        target_organization_id = asset.organization_id
    elif target_type == NotificationTargetType.REPORT.value:
        report = db.get(Report, notification.target_id)
        if report is None:
            return False, None
        target_workspace_id = report.workspace_id
        target_organization_id = report.organization_id
    elif target_type == NotificationTargetType.ACTION.value:
        action = db.get(Action, notification.target_id)
        if action is None:
            return False, None
        target_workspace_id = action.workspace_id
        target_organization_id = action.organization_id
    elif target_type in {
        NotificationTargetType.ORDER.value,
        NotificationTargetType.SHIPMENT.value,
    }:
        order = db.get(Order, notification.target_id)
        if order is None:
            return False, None
        target_workspace_id = order.workspace_id
        target_organization_id = order.organization_id or order.company_id
    else:
        job = db.get(FulfilmentJob, notification.target_id)
        order = db.get(Order, job.order_id) if job else None
        if order is None:
            return False, None
        target_workspace_id = order.workspace_id
        target_organization_id = order.organization_id or order.company_id

    if target_organization_id != notification.organization_id:
        return False, None

    notification_workspace_id = notification.workspace_id
    if notification_workspace_id is None or target_workspace_id is None:
        sole_workspace_id = sole_active_workspace_id(db, notification.organization_id)
        if sole_workspace_id is None:
            return False, None
        if notification_workspace_id not in (None, sole_workspace_id):
            return False, None
        if target_workspace_id not in (None, sole_workspace_id):
            return False, None
        return True, sole_workspace_id

    if notification_workspace_id != target_workspace_id:
        return False, None
    return True, notification_workspace_id


def _active_scope_permissions(
    db: Session,
    *,
    context: AuthorizationContext,
    organization_id: str,
    workspace_id: str | None,
) -> frozenset[str]:
    permissions = set(context.permissions if context.internal_roles else ())
    membership = (
        db.query(CompanyUser)
        .filter(
            CompanyUser.company_id == organization_id,
            CompanyUser.user_id == context.user_id,
            CompanyUser.is_active.is_(True),
            CompanyUser.status == MembershipStatus.ACTIVE.value,
        )
        .one_or_none()
    )
    if membership is None and not context.internal_roles:
        return frozenset()
    if membership is not None:
        permissions.update(customer_permissions(membership.role))
    if workspace_id:
        workspace = db.get(Account, workspace_id)
        workspace_membership = db.get(AccountMember, (workspace_id, context.user_id))
        if (
            workspace is None
            or workspace.organization_id != organization_id
            or workspace.status != "active"
            or (workspace_membership is None and not context.internal_roles)
            or (
                workspace_membership is not None
                and workspace_membership.status != MembershipStatus.ACTIVE.value
                and not context.internal_roles
            )
        ):
            return frozenset()
        if workspace_membership is not None:
            permissions.update(customer_permissions(workspace_membership.role))
    return frozenset(permissions)


def authorize_notification(
    *,
    context: AuthorizationContext,
    notification: Notification | None,
) -> Notification:
    if (
        notification is None
        or notification.recipient_kind != "USER"
        or notification.recipient_user_id != context.user_id
    ):
        raise NotificationError("notification_not_found", "Notification was not found")
    return notification


def notification_scope_visible(
    db: Session,
    *,
    context: AuthorizationContext,
    notification: Notification,
) -> bool:
    """Recheck membership before exposing even notification summary text."""

    if notification.recipient_user_id != context.user_id:
        return False
    valid_scope, workspace_id = _workspace_owned_target_scope(
        db,
        notification=notification,
    )
    if not valid_scope:
        return False
    permissions = _active_scope_permissions(
        db,
        context=context,
        organization_id=notification.organization_id,
        workspace_id=workspace_id,
    )
    return permission_granted(permissions, "organization:read")


def resolve_notification_target(
    db: Session,
    *,
    context: AuthorizationContext,
    notification: Notification,
) -> ResolvedNotificationTarget:
    authorize_notification(context=context, notification=notification)
    target_type = str(notification.target_type or "NONE").upper()
    target_id = notification.target_id
    if target_type == NotificationTargetType.NONE.value or not target_id:
        raise NotificationError(
            "target_unavailable", "Notification has no contextual target"
        )

    valid_scope, workspace_id = _workspace_owned_target_scope(
        db,
        notification=notification,
    )
    if not valid_scope:
        raise NotificationError("target_not_found", "Notification target was not found")

    permissions = _active_scope_permissions(
        db,
        context=context,
        organization_id=notification.organization_id,
        workspace_id=workspace_id,
    )
    required = TARGET_REQUIRED_PERMISSION.get(target_type)
    if not required or not permission_granted(permissions, required):
        raise NotificationError("target_not_found", "Notification target was not found")

    if target_type == NotificationTargetType.ASSET.value:
        asset = db.get(Asset, target_id)
        valid = bool(
            asset
            and asset.organization_id == notification.organization_id
            and asset.workspace_id in (None, workspace_id)
            and asset.status != "archived"
        )
        app_path = portal_path = f"/assets/{target_id}"
    elif target_type == NotificationTargetType.REPORT.value:
        report = db.get(Report, target_id)
        valid = bool(
            report
            and report.organization_id == notification.organization_id
            and report.workspace_id in (None, workspace_id)
            and report.status == "PUBLISHED"
        )
        app_path = portal_path = f"/reports/{target_id}"
    elif target_type == NotificationTargetType.ACTION.value:
        action = db.get(Action, target_id)
        valid = bool(
            action
            and action.organization_id == notification.organization_id
            and action.workspace_id in (None, workspace_id)
        )
        app_path = portal_path = f"/actions/{target_id}"
    elif target_type in {
        NotificationTargetType.ORDER.value,
        NotificationTargetType.SHIPMENT.value,
    }:
        order = db.get(Order, target_id)
        valid = bool(
            order
            and (order.organization_id or order.company_id)
            == notification.organization_id
            and order.workspace_id in (None, workspace_id)
            and (order.user_id in (None, context.user_id) or context.internal_roles)
        )
        app_path = f"/orders/{target_id}"
        portal_path = f"/services/orders/{target_id}"
    elif target_type == NotificationTargetType.SERVICE.value:
        job = db.get(FulfilmentJob, target_id)
        order = db.get(Order, job.order_id) if job else None
        valid = bool(
            job
            and order
            and (order.organization_id or order.company_id)
            == notification.organization_id
            and order.workspace_id in (None, workspace_id)
            and (order.user_id in (None, context.user_id) or context.internal_roles)
        )
        app_path = portal_path = f"/services/{target_id}"
    elif target_type == NotificationTargetType.INVITATION.value:
        invitation = db.get(Invitation, target_id)
        user = db.get(User, context.user_id)
        valid = bool(
            invitation
            and user
            and invitation.organization_id == notification.organization_id
            and invitation.workspace_id == workspace_id
            and invitation.accepted_by_user_id == user.id
        )
        app_path = "/portal"
        portal_path = "/home"
    else:  # pragma: no cover - persisted check constraints reject this.
        valid = False
        app_path = "/portal"
        portal_path = "/home"

    if not valid:
        raise NotificationError("target_not_found", "Notification target was not found")
    return ResolvedNotificationTarget(
        target_type=target_type,
        target_id=target_id,
        workspace_id=workspace_id,
        app_path=app_path,
        portal_path=portal_path,
    )


__all__ = [
    "ResolvedNotificationTarget",
    "authorize_notification",
    "notification_scope_visible",
    "resolve_notification_target",
]
