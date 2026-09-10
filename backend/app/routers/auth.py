"""Authentication endpoints for email/password, Google OAuth, and Microsoft OAuth.

Production-grade implementation with:
- Identity linking (no duplicate accounts for same email across providers)
- Refresh token rotation
- Audit logging
- Rate limiting (handled by middleware)
- Anti-enumeration (forgot-password always returns 202)
"""

import base64
import hashlib
import json
import logging
import re
import secrets
import uuid
from datetime import timedelta
from typing import List, Optional
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, Depends, HTTPException, Header, Query, Request, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..account_profiles import PUBLIC_SECTORS, normalize_account_profile
from ..core import database
from ..core.config import settings
from ..core.integration import IntegrationConfigurationError, IntegrationStatus
from ..core.security import (
    hash_password,
    validate_new_password,
    validate_password_byte_length,
    verify_password,
)
from ..core.time import utc_now
from ..deps import get_current_user_unauthorized as current_user_dependency
from ..integrations.identity.factory import get_identity_provider
from ..mail import send_reset_email
from ..middleware import log_audit
from ..models import (
    Account,
    AccountMember,
    AuthIdentity,
    Company,
    CompanyUser,
    Invitation,
    MobileServiceRequest,
    OAuthState,
    RefreshTokenFamily,
    RefreshTokenModel,
    ResetToken,
    User,
    UserProfile,
)
from ..schemas import AuthResponse, LoginRequest, RegisterRequest
from ..modules.identity.domain import AuthorizationContext, ExternalPrincipal, TokenUse
from ..modules.identity.ports import IdentityProvider
from ..modules.identity.services import (
    IdentityResolutionError,
    IdentityService,
    ResolvedIdentity,
    issue_session_access_token,
)


logger = logging.getLogger(__name__)

get_db = database.get_db

router = APIRouter(prefix="/auth", tags=["auth"])
external_bearer = HTTPBearer(auto_error=False)

DEFAULT_MODULES = ["kpi", "projects", "store", "alerts"]
# Legacy sectors can remain on historical accounts, but new public onboarding is
# deliberately limited to the accepted current offer.
ALLOWED_SECTORS = PUBLIC_SECTORS

REFRESH_TOKEN_BYTES = 48
OAUTH_STATE_TTL_MINUTES = 10
OAUTH_BROWSER_NONCE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43,128}$")

SERVICE_FIRST_INTENT_PROFILES = {
    "request_service": {
        "customer_type": "business",
        "sectors": ["environment"],
        "use_cases": ["site_environment", "maintenance"],
    },
    "monitor_asset": {
        "customer_type": "business",
        "sectors": ["environment"],
        "use_cases": ["site_environment", "maintenance"],
    },
    "buy_product": {
        "customer_type": "device",
        "sectors": ["environment"],
        "use_cases": ["device_monitoring"],
    },
}


def _service_first_profile(
    intent: str | None,
    *,
    customer_type: str,
    sectors: Optional[List[str]],
    sector_focus: str | None,
    use_cases: Optional[List[str]],
) -> tuple[Optional[dict[str, object]], Optional[str]]:
    """Resolve a service intent to internal defaults without exposing types."""

    normalized_intent = (intent or "").strip().lower() or None
    if normalized_intent == "view_invitation":
        return None, normalized_intent
    if normalized_intent is not None:
        defaults = SERVICE_FIRST_INTENT_PROFILES.get(normalized_intent)
        if defaults is None:
            raise ValueError("Invalid onboarding intent")
        return (
            normalize_account_profile(
                str(defaults["customer_type"]),
                sectors=list(defaults["sectors"]),
                use_cases=list(defaults["use_cases"]),
            ),
            normalized_intent,
        )
    return (
        normalize_account_profile(
            customer_type,
            sectors=sectors,
            sector_focus=sector_focus,
            use_cases=use_cases,
        ),
        None,
    )


# ═══════════════════════════════════════════════════════════════
# Helper functions
# ═══════════════════════════════════════════════════════════════


def _ensure_profile(
    db: Session,
    user: User,
    full_name: str | None = None,
    org_name: str | None = None,
    *,
    commit: bool = True,
) -> UserProfile:
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    if profile:
        changed = False
        if full_name and not getattr(profile, "full_name", None):
            profile.full_name = full_name
            changed = True
        if org_name and not getattr(profile, "org_name", None):
            profile.org_name = org_name
            changed = True
        if changed:
            db.add(profile)
            if commit:
                db.commit()
                db.refresh(profile)
        return profile

    profile = UserProfile(
        user_id=user.id,
        full_name=full_name,
        org_name=org_name,
        entity_type="individual",
    )
    db.add(profile)
    if commit:
        db.commit()
        db.refresh(profile)
    else:
        db.flush()
    return profile


def _ensure_company(
    db: Session,
    user: User,
    account_name: str,
    sector_focus: str | None = None,
) -> Company:
    """Auto-create a Company record so the user appears in the admin panel."""
    email = (user.email or "").strip().lower()
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()

    existing_membership = (
        db.query(CompanyUser).filter(CompanyUser.user_id == user.id).first()
    )
    if existing_membership:
        company = db.get(Company, existing_membership.company_id)
        if company is None:
            raise RuntimeError("Company membership points to a missing organization")
        return company

    company = Company(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"geovision:company:{user.id}")),
        name=account_name,
        email=email,
        phone=None,
        organization_type="customer",
        timezone="UTC",
        sectors=json.dumps([sector_focus or "agro"]),
        status="active",
        subscription_plan="trial",
        max_users=5,
        max_sites=10,
        max_storage_gb=50,
        current_users=1,
    )
    db.add(company)
    try:
        db.flush()
    except IntegrityError:
        # The deterministic starter organization can be inserted concurrently
        # by two onboarding requests. Once the winning transaction commits,
        # reuse its immutable membership instead of leaking a database error.
        db.rollback()
        winner = (
            db.query(CompanyUser)
            .filter(CompanyUser.user_id == user.id)
            .order_by(CompanyUser.created_at.asc())
            .first()
        )
        winner_company = db.get(Company, winner.company_id) if winner else None
        if winner_company is None:
            raise
        return winner_company

    # Link user to company
    cu = CompanyUser(
        company_id=company.id,
        user_id=user.id,
        email=email,
        name=getattr(profile, "full_name", None) if profile else None,
        role="owner",
        is_active=True,
        status="active",
        joined_at=utc_now(),
    )
    db.add(cu)
    return company


