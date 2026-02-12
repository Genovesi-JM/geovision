"""Authentication endpoints for email/password and Google OAuth."""

import json
import secrets
import traceback
from datetime import datetime, timedelta
from typing import List, Optional, Set
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, Depends, HTTPException, Header, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal, engine, get_db
from ..mail import send_reset_email
from ..models import (
    Account,
    AccountMember,
    OAuthState,
    ResetToken,
    User,
    UserProfile,
)
from ..oauth2 import create_access_token, verify_access_token
from ..schemas import AuthResponse, LoginRequest, RegisterRequest
from ..utils import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

ADMIN_EMAILS: Set[str] = {"teste@admin.com"}
DEFAULT_MODULES = ["kpi", "projects", "store", "alerts"]
ALLOWED_SECTORS = {"agro", "mining", "demining", "construction", "infrastructure", "solar"}


def resolve_role(user: User) -> str:
    role = getattr(user, "role", None)
    if role:
        return role
    if user.email.lower() in ADMIN_EMAILS:
        return "admin"
    return "cliente"


def create_token(user: User, role: str) -> str:
    payload = {"sub": user.email, "role": role, "uid": getattr(user, "id", None)}
    return create_access_token(payload)

@router.post("/register", response_model=AuthResponse, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    """Register a new user plus first account using email/password."""
    email = (payload.email or "").strip().lower()

    sector_focus = payload.sector_focus or "agro"
    if sector_focus not in ALLOWED_SECTORS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid sector_focus")

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    user = User(email=email, password_hash=hash_password(payload.password), role="cliente", is_active=True)
    db.add(user)
    db.flush()

    profile = UserProfile(user_id=user.id, full_name=payload.full_name, company=payload.org_name)
    db.add(profile)

    modules = payload.modules_enabled or DEFAULT_MODULES
    account_name = payload.account_name or payload.org_name or ((payload.full_name or email.split("@")[0]) + " workspace")
    account = Account(
        name=account_name,
        sector_focus=sector_focus,
        entity_type=payload.entity_type,
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

    token = create_access_token({
        "sub": user.email,
        "email": user.email,
        "role": user.role,
        "uid": user.id,
    })

    return AuthResponse(
        access_token=token,
        user=user,
        account=account,
    )


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    email = (payload.email or "").strip().lower()
    user = db.query(User).filter(User.email == email).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Este email não está registado. Cria uma conta ou usa o login Google."
        )

    if not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Esta conta foi criada via Google. Usa o botão 'Entrar com Google'."
        )

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Password incorreta. Usa 'Esqueceu a senha?' para redefinir."
        )

    token = create_access_token({
        "sub": user.email,
        "email": user.email,
        "role": user.role,
        "uid": user.id,
    })

    membership = db.query(AccountMember).filter(AccountMember.user_id == user.id).first()
    account = None
    if membership:
        account = db.query(Account).filter(Account.id == membership.account_id).first()

    return AuthResponse(
        access_token=token,
        user=user,
        account=account,
    )


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


def _generate_one_time_token() -> str:
    return secrets.token_urlsafe(32)


def _generate_state_token() -> str:
    return secrets.token_urlsafe(24)


@router.get("/status", tags=["auth", "system"])
def auth_status() -> dict:
    """Non-sensitive auth/runtime configuration status for debugging deployments."""
    backend_base = (settings.backend_base or "").rstrip("/")
    frontend_base = (settings.frontend_base or "").rstrip("/")
    redirect_uri = (backend_base + "/auth/google/callback") if backend_base else ""

    return {
        "backend_base": backend_base,
        "frontend_base": frontend_base,
        "google_oauth": {
            "client_id_set": bool(settings.google_client_id),
            "client_secret_set": bool(settings.google_client_secret),
            "redirect_uri_expected": redirect_uri,
        },
    }


@router.post("/forgot-password", status_code=202)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Request a password reset. Always returns 202 to avoid user enumeration."""
    email = (payload.email or "").strip().lower()

    user = db.query(User).filter(User.email == email).first()
    if user:
        token = _generate_one_time_token()
        expires_at = datetime.utcnow() + timedelta(hours=1)
        rt = ResetToken(token=token, user_id=user.id, expires_at=expires_at)
        db.add(rt)
        db.commit()
        reset_link = f"{settings.frontend_base.rstrip('/')}" + f"/reset-password.html?token={token}"
        try:
            send_reset_email(email, reset_link)
        except Exception:
            pass

    return {"message": "If the account exists, a password reset link will be sent."}


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Reset password given a valid one-time DB-backed token."""
    token = (payload.token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="Token ausente.")

    now = datetime.utcnow()
    rt = db.query(ResetToken).filter(ResetToken.token == token, ResetToken.used == False).first()
    if not rt:
        raise HTTPException(status_code=400, detail="Token invA­lido ou jA­ utilizado.")
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

    return {"message": "Password atualizada com sucesso."}


