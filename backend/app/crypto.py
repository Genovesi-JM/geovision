"""Symmetric encryption helpers for sensitive data at rest (API keys, secrets).

Uses Fernet (AES-128-CBC + HMAC-SHA256) from the `cryptography` library.
The encryption key is read from ``settings.encryption_key``.  If no key is
configured the helpers fall back to a plaintext prefix so existing data
can still be read — but a WARNING is logged on every call.
"""

from __future__ import annotations

import logging
import warnings
from typing import Optional

logger = logging.getLogger(__name__)

_PLAINTEXT_PREFIX = "plain:"
_fernet = None  # lazy singleton


def _get_fernet():
    """Return a Fernet instance, or *None* if no key is configured."""
    global _fernet
    if _fernet is not None:
        return _fernet

    from app.config import settings

    key = (settings.encryption_key or "").strip()
    if not key:
        return None

    try:
        from cryptography.fernet import Fernet

        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
        return _fernet
    except Exception as exc:
        logger.error("Failed to initialise Fernet with ENCRYPTION_KEY: %s", exc)
        return None


def encrypt(plaintext: Optional[str]) -> Optional[str]:
    """Encrypt *plaintext* and return a base-64 ciphertext string.

    Returns ``None`` when *plaintext* is falsy.  When no ``ENCRYPTION_KEY``
    is configured a warning is emitted and the value is stored with a
    ``plain:`` prefix so it can round-trip through :func:`decrypt`.
    """
    if not plaintext:
        return plaintext

    f = _get_fernet()
    if f is None:
        warnings.warn(
            "ENCRYPTION_KEY not set — storing sensitive value WITHOUT encryption.",
            stacklevel=2,
        )
        return f"{_PLAINTEXT_PREFIX}{plaintext}"

    return f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: Optional[str]) -> Optional[str]:
    """Decrypt a value previously produced by :func:`encrypt`.

    Handles legacy plaintext values (with or without the ``plain:`` prefix)
    gracefully so that old data is readable after enabling encryption.
    """
    if not ciphertext:
        return ciphertext

    # Legacy / unencrypted fallback
    if ciphertext.startswith(_PLAINTEXT_PREFIX):
        return ciphertext[len(_PLAINTEXT_PREFIX):]

    f = _get_fernet()
    if f is None:
        # No key configured — assume the value was stored in plaintext
        return ciphertext

    try:
        return f.decrypt(ciphertext.encode()).decode()
    except Exception:
        # Value might be legacy plaintext that happens not to have the prefix
        logger.warning("Failed to decrypt value — returning as-is (legacy plaintext?).")
        return ciphertext