def _ensure_default_account(
    db: Session,
    user: User,
    sector_focus: str | None = None,
    *,
    commit: bool = True,
) -> Account:
    membership = (
        db.query(AccountMember).filter(AccountMember.user_id == user.id).first()
    )
    if membership:
        account = db.query(Account).filter(Account.id == membership.account_id).first()
        if account:
            # Ensure company also exists
            company = _ensure_company(db, user, account.name, account.sector_focus)
            if account.organization_id != company.id:
                account.organization_id = company.id
                db.add(account)
            if commit:
                db.commit()
            return account

    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    email = (user.email or "").strip().lower()
    account_name = None
    if profile:
        account_name = profile.org_name or profile.company or None
    if not account_name:
        account_name = (
            email.split("@")[0] if "@" in email else (email or "geovision")
        ) + " workspace"

    default_profile = normalize_account_profile(
        "farm", sector_focus=sector_focus or "agro"
    )
    onboarding_account_id = str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"geovision:onboarding:{user.id}")
    )
    company = _ensure_company(db, user, account_name, sector_focus)
    account = Account(
        id=onboarding_account_id,
        organization_id=company.id,
        name=account_name,
        sector_focus=default_profile["sector_focus"],
        entity_type=default_profile["entity_type"],
        customer_type=default_profile["customer_type"],
        dashboard_profile=default_profile["dashboard_profile"],
        use_cases=json.dumps(default_profile["use_cases"]),
        org_name=(getattr(profile, "org_name", None) if profile else None),
        modules_enabled=json.dumps(DEFAULT_MODULES),
        onboarding_user_id=user.id,
    )
    db.add(account)
    db.flush()

    membership = AccountMember(
        account_id=account.id,
        user_id=user.id,
        role="owner",
        status="active",
        joined_at=utc_now(),
    )
    db.add(membership)

    if commit:
        db.commit()
        db.refresh(account)
    return account


def resolve_role(user: User) -> str:
    role = getattr(user, "role", None)
    return role or "cliente"


def create_token(user: User, role: str) -> str:
    del role
    return issue_session_access_token(user)


def _hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _find_user_by_email(db: Session, canonical_email: str) -> User | None:
    return (
        db.query(User)
        .filter(func.lower(func.trim(User.email)) == canonical_email)
        .first()
    )


def _revoke_refresh_family(
    db: Session,
    family: RefreshTokenFamily,
    *,
    compromised: bool,
) -> None:
    now = utc_now()
    family.revoked_at = family.revoked_at or now
    if compromised:
        family.compromised_at = family.compromised_at or now
    db.add(family)
    db.query(RefreshTokenModel).filter(RefreshTokenModel.family_id == family.id).update(
        {"revoked": True}, synchronize_session=False
    )


def _create_refresh_token(
    db: Session,
    user_id: str,
    family_id: str | None = None,
    *,
    principal: ExternalPrincipal | None = None,
    auth_identity_id: str | None = None,
    auth_generation: int | None = None,
    commit: bool = True,
) -> str:
    import uuid as _uuid_mod

    raw_token = secrets.token_urlsafe(REFRESH_TOKEN_BYTES)
    token_hash = _hash_refresh_token(raw_token)

    family = None
    if family_id is None:
        if auth_generation is None:
            raise RuntimeError("authentication generation is required for a new family")
        family_id = str(_uuid_mod.uuid4())
        identity_provider = (
            (principal.origin_provider or principal.provider)
            if principal is not None
            else "internal"
        )
        family = RefreshTokenFamily(
            id=family_id,
            user_id=user_id,
            auth_identity_id=auth_identity_id,
            identity_provider=identity_provider,
            identity_issuer=(
                principal.issuer
                if principal is not None
                else settings.internal_token_issuer
            ),
            identity_subject=(
                principal.identity_subject if principal is not None else user_id
            ),
            auth_generation=auth_generation,
            expires_at=(
                utc_now()
                + timedelta(hours=settings.external_identity_session_max_hours)
                if principal is not None
                and (principal.origin_provider or principal.provider) != "internal"
                else utc_now() + timedelta(days=settings.refresh_token_expires_days)
            ),
        )
        db.add(family)
        db.flush()
    else:
        family = db.get(RefreshTokenFamily, family_id)
        if family is None or family.user_id != user_id:
            raise RuntimeError("refresh-token family is missing or invalid")

    rt = RefreshTokenModel(
        token_hash=token_hash,
        user_id=user_id,
        family_id=family_id,
        expires_at=min(
            utc_now() + timedelta(days=settings.refresh_token_expires_days),
            family.expires_at,
        ),
    )
    db.add(rt)
    if commit:
        db.commit()
    return raw_token


def _find_or_link_identity(
    db: Session,
    provider: str,
    provider_user_id: str,
    email: str,
    display_name: str | None = None,
    avatar_url: str | None = None,
    raw_data: dict | None = None,
    issuer: str | None = None,
    email_verified: bool = False,
) -> tuple[ResolvedIdentity, ExternalPrincipal]:
    """Resolve an issuer-qualified identity through the Phase 3 boundary."""

    del avatar_url, raw_data
    canonical_subject = (provider_user_id or "").strip()
    if not canonical_subject:
        raise HTTPException(status_code=400, detail="Identity subject is missing")
    canonical_issuer = issuer or f"legacy:{provider}"
    principal = ExternalPrincipal(
        provider=provider,
        issuer=canonical_issuer,
        subject=canonical_subject,
        identity_subject=f"{canonical_issuer}|{canonical_subject}",
        email_hint=email,
        email_verified=email_verified,
        display_name=display_name,
    )
    try:
        resolved = IdentityService(db).resolve_external_principal(
            principal,
            provision=True,
        )
        return resolved, principal
    except IdentityResolutionError as exc:
        status_code = (
            409
            if exc.code in {"email_link_requires_confirmation", "identity_conflict"}
            else 400
        )
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


def _build_auth_response(
    db: Session,
    user: User,
    *,
    expected_password_hash: str,
    expected_auth_generation: int,
    issue_refresh_token: bool,
) -> dict:
    profile = _ensure_profile(db, user, commit=False)
    # An invite recipient must join the pre-provisioned organization instead
    # of silently receiving an unrelated starter workspace on sign-in.
    has_workspace_membership = (
        db.query(AccountMember)
        .filter(
            AccountMember.user_id == user.id,
            AccountMember.status == "active",
        )
        .first()
        is not None
    )
    has_pending_invitation = (
        db.query(Invitation)
        .filter(
            Invitation.target_email == (user.email or "").strip().lower(),
            Invitation.status == "pending",
            Invitation.expires_at > utc_now(),
        )
        .first()
        is not None
    )
    account = (
        None
        if has_pending_invitation and not has_workspace_membership
        else _ensure_default_account(db, user, commit=False)
    )

    # Bind issuance to the exact credential snapshot that was verified. This
    # remains safe even when SQLite ignores SELECT ... FOR UPDATE.
    user = (
        db.query(User)
        .filter(
            User.id == user.id,
            User.password_hash == expected_password_hash,
            User.auth_generation == expected_auth_generation,
        )
        .with_for_update()
        .populate_existing()
        .one_or_none()
    )
    if user is None:
        db.rollback()
        raise HTTPException(
            status_code=401, detail="Credentials changed; sign in again"
        )

    role = resolve_role(user)
    access_token = issue_session_access_token(user)
    refresh_token = (
        _create_refresh_token(
            db,
            user.id,
            auth_generation=expected_auth_generation,
            commit=False,
        )
        if issue_refresh_token
        else None
    )
    db.commit()

    # Build user dict with profile name
    user_data = {
        "id": user.id,
        "email": user.email,
        "role": role,
        "name": getattr(profile, "full_name", None) or "",
    }

    return {
        "access_token": access_token,
        "user": user_data,
        "account": account,
        "refresh_token": refresh_token,
    }


