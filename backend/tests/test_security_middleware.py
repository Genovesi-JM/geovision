from __future__ import annotations

import time

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from app.core.config import Settings, settings
from app.middleware import RATE_LIMIT_RULES, RateLimiter, _get_client_ip


def _request(peer: str, forwarded: str | None = None) -> Request:
    headers = []
    if forwarded is not None:
        headers.append((b"x-forwarded-for", forwarded.encode("ascii")))
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/auth/login",
            "raw_path": b"/auth/login",
            "query_string": b"",
            "headers": headers,
            "client": (peer, 43210),
            "server": ("testserver", 443),
        }
    )


def test_proxy_cidrs_are_validated_and_normalized():
    configured = Settings(
        _env_file=None,
        trusted_proxy_cidrs="127.0.0.1, 10.0.0.9/8,127.0.0.1/32",
    )
    assert configured.trusted_proxy_cidrs == "127.0.0.1/32,10.0.0.0/8"

    with pytest.raises(ValidationError, match="TRUSTED_PROXY_CIDRS"):
        Settings(_env_file=None, trusted_proxy_cidrs="not-a-network")


def test_forwarding_header_is_ignored_from_an_untrusted_peer(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_cidrs", "10.0.0.0/8")
    request = _request("203.0.113.10", "198.51.100.7")

    assert _get_client_ip(request) == "203.0.113.10"


def test_trusted_proxy_chain_selects_nearest_untrusted_client(monkeypatch):
    monkeypatch.setattr(
        settings,
        "trusted_proxy_cidrs",
        "10.0.0.0/8,192.0.2.0/24",
    )
    request = _request(
        "10.0.0.8",
        "198.51.100.99, 203.0.113.20, 192.0.2.40",
    )

    assert _get_client_ip(request) == "203.0.113.20"


def test_malformed_forwarding_chain_fails_closed_to_peer(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_cidrs", "10.0.0.0/8")
    request = _request("10.0.0.8", "forged, 198.51.100.7")

    assert _get_client_ip(request) == "10.0.0.8"


def test_rate_limiter_drops_expired_keys_and_bounds_attacker_keys():
    limiter = RateLimiter()
    limiter.MAX_KEYS = 3
    old = time.time() - limiter.MAX_RETENTION_SECONDS - 1
    limiter._requests = {
        "expired": [old],
        "active-a": [time.time()],
        "active-b": [time.time()],
    }

    limiter.record("active-c")
    assert "expired" not in limiter._requests
    assert len(limiter._requests) == 3

    limiter.record("active-d")
    assert len(limiter._requests) == 3
    assert "active-d" in limiter._requests


def test_rate_limiter_cleanup_removes_an_empty_key():
    limiter = RateLimiter()
    limiter._requests["one-shot"] = [time.time() - 61]

    limited, remaining = limiter.is_rate_limited("one-shot", 1, 60)

    assert limited is False
    assert remaining == 1
    assert "one-shot" not in limiter._requests


def test_paid_location_operations_have_explicit_cost_guardrails():
    assert RATE_LIMIT_RULES[("POST", "/location/places:autocomplete")] == (60, 60)
    assert RATE_LIMIT_RULES[("POST", "/location/places:resolve")] == (30, 60)
    assert RATE_LIMIT_RULES[("POST", "/location/routes:compute")] == (20, 60)
    assert RATE_LIMIT_RULES[("POST", "/location/addresses:reverse")] == (30, 60)
