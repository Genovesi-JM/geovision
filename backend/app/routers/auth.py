"""Authentication endpoints for email/password, Google OAuth, and Microsoft OAuth.

Production-grade implementation with:
- Identity linking (no duplicate accounts for same email across providers)
- Refresh token rotation
- Audit logging
- Rate limiting (handled by middleware)
- Anti-enumeration (forgot-password always returns 202)
"""

import hashlib
import json
import secrets
import traceback
from datetime import datetime, timedelta
from typing import List, Optional, Set
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal, engine, get_db
from ..mail import send_reset_email
from ..middleware import log_audit
from ..models import (
    Account,
    AccountMember,
    AuthIdentity,
    Company,
    CompanyUser,
    OAuthState,
    RefreshTokenModel,
    ResetToken,
    User,
    UserProfile,
)
from ..oauth2 import create_access_token, verify_access_token
from ..schemas import AuthResponse, LoginRequest, RegisterRequest
from ..utils import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

ADMIN_EMAILS: Set[str] = {"genovesi.maria@geovisionops.com"}
DEFAULT_MODULES = ["kpi", "projects", "store", "alerts"]
ALLOWED_SECTORS = {"agro", "mining", "demining", "construction", "infrastructure", "solar"}

REFRESH_TOKEN_BYTES = 48


# ═══════════════════════════════════════════════════════════════
# Helper functions
# ═══════════════════════════════════════════════════════════════

def _ensure_profile(db: Session, user: User, full_name: str | None = None, org_name: str | None = None) -> UserProfile:
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
    db.commit()
    db.refresh(profile)
    return profile


def _ensure_company(db: Session, user: User, account_name: str, sector_focus: str | None = None) -> None:
    """Auto-create a Company record so the user appears in the admin panel."""
    email = (user.email or "").strip().lower()
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()

    existing = db.query(Company).filter(Company.email == email).first()
    if existing:
        # Company exists — ensure CompanyUser link also exists
        cu = db.query(CompanyUser).filter(
            CompanyUser.company_id == existing.id,
            CompanyUser.email == email,
        ).first()
        if not cu:
            db.add(CompanyUser(
                company_id=existing.id,
                email=email,
                name=getattr(profile, "full_name", None) if profile else None,
                role="owner",
                is_active=True,
            ))
        return

    company = Company(
        name=account_name,
        email=email,
        phone=None,
        sectors=json.dumps([sector_focus or "agro"]),
        status="active",
        subscription_plan="trial",
        max_users=5,
        max_sites=10,
        max_storage_gb=50,
        current_users=1,
    )
    db.add(company)
    db.flush()

    # Link user to company
    cu = CompanyUser(
        company_id=company.id,
        email=email,
        name=getattr(profile, "full_name", None) if profile else None,
        role="owner",
        is_active=True,
    )
    db.add(cu)


def _ensure_default_account(db: Session, user: User, sector_focus: str | None = None) -> Account:
    membership = db.query(AccountMember).filter(AccountMember.user_id == user.id).first()
    if membership:
        account = db.query(Account).filter(Account.id == membership.account_id).first()
        if account:
            # Ensure company also exists
            _ensure_company(db, user, account.name, account.sector_focus)
            db.commit()
            return account

    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    email = (user.email or "").strip().lower()
    account_name = None
    if profile:
        account_name = (profile.org_name or profile.company or None)
    if not account_name:
        account_name = (email.split("@")[0] if "@" in email else (email or "geovision")) + " workspace"

    account = Account(
        name=account_name,
        sector_focus=sector_focus or "agro",
        entity_type=(getattr(profile, "entity_type", None) or "individual") if profile else "individual",
        org_name=(getattr(profile, "org_name", None) if profile else None),
        modules_enabled=json.dumps(DEFAULT_MODULES),
    )
    db.add(account)
    db.flush()

    membership = AccountMember(account_id=account.id, user_id=user.id, role="owner")
    db.add(membership)

    # Also create Company for admin panel
    _ensure_company(db, user, account_name, sector_focus)

    db.commit()
    db.refresh(account)
    return account


