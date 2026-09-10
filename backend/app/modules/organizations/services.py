"""Organization/workspace authorization and compatibility services."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.event_names import EventNames
from app.core.time import utc_now
from app.models import (
    Account,
    AccountMember,
    Company,
    CompanyUser,
    InternalRoleAssignment,
    User,
)
from app.modules.organizations.domain import (
    CustomerRole,
    InternalRole,
    MembershipStatus,
    WorkspaceStatus,
    customer_permissions,
    internal_permissions,
    normalize_customer_role,
    permission_granted,
)
from app.modules.audit.services import record_audit_event
from app.services.event_outbox import enqueue_domain_event


class OrganizationAccessError(RuntimeError):
    """Stable authorization/domain failure without resource disclosure."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class WorkspaceAccess:
    user_id: str
    organization: Company
    workspace: Optional[Account]
    organization_membership: Optional[CompanyUser]
    workspace_membership: Optional[AccountMember]
    internal_roles: frozenset[str]
    permissions: frozenset[str]

    @property
    def organization_role(self) -> Optional[str]:
        if self.organization_membership is None:
            return None
        return self.organization_membership.role

    @property
    def workspace_role(self) -> Optional[str]:
        if self.workspace_membership is None:
            return None
        return self.workspace_membership.role


def sole_active_workspace_id(db: Session, organization_id: str) -> str | None:
    """Resolve a legacy organization-only record only when its scope is unique."""

    workspace_ids = [
        row[0]
        for row in db.query(Account.id)
        .filter(
            Account.organization_id == organization_id,
            Account.status == WorkspaceStatus.ACTIVE.value,
        )
        .order_by(Account.id.asc())
        .limit(2)
        .all()
    ]
    return workspace_ids[0] if len(workspace_ids) == 1 else None


def _audit(
    db: Session,
    *,
    actor: User,
    organization_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    details: Optional[dict] = None,
) -> None:
    record_audit_event(
        db,
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        organization_id=organization_id,
        details=details,
    )


def active_internal_roles(db: Session, user: User) -> frozenset[str]:
    roles = {
        row.role
        for row in db.query(InternalRoleAssignment)
        .filter(
            InternalRoleAssignment.user_id == user.id,
            InternalRoleAssignment.is_active.is_(True),
        )
        .all()
    }
    # Temporary cutover bridge for deployments/tests that create a legacy
    # admin after the Phase 4 migration. New staff authorization is persisted
    # only in internal_role_assignments.
    if (user.role or "").strip().lower() == "admin":
        roles.add(InternalRole.SUPER_ADMIN.value)
    return frozenset(roles)


def organization_membership_for_user(
    db: Session,
    user_id: str,
    organization_id: str,
    *,
    active_only: bool = True,
) -> Optional[CompanyUser]:
    query = db.query(CompanyUser).filter(
        CompanyUser.company_id == organization_id,
        CompanyUser.user_id == user_id,
    )
    if active_only:
        query = query.filter(
            CompanyUser.is_active.is_(True),
            CompanyUser.status == MembershipStatus.ACTIVE.value,
        )
    return query.one_or_none()


def _workspace_membership_for_user(
    db: Session,
    user_id: str,
    workspace_id: str,
    *,
    active_only: bool = True,
) -> Optional[AccountMember]:
    query = db.query(AccountMember).filter(
        AccountMember.account_id == workspace_id,
        AccountMember.user_id == user_id,
    )
    if active_only:
        query = query.filter(AccountMember.status == MembershipStatus.ACTIVE.value)
    return query.one_or_none()


def _permissions(
    *,
    organization_role: Optional[str],
    workspace_role: Optional[str],
    staff_roles: frozenset[str],
) -> frozenset[str]:
    values = {"profile:read"}
    values.update(customer_permissions(organization_role))
    values.update(customer_permissions(workspace_role))
    values.update(internal_permissions(staff_roles))
    return frozenset(values)


