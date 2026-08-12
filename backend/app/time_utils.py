"""UTC helpers compatible with the project's existing database schema.

The SQLAlchemy models currently store timezone-naive ``DateTime`` values. These
helpers use the modern timezone-aware Python APIs internally, then remove the
UTC marker at the persistence boundary so existing comparisons and migrations
keep the same semantics without relying on deprecated ``utcnow`` helpers.
"""

from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return the current UTC time as a naive value for existing DB columns."""

    return datetime.now(UTC).replace(tzinfo=None)


def utc_from_timestamp(timestamp: float) -> datetime:
    """Convert a Unix timestamp to a naive UTC value for existing DB columns."""

    return datetime.fromtimestamp(timestamp, UTC).replace(tzinfo=None)


__all__ = ["utc_now", "utc_from_timestamp"]
