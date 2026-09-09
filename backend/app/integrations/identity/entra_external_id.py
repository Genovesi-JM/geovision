"""Strict Microsoft Entra External ID API access-token validation."""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from collections.abc import Mapping
from typing import Any, Callable, Optional, Protocol
from urllib.parse import urlsplit

import jwt
import requests
from jwt import ExpiredSignatureError, InvalidTokenError, PyJWK, PyJWTError

from app.core.integration import (
    IntegrationFailure,
    IntegrationResult,
    IntegrationStatus,
)
from app.modules.identity.domain import ExternalPrincipal, TokenUse


_MAX_TOKEN_BYTES = 16 * 1024
_MAX_DOCUMENT_BYTES = 1024 * 1024
_MAX_JWKS_KEYS = 64
_UNKNOWN_KID_REFRESH_COOLDOWN_SECONDS = 5.0
logger = logging.getLogger(__name__)


class JsonDocumentFetcher(Protocol):
    """Small injectable HTTP seam used for OIDC discovery and JWKS."""

    def fetch_json(
        self,
        url: str,
        *,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
    ) -> Mapping[str, Any]: ...


class _ProviderDocumentUnavailable(RuntimeError):
    """A deliberately detail-free provider-document failure."""


class _UnknownSigningKey(RuntimeError):
    """The configured provider does not currently publish the token key."""


class RequestsJsonDocumentFetcher:
    """TLS-verifying, redirect-refusing JSON document fetcher."""

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self._session = session or requests.Session()

    def fetch_json(
        self,
        url: str,
        *,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
    ) -> Mapping[str, Any]:
        _require_https_url(url)
        try:
            with self._session.get(
                url,
                timeout=(connect_timeout_seconds, read_timeout_seconds),
                allow_redirects=False,
                verify=True,
                headers={"Accept": "application/json"},
                stream=True,
            ) as response:
                if response.status_code < 200 or response.status_code >= 300:
                    raise _ProviderDocumentUnavailable(
                        "identity provider document is unavailable"
                    )
                content_length = response.headers.get("Content-Length")
                if content_length:
                    try:
                        if int(content_length) > _MAX_DOCUMENT_BYTES:
                            raise _ProviderDocumentUnavailable(
                                "identity provider document is invalid"
                            )
                    except ValueError:
                        pass
                body_parts: list[bytes] = []
                body_size = 0
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    body_size += len(chunk)
                    if body_size > _MAX_DOCUMENT_BYTES:
                        raise _ProviderDocumentUnavailable(
                            "identity provider document is invalid"
                        )
                    body_parts.append(chunk)
                body = b"".join(body_parts)
        except requests.RequestException as exc:
            raise _ProviderDocumentUnavailable(
                "identity provider document is unavailable"
            ) from exc
        try:
            document = json.loads(body)
        except (TypeError, ValueError, UnicodeError) as exc:
            raise _ProviderDocumentUnavailable(
                "identity provider document is invalid"
            ) from exc
        if not isinstance(document, dict):
            raise _ProviderDocumentUnavailable(
                "identity provider document is invalid"
            )
        return document