def resolve_workspace_access(
    db: Session,
    user: User,
    *,
    requested_workspace_id: Optional[str] = None,
) -> WorkspaceAccess:
    staff_roles = active_internal_roles(db, user)
    staff_permissions = internal_permissions(staff_roles)

    membership: Optional[AccountMember]
    workspace: Optional[Account]
    if requested_workspace_id:
        workspace = db.get(Account, requested_workspace_id)
        membership = _workspace_membership_for_user(
            db,
            user.id,
            requested_workspace_id,
        )
        if workspace is None or (
            membership is None and "platform:admin" not in staff_permissions
        ):
            raise OrganizationAccessError(
                "workspace_access_denied",
                "Requested workspace is not accessible",
            )
    else:
        membership = (
            db.query(AccountMember)
            .join(Account, Account.id == AccountMember.account_id)
            .filter(
                AccountMember.user_id == user.id,
                AccountMember.status == MembershipStatus.ACTIVE.value,
                Account.status == WorkspaceStatus.ACTIVE.value,
            )
            .order_by(AccountMember.created_at.asc(), AccountMember.account_id.asc())
            .first()
        )
        workspace = db.get(Account, membership.account_id) if membership else None

    if workspace is not None and workspace.status != WorkspaceStatus.ACTIVE.value:
        raise OrganizationAccessError(
            "workspace_access_denied",
            "Requested workspace is not accessible",
        )

    if workspace is not None:
        organization = db.get(Company, workspace.organization_id)
        if organization is None or organization.status == "suspended":
            raise OrganizationAccessError(
                "workspace_access_denied",
                "Requested workspace is not accessible",
            )
        organization_membership = organization_membership_for_user(
            db,
            user.id,
            organization.id,
        )
        persisted_organization_membership = (
            organization_membership
            or organization_membership_for_user(
                db,
                user.id,
                organization.id,
                active_only=False,
            )
        )
        if (
            persisted_organization_membership is not None
            and organization_membership is None
            and "platform:admin" not in staff_permissions
        ):
            raise OrganizationAccessError(
                "workspace_access_denied",
                "Requested workspace is not accessible",
            )
        # During the compatibility window, an active legacy AccountMember is
        # sufficient for that workspace only. Organization-management APIs
        # still require the canonical CompanyUser membership.
        permissions = _permissions(
            organization_role=(
                organization_membership.role if organization_membership else None
            ),
            workspace_role=membership.role if membership else None,
            staff_roles=staff_roles,
        )
        return WorkspaceAccess(
            user_id=user.id,
            organization=organization,
            workspace=workspace,
            organization_membership=organization_membership,
            workspace_membership=membership,
            internal_roles=staff_roles,
            permissions=permissions,
        )

    organization_membership = (
        db.query(CompanyUser)
        .filter(
            CompanyUser.user_id == user.id,
            CompanyUser.is_active.is_(True),
            CompanyUser.status == MembershipStatus.ACTIVE.value,
        )
        .order_by(CompanyUser.created_at.asc(), CompanyUser.id.asc())
        .first()
    )
    if organization_membership is None:
        raise OrganizationAccessError(
            "workspace_missing",
            "No active workspace is available",
        )
    organization = db.get(Company, organization_membership.company_id)
    if organization is None or organization.status == "suspended":
        raise OrganizationAccessError(
            "workspace_missing",
            "No active workspace is available",
        )
    return WorkspaceAccess(
        user_id=user.id,
        organization=organization,
        workspace=None,
        organization_membership=organization_membership,
        workspace_membership=None,
        internal_roles=staff_roles,
        permissions=_permissions(
            organization_role=organization_membership.role,
            workspace_role=None,
            staff_roles=staff_roles,
        ),
    )


def authorize_organization(
    db: Session,
    user: User,
    organization_id: str,
    required_permission: str = "organization:read",
) -> tuple[Company, Optional[CompanyUser], frozenset[str]]:
    organization = db.get(Company, organization_id)
    membership = organization_membership_for_user(
        db,
        user.id,
        organization_id,
    )
    staff_roles = active_internal_roles(db, user)
    permissions = _permissions(
        organization_role=membership.role if membership else None,
        workspace_role=None,
        staff_roles=staff_roles,
    )
    if (
        organization is None
        or organization.status == "suspended"
        or not permission_granted(permissions, required_permission)
    ):
        raise OrganizationAccessError(
            "organization_access_denied",
            "Organization is not accessible",
        )
    return organization, membership, permissions


def get_user_company_id(
    user: User,
    db: Session,
    requested_workspace_id: Optional[str] = None,
) -> Optional[str]:
    """Resolve the active canonical organization without email inference."""

    context = getattr(user, "_authorization_context", None)
    active_id = getattr(context, "active_organization_id", None)
    if requested_workspace_id is None and active_id:
        return active_id
    try:
        return resolve_workspace_access(
            db,
            user,
            requested_workspace_id=requested_workspace_id,
        ).organization.id
    except OrganizationAccessError:
        return None


