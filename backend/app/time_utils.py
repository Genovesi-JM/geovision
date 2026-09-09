"""Backward-compatible UTC helper imports.

New code should import from :mod:`app.core.time`.
"""

from .core.time import utc_from_timestamp, utc_now

__all__ = ["utc_from_timestamp", "utc_now"]
