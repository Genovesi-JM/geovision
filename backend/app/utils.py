"""Backward-compatible password helper imports.

New code should import from :mod:`app.core.passwords`.
"""

from .core.passwords import hash_password, verify_password

__all__ = ["hash_password", "verify_password"]
