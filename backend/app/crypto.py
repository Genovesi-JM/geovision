"""Backward-compatible encryption helper imports.

New code should import from :mod:`app.core.encryption`.
"""

from .core.encryption import decrypt, encrypt

__all__ = ["decrypt", "encrypt"]
