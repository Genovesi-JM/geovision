"""Secure invitation lifecycle and service-first onboarding decisions."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import timedelta
from typing import Any, Optional
from urllib.parse import quote

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import utc_now
from app.models import (
    Account,
    AccountMember,
    Asset,
    AuditLog,
    Company,
    CompanyUser,
    Document,
    Invitation,
    MobileServiceRequest,
    Order,
    Site,
    User,
)
from app.modules.organizations.domain import MembershipStatus, WorkspaceStatus
from app.modules.organizations.invitation_schemas import (
    InvitationDestination,
    InvitationStatus,
    InvitationTargetType,
    OnboardingIntent,
    OnboardingIntentOption,
)
from app.modules.organizations.services import (
    OrganizationAccessError,
    authorize_organization,
)


TOKEN_BYTES = 32
INVITATION_METADATA_MAX_BYTES = 8 * 1024
_SECRET_KEY = re.compile(
    r"(^|[_-])(password|passwd|secret|token|api[_-]?key|private[_-]?key|credential)s?($|[_-])",
    re.IGNORECASE,
)


class InvitationError(RuntimeError):
    """Stable invitation error suitable for an API error mapping."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def canonical_email(value: str) -> str:
    return value.strip().casefold()


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _contains_secret_key(value: object) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            if _SECRET_KEY.search(str(key)) or _contains_secret_key(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_secret_key(item) for item in value)
    return False