# ═══════════════════════════════════════════════════════════════
# Auth Endpoints
# ═══════════════════════════════════════════════════════════════


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    email = (payload.email or "").strip().lower()

    try:
        account_profile, _onboarding_intent = _service_first_profile(
            payload.intent,
            customer_type=payload.customer_type,
            sectors=payload.sectors,
            sector_focus=payload.sector_focus,
            use_cases=payload.use_cases,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    existing = _find_user_by_email(db, email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        role="cliente",
        is_active=True,
    )
    db.add(user)
    db.flush()

    profile = UserProfile(
        user_id=user.id,
        full_name=payload.full_name,
        company=payload.org_name,
        entity_type=(
            str(account_profile["entity_type"])
            if account_profile is not None
            else "individual"
        ),
        org_name=payload.org_name,
    )
    db.add(profile)

    account = None
    if account_profile is not None:
        modules = payload.modules_enabled or DEFAULT_MODULES
        account_name = (
            payload.account_name
            or payload.org_name
            or ((payload.full_name or email.split("@")[0]) + " workspace")
        )
        company = _ensure_company(
            db, user, account_name, str(account_profile["sector_focus"])
        )
        onboarding_account_id = str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"geovision:onboarding:{user.id}")
        )
        account = Account(
            id=onboarding_account_id,
            organization_id=company.id,
            name=account_name,
            sector_focus=str(account_profile["sector_focus"]),
            entity_type=str(account_profile["entity_type"]),
            customer_type=str(account_profile["customer_type"]),
            dashboard_profile=str(account_profile["dashboard_profile"]),
            use_cases=json.dumps(account_profile["use_cases"]),
            org_name=payload.org_name,
            modules_enabled=json.dumps(modules),
            onboarding_user_id=user.id,
        )
        db.add(account)
        membership = AccountMember(
            account_id=onboarding_account_id,
            user_id=user.id,
            role="owner",
            status="active",
            joined_at=utc_now(),
        )
        db.add(membership)
    try:
        access_token = issue_session_access_token(user)
        issue_refresh_token = request.headers.get("X-GeoVision-Client") != "web"
        refresh_token = (
            _create_refresh_token(
                db,
                user.id,
                auth_generation=user.auth_generation,
                commit=False,
            )
            if issue_refresh_token
            else None
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email already registered") from exc
    db.refresh(user)
    if account is not None:
        db.refresh(account)

    log_audit(
        db,
        "register",
        user_id=user.id,
        user_email=user.email,
        resource_type="user",
        resource_id=user.id,
        request=request,
    )

    return AuthResponse(
        access_token=access_token,
        user=user,
        account=account,
        refresh_token=refresh_token,
    )


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    email = (payload.email or "").strip().lower()
    user = (
        db.query(User)
        .filter(func.lower(func.trim(User.email)) == email)
        .with_for_update()
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Este email não está registado. Cria uma conta ou usa o login Google/Microsoft.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Conta inativa.",
        )

    if not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Esta conta foi criada via OAuth. Usa o botão 'Entrar com Google' ou 'Microsoft'.",
        )

    if not verify_password(payload.password, user.password_hash):
        log_audit(
            db,
            "login_failed",
            user_email=email,
            details={"reason": "wrong_password"},
            request=request,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Password incorreta. Usa 'Esqueceu a senha?' para redefinir.",
        )

    verified_password_hash = user.password_hash
    verified_auth_generation = user.auth_generation
    resp = _build_auth_response(
        db,
        user,
        expected_password_hash=verified_password_hash,
        expected_auth_generation=verified_auth_generation,
        issue_refresh_token=request.headers.get("X-GeoVision-Client") != "web",
    )
    log_audit(db, "login", user_id=user.id, user_email=user.email, request=request)
    return AuthResponse(**resp)


# ── Refresh Token ──


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=512)


class RefreshTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


@router.post("/refresh", response_model=RefreshTokenResponse)
def refresh_token_endpoint(payload: RefreshTokenRequest, db: Session = Depends(get_db)):
    token_hash = _hash_refresh_token(payload.refresh_token)

    rt = (
        db.query(RefreshTokenModel)
        .filter(
            RefreshTokenModel.token_hash == token_hash,
        )
        .first()
    )

    if not rt:
        raise HTTPException(status_code=401, detail="Invalid or revoked refresh token")

    family = (
        db.query(RefreshTokenFamily)
        .filter(RefreshTokenFamily.id == rt.family_id)
        .with_for_update()
        .first()
    )
    if family is None:
        raise HTTPException(status_code=401, detail="Invalid refresh-token family")
    if family.user_id != rt.user_id:
        logger.warning("refresh_token result=rejected code=family_user_mismatch")
        _revoke_refresh_family(db, family, compromised=True)
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid refresh-token family")
    if family.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Refresh-token family revoked")
    family_checked_at = utc_now()
    if family.expires_at <= family_checked_at:
        logger.info("refresh_token result=rejected code=family_expired")
        _revoke_refresh_family(db, family, compromised=False)
        db.commit()
        raise HTTPException(
            status_code=401, detail="External reauthentication required"
        )

    if rt.revoked:
        logger.warning("refresh_token result=rejected code=reuse_detected")
        _revoke_refresh_family(db, family, compromised=True)
        db.commit()
        raise HTTPException(status_code=401, detail="Refresh token reuse detected")

    if rt.expires_at < utc_now():
        rt.revoked = True
        db.commit()
        raise HTTPException(status_code=401, detail="Refresh token expired")

    user = db.query(User).filter(User.id == rt.user_id).first()
    if not user or not user.is_active:
        _revoke_refresh_family(db, family, compromised=False)
        db.commit()
        raise HTTPException(status_code=401, detail="User inactive")
    if family.auth_generation != user.auth_generation:
        _revoke_refresh_family(db, family, compromised=False)
        db.commit()
        raise HTTPException(status_code=401, detail="Session has been superseded")

    if family.auth_identity_id:
        origin_identity = db.get(AuthIdentity, family.auth_identity_id)
        if origin_identity is None or origin_identity.user_id != user.id:
            _revoke_refresh_family(db, family, compromised=False)
            db.commit()
            raise HTTPException(status_code=401, detail="External identity inactive")

    claimed = (
        db.query(RefreshTokenModel)
        .filter(
            RefreshTokenModel.id == rt.id,
            RefreshTokenModel.revoked.is_(False),
        )
        .update({"revoked": True}, synchronize_session=False)
    )
    if claimed != 1:
        db.rollback()
        family = (
            db.query(RefreshTokenFamily)
            .filter(RefreshTokenFamily.id == rt.family_id)
            .with_for_update()
            .one()
        )
        _revoke_refresh_family(db, family, compromised=True)
        db.commit()
        logger.warning("refresh_token result=rejected code=concurrent_reuse_detected")
        raise HTTPException(status_code=401, detail="Refresh token reuse detected")

    origin_principal = ExternalPrincipal(
        provider="internal",
        origin_provider=family.identity_provider,
        issuer=family.identity_issuer or settings.internal_token_issuer,
        subject=user.id,
        identity_subject=family.identity_subject,
        internal_user_id=user.id,
        email_hint=user.email,
    )
    new_access = issue_session_access_token(
        user,
        origin_principal,
        expires_at=min(
            family.expires_at,
            utc_now() + timedelta(minutes=settings.access_token_expires_minutes),
        ),
    )
    new_refresh = _create_refresh_token(
        db,
        user.id,
        family_id=rt.family_id,
        commit=False,
    )
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=503, detail="Could not rotate refresh token"
        ) from exc

    return RefreshTokenResponse(access_token=new_access, refresh_token=new_refresh)


