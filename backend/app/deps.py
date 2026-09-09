from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from typing import Optional
import json

from app.core.database import get_db
from app.core.config import settings
from app.integrations.identity.internal import InternalIdentityProvider
from app.models import User, AccountMember, Account
from app.modules.identity.domain import AuthorizationContext, ExternalPrincipal, TokenUse
from app.modules.identity.services import (
    IdentityResolutionError,
    IdentityService,
    build_authorization_context,
)

bearer = HTTPBearer()
optional_bearer = HTTPBearer(auto_error=False)


def _resolve_current_user(
    request: Request,
    token: str,
    db: Session,
) -> User:
    validation = InternalIdentityProvider(
        issuer=settings.internal_token_issuer,
    ).validate_token(
        token,
        token_use=TokenUse.INTERNAL_SESSION,
    )
    if not validation.ok or validation.value is None:
        raise HTTPException(status_code=401, detail="Token inv\u00e1lido")
    principal = validation.value
    try:
        resolved = IdentityService(db).resolve_internal_principal(principal)
    except IdentityResolutionError as exc:
        raise HTTPException(status_code=401, detail="User inv\u00e1lido/inativo") from exc

    request.state.identity_principal = principal
    try:
        request.state.authorization_context = build_authorization_context(
            db,
            resolved.user,
            principal,
            requested_workspace_id=request.headers.get("X-Account-ID"),
        )
    except IdentityResolutionError as exc:
        if exc.code == "workspace_access_denied":
            raise HTTPException(status_code=403, detail="Workspace access denied") from exc
        raise
    return resolved.user


def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    return _resolve_current_user(request, creds.credentials, db)


def get_current_user_unauthorized(
    request: Request,
    creds: HTTPAuthorizationCredentials = Depends(optional_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Preserve legacy auth-route behavior: missing credentials return 401."""

    if not creds or not creds.credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return _resolve_current_user(request, creds.credentials, db)


def get_optional_user(
    request: Request,
    creds: HTTPAuthorizationCredentials = Depends(optional_bearer),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Like get_current_user but returns None for guests instead of 401."""
    if not creds or not creds.credentials:
        return None
    try:
        return _resolve_current_user(request, creds.credentials, db)
    except HTTPException as exc:
        # Guest checkout remains available, but an authenticated caller's
        # workspace authorization failure must never silently erase identity.
        if exc.status_code == 401:
            return None
        raise


def get_authorization_context(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AuthorizationContext:
    context = getattr(request.state, "authorization_context", None)
    if isinstance(context, AuthorizationContext) and context.user_id == user.id:
        return context
    principal = getattr(request.state, "identity_principal", None)
    if not isinstance(principal, ExternalPrincipal):
        raise HTTPException(status_code=401, detail="Identity context unavailable")
    try:
        context = build_authorization_context(
            db,
            user,
            principal,
            requested_workspace_id=request.headers.get("X-Account-ID"),
        )
    except IdentityResolutionError as exc:
        if exc.code == "workspace_access_denied":
            raise HTTPException(status_code=403, detail="Workspace access denied") from exc
        raise
    request.state.authorization_context = context
    return context


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")
    return user


def _parse_modules(value: str):
    try:
        parsed = json.loads(value) if value else None
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def get_current_account(
    request: Request,
    account_id: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Account:
    if account_id is None:
        account_id = request.headers.get("X-Account-ID")

    q = db.query(AccountMember).filter(AccountMember.user_id == user.id)
    if account_id:
        membership = q.filter(AccountMember.account_id == account_id).first()
        if not membership:
            raise HTTPException(status_code=403, detail="Sem acesso Aÿ conta pedida.")
    else:
        membership = q.order_by(AccountMember.created_at.asc()).first()
        if not membership:
            raise HTTPException(status_code=403, detail="Sem acesso Aÿ conta pedida.")

    account = db.get(Account, membership.account_id)
    if not account:
        raise HTTPException(status_code=403, detail="Conta inexistente ou inacessA­vel.")

    try:
        request.state.account = account
        request.state.account_modules = _parse_modules(account.modules_enabled)
        principal = getattr(request.state, "identity_principal", None)
        if isinstance(principal, ExternalPrincipal):
            request.state.authorization_context = build_authorization_context(
                db,
                user,
                principal,
                requested_workspace_id=account.id,
            )
    except Exception:
        pass
    return account
