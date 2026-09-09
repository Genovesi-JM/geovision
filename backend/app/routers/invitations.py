"""Invitation and intent-first onboarding HTTP API."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.time import utc_now
from app.deps import get_current_user, get_optional_user
from app.models import Account, AccountMember, Company, CompanyUser, Invitation, User
from app.modules.organizations.domain import MembershipStatus
from app.modules.organizations.invitation_schemas import (
    InvitationAcceptance,
    InvitationCreate,
    InvitationCreated,
    InvitationOut,
    InvitationPreview,
    InvitationStatus,
    InvitationTokenRequest,
    OnboardingContext,
    OnboardingIntent,
    OnboardingIntentOption,
    OnboardingIntentRequest,
    OnboardingIntentResolution,
)
from app.modules.organizations.invitations import (
    InvitationError,
    accept_invitation,
    create_invitation,
    destination_for,
    mask_email,
    onboarding_options,
    preview_invitation,
    revoke_invitation,
)
from app.modules.organizations.services import (
    OrganizationAccessError,
    authorize_organization,
)


router = APIRouter(tags=["invitations", "onboarding"])


def _http_error(exc: InvitationError) -> HTTPException:
    status_code = {
        "invitation_not_found": status.HTTP_404_NOT_FOUND,
        "target_not_found": status.HTTP_404_NOT_FOUND,
        "organization_access_denied": status.HTTP_404_NOT_FOUND,
        "authenticated_email_mismatch": status.HTTP_403_FORBIDDEN,
        "identity_inactive": status.HTTP_403_FORBIDDEN,
        "invitation_expired": status.HTTP_410_GONE,
        "invitation_revoked": status.HTTP_410_GONE,
        "invitation_used": status.HTTP_409_CONFLICT,
        "membership_changed": status.HTTP_409_CONFLICT,
        "membership_exists": status.HTTP_409_CONFLICT,
        "pending_invitation_exists": status.HTTP_409_CONFLICT,
        "member_limit_reached": status.HTTP_409_CONFLICT,
        "owner_invitation_forbidden": status.HTTP_400_BAD_REQUEST,
        "secret_metadata_rejected": status.HTTP_400_BAD_REQUEST,
        "invalid_metadata": status.HTTP_400_BAD_REQUEST,
        "metadata_too_large": status.HTTP_400_BAD_REQUEST,
    }.get(exc.code, status.HTTP_400_BAD_REQUEST)
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": str(exc)},
    )


def _out(invitation: Invitation) -> InvitationOut:
    return InvitationOut(
        id=invitation.id,
        organization_id=invitation.organization_id,
        workspace_id=invitation.workspace_id,
        membership_id=invitation.membership_id,
        target_email=invitation.target_email,
        identity_hint=invitation.identity_hint,
        intended_role=invitation.intended_role,
        target_type=invitation.target_type,
        target_id=invitation.target_id,
        status=invitation.status,
        invited_by_user_id=invitation.invited_by_user_id,
        accepted_by_user_id=invitation.accepted_by_user_id,
        expires_at=invitation.expires_at,
        accepted_at=invitation.accepted_at,
        revoked_at=invitation.revoked_at,
        created_at=invitation.created_at,
        updated_at=invitation.updated_at,
        destination=destination_for(invitation),
    )


def _preview(db: Session, invitation: Invitation) -> InvitationPreview:
    organization = db.get(Company, invitation.organization_id)
    workspace = db.get(Account, invitation.workspace_id)
    if organization is None or workspace is None:
        raise InvitationError("target_not_found", "Invitation target is not accessible")
    return InvitationPreview(
        invitation_id=invitation.id,
        organization_name=organization.name,
        workspace_name=workspace.name,
        target_email_hint=mask_email(invitation.target_email),
        intended_role=invitation.intended_role,
        status=invitation.status,
        expires_at=invitation.expires_at,
        destination=destination_for(invitation),
    )


@router.post(
    "/invitations",
    response_model=InvitationCreated,
    status_code=status.HTTP_201_CREATED,
)
def issue_invitation(
    payload: InvitationCreate,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InvitationCreated:
    try:
        invitation, token, accept_url, mobile_deep_link = create_invitation(
            db,
            actor=user,
            organization_id=payload.organization_id,
            workspace_id=payload.workspace_id,
            target_email=str(payload.target_email),
            intended_role=payload.intended_role.value,
            identity_hint=payload.identity_hint,
            target_type=payload.target_type,
            target_id=payload.target_id,
            expires_in_hours=payload.expires_in_hours,
            metadata=payload.metadata,
        )
        db.commit()
    except InvitationError as exc:
        db.rollback()
        raise _http_error(exc) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "invitation_conflict",
                "message": "Invitation could not be issued; reload and retry",
            },
        ) from exc
    db.refresh(invitation)
    response.headers["Cache-Control"] = "no-store"
    return InvitationCreated(
        **_out(invitation).model_dump(),
        token=token,
        accept_url=accept_url,
        mobile_deep_link=mobile_deep_link,
    )


@router.get("/invitations", response_model=list[InvitationOut])
def list_invitations(
    organization_id: str = Query(min_length=1, max_length=36),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[InvitationOut]:
    try:
        authorize_organization(
            db,
            user,
            organization_id,
            "organization:manage_members",
        )
    except OrganizationAccessError as exc:
        raise HTTPException(status_code=404, detail="Organization is not accessible") from exc
    rows = (
        db.query(Invitation)
        .filter(Invitation.organization_id == organization_id)
        .order_by(Invitation.created_at.desc(), Invitation.id.desc())
        .all()
    )
    changed = False
    now = utc_now()
    for row in rows:
        if row.status == InvitationStatus.PENDING.value and row.expires_at <= now:
            row.status = InvitationStatus.EXPIRED.value
            row.pending_email_key = None
            changed = True
    if changed:
        db.commit()
    return [_out(row) for row in rows]


@router.post("/invitations/preview", response_model=InvitationPreview)
def inspect_invitation(
    payload: InvitationTokenRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> InvitationPreview:
    try:
        invitation = preview_invitation(db, payload.token)
        result = _preview(db, invitation)
    except InvitationError as exc:
        if exc.code == "invitation_expired":
            db.commit()
        else:
            db.rollback()
        raise _http_error(exc) from exc
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return result


@router.post("/invitations/accept", response_model=InvitationAcceptance)
def use_invitation(
    payload: InvitationTokenRequest,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InvitationAcceptance:
    try:
        invitation, idempotent = accept_invitation(
            db,
            actor=user,
            token=payload.token,
        )
        db.commit()
    except InvitationError as exc:
        if exc.code == "invitation_expired":
            db.commit()
        else:
            db.rollback()
        raise _http_error(exc) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "acceptance_conflict",
                "message": "Invitation acceptance raced with another request; retry safely",
            },
        ) from exc
    db.refresh(invitation)
    response.headers["Cache-Control"] = "no-store"
    return InvitationAcceptance(
        invitation=_out(invitation),
        accepted=True,
        idempotent=idempotent,
    )


@router.post("/invitations/{invitation_id}/revoke", response_model=InvitationOut)
def cancel_invitation(
    invitation_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InvitationOut:
    try:
        invitation = revoke_invitation(
            db,
            actor=user,
            invitation_id=invitation_id,
        )
        db.commit()
    except InvitationError as exc:
        db.rollback()
        raise _http_error(exc) from exc
    db.refresh(invitation)
    return _out(invitation)


@router.get("/onboarding/options", response_model=list[OnboardingIntentOption])
def read_onboarding_options() -> list[OnboardingIntentOption]:
    return onboarding_options()


@router.post("/onboarding/intent", response_model=OnboardingIntentResolution)
def resolve_onboarding_intent(
    payload: OnboardingIntentRequest,
    response: Response,
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> OnboardingIntentResolution:
    options = {option.id: option for option in onboarding_options()}
    option = options[payload.intent]
    if payload.intent is OnboardingIntent.VIEW_INVITATION:
        try:
            invitation = preview_invitation(db, payload.invitation_token or "")
            invitation_preview = _preview(db, invitation)
        except InvitationError as exc:
            if exc.code == "invitation_expired":
                db.commit()
            else:
                db.rollback()
            raise _http_error(exc) from exc
        response.headers["Cache-Control"] = "no-store"
        return OnboardingIntentResolution(
            intent=payload.intent,
            next_path=option.next_path,
            onboarding_required=False,
            invitation_preview=invitation_preview,
        )

    onboarding_complete = False
    if user is not None:
        onboarding_complete = (
            db.query(AccountMember)
            .filter(
                AccountMember.user_id == user.id,
                AccountMember.status == MembershipStatus.ACTIVE.value,
            )
            .first()
            is not None
        )
    return OnboardingIntentResolution(
        intent=payload.intent,
        next_path=option.next_path,
        onboarding_required=not onboarding_complete,
    )


@router.get("/onboarding/context", response_model=OnboardingContext)
def read_onboarding_context(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OnboardingContext:
    organizations = (
        db.query(CompanyUser)
        .filter(
            CompanyUser.user_id == user.id,
            CompanyUser.is_active.is_(True),
            CompanyUser.status == MembershipStatus.ACTIVE.value,
        )
        .order_by(CompanyUser.created_at.asc(), CompanyUser.id.asc())
        .all()
    )
    workspaces = (
        db.query(AccountMember)
        .filter(
            AccountMember.user_id == user.id,
            AccountMember.status == MembershipStatus.ACTIVE.value,
        )
        .order_by(AccountMember.created_at.asc(), AccountMember.account_id.asc())
        .all()
    )
    pending_count = (
        db.query(Invitation)
        .filter(
            Invitation.target_email == user.email.strip().casefold(),
            Invitation.status == InvitationStatus.PENDING.value,
            Invitation.expires_at > utc_now(),
        )
        .count()
    )
    return OnboardingContext(
        onboarding_complete=bool(workspaces),
        pending_invitation_count=pending_count,
        organization_ids=[row.company_id for row in organizations],
        workspace_ids=[row.account_id for row in workspaces],
        intents=onboarding_options(),
    )


__all__ = ["router"]