@router.post("/logout")
def logout(
    payload: Optional[RefreshTokenRequest] = None,
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    if payload and payload.refresh_token:
        token_hash = _hash_refresh_token(payload.refresh_token)
        rt = (
            db.query(RefreshTokenModel)
            .filter(RefreshTokenModel.token_hash == token_hash)
            .first()
        )
        if rt:
            family = db.get(RefreshTokenFamily, rt.family_id)
            if family is not None:
                _revoke_refresh_family(db, family, compromised=False)
            db.commit()

    return {"message": "Logged out"}


# ── Current User ──


@router.get("/me", tags=["auth"])
def get_current_user(
    request: Request,
    user: User = Depends(current_user_dependency),
    db: Session = Depends(get_db),
):
    """Return the current profile using the immutable GeoVision user ID."""
    auth_context = getattr(request.state, "authorization_context", None)
    if not isinstance(auth_context, AuthorizationContext):
        raise HTTPException(status_code=401, detail="Identity context unavailable")
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    account = (
        db.get(Account, auth_context.active_workspace_id)
        if auth_context.active_workspace_id
        else None
    )

    return {
        "id": user.id,
        "email": user.email,
        "name": getattr(profile, "full_name", None) or "",
        "full_name": getattr(profile, "full_name", None) or "",
        "phone": getattr(profile, "phone", None),
        "role": resolve_role(user),
        "company": getattr(profile, "company", None)
        or getattr(profile, "org_name", None)
        or "",
        "account_id": getattr(account, "id", "") if account else "",
        "account_name": getattr(account, "name", "") if account else "",
        "customer_type": getattr(account, "customer_type", "farm")
        if account
        else "farm",
        "dashboard_profile": getattr(account, "dashboard_profile", "farm")
        if account
        else "farm",
        "sector_focus": getattr(account, "sector_focus", "agro") if account else "agro",
        "use_cases": json.loads(getattr(account, "use_cases", None) or "[]")
        if account
        else [],
        "account": (
            {
                "id": account.id,
                "name": account.name,
                "org_name": getattr(account, "org_name", None),
                "customer_type": getattr(account, "customer_type", "farm"),
                "dashboard_profile": getattr(account, "dashboard_profile", "farm"),
                "sector_focus": getattr(account, "sector_focus", "agro"),
                "use_cases": json.loads(getattr(account, "use_cases", None) or "[]"),
            }
            if account
            else None
        ),
        "company_id": auth_context.active_organization_id or "",
        "authorization_context": {
            "user_id": auth_context.user_id,
            "identity_subject": auth_context.identity_subject,
            "active_workspace_id": auth_context.active_workspace_id,
            "active_organization_id": auth_context.active_organization_id,
            "workspace_role": auth_context.workspace_role,
            "organization_role": auth_context.organization_role,
            "internal_roles": sorted(auth_context.internal_roles),
            "permissions": sorted(auth_context.permissions),
        },
    }


# ── Account Deletion (self-service) ──


class DeleteAccountRequest(BaseModel):
    password: Optional[str] = None

    @field_validator("password")
    @classmethod
    def validate_password_size(cls, value: Optional[str]) -> Optional[str]:
        return validate_password_byte_length(value) if value is not None else None


@router.delete("/account", tags=["auth"])
@router.post("/account/delete", tags=["auth"], include_in_schema=False)
def delete_account(
    request: Request,
    payload: Optional[DeleteAccountRequest] = None,
    user: User = Depends(current_user_dependency),
    db: Session = Depends(get_db),
):
    """Permanently delete the authenticated user's account and personal data.

    Removes the user identity, profile, auth/refresh/reset tokens, external
    identities, company links and workspace memberships. Any workspace
    (Account) left with no remaining members is also removed. Operational
    records the law may require us to keep (e.g. billing) are out of scope.
    """
    user = (
        db.query(User)
        .filter(User.id == user.id)
        .with_for_update()
        .populate_existing()
        .one_or_none()
    )
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User invalid or inactive")
    email = (user.email or "").strip().lower()

    # Permanent deletion requires a second factor beyond the bearer token.
    # Password accounts must prove the current password. External-only
    # accounts require a dedicated provider reauthentication flow, which is
    # deliberately not emulated with an ordinary refresh/access token.
    if user.password_hash:
        if not payload or not payload.password:
            raise HTTPException(status_code=403, detail="Password is required")
        if not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=403, detail="Password does not match")
    else:
        raise HTTPException(
            status_code=403,
            detail="External identity reauthentication is required",
        )

    user_id = user.id
    verified_password_hash = user.password_hash
    account_ids = [
        m.account_id
        for m in db.query(AccountMember).filter(AccountMember.user_id == user_id).all()
    ]

    try:
        db.query(RefreshTokenModel).filter(RefreshTokenModel.user_id == user_id).delete(
            synchronize_session=False
        )
        db.query(RefreshTokenFamily).filter(
            RefreshTokenFamily.user_id == user_id
        ).delete(synchronize_session=False)
        db.query(AuthIdentity).filter(AuthIdentity.user_id == user_id).delete(
            synchronize_session=False
        )
        db.query(ResetToken).filter(ResetToken.user_id == user_id).delete(
            synchronize_session=False
        )
        # Remove customer-created service requests before deleting an empty
        # personal workspace. This is deterministic even where FK cascades are
        # disabled and avoids a transient workspace SET NULL/check conflict.
        db.query(MobileServiceRequest).filter(
            MobileServiceRequest.user_id == user_id
        ).delete(synchronize_session=False)
        db.query(AccountMember).filter(AccountMember.user_id == user_id).delete(
            synchronize_session=False
        )
        db.query(CompanyUser).filter(CompanyUser.user_id == user_id).delete(
            synchronize_session=False
        )
        db.query(UserProfile).filter(UserProfile.user_id == user_id).delete(
            synchronize_session=False
        )

        # Drop personal workspaces that no longer have any members.
        for account_id in account_ids:
            remaining = (
                db.query(AccountMember)
                .filter(AccountMember.account_id == account_id)
                .count()
            )
            if remaining == 0:
                db.query(Account).filter(Account.id == account_id).delete(
                    synchronize_session=False
                )

        deleted_user = (
            db.query(User)
            .filter(
                User.id == user_id,
                User.password_hash == verified_password_hash,
            )
            .delete(synchronize_session=False)
        )
        if deleted_user != 1:
            raise RuntimeError("credentials changed during account deletion")
        log_audit(
            db,
            "delete_account",
            user_id=user_id,
            user_email=email,
            resource_type="user",
            resource_id=user_id,
            request=request,
            commit=False,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("Account deletion failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=409,
            detail="Account cannot be deleted while retained records reference it",
        ) from exc
    return {"success": True, "deleted": True}


# ── Status ──


@router.get("/status", tags=["auth", "system"])
def auth_status() -> dict:
    backend_base = (settings.backend_base or "").rstrip("/")
    frontend_base = (settings.frontend_base or "").rstrip("/")

    return {
        "backend_base": backend_base,
        "frontend_base": frontend_base,
        "google_oauth": {
            "client_id_set": bool(settings.google_client_id),
            "client_secret_set": bool(settings.google_client_secret),
            "redirect_uri_expected": backend_base + "/auth/google/callback",
        },
        "microsoft_oauth": {
            "client_id_set": bool(settings.microsoft_client_id),
            "client_secret_set": bool(settings.microsoft_client_secret),
            "tenant_id": settings.microsoft_tenant_id,
            "mode": "legacy_graph_callback",
            "redirect_uri_expected": backend_base + "/auth/microsoft/callback",
        },
        "identity": {
            "provider": settings.identity_provider,
            "entra_external_id_configured": settings.entra_external_id_configuration_complete,
            "external_session_endpoint_enabled": settings.identity_provider
            in {"transition", "entra_external_id"},
            "legacy_sessions_accepted": settings.accept_legacy_access_tokens,
        },
    }


def get_external_identity_provider() -> IdentityProvider:
    """Resolve the external-token validator through an overridable dependency."""

    if settings.identity_provider not in {"transition", "entra_external_id"}:
        raise HTTPException(status_code=503, detail="External identity is not enabled")
    try:
        return get_identity_provider()
    except IntegrationConfigurationError as exc:
        raise HTTPException(
            status_code=503,
            detail="External identity is not configured",
        ) from exc


@router.post("/identity/session", response_model=AuthResponse, tags=["auth"])
def create_external_identity_session(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(external_bearer),
    provider: IdentityProvider = Depends(get_external_identity_provider),
    db: Session = Depends(get_db),
):
    """Exchange a validated external API token for a GeoVision session."""

    if not credentials or not credentials.credentials.strip():
        raise HTTPException(status_code=401, detail="Bearer token required")

    validation = provider.validate_token(
        credentials.credentials.strip(),
        token_use=TokenUse.API_ACCESS_TOKEN,
    )
    if not validation.ok or validation.value is None:
        logger.info(
            "identity_exchange result=rejected provider=%s code=%s",
            getattr(provider, "provider_name", "identity"),
            (
                validation.failure.code
                if validation.failure is not None
                else "identity_validation_failed"
            ),
        )
        if validation.status in {
            IntegrationStatus.NOT_CONFIGURED,
            IntegrationStatus.RETRYING,
        } or (validation.failure is not None and validation.failure.retryable):
            raise HTTPException(status_code=503, detail="Identity provider unavailable")
        raise HTTPException(status_code=401, detail="Invalid or expired identity token")

    principal = validation.value
    try:
        resolved = IdentityService(db).resolve_external_principal(
            principal,
            provision=True,
        )
    except IdentityResolutionError as exc:
        logger.info(
            "identity_exchange result=rejected provider=%s code=%s",
            principal.provider,
            exc.code,
        )
        if exc.code in {"email_link_requires_confirmation", "identity_conflict"}:
            status_code = 409
        elif exc.code == "verified_email_required":
            status_code = 403
        elif exc.code == "inactive_or_missing_user":
            status_code = 401
        else:
            status_code = 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    user = resolved.user
    profile = db.get(UserProfile, user.id)
    membership = (
        db.query(AccountMember)
        .filter(AccountMember.user_id == user.id)
        .order_by(AccountMember.created_at.asc())
        .first()
    )
    account = db.get(Account, membership.account_id) if membership else None
    access_token = issue_session_access_token(user, principal)
    refresh_token = _create_refresh_token(
        db,
        user.id,
        principal=principal,
        auth_identity_id=resolved.identity.id if resolved.identity else None,
        auth_generation=user.auth_generation,
    )
    log_audit(
        db,
        "external_identity_login",
        user_id=user.id,
        user_email=user.email,
        details={"provider": principal.provider, "first_login": resolved.created},
        request=request,
    )
    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user={
            "id": user.id,
            "email": user.email,
            "role": resolve_role(user),
            "name": getattr(profile, "full_name", None) or "",
        },
        account=account,
    )


