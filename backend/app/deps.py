from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from typing import Optional
import json

from app.database import get_db
from app.oauth2 import verify_access_token
from app.models import User, AccountMember, Account

bearer = HTTPBearer()
optional_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    token = creds.credentials if creds else None
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = verify_access_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Token inv\u00e1lido")

    uid = payload.get("uid")
    sub = payload.get("sub")

    user = None
    if uid:
        user = db.get(User, uid)
    if not user and sub:
        user = db.query(User).filter(User.email == sub).first()

    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User inv\u00e1lido/inativo")
    return user


def get_optional_user(
    creds: HTTPAuthorizationCredentials = Depends(optional_bearer),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Like get_current_user but returns None for guests instead of 401."""
    if not creds or not creds.credentials:
        return None
    try:
        payload = verify_access_token(creds.credentials)
    except Exception:
        return None
    uid = payload.get("uid")
    sub = payload.get("sub")
    user = None
    if uid:
        user = db.get(User, uid)
    if not user and sub:
        user = db.query(User).filter(User.email == sub).first()
    if not user or not user.is_active:
        return None
    return user


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
        q = q.filter(AccountMember.account_id == account_id)
    membership = q.first()

    if not membership:
        membership = (
            db.query(AccountMember)
            .filter(AccountMember.user_id == user.id)
            .order_by(AccountMember.role.desc())
            .first()
        )
        if not membership:
            raise HTTPException(status_code=403, detail="Sem acesso Aÿ conta pedida.")

    account = db.get(Account, membership.account_id)
    if not account:
        raise HTTPException(status_code=403, detail="Conta inexistente ou inacessA­vel.")

    try:
        request.state.account = account
        request.state.account_modules = _parse_modules(account.modules_enabled)
    except Exception:
        pass
    return account
