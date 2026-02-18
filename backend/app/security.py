# app/security.py
"""Thin wrapper that re-exports canonical implementations.

Password hashing/verification: ``app.utils`` (supports bcrypt + legacy SHA256).
Token creation/decoding:       ``app.oauth2`` (uses settings directly).

Importing from this module is **deprecated** — prefer importing directly
from ``app.utils`` or ``app.oauth2``.
"""

# Re-export password helpers from the canonical location (app.utils)
from app.utils import hash_password, verify_password  # noqa: F401

# Re-export token helpers from the canonical location (app.oauth2)
from app.oauth2 import create_access_token, verify_access_token  # noqa: F401


def decode_token(token: str) -> dict:
    """Alias for verify_access_token (backward compat)."""
    return verify_access_token(token)