# ── Forgot / Reset Password ──


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=6)

    _validate_password = field_validator("new_password")(validate_new_password)


def _generate_one_time_token() -> str:
    return secrets.token_urlsafe(32)


def _generate_state_token() -> str:
    return secrets.token_urlsafe(24)


def _generate_pkce_verifier() -> str:
    return secrets.token_urlsafe(64)


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _oauth_state_cookie_name(provider: str) -> str:
    return f"geovision_{provider}_oauth_state"


def _oauth_nonce_cookie_name(provider: str) -> str:
    return f"geovision_{provider}_oauth_nonce"


def _create_oauth_state(db: Session, provider: str) -> tuple[str, str]:
    now = utc_now()
    db.query(OAuthState).filter(
        (OAuthState.used.is_(True)) | (OAuthState.expires_at < now)
    ).delete(synchronize_session=False)
    state = _generate_state_token()
    verifier = _generate_pkce_verifier()
    db.add(
        OAuthState(
            state=state,
            provider=provider,
            code_verifier=verifier,
            expires_at=now + timedelta(minutes=OAUTH_STATE_TTL_MINUTES),
        )
    )
    db.commit()
    return state, verifier


def _consume_oauth_state(
    db: Session,
    *,
    provider: str,
    state: str | None,
    cookie_state: str | None,
    browser_nonce: str | None,
) -> tuple[str, str]:
    if not state or not cookie_state or not browser_nonce:
        raise HTTPException(status_code=400, detail="OAuth state ausente.")
    if not secrets.compare_digest(state, cookie_state):
        raise HTTPException(status_code=400, detail="OAuth state inválido.")
    if not OAUTH_BROWSER_NONCE_PATTERN.fullmatch(browser_nonce):
        raise HTTPException(status_code=400, detail="OAuth browser binding inválido.")

    stored = (
        db.query(OAuthState)
        .filter(
            OAuthState.state == state,
            OAuthState.provider == provider,
        )
        .first()
    )
    if not stored or not stored.code_verifier:
        raise HTTPException(status_code=400, detail="OAuth state inválido.")
    if stored.used:
        raise HTTPException(
            status_code=400, detail="OAuth state já utilizado (replay)."
        )
    if stored.expires_at < utc_now():
        raise HTTPException(status_code=400, detail="OAuth state expirado.")

    verifier = stored.code_verifier
    consumed = (
        db.query(OAuthState)
        .filter(OAuthState.id == stored.id, OAuthState.used.is_(False))
        .update({"used": True}, synchronize_session=False)
    )
    if consumed != 1:
        db.rollback()
        raise HTTPException(
            status_code=400, detail="OAuth state já utilizado (replay)."
        )
    db.commit()
    return verifier, browser_nonce