def resolve_role(user: User) -> str:
    email = (getattr(user, "email", "") or "").strip().lower()
    if email in ADMIN_EMAILS:
        return "admin"
    role = getattr(user, "role", None)
    return role or "cliente"


def create_token(user: User, role: str) -> str:
    payload = {"sub": user.email, "role": role, "uid": getattr(user, "id", None)}
    return create_access_token(payload)


def _hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _create_refresh_token(db: Session, user_id: str, family_id: str | None = None) -> str:
    import uuid as _uuid_mod
    raw_token = secrets.token_urlsafe(REFRESH_TOKEN_BYTES)
    token_hash = _hash_refresh_token(raw_token)

    if not family_id:
        family_id = str(_uuid_mod.uuid4())

    rt = RefreshTokenModel(
        token_hash=token_hash,
        user_id=user_id,
        family_id=family_id,
        expires_at=datetime.utcnow() + timedelta(days=settings.refresh_token_expires_days),
    )
    db.add(rt)
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
) -> User:
    """Identity linking: provider+sub → user, or email → user + link, or create new."""
    identity = (
        db.query(AuthIdentity)
        .filter(AuthIdentity.provider == provider, AuthIdentity.provider_user_id == provider_user_id)
        .first()
    )
    if identity:
        user = db.query(User).filter(User.id == identity.user_id).first()
        if user:
            return user

    email_lower = email.strip().lower()
    user = db.query(User).filter(User.email == email_lower).first()

    if not user:
        role = "admin" if email_lower in ADMIN_EMAILS else "cliente"
        user = User(email=email_lower, password_hash=None, role=role, is_active=True)
        db.add(user)
        db.flush()

    existing_link = (
        db.query(AuthIdentity)
        .filter(AuthIdentity.provider == provider, AuthIdentity.user_id == user.id)
        .first()
    )
    if not existing_link:
        identity = AuthIdentity(
            user_id=user.id,
            provider=provider,
            provider_user_id=provider_user_id,
            email=email_lower,
            display_name=display_name,
            avatar_url=avatar_url,
            raw_data=json.dumps(raw_data, default=str) if raw_data else None,
        )
        db.add(identity)

    db.commit()
    db.refresh(user)
    return user


def _build_auth_response(db: Session, user: User) -> dict:
    desired_role = "admin" if (user.email or "").strip().lower() in ADMIN_EMAILS else (user.role or "cliente")
    if user.role != desired_role:
        user.role = desired_role
        db.add(user)
        db.commit()
        db.refresh(user)

    profile = _ensure_profile(db, user)
    account = _ensure_default_account(db, user)

    role = resolve_role(user)
    access_token = create_access_token({
        "sub": user.email, "email": user.email,
        "role": role, "uid": user.id,
    })
    refresh_token = _create_refresh_token(db, user.id)

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

    sector_focus = payload.sector_focus or "agro"
    if sector_focus not in ALLOWED_SECTORS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid sector_focus")

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    role = "admin" if email in ADMIN_EMAILS else "cliente"
    user = User(email=email, password_hash=hash_password(payload.password), role=role, is_active=True)
    db.add(user)
    db.flush()

    profile = UserProfile(user_id=user.id, full_name=payload.full_name, company=payload.org_name)
    db.add(profile)

    modules = payload.modules_enabled or DEFAULT_MODULES
    account_name = payload.account_name or payload.org_name or ((payload.full_name or email.split("@")[0]) + " workspace")
    account = Account(
        name=account_name, sector_focus=sector_focus,
        entity_type=payload.entity_type, org_name=payload.org_name,
        modules_enabled=json.dumps(modules),
    )
    db.add(account)
    db.flush()

    membership = AccountMember(account_id=account.id, user_id=user.id, role="owner")
    db.add(membership)
    db.commit()
    db.refresh(user)
    db.refresh(account)

    access_token = create_access_token({
        "sub": user.email, "email": user.email,
        "role": user.role, "uid": user.id,
    })
    refresh_token = _create_refresh_token(db, user.id)

    log_audit(db, "register", user_id=user.id, user_email=user.email,
              resource_type="user", resource_id=user.id, request=request)

    return AuthResponse(access_token=access_token, user=user, account=account,
                        refresh_token=refresh_token)


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    email = (payload.email or "").strip().lower()
    user = db.query(User).filter(User.email == email).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Este email não está registado. Cria uma conta ou usa o login Google/Microsoft."
        )

    if not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Esta conta foi criada via OAuth. Usa o botão 'Entrar com Google' ou 'Microsoft'."
        )

    if not verify_password(payload.password, user.password_hash):
        log_audit(db, "login_failed", user_email=email,
                  details={"reason": "wrong_password"}, request=request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Password incorreta. Usa 'Esqueceu a senha?' para redefinir."
        )

    resp = _build_auth_response(db, user)
    log_audit(db, "login", user_id=user.id, user_email=user.email, request=request)
    return AuthResponse(**resp)