def safe_metadata(value: dict[str, Any]) -> str:
    if _contains_secret_key(value):
        raise InvitationError(
            "secret_metadata_rejected",
            "Invitation metadata cannot contain credentials or secret-like fields",
        )
    try:
        encoded = json.dumps(value, separators=(",", ":"), sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise InvitationError(
            "invalid_metadata", "Invitation metadata must be valid JSON"
        ) from exc
    if len(encoded.encode("utf-8")) > INVITATION_METADATA_MAX_BYTES:
        raise InvitationError(
            "metadata_too_large",
            f"Invitation metadata cannot exceed {INVITATION_METADATA_MAX_BYTES} bytes",
        )
    return encoded


def mask_email(value: str) -> str:
    local, separator, domain = value.partition("@")
    if not separator:
        return "***"
    visible = local[:1]
    return f"{visible}{'*' * max(3, len(local) - 1)}@{domain}"


def destination_for(invitation: Invitation) -> InvitationDestination:
    target_type = InvitationTargetType(invitation.target_type)
    target_id = invitation.target_id
    paths = {
        InvitationTargetType.WORKSPACE: "/portal",
        InvitationTargetType.ASSET: f"/assets/{target_id}",
        InvitationTargetType.REPORT: f"/reports/{target_id}",
        InvitationTargetType.SERVICE_RESULT: f"/work/{target_id}",
        InvitationTargetType.ORDER: f"/orders/{target_id}",
    }
    return InvitationDestination(
        kind=target_type,
        organization_id=invitation.organization_id,
        workspace_id=invitation.workspace_id,
        target_id=target_id,
        path=paths[target_type],
    )


def _validate_workspace(
    db: Session,
    *,
    organization_id: str,
    workspace_id: str,
) -> Account:
    workspace = db.get(Account, workspace_id)
    if (
        workspace is None
        or workspace.organization_id != organization_id
        or workspace.status != WorkspaceStatus.ACTIVE.value
    ):
        raise InvitationError("target_not_found", "Invitation target is not accessible")
    return workspace


def validate_target(
    db: Session,
    *,
    organization_id: str,
    workspace_id: str,
    target_type: InvitationTargetType,
    target_id: Optional[str],
) -> None:
    _validate_workspace(
        db,
        organization_id=organization_id,
        workspace_id=workspace_id,
    )
    if target_type is InvitationTargetType.WORKSPACE:
        if target_id not in (None, workspace_id):
            raise InvitationError("target_not_found", "Invitation target is not accessible")
        return
    if not target_id:
        raise InvitationError("target_not_found", "Invitation target is not accessible")

    if target_type is InvitationTargetType.ASSET:
        target = db.get(Asset, target_id)
        valid = bool(
            target
            and target.organization_id == organization_id
            and target.status != "archived"
            and target.workspace_id in (None, workspace_id)
        )
    elif target_type is InvitationTargetType.REPORT:
        target = db.get(Document, target_id)
        valid = bool(target and target.company_id == organization_id)
    elif target_type is InvitationTargetType.ORDER:
        target = db.get(Order, target_id)
        valid = bool(target and target.company_id == organization_id)
    elif target_type is InvitationTargetType.SERVICE_RESULT:
        target = db.get(MobileServiceRequest, target_id)
        site = db.get(Site, target.site_id) if target and target.site_id else None
        valid = bool(target and site and site.company_id == organization_id)
    else:  # pragma: no cover - enum validation rejects this at the API boundary.
        valid = False
    if not valid:
        raise InvitationError("target_not_found", "Invitation target is not accessible")


def _audit(
    db: Session,
    *,
    actor: User,
    invitation: Invitation,
    action: str,
    details: Optional[dict[str, Any]] = None,
) -> None:
    db.add(
        AuditLog(
            user_id=actor.id,
            user_email=actor.email,
            action=action,
            resource_type="invitation",
            resource_id=invitation.id,
            details=json.dumps(
                {
                    "organization_id": invitation.organization_id,
                    "workspace_id": invitation.workspace_id,
                    "target_type": invitation.target_type,
                    "target_id": invitation.target_id,
                    **(details or {}),
                },
                sort_keys=True,
            ),
        )
    )


def _expire_if_needed(invitation: Invitation) -> bool:
    if (
        invitation.status == InvitationStatus.PENDING.value
        and invitation.expires_at <= utc_now()
    ):
        invitation.status = InvitationStatus.EXPIRED.value
        invitation.pending_email_key = None
        return True
    return False


def create_invitation(
    db: Session,
    *,
    actor: User,
    organization_id: str,
    workspace_id: str,
    target_email: str,
    intended_role: str,
    identity_hint: Optional[str],
    target_type: InvitationTargetType,
    target_id: Optional[str],
    expires_in_hours: int,
    metadata: dict[str, Any],
) -> tuple[Invitation, str, str, str]:
    try:
        organization, _, _ = authorize_organization(
            db,
            actor,
            organization_id,
            "organization:manage_members",
        )
    except OrganizationAccessError as exc:
        raise InvitationError("organization_access_denied", str(exc)) from exc

    if intended_role == "owner":
        raise InvitationError(
            "owner_invitation_forbidden",
            "Ownership must be transferred through the authenticated ownership-transfer flow",
        )
    validate_target(
        db,
        organization_id=organization.id,
        workspace_id=workspace_id,
        target_type=target_type,
        target_id=target_id,
    )

    email = canonical_email(target_email)
    now = utc_now()
    pending_rows = (
        db.query(Invitation)
        .filter(
            Invitation.organization_id == organization.id,
            func.lower(func.trim(Invitation.target_email)) == email,
            Invitation.status == InvitationStatus.PENDING.value,
        )
        .with_for_update()
        .all()
    )
    for pending in pending_rows:
        _expire_if_needed(pending)
    if any(row.status == InvitationStatus.PENDING.value for row in pending_rows):
        raise InvitationError(
            "pending_invitation_exists",
            "A pending invitation already exists for this email and organization",
        )
    if pending_rows:
        db.flush()

    active_membership = (
        db.query(CompanyUser)
        .filter(
            CompanyUser.company_id == organization.id,
            func.lower(func.trim(CompanyUser.email)) == email,
            CompanyUser.is_active.is_(True),
            CompanyUser.status == MembershipStatus.ACTIVE.value,
        )
        .first()
    )
    if active_membership is not None:
        raise InvitationError(
            "membership_exists",
            "This identity already has an active organization membership",
        )

    membership = (
        db.query(CompanyUser)
        .filter(
            CompanyUser.company_id == organization.id,
            func.lower(func.trim(CompanyUser.email)) == email,
            CompanyUser.user_id.is_(None),
            CompanyUser.status == MembershipStatus.INVITED.value,
        )
        .order_by(CompanyUser.created_at.asc(), CompanyUser.id.asc())
        .first()
    )
    if membership is None:
        membership = CompanyUser(
            company_id=organization.id,
            user_id=None,
            email=email,
            role=intended_role,
            is_active=False,
            status=MembershipStatus.INVITED.value,
            invited_by_user_id=actor.id,
            invited_at=now,
        )
        db.add(membership)
        db.flush()
    else:
        membership.role = intended_role
        membership.invited_by_user_id = actor.id
        membership.invited_at = now

    raw_token = secrets.token_urlsafe(TOKEN_BYTES)
    invitation = Invitation(
        token_hash=token_digest(raw_token),
        token_prefix=raw_token[:8],
        organization_id=organization.id,
        workspace_id=workspace_id,
        membership_id=membership.id,
        target_email=email,
        pending_email_key=email,
        identity_hint=identity_hint.strip() if identity_hint else None,
        intended_role=intended_role,
        target_type=target_type.value,
        target_id=workspace_id if target_type is InvitationTargetType.WORKSPACE else target_id,
        metadata_json=safe_metadata(metadata),
        status=InvitationStatus.PENDING.value,
        invited_by_user_id=actor.id,
        expires_at=now + timedelta(hours=expires_in_hours),
    )
    db.add(invitation)
    db.flush()
    _audit(
        db,
        actor=actor,
        invitation=invitation,
        action="invitation.created",
        details={"intended_role": intended_role},
    )

    frontend = settings.frontend_base.rstrip("/")
    encoded = quote(raw_token, safe="")
    accept_url = f"{frontend}/onboarding.html#invitation={encoded}"
    mobile_deep_link = f"geovision://app/invitation/accept#token={encoded}"
    return invitation, raw_token, accept_url, mobile_deep_link


def invitation_by_token(db: Session, token: str, *, lock: bool = False) -> Invitation:
    query = db.query(Invitation).filter(Invitation.token_hash == token_digest(token))
    if lock:
        query = query.with_for_update()
    invitation = query.one_or_none()
    if invitation is None:
        raise InvitationError("invitation_not_found", "Invitation is unavailable")
    _expire_if_needed(invitation)
    return invitation


def preview_invitation(db: Session, token: str) -> Invitation:
    invitation = invitation_by_token(db, token)
    if invitation.status == InvitationStatus.EXPIRED.value:
        raise InvitationError("invitation_expired", "Invitation has expired")
    if invitation.status == InvitationStatus.REVOKED.value:
        raise InvitationError("invitation_revoked", "Invitation has been revoked")
    if invitation.status == InvitationStatus.ACCEPTED.value:
        raise InvitationError("invitation_used", "Invitation has already been accepted")
    validate_target(
        db,
        organization_id=invitation.organization_id,
        workspace_id=invitation.workspace_id,
        target_type=InvitationTargetType(invitation.target_type),
        target_id=invitation.target_id,
    )
    return invitation


def accept_invitation(
    db: Session,
    *,
    actor: User,
    token: str,
) -> tuple[Invitation, bool]:
    invitation = invitation_by_token(db, token, lock=True)
    if invitation.status == InvitationStatus.ACCEPTED.value:
        if invitation.accepted_by_user_id == actor.id:
            return invitation, True
        raise InvitationError("invitation_used", "Invitation has already been accepted")
    if invitation.status == InvitationStatus.EXPIRED.value:
        raise InvitationError("invitation_expired", "Invitation has expired")
    if invitation.status == InvitationStatus.REVOKED.value:
        raise InvitationError("invitation_revoked", "Invitation has been revoked")

    if canonical_email(actor.email) != canonical_email(invitation.target_email):
        raise InvitationError(
            "authenticated_email_mismatch",
            "Sign in with the invited email address or ask the inviter to reissue the invitation",
        )
    if not actor.is_active:
        raise InvitationError("identity_inactive", "Authenticated identity is inactive")

    organization = db.get(Company, invitation.organization_id)
    if organization is None or organization.status == "suspended":
        raise InvitationError("target_not_found", "Invitation target is not accessible")
    validate_target(
        db,
        organization_id=invitation.organization_id,
        workspace_id=invitation.workspace_id,
        target_type=InvitationTargetType(invitation.target_type),
        target_id=invitation.target_id,
    )

    membership = db.get(CompanyUser, invitation.membership_id)
    if (
        membership is None
        or membership.company_id != invitation.organization_id
        or canonical_email(membership.email) != canonical_email(invitation.target_email)
    ):
        raise InvitationError("membership_changed", "Invitation membership is unavailable")

    active_membership = (
        db.query(CompanyUser)
        .filter(
            CompanyUser.company_id == invitation.organization_id,
            CompanyUser.user_id == actor.id,
            CompanyUser.is_active.is_(True),
            CompanyUser.status == MembershipStatus.ACTIVE.value,
        )
        .with_for_update()
        .one_or_none()
    )
    if active_membership is not None and active_membership.id != membership.id:
        if active_membership.role != invitation.intended_role:
            raise InvitationError(
                "membership_changed",
                "Existing organization access does not match the invitation",
            )
        invitation.membership_id = active_membership.id
        if membership.user_id is None and membership.status == MembershipStatus.INVITED.value:
            membership.status = MembershipStatus.REVOKED.value
            membership.is_active = False
        membership = active_membership
    else:
        if membership.user_id not in (None, actor.id):
            raise InvitationError("invitation_used", "Invitation has already been accepted")
        if membership.status not in (
            MembershipStatus.INVITED.value,
            MembershipStatus.ACTIVE.value,
        ):
            raise InvitationError("membership_changed", "Invitation membership is unavailable")
        if membership.status == MembershipStatus.ACTIVE.value and membership.role != invitation.intended_role:
            raise InvitationError(
                "membership_changed",
                "Existing organization access does not match the invitation",
            )

        active_members = (
            db.query(CompanyUser)
            .filter(
                CompanyUser.company_id == invitation.organization_id,
                CompanyUser.user_id.is_not(None),
                CompanyUser.is_active.is_(True),
                CompanyUser.status == MembershipStatus.ACTIVE.value,
            )
            .count()
        )
        if membership.status != MembershipStatus.ACTIVE.value and active_members >= organization.max_users:
            raise InvitationError(
                "member_limit_reached",
                f"Organization member limit reached ({organization.max_users})",
            )
        membership.user_id = actor.id
        membership.role = invitation.intended_role
        membership.status = MembershipStatus.ACTIVE.value
        membership.is_active = True
        membership.joined_at = membership.joined_at or utc_now()

    workspace_membership = (
        db.query(AccountMember)
        .filter(
            AccountMember.account_id == invitation.workspace_id,
            AccountMember.user_id == actor.id,
        )
        .with_for_update()
        .one_or_none()
    )
    if workspace_membership is None:
        workspace_membership = AccountMember(
            account_id=invitation.workspace_id,
            user_id=actor.id,
            role=invitation.intended_role,
            status=MembershipStatus.ACTIVE.value,
            invited_by_user_id=invitation.invited_by_user_id,
            invited_at=invitation.created_at,
            joined_at=utc_now(),
        )
        db.add(workspace_membership)
    elif (
        workspace_membership.status == MembershipStatus.ACTIVE.value
        and workspace_membership.role != invitation.intended_role
    ):
        raise InvitationError(
            "membership_changed",
            "Existing workspace access does not match the invitation",
        )
    else:
        workspace_membership.role = invitation.intended_role
        workspace_membership.status = MembershipStatus.ACTIVE.value
        workspace_membership.joined_at = workspace_membership.joined_at or utc_now()

    now = utc_now()
    invitation.status = InvitationStatus.ACCEPTED.value
    invitation.pending_email_key = None
    invitation.accepted_by_user_id = actor.id
    invitation.accepted_at = now
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
        invitation=invitation,
        action="invitation.accepted",
        details={"idempotent": False},
    )
    db.flush()
    return invitation, False