def create_organization_with_workspace(
    db: Session,
    *,
    actor: User,
    name: str,
    organization_type: str,
    country: str,
    timezone: str,
    workspace_name: str,
    sector_focus: str,
    entity_type: str,
    customer_type: str,
    dashboard_profile: str,
    use_cases: list[str],
    modules_enabled: list[str],
    org_name: Optional[str] = None,
) -> tuple[Company, Account, CompanyUser, AccountMember]:
    now = utc_now()
    organization = Company(
        name=name.strip(),
        email=actor.email.strip().lower(),
        country=country.strip(),
        organization_type=organization_type.strip().lower(),
        timezone=timezone.strip(),
        status="active",
        subscription_plan="trial",
        sectors=json.dumps([sector_focus]),
        current_users=1,
    )
    db.add(organization)
    db.flush()

    organization_membership = CompanyUser(
        company_id=organization.id,
        user_id=actor.id,
        email=actor.email.strip().lower(),
        role=CustomerRole.OWNER.value,
        is_active=True,
        status=MembershipStatus.ACTIVE.value,
        joined_at=now,
    )
    workspace = Account(
        organization_id=organization.id,
        name=workspace_name.strip(),
        sector_focus=sector_focus,
        entity_type=entity_type,
        customer_type=customer_type,
        dashboard_profile=dashboard_profile,
        use_cases=json.dumps(use_cases),
        org_name=org_name,
        modules_enabled=json.dumps(modules_enabled),
        status=WorkspaceStatus.ACTIVE.value,
    )
    db.add_all([organization_membership, workspace])
    db.flush()
    workspace_membership = AccountMember(
        account_id=workspace.id,
        user_id=actor.id,
        role=CustomerRole.OWNER.value,
        status=MembershipStatus.ACTIVE.value,
        joined_at=now,
    )
    db.add(workspace_membership)
    _audit(
        db,
        actor=actor,
        organization_id=organization.id,
        action="organization.created",
        resource_type="organization",
        resource_id=organization.id,
        details={"workspace_id": workspace.id},
    )
    enqueue_domain_event(
        db,
        name=EventNames.ORGANIZATION_CREATED,
        aggregate_type="organization",
        aggregate_id=organization.id,
        idempotency_key=f"organization:{organization.id}:created",
        correlation_id=organization.id,
        payload={
            "organization_id": organization.id,
            "workspace_id": workspace.id,
            "owner_user_id": actor.id,
        },
    )
    return organization, workspace, organization_membership, workspace_membership


def create_workspace(
    db: Session,
    *,
    actor: User,
    organization_id: str,
    name: str,
    sector_focus: str,
    entity_type: str,
    customer_type: str,
    dashboard_profile: str,
    use_cases: list[str],
    modules_enabled: list[str],
) -> Account:
    organization, _, _ = authorize_organization(
        db,
        actor,
        organization_id,
        "workspace:manage",
    )
    workspace = Account(
        organization_id=organization.id,
        name=name.strip(),
        sector_focus=sector_focus,
        entity_type=entity_type,
        customer_type=customer_type,
        dashboard_profile=dashboard_profile,
        use_cases=json.dumps(use_cases),
        org_name=organization.name,
        modules_enabled=json.dumps(modules_enabled),
        status=WorkspaceStatus.ACTIVE.value,
    )
    db.add(workspace)
    db.flush()
    now = utc_now()
    memberships = (
        db.query(CompanyUser)
        .filter(
            CompanyUser.company_id == organization.id,
            CompanyUser.user_id.is_not(None),
            CompanyUser.is_active.is_(True),
            CompanyUser.status == MembershipStatus.ACTIVE.value,
        )
        .all()
    )
    for membership in memberships:
        db.add(
            AccountMember(
                account_id=workspace.id,
                user_id=membership.user_id,
                role=normalize_customer_role(membership.role).value,
                status=MembershipStatus.ACTIVE.value,
                joined_at=now,
            )
        )
    _audit(
        db,
        actor=actor,
        organization_id=organization.id,
        action="workspace.created",
        resource_type="workspace",
        resource_id=workspace.id,
    )
    return workspace