def _set_oauth_cookies(
    response: RedirectResponse,
    provider: str,
    state: str,
    browser_nonce: str,
) -> None:
    response.set_cookie(
        key=_oauth_state_cookie_name(provider),
        value=state,
        max_age=OAUTH_STATE_TTL_MINUTES * 60,
        httponly=True,
        secure=settings.is_deployed,
        samesite="lax",
        path=f"/auth/{provider}",
    )
    response.set_cookie(
        key=_oauth_nonce_cookie_name(provider),
        value=browser_nonce,
        max_age=OAUTH_STATE_TTL_MINUTES * 60,
        httponly=True,
        secure=settings.is_deployed,
        samesite="lax",
        path=f"/auth/{provider}",
    )


def _clear_oauth_state_cookie(response: RedirectResponse, provider: str) -> None:
    for cookie_name in (
        _oauth_state_cookie_name(provider),
        _oauth_nonce_cookie_name(provider),
    ):
        response.delete_cookie(
            key=cookie_name,
            httponly=True,
            secure=settings.is_deployed,
            samesite="lax",
            path=f"/auth/{provider}",
        )


@router.post("/forgot-password", status_code=202)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    email = (payload.email or "").strip().lower()

    user = _find_user_by_email(db, email)
    # External-only accounts do not gain a local password through recovery.
    if user and user.password_hash:
        token = _generate_one_time_token()
        expires_at = utc_now() + timedelta(hours=1)
        rt = ResetToken(
            token_hash=_hash_reset_token(token),
            user_id=user.id,
            auth_generation=user.auth_generation,
            expires_at=expires_at,
        )
        db.add(rt)
        db.commit()
        reset_link = (
            f"{settings.frontend_base.rstrip('/')}/reset-password.html?v=8#"
            f"{urlencode({'token': token})}"
        )
        try:
            send_reset_email(email, reset_link)
        except Exception:
            pass

    return {"message": "If the account exists, a password reset link will be sent."}


@router.post("/reset-password")
def reset_password(
    payload: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)
):
    token = (payload.token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="Token ausente.")

    now = utc_now()
    rt = (
        db.query(ResetToken)
        .filter(ResetToken.token_hash == _hash_reset_token(token))
        .first()
    )
    if not rt or rt.used:
        raise HTTPException(status_code=400, detail="Token inválido ou já utilizado.")
    if rt.expires_at < now:
        raise HTTPException(status_code=400, detail="Token expirou.")

    # Do the intentionally expensive bcrypt work before taking the per-user
    # credential lock so one valid reset does not unnecessarily stall logins.
    new_hash = hash_password(payload.new_password)
    user = (
        db.query(User)
        .filter(User.id == rt.user_id)
        .with_for_update()
        .populate_existing()
        .one_or_none()
    )
    if not user or not user.is_active or not user.password_hash:
        rt.used = True
        db.add(rt)
        db.commit()
        raise HTTPException(status_code=400, detail="Token inválido ou já utilizado.")

    # Every link is bound to the credential generation at issuance. Locking
    # the user first gives PostgreSQL a consistent lock order; the conditional
    # update below remains the correctness gate on SQLite, where FOR UPDATE is
    # intentionally ignored.
    expected_generation = rt.auth_generation
    expected_password_hash = user.password_hash
    if expected_generation != user.auth_generation:
        raise HTTPException(status_code=400, detail="Token inválido ou já utilizado.")

    try:
        advanced = (
            db.query(User)
            .filter(
                User.id == user.id,
                User.is_active.is_(True),
                User.password_hash == expected_password_hash,
                User.auth_generation == expected_generation,
            )
            .update(
                {
                    User.password_hash: new_hash,
                    User.auth_generation: User.auth_generation + 1,
                },
                synchronize_session=False,
            )
        )
        if advanced != 1:
            raise HTTPException(
                status_code=400,
                detail="Token inválido ou já utilizado.",
            )
        claimed = (
            db.query(ResetToken)
            .filter(
                ResetToken.id == rt.id,
                ResetToken.used.is_(False),
                ResetToken.expires_at >= now,
                ResetToken.auth_generation == expected_generation,
            )
            .update({"used": True}, synchronize_session=False)
        )
        if claimed != 1:
            raise HTTPException(
                status_code=400,
                detail="Token inválido ou já utilizado.",
            )
        db.query(ResetToken).filter(
            ResetToken.user_id == user.id,
            ResetToken.used.is_(False),
        ).update({"used": True}, synchronize_session=False)
        for family in db.query(RefreshTokenFamily).filter(
            RefreshTokenFamily.user_id == user.id
        ):
            _revoke_refresh_family(db, family, compromised=False)
        log_audit(
            db,
            "password_reset",
            user_id=rt.user_id,
            resource_type="user",
            resource_id=rt.user_id,
            request=request,
            commit=False,
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.error("Password reset persistence failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=500, detail="Não foi possível atualizar a password"
        ) from exc

    return {"message": "Password atualizada com sucesso."}


# ═══════════════════════════════════════════════════════════════
# Google OAuth
# ═══════════════════════════════════════════════════════════════


@router.get("/google/login")
def google_login(
    browser_nonce: str = Query(
        min_length=43,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
    ),
    db: Session = Depends(get_db),
):
    redirect_uri = settings.backend_base.rstrip("/") + "/auth/google/callback"
    missing = []
    if not settings.google_client_id:
        missing.append("GOOGLE_CLIENT_ID")
    if not settings.google_client_secret:
        missing.append("GOOGLE_CLIENT_SECRET")
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Google OAuth não configurado. Defina {', '.join(missing)}.",
        )

    state, verifier = _create_oauth_state(db, "google")

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "state": state,
        "code_challenge": _pkce_challenge(verifier),
        "code_challenge_method": "S256",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth"
    req = requests.Request("GET", url, params=params).prepare()
    response = RedirectResponse(str(req.url))
    _set_oauth_cookies(response, "google", state, browser_nonce)
    return response


