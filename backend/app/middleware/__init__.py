"""Security middleware for production hardening.

Includes:
- Security headers (CSP, HSTS, X-Frame-Options, etc.)
- Rate limiting (login, reset-password, webhooks)
- Audit logging helper
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict
from datetime import datetime
from typing import Callable, Dict, Optional, Tuple

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from ..config import settings


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
    CSP_POLICY = "; ".join([
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline' https://apis.google.com https://accounts.google.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com",
        "img-src 'self' data: https: blob:",
        "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com",
        "connect-src 'self' https://api.geovisionops.com https://geovisionops-sqknb.ondigitalocean.app https://accounts.google.com https://login.microsoftonline.com https://graph.microsoft.com https://wa.me",
        "frame-src 'self' https://accounts.google.com https://login.microsoftonline.com https://www.youtube.com https://youtube.com",
        "media-src 'self' https: blob:",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self' https://accounts.google.com https://login.microsoftonline.com",
        "frame-ancestors 'self'",
    ])

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # Only add security headers on production or when explicitly enabled
        is_prod = settings.env == "prod"

        # Always add these headers (safe for dev too)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(self), payment=(self)"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"

        if is_prod:
            # HSTS: 1 year, include subdomains (preload when ready)
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            response.headers["Content-Security-Policy"] = self.CSP_POLICY
            response.headers["Cross-Origin-Resource-Policy"] = "same-site"

        return response


# ═══════════════════════════════════════════════════════════════
# 2) Rate Limiting Middleware
# ═══════════════════════════════════════════════════════════════

class RateLimiter:
    """In-memory sliding-window rate limiter.

    For production at scale, replace with Redis-based implementation.
    """

    def __init__(self):
        # key → list of timestamps
        self._requests: Dict[str, list] = defaultdict(list)

    def _cleanup(self, key: str, window_seconds: int):
        cutoff = time.time() - window_seconds
        self._requests[key] = [t for t in self._requests[key] if t > cutoff]

    def is_rate_limited(self, key: str, max_requests: int, window_seconds: int) -> Tuple[bool, int]:
        """Check if key is rate limited. Returns (is_limited, remaining)."""
        self._cleanup(key, window_seconds)
        count = len(self._requests[key])
        if count >= max_requests:
            return True, 0
        return False, max_requests - count

    def record(self, key: str):
        self._requests[key].append(time.time())


# Global rate limiter instance
_limiter = RateLimiter()

# Rate limit configs: path_prefix → (max_requests, window_seconds)
RATE_LIMIT_RULES: Dict[str, Tuple[int, int]] = {
    "/auth/login": (10, 60),           # 10 attempts per minute
    "/auth/register": (5, 60),         # 5 registrations per minute
    "/auth/forgot-password": (3, 300), # 3 resets per 5 minutes
    "/auth/reset-password": (5, 300),  # 5 attempts per 5 minutes
    "/payments/webhook": (60, 60),     # 60 webhook calls per minute
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limits sensitive endpoints by client IP."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path.rstrip("/")
        method = request.method.upper()

        # Only rate limit POST requests on sensitive paths
        if method != "POST":
            return await call_next(request)

        rule = None
        for prefix, limits in RATE_LIMIT_RULES.items():
            if path == prefix or path.startswith(prefix + "/"):
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
                content=json.dumps({"detail": "Too many requests. Please try again later."}),
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
    """Extract client IP, respecting X-Forwarded-For from reverse proxies."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


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
):
    """Write an audit log entry to the database."""
    from ..models import AuditLog

    ip = None
    ua = None
    if request:
        ip = _get_client_ip(request)
        ua = (request.headers.get("user-agent") or "")[:500]

    entry = AuditLog(
        user_id=user_id,
        user_email=user_email,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=json.dumps(details, default=str) if details else None,
        ip_address=ip,
        user_agent=ua,
    )
    try:
        db.add(entry)
        db.commit()
    except Exception:
        db.rollback()


# ═══════════════════════════════════════════════════════════════
# 4) HTTPS Redirect (for non-Render deployments)
# ═══════════════════════════════════════════════════════════════

class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """Redirect HTTP to HTTPS in production.

    Render handles this at the load balancer level, but this is a
    safety net for other deployments.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if settings.env != "prod":
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