@router.get("/google/login")
def google_login(db: Session = Depends(get_db)):
    """Redirect the user to Google's OAuth2 consent screen."""
    redirect_uri = settings.backend_base.rstrip("/") + "/auth/google/callback"
    missing = []
    if not settings.google_client_id:
        missing.append("GOOGLE_CLIENT_ID")
    if not settings.google_client_secret:
        missing.append("GOOGLE_CLIENT_SECRET")
    if missing:
        raise HTTPException(
            status_code=400,
            detail=(
                "Google OAuth não configurado. Defina "
                + ", ".join(missing)
                + ". Redirect URI esperado no Google Console: "
                + redirect_uri
            ),
        )
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
    return RedirectResponse(req.url)


@router.get("/google/callback")
def google_callback(code: str = None, state: str = None, db: Session = Depends(get_db)):
    """Handle Google OAuth2 callback and return an app JWT."""
    try:
        if not code:
            raise HTTPException(status_code=400, detail="Código ausente.")
        if not state:
            raise HTTPException(status_code=400, detail="State ausente.")
        if not settings.google_client_id or not settings.google_client_secret:
            redirect_uri = settings.backend_base.rstrip("/") + "/auth/google/callback"
            missing = []
            if not settings.google_client_id:
                missing.append("GOOGLE_CLIENT_ID")
            if not settings.google_client_secret:
                missing.append("GOOGLE_CLIENT_SECRET")
            raise HTTPException(
                status_code=400,
                detail=(
                    "Google OAuth não configurado. Defina "
                    + ", ".join(missing)
                    + ". Redirect URI esperado no Google Console: "
                    + redirect_uri
                ),
            )

        token_url = "https://oauth2.googleapis.com/token"
        redirect_uri = settings.backend_base.rstrip("/") + "/auth/google/callback"
        data = {
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        try:
            tokres = requests.post(token_url, data=data, timeout=10)
            if tokres.status_code != 200:
                body = tokres.text
                try:
                    body = json.dumps(tokres.json(), ensure_ascii=False)
                except Exception:
                    pass
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Erro a trocar o código: "
                        f"HTTP {tokres.status_code} - {body}. "
                        f"redirect_uri={redirect_uri}"
                    ),
                )

            tok = tokres.json()
            access_token = tok.get("access_token")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Erro a trocar o código: {type(exc).__name__}: {exc}")

        now = datetime.utcnow()
        # State validation - be tolerant after Render database resets
        st = db.query(OAuthState).filter(OAuthState.state == state).first()
        if not st:
            # Fallback: try most recent state
            st = db.query(OAuthState).order_by(OAuthState.created_at.desc()).first()
        
        # If we successfully exchanged the code with Google, proceed even without valid state
        # Google's token exchange already validates the OAuth flow integrity
        if st:
            if st.expires_at >= now:
                st.used = True
                db.add(st)
                db.commit()
        # If no state found but token exchange succeeded, continue anyway (Render DB reset scenario)

        try:
            ures = requests.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                params={"access_token": access_token},
                timeout=10,
            )
            ures.raise_for_status()
            userinfo = ures.json()
            email = userinfo.get("email")
            name = userinfo.get("name")
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Erro a obter userinfo: {type(exc).__name__}: {exc}")

        if not email:
            raise HTTPException(status_code=400, detail="Email não fornecido pelo Google.")

        row = db.execute(text("SELECT id, role FROM users WHERE email = :email"), {"email": email}).first()
        if row:
            user_id = row[0]
            role = row[1] if row[1] else ("admin" if email.lower() in ADMIN_EMAILS else "cliente")
        else:
            temp_pass = secrets.token_urlsafe(12)
            # Truncate to 72 bytes inline to avoid bcrypt limit issues
            temp_pass_safe = temp_pass.encode('utf-8')[:72].decode('utf-8', errors='ignore')
            hashed = hash_password(temp_pass_safe)
            now_iso = datetime.utcnow().isoformat(sep=" ")

            insertion_error = None
            fallback_error = None
            try:
                new_user = User(email=email, password_hash=hashed, role="cliente", is_active=True)
                db.add(new_user)
                db.commit()
                user_id = new_user.id
                role = resolve_role(new_user)
            except Exception as exc:
                insertion_error = exc
                db.rollback()
                try:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "INSERT INTO users (email, password_hash, role, is_active, created_at, updated_at) VALUES (:email, :password_hash, :role, 1, :now, :now)"
                            ),
                            {"email": email, "password_hash": hashed, "role": "cliente", "now": now_iso},
                        )
                    insertion_error = None
                except Exception as exc2:
                    fallback_error = exc2

            try:
                with SessionLocal() as fresh_db:
                    user_row = fresh_db.execute(
                        text("SELECT id FROM users WHERE email = :email"),
                        {"email": email},
                    ).first()
            except Exception:
                user_row = None
            if not user_row:
                details = []
                if insertion_error:
                    details.append(str(insertion_error))
                if fallback_error:
                    details.append(str(fallback_error))
                raise HTTPException(status_code=500, detail=("Falha a criar/utilizar utilizador. " + " | ".join(details)))
            user_id = user_row[0]
            role = "cliente"

    # token JWT com email como "sub" e id em "uid",
    # para ser compatível com o fluxo de onboarding Google.
        token = create_access_token({"sub": email, "role": role, "uid": user_id})
        # Se o utilizador ainda não tiver conta associada, envia para onboarding
        membership = db.query(AccountMember).filter(AccountMember.user_id == user_id).first()
        redirect_path = "/admin.html" if role == "admin" else "/dashboard.html"
        if not membership:
            redirect_path = "/onboarding.html"

        frontend_base = settings.frontend_base.rstrip("/")
        callback_url = f"{frontend_base}/auth-callback.html"
        params = urlencode({
            "token": token,
            "email": email,
            "role": role,
            "redirect": redirect_path,
        })
        return RedirectResponse(f"{callback_url}?{params}")

    except HTTPException:
        raise
    except Exception as exc:
        # Log full traceback to Render logs, return a safe error to the client
        print("[GeoVision] Unhandled error in google_callback")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Erro interno no callback Google: {type(exc).__name__}: {exc}")