@router.get("/google/callback")
def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    db: Session = Depends(get_db),
):
    try:
        if not code:
            raise HTTPException(status_code=400, detail="Código ausente.")

        redirect_uri = settings.backend_base.rstrip("/") + "/auth/google/callback"
        if not settings.google_client_id or not settings.google_client_secret:
            raise HTTPException(status_code=400, detail="Google OAuth não configurado.")

        code_verifier, browser_nonce = _consume_oauth_state(
            db,
            provider="google",
            state=state,
            cookie_state=request.cookies.get(_oauth_state_cookie_name("google")),
            browser_nonce=request.cookies.get(_oauth_nonce_cookie_name("google")),
        )

        tokres = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            },
            timeout=(
                settings.integration_connect_timeout_seconds,
                settings.integration_read_timeout_seconds,
            ),
            allow_redirects=False,
        )

        if tokres.status_code != 200:
            logger.warning(
                "Google OAuth token exchange rejected (status=%s)",
                tokres.status_code,
            )
            raise HTTPException(
                status_code=400,
                detail="Não foi possível concluir a autenticação Google",
            )

        access_token = tokres.json().get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise HTTPException(
                status_code=400, detail="Resposta OAuth Google inválida"
            )

        ures = requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=(
                settings.integration_connect_timeout_seconds,
                settings.integration_read_timeout_seconds,
            ),
            allow_redirects=False,
        )
        if ures.status_code != 200:
            raise HTTPException(
                status_code=400, detail="Não foi possível validar a conta Google"
            )
        userinfo = ures.json()
        email = userinfo.get("email")
        name = userinfo.get("name")
        picture = userinfo.get("picture")
        google_sub = userinfo.get("id", "")

        if not email:
            raise HTTPException(
                status_code=400, detail="Email não fornecido pelo Google."
            )

        resolved, principal = _find_or_link_identity(
            db,
            provider="google",
            provider_user_id=google_sub,
            email=email,
            display_name=name,
            avatar_url=picture,
            issuer="https://accounts.google.com",
            email_verified=userinfo.get("verified_email") is True,
        )
        user = resolved.user

        _ensure_profile(db, user, full_name=name)
        membership = (
            db.query(AccountMember).filter(AccountMember.user_id == user.id).first()
        )
        account = db.get(Account, membership.account_id) if membership else None

        role = resolve_role(user)
        token = issue_session_access_token(user, principal)

        log_audit(
            db,
            "oauth_login",
            user_id=user.id,
            user_email=email,
            details={"provider": "google"},
            request=request,
        )

        redirect_path = (
            "/admin.html"
            if role == "admin"
            else ("/dashboard.html" if account else "/onboarding.html")
        )
        frontend_base = settings.frontend_base.rstrip("/")
        callback_url = f"{frontend_base}/auth-callback.html?v=8"
        # Use URL fragment (#) instead of query params (?) so the token
        # never appears in server logs, Referer headers, or browser history.
        params = urlencode(
            {
                "token": token,
                "provider": "google",
                "browser_nonce": browser_nonce,
                "redirect": redirect_path,
            }
        )
        response = RedirectResponse(f"{callback_url}#{params}")
        _clear_oauth_state_cookie(response, "google")
        return response

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Google OAuth callback failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=500,
            detail="Erro interno ao concluir autenticação",
        ) from exc


class OnboardingRequest(BaseModel):
    sector_focus: Optional[str] = None
    sectors: Optional[List[str]] = None
    customer_type: str = "farm"
    use_cases: Optional[List[str]] = None
    account_name: Optional[str] = None
    org_name: Optional[str] = None
    modules_enabled: Optional[List[str]] = None
    intent: Optional[str] = Field(default=None, max_length=40)


@router.post("/onboarding", response_model=AuthResponse)
@router.post("/google/onboarding", response_model=AuthResponse, include_in_schema=False)
def complete_onboarding(
    request: Request,
    payload: OnboardingRequest,
    user: User = Depends(current_user_dependency),
    db: Session = Depends(get_db),
):
    email = (user.email or "").strip().lower()
    principal = getattr(request.state, "identity_principal", None)
    if not isinstance(principal, ExternalPrincipal):
        raise HTTPException(status_code=401, detail="Identity context unavailable")

    authorization = request.headers.get("Authorization", "")
    scheme, _, current_access_token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not current_access_token:
        raise HTTPException(status_code=401, detail="Identity token unavailable")

    # Serialize onboarding for this user in databases that support row locks.
    # Reusing the already validated token also preserves its original expiry;
    # onboarding must never become a way to extend an external session.
    locked_user = (
        db.query(User).filter(User.id == user.id).with_for_update().one_or_none()
    )
    if locked_user is None or not locked_user.is_active:
        raise HTTPException(status_code=401, detail="User inválido/inativo")
    user = locked_user

    membership = (
        db.query(AccountMember).filter(AccountMember.user_id == user.id).first()
    )
    if membership:
        account = db.query(Account).filter(Account.id == membership.account_id).first()
        if account is None:
            raise HTTPException(
                status_code=409, detail="Workspace membership is invalid"
            )
        try:
            _ensure_company(db, user, account.name, account.sector_focus)
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            company_membership = (
                db.query(CompanyUser).filter(CompanyUser.user_id == user.id).first()
            )
            if company_membership is None:
                raise HTTPException(
                    status_code=409,
                    detail="Company binding is already in progress; retry the request",
                ) from exc
        return AuthResponse(
            access_token=current_access_token, user=user, account=account
        )

    try:
        account_profile, onboarding_intent = _service_first_profile(
            payload.intent,
            customer_type=payload.customer_type,
            sectors=payload.sectors,
            sector_focus=payload.sector_focus,
            use_cases=payload.use_cases,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    if account_profile is None or onboarding_intent == "view_invitation":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Invitation onboarding must use /invitations/accept",
        )

    modules = payload.modules_enabled or DEFAULT_MODULES
    account_name = (
        payload.account_name or payload.org_name or (email.split("@")[0] + " workspace")
    )
    company = _ensure_company(
        db, user, account_name, str(account_profile["sector_focus"])
    )

    onboarding_account_id = str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"geovision:onboarding:{user.id}")
    )
    account = Account(
        id=onboarding_account_id,
        organization_id=company.id,
        name=account_name,
        sector_focus=str(account_profile["sector_focus"]),
        entity_type=str(account_profile["entity_type"]),
        customer_type=str(account_profile["customer_type"]),
        dashboard_profile=str(account_profile["dashboard_profile"]),
        use_cases=json.dumps(account_profile["use_cases"]),
        org_name=payload.org_name,
        modules_enabled=json.dumps(modules),
        onboarding_user_id=user.id,
    )
    db.add(account)
    membership = AccountMember(
        account_id=onboarding_account_id,
        user_id=user.id,
        role="owner",
        status="active",
        joined_at=utc_now(),
    )
    db.add(membership)
    try:
        db.commit()
    except IntegrityError as exc:
        # A concurrent request may have committed the deterministic starter
        # workspace first. Return that completed result instead of creating a
        # second workspace or turning an idempotent retry into a server error.
        db.rollback()
        account = (
            db.query(Account)
            .filter(Account.onboarding_user_id == user.id)
            .one_or_none()
        )
        membership = (
            db.query(AccountMember)
            .filter(
                AccountMember.account_id == getattr(account, "id", None),
                AccountMember.user_id == user.id,
            )
            .one_or_none()
        )
        company_membership = (
            db.query(CompanyUser).filter(CompanyUser.user_id == user.id).first()
        )
        if account is None or membership is None or company_membership is None:
            raise HTTPException(
                status_code=409,
                detail="Onboarding is already in progress; retry the request",
            ) from exc
    db.refresh(user)
    db.refresh(account)

    return AuthResponse(access_token=current_access_token, user=user, account=account)


