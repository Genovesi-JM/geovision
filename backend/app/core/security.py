"""Stable security facade for shared password and token primitives."""

from .passwords import hash_password, verify_password
from .tokens import create_access_token, verify_access_token


def decode_token(token: str) -> dict:
    """Backward-compatible alias for access-token verification."""

    return verify_access_token(token)


__all__ = [
    "create_access_token",
    "decode_token",
    "hash_password",
    "verify_access_token",
    "verify_password",
]