def add_or_invite_member(
    db: Session,
    *,
    actor: User,
    organization_id: str,
    email: str,
    role: str,
    user_id: Optional[str] = None,
    name: Optional[str] = None,
) -> CompanyUser:
    organization, _, permissions = authorize_organization(
        db,
        actor,
        organization_id,
        "organization:manage_members",
    )
    normalized_role = normalize_customer_role(role)
    if normalized_role is CustomerRole.OWNER and not permission_granted(
        permissions,
        "organization:transfer_ownership",
    ):
        raise OrganizationAccessError(
            "owner_role_required",
            "Only an organization owner can assign the owner role",
        )

    canonical_email = email.strip().lower()
    bound_user = db.get(User, user_id) if user_id else None
    if user_id and bound_user is None:
        raise OrganizationAccessError("user_not_found", "GeoVision user not found")
    if bound_user is None:
        candidates = (
            db.query(User)
            .filter(func.lower(func.trim(User.email)) == canonical_email)
            .limit(2)
            .all()
        )
        if len(candidates) > 1:
            raise OrganizationAccessError(
                "identity_conflict",
                "Email matches multiple GeoVision users",
            )
        bound_user = candidates[0] if candidates else None
    if bound_user is not None:
        if not bound_user.is_active:
            raise OrganizationAccessError("user_inactive", "GeoVision user is inactive")
        if bound_user.email.strip().lower() != canonical_email:
            raise OrganizationAccessError(
                "email_mismatch",
                "Email does not match the selected GeoVision user",
            )

    existing = None
    if bound_user is not None:
        existing = organization_membership_for_user(
            db,
            bound_user.id,
            organization.id,
            active_only=False,
        )
    if existing is None:
        existing = (
            db.query(CompanyUser)
            .filter(
                CompanyUser.company_id == organization.id,
                func.lower(func.trim(CompanyUser.email)) == canonical_email,
                CompanyUser.status != MembershipStatus.REVOKED.value,
            )
            .first()
        )
    if existing is not None:
        raise OrganizationAccessError(
            "membership_exists",
            "A current or pending membership already exists",
        )

    now = utc_now()
    membership = CompanyUser(
        company_id=organization.id,
        user_id=bound_user.id if bound_user else None,
        email=canonical_email,
        name=name,
        role=normalized_role.value,
        is_active=bound_user is not None,
        status=(
            MembershipStatus.ACTIVE.value
            if bound_user is not None
            else MembershipStatus.INVITED.value
        ),
        invited_by_user_id=actor.id,
        invited_at=now,
        joined_at=now if bound_user is not None else None,
    )
    db.add(membership)
    db.flush()
    if bound_user is not None:
        active_members = (
            db.query(CompanyUser)
            .filter(
                CompanyUser.company_id == organization.id,
                CompanyUser.user_id.is_not(None),
                CompanyUser.is_active.is_(True),
                CompanyUser.status == MembershipStatus.ACTIVE.value,
            )
            .count()
        )
        if active_members > organization.max_users:
            raise OrganizationAccessError(
                "member_limit_reached",
                f"Organization member limit reached ({organization.max_users})",
            )
        for workspace in (
            db.query(Account)
            .filter(
                Account.organization_id == organization.id,
                Account.status == WorkspaceStatus.ACTIVE.value,
            )
            .all()
        ):
            db.add(
                AccountMember(
                    account_id=workspace.id,
                    user_id=bound_user.id,
                    role=normalized_role.value,
                    status=MembershipStatus.ACTIVE.value,
                    invited_by_user_id=actor.id,
                    invited_at=now,
                    joined_at=now,
                )
            )
        organization.current_users = active_members
    _audit(
        db,
        actor=actor,
        organization_id=organization.id,
        action=(
            "organization.member_added"
            if bound_user is not None
            else "organization.member_invited"
        ),
        resource_type="organization_membership",
        resource_id=membership.id,
        details={"role": normalized_role.value, "status": membership.status},
    )
    enqueue_domain_event(
        db,
        name=(
            EventNames.ORGANIZATION_MEMBER_ADDED
            if bound_user is not None
            else EventNames.ORGANIZATION_MEMBER_INVITED
        ),
        aggregate_type="organization_membership",
        aggregate_id=membership.id,
        idempotency_key=f"organization-member:{membership.id}:created",
        correlation_id=organization.id,
        payload={
            "organization_id": organization.id,
            "membership_id": membership.id,
            "user_id": membership.user_id,
            "role": membership.role,
            "status": membership.status,
        },
    )
    return membership


