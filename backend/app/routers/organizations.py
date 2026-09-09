"""Canonical organization, workspace, membership, and context API."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.account_profiles import normalize_account_profile
from app.core.database import get_db
from app.deps import get_authorization_context, get_current_user
from app.models import Account, AccountMember, Company, CompanyUser, User
from app.modules.identity.domain import AuthorizationContext, ExternalPrincipal
from app.modules.identity.services import IdentityResolutionError, build_authorization_context
from app.modules.organizations.domain import MembershipStatus
from app.modules.organizations.schemas import (
    MembershipCreate,
    MembershipOut,
    MembershipUpdate,
    OrganizationCreate,
    OrganizationOut,
    WorkspaceContextOut,
    WorkspaceContextRequest,
    WorkspaceCreate,
    WorkspaceOut,
)
from app.modules.organizations.services import (
    OrganizationAccessError,
    add_or_invite_member,
    authorize_organization,
    create_organization_with_workspace,
    create_workspace,
    organization_membership_for_user,
    update_member,
)


router = APIRouter(prefix="/organizations", tags=["organizations"])


def _organization_error(exc: OrganizationAccessError) -> HTTPException:
    status_code = {
        "organization_access_denied": status.HTTP_404_NOT_FOUND,
        "workspace_access_denied": status.HTTP_404_NOT_FOUND,
        "membership_not_found": status.HTTP_404_NOT_FOUND,
        "user_not_found": status.HTTP_404_NOT_FOUND,
        "owner_role_required": status.HTTP_403_FORBIDDEN,
        "membership_exists": status.HTTP_409_CONFLICT,
        "member_limit_reached": status.HTTP_409_CONFLICT,
        "last_owner_required": status.HTTP_409_CONFLICT,
        "unbound_invitation": status.HTTP_409_CONFLICT,
        "user_inactive": status.HTTP_409_CONFLICT,
        "identity_conflict": status.HTTP_409_CONFLICT,
        "email_mismatch": status.HTTP_400_BAD_REQUEST,
        "invalid_membership_status": status.HTTP_400_BAD_REQUEST,
    }.get(exc.code, status.HTTP_400_BAD_REQUEST)
    return HTTPException(status_code=status_code, detail=str(exc))


def _workspace_out(
    workspace: Account,
    membership: Optional[AccountMember] = None,
) -> WorkspaceOut:
    return WorkspaceOut(
        id=workspace.id,
        organization_id=workspace.organization_id,
        name=workspace.name,
        sector_focus=workspace.sector_focus,
        entity_type=workspace.entity_type,
        customer_type=workspace.customer_type,
        dashboard_profile=workspace.dashboard_profile,
        use_cases=workspace.use_cases,
        modules_enabled=workspace.modules_enabled,
        status=workspace.status,
        role=membership.role if membership else None,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )


def _organization_out(
    db: Session,
    organization: Company,
    user: User,
) -> OrganizationOut:
    membership = organization_membership_for_user(
        db,
        user.id,
        organization.id,
    )
    workspace_memberships = {
        row.account_id: row
        for row in db.query(AccountMember)
        .join(Account, Account.id == AccountMember.account_id)
        .filter(
            Account.organization_id == organization.id,
            AccountMember.user_id == user.id,
            AccountMember.status == MembershipStatus.ACTIVE.value,
        )
        .all()
    }
    workspaces = (
        db.query(Account)
        .filter(
            Account.organization_id == organization.id,
            Account.status == "active",
        )
        .order_by(Account.created_at.asc(), Account.id.asc())
        .all()
    )
    # Customer responses only expose workspaces the user is explicitly a
    # member of. Platform staff use the separate Operations surface.
    visible = [row for row in workspaces if row.id in workspace_memberships]
    return OrganizationOut(
        id=organization.id,
        name=organization.name,
        organization_type=organization.organization_type,
        country=organization.country,
        timezone=organization.timezone,
        status=organization.status,
        role=membership.role if membership else None,
        created_at=organization.created_at,
        updated_at=organization.updated_at,
        workspaces=[
            _workspace_out(row, workspace_memberships.get(row.id)) for row in visible
        ],
    )


def _membership_out(membership: CompanyUser) -> MembershipOut:
    return MembershipOut(
        id=membership.id,
        organization_id=membership.company_id,
        user_id=membership.user_id,
        email=membership.email,
        name=membership.name,
        role=membership.role,
        status=membership.status,
        invited_by_user_id=membership.invited_by_user_id,
        invited_at=membership.invited_at,
        joined_at=membership.joined_at,
        created_at=membership.created_at,
        updated_at=membership.updated_at,
    )


def _context_out(context: AuthorizationContext) -> WorkspaceContextOut:
    return WorkspaceContextOut(
        user_id=context.user_id,
        identity_subject=context.identity_subject,
        active_workspace_id=context.active_workspace_id,
        active_organization_id=context.active_organization_id,
        workspace_role=getattr(context, "workspace_role", None),
        organization_role=getattr(context, "organization_role", None),
        internal_roles=sorted(getattr(context, "internal_roles", frozenset())),
        permissions=sorted(context.permissions),
    )


@router.get("/context", response_model=WorkspaceContextOut)
def read_context(
    context: AuthorizationContext = Depends(get_authorization_context),
) -> WorkspaceContextOut:
    return _context_out(context)


@router.post("/context", response_model=WorkspaceContextOut)
def select_context(
    payload: WorkspaceContextRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceContextOut:
    principal = getattr(request.state, "identity_principal", None)
    if not isinstance(principal, ExternalPrincipal):
        raise HTTPException(status_code=401, detail="Identity context unavailable")
    try:
        context = build_authorization_context(
            db,
            user,
            principal,
            requested_workspace_id=payload.workspace_id,
        )
    except IdentityResolutionError as exc:
        if exc.code == "workspace_access_denied":
            raise HTTPException(status_code=404, detail="Workspace is not accessible") from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _context_out(context)


@router.get("", response_model=list[OrganizationOut])
def list_organizations(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[OrganizationOut]:
    memberships = (
        db.query(CompanyUser)
        .filter(
            CompanyUser.user_id == user.id,
            CompanyUser.is_active.is_(True),
            CompanyUser.status == MembershipStatus.ACTIVE.value,
        )
        .order_by(CompanyUser.created_at.asc(), CompanyUser.id.asc())
        .all()
    )
    organizations = [db.get(Company, row.company_id) for row in memberships]
    return [
        _organization_out(db, organization, user)
        for organization in organizations
        if organization is not None and organization.status != "suspended"
    ]


@router.post("", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
def create_organization(
    payload: OrganizationCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrganizationOut:
    try:
        profile = normalize_account_profile(
            payload.workspace.customer_type,
            sectors=payload.workspace.sectors,
            sector_focus=payload.workspace.sector_focus,
            use_cases=payload.workspace.use_cases,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    organization, _, _, _ = create_organization_with_workspace(
        db,
        actor=user,
        name=payload.name,
        organization_type=payload.organization_type,
        country=payload.country,
        timezone=payload.timezone,
        workspace_name=payload.workspace.name,
        sector_focus=profile["sector_focus"],
        entity_type=profile["entity_type"],
        customer_type=profile["customer_type"],
        dashboard_profile=profile["dashboard_profile"],
        use_cases=profile["use_cases"],
        modules_enabled=payload.workspace.modules_enabled,
        org_name=payload.name,
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Organization could not be created") from exc
    db.refresh(organization)
    return _organization_out(db, organization, user)


@router.get("/{organization_id}", response_model=OrganizationOut)
def read_organization(
    organization_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrganizationOut:
    try:
        organization, membership, _ = authorize_organization(
            db,
            user,
            organization_id,
        )
    except OrganizationAccessError as exc:
        raise _organization_error(exc) from exc
    if membership is None:
        # Keep customer and internal Operations experiences separated.
        raise HTTPException(status_code=404, detail="Organization is not accessible")
    return _organization_out(db, organization, user)


@router.get("/{organization_id}/membership", response_model=MembershipOut)
def read_membership(
    organization_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MembershipOut:
    try:
        _, membership, _ = authorize_organization(db, user, organization_id)
    except OrganizationAccessError as exc:
        raise _organization_error(exc) from exc
    if membership is None:
        raise HTTPException(status_code=404, detail="Membership was not found")
    return _membership_out(membership)


@router.get("/{organization_id}/members", response_model=list[MembershipOut])
def list_members(
    organization_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MembershipOut]:
    try:
        authorize_organization(
            db,
            user,
            organization_id,
            "organization:manage_members",
        )
    except OrganizationAccessError as exc:
        raise _organization_error(exc) from exc
    rows = (
        db.query(CompanyUser)
        .filter(CompanyUser.company_id == organization_id)
        .order_by(CompanyUser.created_at.asc(), CompanyUser.id.asc())
        .all()
    )
    return [_membership_out(row) for row in rows]


@router.post(
    "/{organization_id}/members",
    response_model=MembershipOut,
    status_code=status.HTTP_201_CREATED,
)
def create_membership(
    organization_id: str,
    payload: MembershipCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MembershipOut:
    try:
        membership = add_or_invite_member(
            db,
            actor=user,
            organization_id=organization_id,
            email=str(payload.email),
            user_id=payload.user_id,
            name=payload.name,
            role=payload.role.value,
        )
        db.commit()
    except OrganizationAccessError as exc:
        db.rollback()
        raise _organization_error(exc) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Membership already exists") from exc
    db.refresh(membership)
    return _membership_out(membership)


@router.patch(
    "/{organization_id}/members/{membership_id}",
    response_model=MembershipOut,
)
def change_membership(
    organization_id: str,
    membership_id: str,
    payload: MembershipUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MembershipOut:
    try:
        membership = update_member(
            db,
            actor=user,
            organization_id=organization_id,
            membership_id=membership_id,
            role=payload.role.value if payload.role else None,
            status=payload.status.value if payload.status else None,
        )
        db.commit()
    except OrganizationAccessError as exc:
        db.rollback()
        raise _organization_error(exc) from exc
    db.refresh(membership)
    return _membership_out(membership)


@router.delete(
    "/{organization_id}/members/{membership_id}",
    response_model=MembershipOut,
)
def revoke_membership(
    organization_id: str,
    membership_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MembershipOut:
    try:
        membership = update_member(
            db,
            actor=user,
            organization_id=organization_id,
            membership_id=membership_id,
            status=MembershipStatus.REVOKED.value,
        )
        db.commit()
    except OrganizationAccessError as exc:
        db.rollback()
        raise _organization_error(exc) from exc
    db.refresh(membership)
    return _membership_out(membership)


@router.get("/{organization_id}/workspaces", response_model=list[WorkspaceOut])
def list_workspaces(
    organization_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[WorkspaceOut]:
    try:
        _, membership, _ = authorize_organization(db, user, organization_id)
    except OrganizationAccessError as exc:
        raise _organization_error(exc) from exc
    if membership is None:
        raise HTTPException(status_code=404, detail="Organization is not accessible")
    rows = (
        db.query(Account, AccountMember)
        .join(
            AccountMember,
            (AccountMember.account_id == Account.id)
            & (AccountMember.user_id == user.id),
        )
        .filter(
            Account.organization_id == organization_id,
            Account.status == "active",
            AccountMember.status == MembershipStatus.ACTIVE.value,
        )
        .order_by(Account.created_at.asc(), Account.id.asc())
        .all()
    )
    return [_workspace_out(workspace, member) for workspace, member in rows]


@router.post(
    "/{organization_id}/workspaces",
    response_model=WorkspaceOut,
    status_code=status.HTTP_201_CREATED,
)
def add_workspace(
    organization_id: str,
    payload: WorkspaceCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceOut:
    try:
        profile = normalize_account_profile(
            payload.customer_type,
            sectors=payload.sectors,
            sector_focus=payload.sector_focus,
            use_cases=payload.use_cases,
        )
        workspace = create_workspace(
            db,
            actor=user,
            organization_id=organization_id,
            name=payload.name,
            sector_focus=profile["sector_focus"],
            entity_type=profile["entity_type"],
            customer_type=profile["customer_type"],
            dashboard_profile=profile["dashboard_profile"],
            use_cases=profile["use_cases"],
            modules_enabled=payload.modules_enabled,
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OrganizationAccessError as exc:
        db.rollback()
        raise _organization_error(exc) from exc
    db.refresh(workspace)
    membership = (
        db.query(AccountMember)
        .filter(
            AccountMember.account_id == workspace.id,
            AccountMember.user_id == user.id,
        )
        .one_or_none()
    )
    return _workspace_out(workspace, membership)


__all__ = ["router"]