# ── Refresh Token ──

class RefreshTokenRequest(BaseModel):
    refresh_token: str


class RefreshTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


@router.post("/refresh", response_model=RefreshTokenResponse)
def refresh_token_endpoint(payload: RefreshTokenRequest, db: Session = Depends(get_db)):
    token_hash = _hash_refresh_token(payload.refresh_token)

    rt = db.query(RefreshTokenModel).filter(
        RefreshTokenModel.token_hash == token_hash,
        RefreshTokenModel.revoked == False,
    ).first()

    if not rt:
        raise HTTPException(status_code=401, detail="Invalid or revoked refresh token")

    if rt.expires_at < datetime.utcnow():
        rt.revoked = True
        db.commit()
        raise HTTPException(status_code=401, detail="Refresh token expired")

    user = db.query(User).filter(User.id == rt.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User inactive")

    rt.revoked = True
    db.add(rt)

    role = resolve_role(user)
    new_access = create_access_token({
        "sub": user.email, "email": user.email,
        "role": role, "uid": user.id,
    })
    new_refresh = _create_refresh_token(db, user.id, family_id=rt.family_id)

    return RefreshTokenResponse(access_token=new_access, refresh_token=new_refresh)


@router.post("/logout")
def logout(
    payload: Optional[RefreshTokenRequest] = None,
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    if payload and payload.refresh_token:
        token_hash = _hash_refresh_token(payload.refresh_token)
        rt = db.query(RefreshTokenModel).filter(RefreshTokenModel.token_hash == token_hash).first()
        if rt:
            db.query(RefreshTokenModel).filter(
                RefreshTokenModel.family_id == rt.family_id
            ).update({"revoked": True})
            db.commit()

    return {"message": "Logged out"}


# ── Current User ──

@router.get("/me", tags=["auth"])
def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    """Return current user profile info from access token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token required")

    token = authorization[7:]
    payload = verify_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    email = payload.get("sub", "")
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    membership = db.query(AccountMember).filter(AccountMember.user_id == user.id).first()
    account = None
    if membership:
        account = db.query(Account).filter(Account.id == membership.account_id).first()

    # Find the company linked to this user (for client document access)
    company_row = None
    try:
        company_row = db.query(CompanyUser).filter(CompanyUser.email == email.lower()).first()
        if not company_row:
            # Fallback: Company exists but CompanyUser link missing
            co = db.query(Company).filter(Company.email == email.lower()).first()
            if co:
                company_row = CompanyUser(company_id=co.id, email=email.lower(),
                                          name=getattr(profile, "full_name", None) or "",
                                          role="owner", is_active=True)
                db.add(company_row)
                db.commit()
    except Exception:
        pass

    return {
        "email": user.email,
        "name": getattr(profile, "full_name", None) or "",
        "role": resolve_role(user),
        "company": getattr(profile, "company", None) or getattr(profile, "org_name", None) or "",
        "account_id": getattr(account, "id", "") if account else "",
        "account_name": getattr(account, "name", "") if account else "",
        "company_id": company_row.company_id if company_row else "",
    }


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
            "redirect_uri_expected": backend_base + "/auth/microsoft/callback",
        },
    }


# ── Forgot / Reset Password ──

class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


def _generate_one_time_token() -> str:
    return secrets.token_urlsafe(32)


def _generate_state_token() -> str:
    return secrets.token_urlsafe(24)


@router.post("/forgot-password", status_code=202)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    email = (payload.email or "").strip().lower()

    user = db.query(User).filter(User.email == email).first()
    if user:
        token = _generate_one_time_token()
        expires_at = datetime.utcnow() + timedelta(hours=1)
        rt = ResetToken(token=token, user_id=user.id, expires_at=expires_at)
        db.add(rt)
        db.commit()
        reset_link = f"{settings.frontend_base.rstrip('/')}/reset-password.html?token={token}"
        try:
            send_reset_email(email, reset_link)
        except Exception:
            pass

    return {"message": "If the account exists, a password reset link will be sent."}


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    token = (payload.token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="Token ausente.")

    now = datetime.utcnow()
    rt = db.query(ResetToken).filter(ResetToken.token == token, ResetToken.used == False).first()
    if not rt:
        raise HTTPException(status_code=400, detail="Token inválido ou já utilizado.")
    if rt.expires_at < now:
        raise HTTPException(status_code=400, detail="Token expirou.")

    new_hash = hash_password(payload.new_password)
    try:
        with engine.begin() as conn:
            conn.execute(text("UPDATE users SET password_hash=:h WHERE id=:uid"), {"h": new_hash, "uid": rt.user_id})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    rt.used = True
    db.add(rt)
    db.commit()

    log_audit(db, "password_reset", user_id=rt.user_id, resource_type="user",
              resource_id=rt.user_id, request=request)

    return {"message": "Password atualizada com sucesso."}


# ═══════════════════════════════════════════════════════════════
# Google OAuth
# ═══════════════════════════════════════════════════════════════

@router.get("/google/login")
def google_login(db: Session = Depends(get_db)):
    redirect_uri = settings.backend_base.rstrip("/") + "/auth/google/callback"
    missing = []
    if not settings.google_client_id:
        missing.append("GOOGLE_CLIENT_ID")
    if not settings.google_client_secret:
        missing.append("GOOGLE_CLIENT_SECRET")
    if missing:
        raise HTTPException(status_code=400, detail=f"Google OAuth não configurado. Defina {', '.join(missing)}.")

    state = _generate_state_token()
    expires_at = datetime.utcnow() + timedelta(minutes=10)
    os_state = OAuthState(state=state, expires_at=expires_at)
    db.add(os_state)
    db.commit()

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "state": state,
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth"
    req = requests.Request("GET", url, params=params).prepare()
    return RedirectResponse(str(req.url))


@router.get("/google/callback")
def google_callback(code: str | None = None, state: str | None = None,
                    request: Request = None, db: Session = Depends(get_db)):
    try:
        if not code:
            raise HTTPException(status_code=400, detail="Código ausente.")

        redirect_uri = settings.backend_base.rstrip("/") + "/auth/google/callback"
        if not settings.google_client_id or not settings.google_client_secret:
            raise HTTPException(status_code=400, detail="Google OAuth não configurado.")

        tokres = requests.post("https://oauth2.googleapis.com/token", data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }, timeout=10)

        if tokres.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Erro a trocar o código: {tokres.text}")

        access_token = tokres.json().get("access_token")

        # ── CRITICAL: validate OAuth state (CSRF protection) ──
        if not state:
            raise HTTPException(status_code=400, detail="OAuth state ausente.")
        st = db.query(OAuthState).filter(OAuthState.state == state).first()
        if not st:
            raise HTTPException(status_code=400, detail="OAuth state inválido.")
        if st.used:
            raise HTTPException(status_code=400, detail="OAuth state já utilizado (replay).")
        if st.expires_at < datetime.utcnow():
            raise HTTPException(status_code=400, detail="OAuth state expirado.")
        st.used = True
        db.add(st)
        db.commit()

        ures = requests.get("https://www.googleapis.com/oauth2/v2/userinfo",
                            params={"access_token": access_token}, timeout=10)
        ures.raise_for_status()
        userinfo = ures.json()
        email = userinfo.get("email")
        name = userinfo.get("name")
        picture = userinfo.get("picture")
        google_sub = userinfo.get("id", "")

        if not email:
            raise HTTPException(status_code=400, detail="Email não fornecido pelo Google.")

        user = _find_or_link_identity(
            db, provider="google", provider_user_id=google_sub,
            email=email, display_name=name, avatar_url=picture,
            raw_data=userinfo,
        )

        _ensure_profile(db, user, full_name=name)
        account = _ensure_default_account(db, user)

        role = resolve_role(user)
        token = create_access_token({"sub": email, "role": role, "uid": user.id})

        log_audit(db, "oauth_login", user_id=user.id, user_email=email,
                  details={"provider": "google"}, request=request)

        redirect_path = "/admin.html" if role == "admin" else "/dashboard.html"
        frontend_base = settings.frontend_base.rstrip("/")
        callback_url = f"{frontend_base}/auth-callback.html"
        # Use URL fragment (#) instead of query params (?) so the token
        # never appears in server logs, Referer headers, or browser history.
        params = urlencode({
            "token": token, "email": email, "role": role,
            "name": name or "",
            "account_id": getattr(account, "id", ""),
            "account_name": getattr(account, "name", ""),
            "redirect": redirect_path,
        })
        return RedirectResponse(f"{callback_url}#{params}")

    except HTTPException:
        raise
    except Exception as exc:
        print("[GeoVision] Unhandled error in google_callback")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Erro interno: {type(exc).__name__}: {exc}")


class GoogleOnboardingRequest(BaseModel):
    sector_focus: str
    sectors: Optional[List[str]] = None
    entity_type: str = "individual"
    account_name: Optional[str] = None
    org_name: Optional[str] = None
    modules_enabled: Optional[List[str]] = None


@router.post("/google/onboarding", response_model=AuthResponse)
def google_onboarding(
    payload: GoogleOnboardingRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    token = authorization.split()[1].strip()
    claims = verify_access_token(token)
    user_id = claims.get("uid")
    email = claims.get("sub")
    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    user = None
    if user_id:
        user = db.query(User).filter(User.id == user_id).first()
    if not user and email:
        user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email, password_hash=None, role="cliente", is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)

    membership = db.query(AccountMember).filter(AccountMember.user_id == user.id).first()
    if membership:
        account = db.query(Account).filter(Account.id == membership.account_id).first()
        new_token = create_access_token({
            "sub": user.email, "email": user.email,
            "role": user.role, "uid": user.id,
        })
        return AuthResponse(access_token=new_token, user=user, account=account)

    if payload.sectors:
        sectors_list = [s.strip() for s in payload.sectors if s.strip() in ALLOWED_SECTORS]
    else:
        sectors_list = [s.strip() for s in (payload.sector_focus or "agro").split(",") if s.strip() in ALLOWED_SECTORS]
    if not sectors_list:
        sectors_list = ["agro"]

    sector = ",".join(sectors_list)
    modules = payload.modules_enabled or DEFAULT_MODULES
    account_name = payload.account_name or payload.org_name or (email.split("@")[0] + " workspace")

    account = Account(
        name=account_name, sector_focus=sector,
        entity_type=payload.entity_type or "individual",
        org_name=payload.org_name,
        modules_enabled=json.dumps(modules),
    )
    db.add(account)
    db.flush()

    membership = AccountMember(account_id=account.id, user_id=user.id, role="owner")
    db.add(membership)
    db.commit()
    db.refresh(user)
    db.refresh(account)

    new_token = create_access_token({
        "sub": user.email, "email": user.email,
        "role": user.role, "uid": user.id,
    })
    return AuthResponse(access_token=new_token, user=user, account=account)


# ═══════════════════════════════════════════════════════════════
# Microsoft OAuth (Entra ID)
# ═══════════════════════════════════════════════════════════════

@router.get("/microsoft/login")
def microsoft_login(db: Session = Depends(get_db)):
    redirect_uri = settings.backend_base.rstrip("/") + "/auth/microsoft/callback"
    missing = []
    if not settings.microsoft_client_id:
        missing.append("MICROSOFT_CLIENT_ID")
    if not settings.microsoft_client_secret:
        missing.append("MICROSOFT_CLIENT_SECRET")
    if missing:
        raise HTTPException(status_code=400, detail=f"Microsoft OAuth não configurado. Defina {', '.join(missing)}.")

    state = _generate_state_token()
    expires_at = datetime.utcnow() + timedelta(minutes=10)
    os_state = OAuthState(state=state, expires_at=expires_at)
    db.add(os_state)
    db.commit()

    tenant = settings.microsoft_tenant_id or "common"
    params = {
        "client_id": settings.microsoft_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile User.Read",
        "state": state,
        "response_mode": "query",
    }
    url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
    req = requests.Request("GET", url, params=params).prepare()
    return RedirectResponse(str(req.url))


@router.get("/microsoft/callback")
def microsoft_callback(code: str | None = None, state: str | None = None,
                        request: Request = None, db: Session = Depends(get_db)):
    try:
        if not code:
            raise HTTPException(status_code=400, detail="Código ausente.")

        redirect_uri = settings.backend_base.rstrip("/") + "/auth/microsoft/callback"
        if not settings.microsoft_client_id or not settings.microsoft_client_secret:
            raise HTTPException(status_code=400, detail="Microsoft OAuth não configurado.")

        tenant = settings.microsoft_tenant_id or "common"

        tokres = requests.post(
            f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
            data={
                "client_id": settings.microsoft_client_id,
                "client_secret": settings.microsoft_client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "scope": "openid email profile User.Read",
            },
            timeout=10,
        )

        if tokres.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Erro a trocar o código Microsoft: {tokres.text}")

        ms_access_token = tokres.json().get("access_token")

        # ── CRITICAL: validate OAuth state (CSRF protection) ──
        if not state:
            raise HTTPException(status_code=400, detail="OAuth state ausente.")
        st = db.query(OAuthState).filter(OAuthState.state == state).first()
        if not st:
            raise HTTPException(status_code=400, detail="OAuth state inválido.")
        if st.used:
            raise HTTPException(status_code=400, detail="OAuth state já utilizado (replay).")
        if st.expires_at < datetime.utcnow():
            raise HTTPException(status_code=400, detail="OAuth state expirado.")
        st.used = True
        db.add(st)
        db.commit()

        ures = requests.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {ms_access_token}"},
            timeout=10,
        )
        ures.raise_for_status()
        userinfo = ures.json()

        email = userinfo.get("mail") or userinfo.get("userPrincipalName")
        name = userinfo.get("displayName")
        ms_id = userinfo.get("id", "")

        if not email:
            raise HTTPException(status_code=400, detail="Email não fornecido pelo Microsoft.")

        email = email.strip().lower()

        user = _find_or_link_identity(
            db, provider="microsoft", provider_user_id=ms_id,
            email=email, display_name=name, raw_data=userinfo,
        )

        _ensure_profile(db, user, full_name=name)
        account = _ensure_default_account(db, user)

        role = resolve_role(user)
        token = create_access_token({"sub": email, "role": role, "uid": user.id})

        log_audit(db, "oauth_login", user_id=user.id, user_email=email,
                  details={"provider": "microsoft"}, request=request)

        redirect_path = "/admin.html" if role == "admin" else "/dashboard.html"
        frontend_base = settings.frontend_base.rstrip("/")
        callback_url = f"{frontend_base}/auth-callback.html"
        params = urlencode({
            "token": token, "email": email, "role": role,
            "name": name or "",
            "account_id": getattr(account, "id", ""),
            "account_name": getattr(account, "name", ""),
            "redirect": redirect_path,
        })
        return RedirectResponse(f"{callback_url}#{params}")

    except HTTPException:
        raise
    except Exception as exc:
        print("[GeoVision] Unhandled error in microsoft_callback")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Erro interno: {type(exc).__name__}: {exc}")