def update_member(
    db: Session,
    *,
    actor: User,
    organization_id: str,
    membership_id: str,
    role: Optional[str] = None,
    status: Optional[str] = None,
) -> CompanyUser:
    organization, _, permissions = authorize_organization(
        db,
        actor,
        organization_id,
        "organization:manage_members",
    )
    membership = db.get(CompanyUser, membership_id)
    if membership is None or membership.company_id != organization.id:
        raise OrganizationAccessError(
            "membership_not_found",
            "Organization membership was not found",
        )

    next_role = normalize_customer_role(role or membership.role)
    try:
        next_status = MembershipStatus(status or membership.status)
    except ValueError as exc:
        raise OrganizationAccessError(
            "invalid_membership_status",
            "Unsupported membership status",
        ) from exc
    if next_role is CustomerRole.OWNER and not permission_granted(
        permissions,
        "organization:transfer_ownership",
    ):
        raise OrganizationAccessError(
            "owner_role_required",
            "Only an organization owner can assign the owner role",
        )
    if next_status is MembershipStatus.ACTIVE and membership.user_id is None:
        raise OrganizationAccessError(
            "unbound_invitation",
            "An invitation must be accepted by an authenticated user first",
        )

    removes_owner = normalize_customer_role(membership.role) is CustomerRole.OWNER and (
        next_role is not CustomerRole.OWNER
        or next_status is not MembershipStatus.ACTIVE
    )
    if removes_owner:
        other_owner_count = (
            db.query(CompanyUser)
            .filter(
                CompanyUser.company_id == organization.id,
                CompanyUser.id != membership.id,
                CompanyUser.role == CustomerRole.OWNER.value,
                CompanyUser.is_active.is_(True),
                CompanyUser.status == MembershipStatus.ACTIVE.value,
            )
            .count()
        )
        if other_owner_count == 0:
            raise OrganizationAccessError(
                "last_owner_required",
                "An organization must retain at least one active owner",
            )

    membership.role = next_role.value
    membership.status = next_status.value
    membership.is_active = bool(
        membership.user_id and next_status is MembershipStatus.ACTIVE
    )
    if membership.is_active and membership.joined_at is None:
        membership.joined_at = utc_now()

    if membership.user_id:
        workspace_memberships = (
            db.query(AccountMember)
            .join(Account, Account.id == AccountMember.account_id)
            .filter(
                Account.organization_id == organization.id,
                AccountMember.user_id == membership.user_id,
            )
            .all()
        )
        for workspace_membership in workspace_memberships:
            workspace_membership.role = next_role.value
            workspace_membership.status = next_status.value
            db.add(workspace_membership)
    db.add(membership)
    db.flush()
    organization.current_users = (
        db.query(CompanyUser)
        .filter(
            CompanyUser.company_id == organization.id,
            CompanyUser.user_id.is_not(None),
            CompanyUser.is_active.is_(True),
            CompanyUser.status == MembershipStatus.ACTIVE.value,
        )
        .count()
    )
    _audit(
        db,
        actor=actor,
        organization_id=organization.id,
        action="organization.membership_updated",
        resource_type="organization_membership",
        resource_id=membership.id,
        details={"role": membership.role, "status": membership.status},
    )
    enqueue_domain_event(
        db,
        name=EventNames.ORGANIZATION_MEMBER_UPDATED,
        aggregate_type="organization_membership",
        aggregate_id=membership.id,
        idempotency_key=(
            f"organization-member:{membership.id}:{membership.role}:{membership.status}"
        ),
        correlation_id=organization.id,
        payload={
            "organization_id": organization.id,
            "membership_id": membership.id,
            "user_id": membership.user_id,
            "role": membership.role,
            "status": membership.status,
        },
    )
    return membership


__all__ = [
    "OrganizationAccessError",
    "WorkspaceAccess",
    "active_internal_roles",
    "add_or_invite_member",
    "authorize_organization",
    "create_organization_with_workspace",
    "create_workspace",
    "get_user_company_id",
    "organization_membership_for_user",
    "resolve_workspace_access",
    "sole_active_workspace_id",
    "update_member",
]
