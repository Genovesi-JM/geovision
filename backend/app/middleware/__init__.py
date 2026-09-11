"""Security middleware for production hardening.

Includes:
- Security headers (CSP, HSTS, X-Frame-Options, etc.)
- Rate limiting (login, reset-password, webhooks)
- Audit logging helper
"""

from __future__ import annotations

import ipaddress
import json
import logging
import time
import uuid
from typing import Callable, Dict, Optional, Tuple

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ..core.config import settings
from ..core.observability import (
    bind_context,
    enrich_context,
    get_logger,
    log_event,
    reset_context,
    safe_identifier,
)


logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════
# 0) Request correlation and structured completion logs
# ═══════════════════════════════════════════════════════════════


def _request_scope_fields(request: Request) -> dict[str, str]:
    """Collect stable domain identifiers without logging query/body data."""

    fields: dict[str, str] = {}
    context = getattr(request.state, "authorization_context", None)
    for key, value in (
        ("organization_id", getattr(context, "active_organization_id", None)),
        ("workspace_id", getattr(context, "active_workspace_id", None)),
    ):
        identifier = safe_identifier(value)
        if identifier:
            fields[key] = identifier
    aliases = {
        "company_id": "organization_id",
        "organization_id": "organization_id",
        "workspace_id": "workspace_id",
        "account_id": "workspace_id",
        "asset_id": "asset_id",
        "mission_id": "mission_id",
        "acquisition_id": "mission_id",
        "job_id": "job_id",
        "processing_job_id": "processing_job_id",
        "report_id": "report_id",
        "order_id": "order_id",
        "device_id": "device_id",
    }
    for raw_key, value in request.path_params.items():
        key = aliases.get(raw_key)
        identifier = safe_identifier(value)
        if key and identifier:
            fields[key] = identifier
    return fields


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach bounded request/correlation IDs and emit a safe completion event."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = safe_identifier(request.headers.get("x-request-id")) or str(
            uuid.uuid4()
        )
        correlation_id = (
            safe_identifier(request.headers.get("x-correlation-id")) or request_id
        )
        request.state.request_id = request_id
        request.state.correlation_id = correlation_id
        token = bind_context(
            request_id=request_id,
            correlation_id=correlation_id,
            http_method=request.method,
        )
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            fields = _request_scope_fields(request)
            enrich_context(**fields)
            route = getattr(request.scope.get("route"), "path", request.url.path)
            log_event(
                logger,
                logging.ERROR,
                "http.request.failed",
                route=route,
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
                exception_type=exc.__class__.__name__,
                **fields,
            )
            raise
        else:
            fields = _request_scope_fields(request)
            enrich_context(**fields)
            route = getattr(request.scope.get("route"), "path", request.url.path)
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Correlation-ID"] = correlation_id
            log_event(
                logger,
                logging.INFO if response.status_code < 500 else logging.ERROR,
                "http.request.completed",
                route=route,
                status_code=response.status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
                **fields,
            )
            return response
        finally:
            reset_context(token)