def revoke_invitation(
    db: Session,
    *,
    actor: User,
    invitation_id: str,
) -> Invitation:
    invitation = (
        db.query(Invitation)
        .filter(Invitation.id == invitation_id)
        .with_for_update()
        .one_or_none()
    )
    if invitation is None:
        raise InvitationError("invitation_not_found", "Invitation was not found")
    try:
        authorize_organization(
            db,
            actor,
            invitation.organization_id,
            "organization:manage_members",
        )
    except OrganizationAccessError as exc:
        raise InvitationError("invitation_not_found", "Invitation was not found") from exc
    _expire_if_needed(invitation)
    if invitation.status == InvitationStatus.ACCEPTED.value:
        raise InvitationError(
            "invitation_used",
            "Accepted access must be revoked through membership management",
        )
    if invitation.status == InvitationStatus.REVOKED.value:
        return invitation
    if invitation.status == InvitationStatus.EXPIRED.value:
        raise InvitationError("invitation_expired", "Invitation has expired")

    invitation.status = InvitationStatus.REVOKED.value
    invitation.pending_email_key = None
    invitation.revoked_at = utc_now()
    membership = db.get(CompanyUser, invitation.membership_id)
    if (
        membership is not None
        and membership.user_id is None
        and membership.status == MembershipStatus.INVITED.value
    ):
        other_pending = (
            db.query(Invitation)
            .filter(
                Invitation.membership_id == membership.id,
                Invitation.id != invitation.id,
                Invitation.status == InvitationStatus.PENDING.value,
            )
            .count()
        )
        if other_pending == 0:
            membership.status = MembershipStatus.REVOKED.value
            membership.is_active = False
    _audit(
        db,
        actor=actor,
        invitation=invitation,
        action="invitation.revoked",
    )
    db.flush()
    return invitation


