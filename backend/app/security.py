# app/security.py
"""Backward-compatible security facade.

New code should import these primitives from :mod:`app.core.security`.
"""

from .core.security import (
    create_access_token,
    create_user_access_token,
    decode_access_token,
    decode_token,
    hash_password,
    verify_access_token,
    verify_password,
)

__all__ = [
    "create_access_token",
    "create_user_access_token",
    "decode_access_token",
    "decode_token",
    "hash_password",
    "verify_access_token",
    "verify_password",
]