# ═══════════════════════════════════════════════════════════════
# 1) Security Headers Middleware
# ═══════════════════════════════════════════════════════════════


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds production security headers to every response.

    - Content-Security-Policy
    - Strict-Transport-Security (HSTS)
    - X-Frame-Options
    - X-Content-Type-Options
    - Referrer-Policy
    - Permissions-Policy
    - Cross-Origin-Opener-Policy
    - Cross-Origin-Resource-Policy
    """

    # CSP policy — allows YouTube embeds, Google APIs, CDN assets
    CSP_POLICY = "; ".join(
        [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' https://apis.google.com https://accounts.google.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com",
            "img-src 'self' data: https: blob:",
            "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com",
            "connect-src 'self' https://api.geovisionops.com https://accounts.google.com https://login.microsoftonline.com https://graph.microsoft.com https://wa.me",
            "frame-src 'self' https://accounts.google.com https://login.microsoftonline.com https://www.youtube.com https://youtube.com",
            "media-src 'self' https: blob:",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self' https://accounts.google.com https://login.microsoftonline.com",
            "frame-ancestors 'self'",
        ]
    )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # Production-like profiles use the complete browser security policy.
        is_deployed = settings.is_deployed

        # Always add these headers (safe for dev too)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(self), payment=(self)"
        )
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"

        # Authentication responses can contain access/refresh tokens or
        # token-bearing redirects and must not be stored by browsers/proxies.
        if request.url.path.rstrip("/").startswith("/auth"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"

        if is_deployed:
            # HSTS: 1 year, include subdomains (preload when ready)
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
            response.headers["Content-Security-Policy"] = self.CSP_POLICY
            response.headers["Cross-Origin-Resource-Policy"] = "same-site"

        return response


# ═══════════════════════════════════════════════════════════════
# 2) Rate Limiting Middleware
# ═══════════════════════════════════════════════════════════════


class RateLimiter:
    """In-memory sliding-window rate limiter.

    Storage is bounded to prevent attacker-controlled client keys from growing
    process memory without limit. For production at scale, replace this
    per-process implementation with a shared Redis-backed limiter.
    """

    MAX_KEYS = 10_000
    MAX_RETENTION_SECONDS = 300
    SWEEP_INTERVAL = 100

    def __init__(self):
        # key → list of timestamps
        self._requests: Dict[str, list[float]] = {}
        self._operations = 0

    def _cleanup(self, key: str, window_seconds: int, *, now: float) -> None:
        timestamps = self._requests.get(key)
        if not timestamps:
            self._requests.pop(key, None)
            return
        cutoff = now - window_seconds
        active = [timestamp for timestamp in timestamps if timestamp > cutoff]
        if active:
            self._requests[key] = active
        else:
            self._requests.pop(key, None)

    def _sweep(self, *, now: float, reserve_slot: bool = False) -> None:
        """Drop inactive keys and evict the oldest if the hard cap is reached."""

        cutoff = now - self.MAX_RETENTION_SECONDS
        for key, timestamps in list(self._requests.items()):
            if not timestamps or timestamps[-1] <= cutoff:
                self._requests.pop(key, None)
        capacity = self.MAX_KEYS - (1 if reserve_slot else 0)
        overflow = len(self._requests) - capacity
        if overflow > 0:
            oldest = sorted(
                self._requests,
                key=lambda key: self._requests[key][-1],
            )[:overflow]
            for key in oldest:
                self._requests.pop(key, None)

    def is_rate_limited(
        self, key: str, max_requests: int, window_seconds: int
    ) -> Tuple[bool, int]:
        """Check if key is rate limited. Returns (is_limited, remaining)."""
        now = time.time()
        self._operations += 1
        if (
            self._operations % self.SWEEP_INTERVAL == 0
            or len(self._requests) >= self.MAX_KEYS
        ):
            self._sweep(now=now)
        self._cleanup(key, window_seconds, now=now)
        count = len(self._requests.get(key, ()))
        if count >= max_requests:
            return True, 0
        return False, max_requests - count

    def record(self, key: str):
        now = time.time()
        if key not in self._requests and len(self._requests) >= self.MAX_KEYS:
            self._sweep(now=now, reserve_slot=True)
        self._requests.setdefault(key, []).append(now)


# Global rate limiter instance
_limiter = RateLimiter()

# Rate limit configs: (method, path_prefix) → (max_requests, window_seconds)
RATE_LIMIT_RULES: Dict[Tuple[str, str], Tuple[int, int]] = {
    ("POST", "/auth/login"): (10, 60),
    ("GET", "/auth/google/login"): (10, 300),
    ("GET", "/auth/microsoft/login"): (10, 300),
    ("POST", "/auth/register"): (5, 60),
    ("POST", "/auth/identity/session"): (20, 60),
    ("POST", "/auth/forgot-password"): (3, 300),
    ("POST", "/auth/reset-password"): (5, 300),
    ("DELETE", "/auth/account"): (5, 300),
    ("POST", "/auth/account/delete"): (5, 300),
    ("POST", "/payments/webhook"): (60, 60),
    # Paid location-provider operations receive tighter per-client ceilings.
    # Provider-console quotas and budget alerts remain mandatory deployment gates.
    ("POST", "/location/places:autocomplete"): (60, 60),
    ("POST", "/location/places:resolve"): (30, 60),
    ("POST", "/location/routes:compute"): (20, 60),
    ("POST", "/location/addresses:reverse"): (30, 60),
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limits sensitive endpoints by client IP."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path.rstrip("/")
        method = request.method.upper()

        rule = None
        for (rule_method, prefix), limits in RATE_LIMIT_RULES.items():
            if method == rule_method and (
                path == prefix or path.startswith(prefix + "/")
            ):
                rule = limits
                break

        if not rule:
            return await call_next(request)

        max_req, window = rule
        # Use client IP as rate limit key
        client_ip = _get_client_ip(request)
        key = f"rl:{path}:{client_ip}"

        is_limited, remaining = _limiter.is_rate_limited(key, max_req, window)
        if is_limited:
            return Response(
                content=json.dumps(
                    {"detail": "Too many requests. Please try again later."}
                ),
                status_code=429,
                media_type="application/json",
                headers={
                    "Retry-After": str(window),
                    "X-RateLimit-Limit": str(max_req),
                    "X-RateLimit-Remaining": "0",
                },
            )

        _limiter.record(key)
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(max_req)
        response.headers["X-RateLimit-Remaining"] = str(remaining - 1)
        return response


def _get_client_ip(request: Request) -> str:
    """Resolve a client IP without trusting caller-controlled proxy headers."""

    peer = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded or len(forwarded) > 1024:
        return peer
    try:
        peer_address = ipaddress.ip_address(peer)
        trusted_networks = settings.trusted_proxy_networks
    except ValueError:
        return peer
    if not any(peer_address in network for network in trusted_networks):
        return peer

    raw_chain = [part.strip() for part in forwarded.split(",")]
    if not raw_chain or len(raw_chain) > 16 or any(not part for part in raw_chain):
        return peer
    try:
        forwarded_chain = [ipaddress.ip_address(part) for part in raw_chain]
    except ValueError:
        return peer

    # Walk from the trusted peer toward the client. This resists a caller that
    # prepends a forged address when a well-behaved edge appends its own value.
    for candidate in reversed(forwarded_chain):
        if not any(candidate in network for network in trusted_networks):
            return str(candidate)
    return str(forwarded_chain[0])


# ═══════════════════════════════════════════════════════════════
# 3) Audit Logging Helper
# ═══════════════════════════════════════════════════════════════


def log_audit(
    db,
    action: str,
    user_id: Optional[str] = None,
    user_email: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[dict] = None,
    request: Optional[Request] = None,
    commit: bool = True,
):
    """Write an audit entry, optionally joining the caller's transaction."""
    from ..modules.audit.services import record_audit_event

    ip = None
    ua = None
    if request:
        ip = _get_client_ip(request)
        ua = (request.headers.get("user-agent") or "")[:500]

    entry = record_audit_event(
        db,
        action=action,
        resource_type=resource_type or "system",
        resource_id=resource_id,
        user_id=user_id,
        user_email=user_email,
        details=details,
        request=request,
        ip_address=ip,
        user_agent=ua,
    )
    try:
        if commit:
            db.commit()
    except Exception:
        if commit:
            db.rollback()
            return None
        raise
    return entry


# ═══════════════════════════════════════════════════════════════
# 4) HTTPS Redirect (for non-Render deployments)
# ═══════════════════════════════════════════════════════════════


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """Redirect HTTP to HTTPS in staging and production.

    Render handles this at the load balancer level, but this is a
    safety net for other deployments.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not settings.is_deployed:
            return await call_next(request)

        # Check X-Forwarded-Proto (set by Render/Heroku/AWS ALB)
        proto = request.headers.get("x-forwarded-proto", "https")
        if proto == "http":
            url = str(request.url).replace("http://", "https://", 1)
            return Response(
                status_code=301,
                headers={"Location": url},
            )

        return await call_next(request)