def onboarding_options() -> list[OnboardingIntentOption]:
    return [
        OnboardingIntentOption(
            id=OnboardingIntent.REQUEST_SERVICE,
            label="Request a service",
            description="Describe work for GeoVision to acquire, process, or deliver.",
            next_path="/work/new",
        ),
        OnboardingIntentOption(
            id=OnboardingIntent.MONITOR_ASSET,
            label="Monitor an asset",
            description="Add a field, site, facility, corridor, mine, or port asset.",
            next_path="/assets/new",
        ),
        OnboardingIntentOption(
            id=OnboardingIntent.BUY_PRODUCT,
            label="Buy a product",
            description="Open the equipment and service catalogue.",
            next_path="/store",
        ),
        OnboardingIntentOption(
            id=OnboardingIntent.VIEW_INVITATION,
            label="View an invitation",
            description="Join an existing organization and open shared work.",
            next_path="/invitations/accept",
            requires_invitation=True,
        ),
    ]


__all__ = [
    "InvitationError",
    "accept_invitation",
    "canonical_email",
    "create_invitation",
    "destination_for",
    "invitation_by_token",
    "mask_email",
    "onboarding_options",
    "preview_invitation",
    "revoke_invitation",
    "safe_metadata",
    "token_digest",
    "validate_target",
]