# ═══════════════════════════════════════════════════════════════
# Microsoft OAuth (Entra ID)
# ═══════════════════════════════════════════════════════════════


@router.get("/microsoft/login")
def microsoft_login(
    browser_nonce: str = Query(
        min_length=43,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
    ),
    db: Session = Depends(get_db),
):
    redirect_uri = settings.backend_base.rstrip("/") + "/auth/microsoft/callback"
    missing = []
    if not settings.microsoft_client_id:
        missing.append("MICROSOFT_CLIENT_ID")
    if not settings.microsoft_client_secret:
        missing.append("MICROSOFT_CLIENT_SECRET")
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Microsoft OAuth não configurado. Defina {', '.join(missing)}.",
        )

    state, verifier = _create_oauth_state(db, "microsoft")

    tenant = settings.microsoft_tenant_id or "common"
    params = {
        "client_id": settings.microsoft_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile User.Read",
        "state": state,
        "response_mode": "query",
        "code_challenge": _pkce_challenge(verifier),
        "code_challenge_method": "S256",
    }
    url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
    req = requests.Request("GET", url, params=params).prepare()
    response = RedirectResponse(str(req.url))
    _set_oauth_cookies(response, "microsoft", state, browser_nonce)
    return response


@router.get("/microsoft/callback")
def microsoft_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    db: Session = Depends(get_db),
):
    try:
        if not code:
            raise HTTPException(status_code=400, detail="Código ausente.")

        redirect_uri = settings.backend_base.rstrip("/") + "/auth/microsoft/callback"
        if not settings.microsoft_client_id or not settings.microsoft_client_secret:
            raise HTTPException(
                status_code=400, detail="Microsoft OAuth não configurado."
            )

        tenant = settings.microsoft_tenant_id or "common"
        code_verifier, browser_nonce = _consume_oauth_state(
            db,
            provider="microsoft",
            state=state,
            cookie_state=request.cookies.get(_oauth_state_cookie_name("microsoft")),
            browser_nonce=request.cookies.get(_oauth_nonce_cookie_name("microsoft")),
        )

        tokres = requests.post(
            f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
            data={
                "client_id": settings.microsoft_client_id,
                "client_secret": settings.microsoft_client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "scope": "openid email profile User.Read",
                "code_verifier": code_verifier,
            },
            timeout=(
                settings.integration_connect_timeout_seconds,
                settings.integration_read_timeout_seconds,
            ),
            allow_redirects=False,
        )

        if tokres.status_code != 200:
            logger.warning(
                "Microsoft OAuth token exchange rejected (status=%s)",
                tokres.status_code,
            )
            raise HTTPException(
                status_code=400,
                detail="Não foi possível concluir a autenticação Microsoft",
            )

        ms_access_token = tokres.json().get("access_token")
        if not isinstance(ms_access_token, str) or not ms_access_token:
            raise HTTPException(
                status_code=400, detail="Resposta OAuth Microsoft inválida"
            )

        ures = requests.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {ms_access_token}"},
            timeout=(
                settings.integration_connect_timeout_seconds,
                settings.integration_read_timeout_seconds,
            ),
            allow_redirects=False,
        )
        if ures.status_code != 200:
            raise HTTPException(
                status_code=400, detail="Não foi possível validar a conta Microsoft"
            )
        userinfo = ures.json()

        email = userinfo.get("mail") or userinfo.get("userPrincipalName")
        name = userinfo.get("displayName")
        ms_id = userinfo.get("id", "")

        if not email:
            raise HTTPException(
                status_code=400, detail="Email não fornecido pelo Microsoft."
            )

        email = email.strip().lower()

        resolved, principal = _find_or_link_identity(
            db,
            provider="microsoft",
            provider_user_id=ms_id,
            email=email,
            display_name=name,
            issuer="legacy:microsoft",
            # Graph mail/UPN is not a provider-verified mailbox claim. Existing
            # mappings continue; new linking/provisioning requires Entra or an
            # explicit audited flow.
            email_verified=False,
        )
        user = resolved.user

        _ensure_profile(db, user, full_name=name)
        membership = (
            db.query(AccountMember).filter(AccountMember.user_id == user.id).first()
        )
        account = db.get(Account, membership.account_id) if membership else None

        role = resolve_role(user)
        token = issue_session_access_token(user, principal)

        log_audit(
            db,
            "oauth_login",
            user_id=user.id,
            user_email=email,
            details={"provider": "microsoft"},
            request=request,
        )

        redirect_path = (
            "/admin.html"
            if role == "admin"
            else ("/dashboard.html" if account else "/onboarding.html")
        )
        frontend_base = settings.frontend_base.rstrip("/")
        callback_url = f"{frontend_base}/auth-callback.html?v=8"
        params = urlencode(
            {
                "token": token,
                "provider": "microsoft",
                "browser_nonce": browser_nonce,
                "redirect": redirect_path,
            }
        )
        response = RedirectResponse(f"{callback_url}#{params}")
        _clear_oauth_state_cookie(response, "microsoft")
        return response

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Microsoft OAuth callback failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=500,
            detail="Erro interno ao concluir autenticação",
        ) from exc
