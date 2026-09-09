"""Backward-compatible configuration imports.

New code should import from :mod:`app.core.config`. This module remains so
existing routers, scripts, Alembic configuration, and external imports keep
working during the modular-monolith migration.
"""

from .core.config import (
    DATABASE_URL,
    JWT_ALG,
    JWT_EXPIRE_MIN,
    JWT_SECRET,
    OPENAI_API_KEY,
    RuntimeEnvironment,
    Settings,
    settings,
)

__all__ = [
    "DATABASE_URL",
    "JWT_ALG",
    "JWT_EXPIRE_MIN",
    "JWT_SECRET",
    "OPENAI_API_KEY",
    "RuntimeEnvironment",
    "Settings",
    "settings",
]
