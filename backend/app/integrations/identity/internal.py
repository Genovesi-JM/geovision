"""Compatibility adapter for GeoVision-issued session tokens."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any, Optional

from jwt import InvalidTokenError, PyJWTError

from app.core.integration import IntegrationFailure, IntegrationResult
from app.core.tokens import decode_access_token
from app.modules.identity.domain import ExternalPrincipal, TokenUse


_MAX_TOKEN_BYTES = 16 * 1024


class InternalIdentityProvider:
    """Validate the existing HS256 session format through ``core.tokens``."""

    provider_name = "internal"

    def __init__(self, *, issuer: str = "geovision") -> None:
        self._issuer = issuer.strip() or "geovision"

    def validate_token(
        self,
        token: str,
        *,
        token_use: TokenUse,
        expected_nonce: Optional[str] = None,
    ) -> IntegrationResult[ExternalPrincipal]:
        del expected_nonce
        operation = "validate_internal_session"
        if token_use is not TokenUse.INTERNAL_SESSION:
            return self._invalid(operation, "identity_token_use_invalid")
        if not _token_is_within_limit(token):
            return self._invalid(operation)

        try:
            claims = decode_access_token(token)
        except (InvalidTokenError, PyJWTError, TypeError, ValueError):
            return self._invalid(operation)

        principal = self._principal_from_claims(claims)
        if principal is None:
            return self._invalid(operation)
        return IntegrationResult.succeeded(
            provider=self.provider_name,
            operation=operation,
            value=principal,
        )

    def _principal_from_claims(
        self,
        claims: Mapping[str, Any],
    ) -> Optional[ExternalPrincipal]:
        raw_subject = claims.get("sub")
        raw_uid = claims.get("uid")
        subject = raw_subject.strip() if isinstance(raw_subject, str) else ""
        canonical_uid = _canonical_uuid(raw_uid)

        # Versioned sessions use UUID subjects; legacy sessions may only carry
        # an email ``sub`` and remain accepted while the compatibility flag is on.
        if canonical_uid is None and claims.get("gv") is not None:
            canonical_uid = _canonical_uuid(subject)
        signed_identity_subject = claims.get("identity_subject")
        if isinstance(signed_identity_subject, str):
            signed_identity_subject = signed_identity_subject.strip() or None
        else:
            signed_identity_subject = None

        if canonical_uid:
            identity_subject = signed_identity_subject or canonical_uid
            if not subject:
                subject = canonical_uid
        elif subject:
            identity_subject = signed_identity_subject or subject
        else:
            return None

        email_hint = claims.get("email")
        if not isinstance(email_hint, str) or not email_hint.strip():
            email_hint = subject if "@" in subject else None

        raw_role = claims.get("role")
        roles = (
            frozenset({raw_role})
            if isinstance(raw_role, str) and raw_role.strip()
            else frozenset()
        )
        raw_issuer = claims.get("identity_issuer")
        if not isinstance(raw_issuer, str) or not raw_issuer.strip():
            raw_issuer = claims.get("iss")
        issuer = (
            raw_issuer.strip()
            if isinstance(raw_issuer, str) and raw_issuer.strip()
            else self._issuer
        )
        raw_origin_provider = claims.get("idp")
        origin_provider = (
            raw_origin_provider.strip()
            if isinstance(raw_origin_provider, str) and raw_origin_provider.strip()
            else self.provider_name
        )
        auth_generation = claims.get("agen", 0)
        if (
            isinstance(auth_generation, bool)
            or not isinstance(auth_generation, int)
            or auth_generation < 0
        ):
            return None

        return ExternalPrincipal(
            provider=self.provider_name,
            origin_provider=origin_provider,
            identity_subject=identity_subject,
            subject=subject,
            issuer=issuer,
            internal_user_id=canonical_uid,
            internal_auth_generation=auth_generation,
            email_hint=email_hint,
            email_verified=False,
            roles=roles,
        )

    def _invalid(
        self,
        operation: str,
        code: str = "identity_token_invalid",
    ) -> IntegrationResult[ExternalPrincipal]:
        return IntegrationResult.failed(
            provider=self.provider_name,
            operation=operation,
            failure=IntegrationFailure(
                code=code,
                message="identity token is invalid",
                retryable=False,
            ),
        )


def _canonical_uuid(value: object) -> Optional[str]:
    if value is None:
        return None
    try:
        return str(uuid.UUID(str(value)))
    except (AttributeError, TypeError, ValueError):
        return None


def _token_is_within_limit(token: object) -> bool:
    if not isinstance(token, str) or not token:
        return False
    try:
        return len(token.encode("utf-8")) <= _MAX_TOKEN_BYTES
    except UnicodeError:
        return False


__all__ = ["InternalIdentityProvider"]
