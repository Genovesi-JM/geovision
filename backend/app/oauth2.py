"""Lightweight oauth2 helpers for demo purposes.

This module provides a tiny dependency that checks for an Authorization
header and returns a simple user dict. Replace with a real implementation
using OAuth2PasswordBearer / JWT verification for production.
"""
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from typing import Dict

security = HTTPBearer()


def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)) -> Dict:
    token = credentials.credentials if credentials else None
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    # For development, accept any token and return a simple user object
    return {"email": "dev@example.com", "token": token}
"""OAuth2 helper utilities for token creation and validation."""

from datetime import datetime, timedelta
from typing import Any, Optional, Dict

from fastapi import HTTPException, status
from jose import JWTError, jwt

from .config import settings


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    minutes = getattr(settings, "access_token_expires_minutes", None) or getattr(settings, "access_token_expire_minutes", 60)
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=minutes))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt


def verify_access_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError as exc:  # pragma: no cover
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    return payload