class EntraExternalIdProvider:
    """Validate delegated v2.0 access tokens from one external tenant."""

    provider_name = "entra_external_id"

    def __init__(
        self,
        *,
        issuer: Optional[str],
        audience: Optional[str],
        tenant_id: Optional[str],
        discovery_url: Optional[str],
        required_scope: Optional[str],
        authorized_party: Optional[str] = None,
        clock_skew_seconds: int = 60,
        jwks_cache_seconds: int = 3600,
        connect_timeout_seconds: float = 5.0,
        read_timeout_seconds: float = 10.0,
        fetcher: Optional[JsonDocumentFetcher] = None,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._issuer = _clean_optional(issuer)
        self._audience = _clean_optional(audience)
        self._tenant_id = _canonical_uuid_or_none(tenant_id)
        self._discovery_url = _clean_optional(discovery_url)
        self._required_scope = _clean_optional(required_scope)
        self._authorized_party = _clean_optional(authorized_party)
        self._clock_skew_seconds = max(0, int(clock_skew_seconds))
        self._cache_seconds = max(1, int(jwks_cache_seconds))
        self._connect_timeout_seconds = float(connect_timeout_seconds)
        self._read_timeout_seconds = float(read_timeout_seconds)
        self._fetcher = fetcher or RequestsJsonDocumentFetcher()
        self._clock = monotonic_clock
        self._lock = threading.RLock()

        self._discovery: Optional[Mapping[str, Any]] = None
        self._discovery_expires_at = 0.0
        self._keys: dict[str, PyJWK] = {}
        self._keys_expires_at = 0.0
        self._keys_uri: Optional[str] = None
        self._last_unknown_kid_refresh_at = float("-inf")
        self._last_unknown_kid_refresh_failed = False

        if self._connect_timeout_seconds <= 0 or self._read_timeout_seconds <= 0:
            raise ValueError("identity provider timeouts must be positive")
        if self._issuer:
            _require_https_url(self._issuer)
        if self._discovery_url:
            _require_https_url(self._discovery_url)

    @property
    def configured(self) -> bool:
        return bool(
            self._issuer
            and self._audience
            and self._tenant_id
            and self._discovery_url
            and self._required_scope
        )

    def clear_cache(self) -> None:
        """Drop public metadata only; useful for operator recovery and tests."""

        with self._lock:
            self._discovery = None
            self._discovery_expires_at = 0.0
            self._keys = {}
            self._keys_expires_at = 0.0
            self._keys_uri = None
            self._last_unknown_kid_refresh_at = float("-inf")
            self._last_unknown_kid_refresh_failed = False

    def validate_token(
        self,
        token: str,
        *,
        token_use: TokenUse,
        expected_nonce: Optional[str] = None,
    ) -> IntegrationResult[ExternalPrincipal]:
        """Validate one delegated access token without exposing its contents."""

        del expected_nonce  # Nonces belong to the separate interactive ID-token flow.
        operation = "validate_api_access_token"
        if token_use is not TokenUse.API_ACCESS_TOKEN:
            return self._invalid(operation, "identity_token_use_invalid")
        if not self.configured:
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation=operation,
                status=IntegrationStatus.NOT_CONFIGURED,
                failure=IntegrationFailure(
                    code="identity_provider_not_configured",
                    message="identity provider is not configured",
                    retryable=False,
                ),
            )
        if not _token_is_within_limit(token):
            return self._invalid(operation)

        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256":
                return self._invalid(operation)
            token_type = header.get("typ")
            if token_type is not None and token_type != "JWT":
                return self._invalid(operation)
            key_id = header.get("kid")
            if not isinstance(key_id, str) or not key_id or len(key_id) > 256:
                return self._invalid(operation)

            signing_key = self._resolve_signing_key(key_id)
            claims = jwt.decode(
                token,
                key=signing_key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._clock_skew_seconds,
                options={
                    "require": [
                        "exp",
                        "iat",
                        "nbf",
                        "aud",
                        "iss",
                        "sub",
                        "tid",
                        "oid",
                    ],
                    "strict_aud": True,
                    "enforce_minimum_key_length": True,
                },
            )
        except ExpiredSignatureError:
            return self._invalid(operation, "identity_token_expired")
        except _ProviderDocumentUnavailable:
            logger.warning(
                "identity_validation provider=entra_external_id "
                "result=rejected code=identity_provider_unavailable"
            )
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation=operation,
                failure=IntegrationFailure(
                    code="identity_provider_unavailable",
                    message="identity provider signing keys are unavailable",
                    retryable=True,
                ),
            )
        except _UnknownSigningKey:
            return self._invalid(operation, "identity_signing_key_unknown")
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
        if claims.get("ver") != "2.0" or claims.get("idtyp") == "app":
            return None

        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject.strip():
            return None
        tenant_id = _canonical_uuid_or_none(claims.get("tid"))
        object_id = _canonical_uuid_or_none(claims.get("oid"))
        if not tenant_id or not object_id or tenant_id != self._tenant_id:
            return None

        scope_claim = claims.get("scp")
        if not isinstance(scope_claim, str):
            return None
        scopes = frozenset(scope for scope in scope_claim.split() if scope)
        if self._required_scope not in scopes:
            return None

        if self._authorized_party:
            authorized_party = claims.get("azp")
            if not isinstance(authorized_party, str) or authorized_party != self._authorized_party:
                return None

        raw_roles = claims.get("roles")
        if isinstance(raw_roles, str):
            roles = frozenset({raw_roles})
        elif isinstance(raw_roles, list) and all(isinstance(role, str) for role in raw_roles):
            roles = frozenset(raw_roles)
        else:
            roles = frozenset()

        email_claim = claims.get("email")
        email_claim_present = isinstance(email_claim, str) and bool(email_claim.strip())
        email_hint = email_claim if email_claim_present else claims.get("preferred_username")
        if not isinstance(email_hint, str) or not email_hint.strip():
            email_hint = None
        display_name = claims.get("name")
        if not isinstance(display_name, str):
            display_name = None

        return ExternalPrincipal(
            provider=self.provider_name,
            identity_subject=f"{tenant_id}:{object_id}",
            subject=subject,
            issuer=self._issuer or "entra_external_id",
            tenant_id=tenant_id,
            object_id=object_id,
            email_hint=email_hint,
            # The verification flag applies only to the explicit email claim;
            # preferred_username is a sign-in hint, not a verified mailbox.
            email_verified=email_claim_present and claims.get("email_verified") is True,
            display_name=display_name,
            scopes=scopes,
            roles=roles,
        )

    def _resolve_signing_key(self, key_id: str) -> PyJWK:
        with self._lock:
            keys = self._get_keys()
            key = keys.get(key_id)
            if key is not None:
                return key

            now = self._clock()
            if now - self._last_unknown_kid_refresh_at >= _UNKNOWN_KID_REFRESH_COOLDOWN_SECONDS:
                self._last_unknown_kid_refresh_at = now
                try:
                    keys = self._get_keys(force=True)
                except _ProviderDocumentUnavailable:
                    self._last_unknown_kid_refresh_failed = True
                    raise
                self._last_unknown_kid_refresh_failed = False
                key = keys.get(key_id)
                if key is not None:
                    return key
            elif self._last_unknown_kid_refresh_failed:
                raise _ProviderDocumentUnavailable(
                    "identity provider signing keys are unavailable"
                )
            raise _UnknownSigningKey("identity token signing key is unknown")

    def _get_discovery(self) -> Mapping[str, Any]:
        with self._lock:
            now = self._clock()
            if self._discovery is not None and now < self._discovery_expires_at:
                return self._discovery
            if not self._discovery_url or not self._issuer:
                raise _ProviderDocumentUnavailable(
                    "identity provider discovery is not configured"
                )
            document = self._fetch_document(self._discovery_url)
            issuer = document.get("issuer")
            keys_uri = document.get("jwks_uri")
            if issuer != self._issuer or not isinstance(keys_uri, str):
                raise _ProviderDocumentUnavailable(
                    "identity provider discovery is invalid"
                )
            try:
                _require_https_url(keys_uri)
            except ValueError as exc:
                raise _ProviderDocumentUnavailable(
                    "identity provider discovery is invalid"
                ) from exc
            self._discovery = document
            self._discovery_expires_at = now + self._cache_seconds
            if self._keys_uri and self._keys_uri != keys_uri:
                self._keys = {}
                self._keys_expires_at = 0.0
            self._keys_uri = keys_uri
            return document

    def _get_keys(self, *, force: bool = False) -> dict[str, PyJWK]:
        with self._lock:
            now = self._clock()
            self._get_discovery()
            if not force and self._keys and now < self._keys_expires_at:
                return self._keys
            if not self._keys_uri:
                raise _ProviderDocumentUnavailable(
                    "identity provider signing keys are unavailable"
                )
            document = self._fetch_document(self._keys_uri)
            raw_keys = document.get("keys")
            if (
                not isinstance(raw_keys, list)
                or not raw_keys
                or len(raw_keys) > _MAX_JWKS_KEYS
            ):
                raise _ProviderDocumentUnavailable(
                    "identity provider signing keys are invalid"
                )

            parsed: dict[str, PyJWK] = {}
            for raw_key in raw_keys:
                if not isinstance(raw_key, dict):
                    continue
                key_id = raw_key.get("kid")
                if not isinstance(key_id, str) or not key_id or len(key_id) > 256:
                    continue
                if key_id in parsed:
                    raise _ProviderDocumentUnavailable(
                        "identity provider signing keys are ambiguous"
                    )
                if raw_key.get("kty") != "RSA":
                    continue
                if raw_key.get("use") not in {None, "sig"}:
                    continue
                if raw_key.get("alg") not in {None, "RS256"}:
                    continue
                if not isinstance(raw_key.get("n"), str) or not isinstance(
                    raw_key.get("e"), str
                ):
                    continue
                if any(
                    private_parameter in raw_key
                    for private_parameter in ("d", "p", "q", "dp", "dq", "qi", "oth")
                ):
                    continue
                key_issuer = raw_key.get("issuer")
                if key_issuer is not None and key_issuer != self._issuer:
                    continue
                try:
                    parsed_key = PyJWK.from_dict(raw_key, algorithm="RS256")
                except (PyJWTError, TypeError, ValueError):
                    continue
                if parsed_key.algorithm_name != "RS256":
                    continue
                if getattr(parsed_key.key, "key_size", 0) < 2048:
                    continue
                parsed[key_id] = parsed_key

            if not parsed:
                raise _ProviderDocumentUnavailable(
                    "identity provider signing keys are invalid"
                )
            self._keys = parsed
            self._keys_expires_at = now + self._cache_seconds
            self._last_unknown_kid_refresh_failed = False
            return self._keys

    def _fetch_document(self, url: str) -> Mapping[str, Any]:
        try:
            document = self._fetcher.fetch_json(
                url,
                connect_timeout_seconds=self._connect_timeout_seconds,
                read_timeout_seconds=self._read_timeout_seconds,
            )
        except _ProviderDocumentUnavailable:
            raise
        except Exception as exc:
            raise _ProviderDocumentUnavailable(
                "identity provider document is unavailable"
            ) from exc
        if not isinstance(document, Mapping):
            raise _ProviderDocumentUnavailable(
                "identity provider document is invalid"
            )
        return document

    def _invalid(
        self,
        operation: str,
        code: str = "identity_token_invalid",
    ) -> IntegrationResult[ExternalPrincipal]:
        logger.info(
            "identity_validation provider=entra_external_id "
            "result=rejected code=%s",
            code,
        )
        return IntegrationResult.failed(
            provider=self.provider_name,
            operation=operation,
            failure=IntegrationFailure(
                code=code,
                message="identity token is invalid",
                retryable=False,
            ),
        )


def _clean_optional(value: object) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _canonical_uuid_or_none(value: object) -> Optional[str]:
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


def _require_https_url(url: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise ValueError("identity provider URL must be an absolute HTTPS URL")


__all__ = [
    "EntraExternalIdProvider",
    "JsonDocumentFetcher",
    "RequestsJsonDocumentFetcher",
]
