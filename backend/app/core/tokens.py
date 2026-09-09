"""OAuth2/JWT helper utilities for token creation and validation.

Keep this module focused on JWT encode/decode.
Request authentication dependencies live in `app.deps`.
"""

from datetime import datetime, timedelta
from typing import Any, Optional, Dict
import uuid

from fastapi import HTTPException, status
import jwt
from jwt import InvalidTokenError

from .config import settings
from .time import utc_now


CURRENT_ACCESS_TOKEN_VERSION = 2


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
    *,
    expires_at: Optional[datetime] = None,
) -> str:
    """Create a signed token while retaining the legacy low-level API."""

    if expires_delta is not None and expires_at is not None:
        raise ValueError("Specify either expires_delta or expires_at, not both")
    to_encode = data.copy()
    minutes = getattr(settings, "access_token_expires_minutes", None) or getattr(settings, "access_token_expire_minutes", 60)
    now = utc_now()
    expire = expires_at or now + (
        expires_delta if expires_delta is not None else timedelta(minutes=minutes)
    )
    to_encode.setdefault("iat", now)
    to_encode.setdefault("jti", str(uuid.uuid4()))
    to_encode["exp"] = expire
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt


def create_user_access_token(
    *,
    user_id: str,
    email: str,
    role: str,
    identity_provider: str = "internal",
    identity_issuer: Optional[str] = None,
    identity_subject: Optional[str] = None,
    auth_generation: int = 0,
    expires_delta: Optional[timedelta] = None,
    expires_at: Optional[datetime] = None,
) -> str:
    """Mint a versioned GeoVision session whose subject is the internal user ID."""

    canonical_user_id = str(uuid.UUID(str(user_id)))
    if (
        isinstance(auth_generation, bool)
        or not isinstance(auth_generation, int)
        or auth_generation < 0
    ):
        raise ValueError("auth_generation must be a non-negative integer")
    return create_access_token(
        {
            "sub": canonical_user_id,
            # ``uid`` remains during the transition for older web/mobile clients.
            "uid": canonical_user_id,
            "email": email,
            "role": role,
            "iss": settings.internal_token_issuer,
            "aud": settings.internal_token_audience,
            "gv": CURRENT_ACCESS_TOKEN_VERSION,
            "idp": identity_provider,
            "identity_issuer": identity_issuer or settings.internal_token_issuer,
            "identity_subject": identity_subject or canonical_user_id,
            "agen": auth_generation,
        },
        expires_delta=expires_delta,
        expires_at=expires_at,
    )


def decode_access_token(token: str) -> Dict[str, Any]:
    """Validate a GeoVision token without converting JWT failures to HTTP errors."""

    unverified = jwt.decode(
        token,
        options={
            "verify_signature": False,
            "verify_exp": False,
            "verify_aud": False,
            "verify_iss": False,
        },
    )
    token_version = unverified.get("gv")
    if token_version == CURRENT_ACCESS_TOKEN_VERSION:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
            audience=settings.internal_token_audience,
            issuer=settings.internal_token_issuer,
            options={
                "require": ["exp", "iat", "sub", "iss", "aud", "uid", "agen"],
                "strict_aud": True,
            },
        )
        try:
            subject_user_id = str(uuid.UUID(str(payload["sub"])))
            compatibility_user_id = str(uuid.UUID(str(payload["uid"])))
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidTokenError("session user identifier is invalid") from exc
        if subject_user_id != compatibility_user_id:
            raise InvalidTokenError("session user identifiers do not match")
        auth_generation = payload.get("agen")
        if (
            isinstance(auth_generation, bool)
            or not isinstance(auth_generation, int)
            or auth_generation < 0
        ):
            raise InvalidTokenError("session authentication generation is invalid")
        return payload
    if token_version is not None:
        raise InvalidTokenError("unsupported access-token version")
    if not settings.accept_legacy_access_tokens:
        raise InvalidTokenError("legacy access tokens are disabled")
    payload = jwt.decode(
        token,
        settings.secret_key,
        algorithms=[settings.algorithm],
        options={"require": ["exp", "uid"]},
    )
    try:
        payload["uid"] = str(uuid.UUID(str(payload["uid"])))
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidTokenError("legacy session user identifier is invalid") from exc
    payload.setdefault("agen", 0)
    return payload


def verify_access_token(token: str) -> Dict[str, Any]:
    try:
        payload = decode_access_token(token)
    except InvalidTokenError as exc:  # pragma: no cover
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    return payload


__all__ = [
    "CURRENT_ACCESS_TOKEN_VERSION",
    "create_access_token",
    "create_user_access_token",
    "decode_access_token",
    "verify_access_token",
]