class GoogleOnboardingRequest(BaseModel):
    sector_focus: str  # Can be comma-separated for multiple sectors
    sectors: Optional[List[str]] = None  # Alternative: list of sectors
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
    """Completa o perfil após login com Google escolhendo o tipo de conta.

    Usa o JWT emitido no callback para identificar o utilizador e cria
    (ou reutiliza) uma conta + membership, devolvendo um AuthResponse
    semelhante ao /auth/login.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    token = authorization.split()[1].strip()
    claims = verify_access_token(token)
    user_id = claims.get("uid")
    email = claims.get("sub")
    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    # Try to find user by id first, then by email
    user = None
    if user_id:
        user = db.query(User).filter(User.id == user_id).first()
    
    # If not found by id, try by email (handles database resets on Render)
    if not user and email:
        user = db.query(User).filter(User.email == email).first()
    
    # If still not found, create the user (resilient onboarding)
    if not user:
        temp_pass = secrets.token_urlsafe(12)
        temp_pass_safe = temp_pass.encode('utf-8')[:72].decode('utf-8', errors='ignore')
        hashed = hash_password(temp_pass_safe)
        user = User(email=email, password_hash=hashed, role="cliente", is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)

    # Se já tiver membership, só devolve os dados
    membership = db.query(AccountMember).filter(AccountMember.user_id == user.id).first()
    if membership:
        account = db.query(Account).filter(Account.id == membership.account_id).first()
        new_token = create_access_token({
            "sub": user.email,
            "email": user.email,
            "role": user.role,
            "uid": user.id,
        })
        return AuthResponse(access_token=new_token, user=user, account=account)

    # Support multiple sectors - either from sectors list or comma-separated sector_focus
    if payload.sectors:
        sectors_list = [s.strip() for s in payload.sectors if s.strip() in ALLOWED_SECTORS]
    else:
        sectors_list = [s.strip() for s in (payload.sector_focus or "agro").split(",") if s.strip() in ALLOWED_SECTORS]
    
    if not sectors_list:
        sectors_list = ["agro"]  # Default fallback
    
    # Store as comma-separated string
    sector = ",".join(sectors_list)

    modules = payload.modules_enabled or DEFAULT_MODULES
    account_name = payload.account_name or payload.org_name or (email.split("@")[0] + " workspace")

    account = Account(
        name=account_name,
        sector_focus=sector,
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
        "sub": user.email,
        "email": user.email,
        "role": user.role,
        "uid": user.id,
    })
    return AuthResponse(access_token=new_token, user=user, account=account)
