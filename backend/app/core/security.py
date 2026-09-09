"""Stable security facade for shared password and token primitives."""

from .passwords import (
    hash_password,
    validate_new_password,
    validate_password_byte_length,
    verify_password,
)
from .tokens import (
    create_access_token,
    create_user_access_token,
    decode_access_token,
    verify_access_token,
)


def decode_token(token: str) -> dict:
    """Backward-compatible alias for access-token verification."""

    return verify_access_token(token)


__all__ = [
    "create_access_token",
    "create_user_access_token",
    "decode_access_token",
    "decode_token",
    "hash_password",
    "validate_new_password",
    "validate_password_byte_length",
    "verify_access_token",
    "verify_password",
]
