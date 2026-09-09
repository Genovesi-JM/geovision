"""Backward-compatible access to the canonical database module.

Mutable globals such as ``engine`` and ``SessionLocal`` are deliberately
resolved through ``__getattr__`` instead of copied here. This keeps legacy
imports working while new code uses :mod:`app.core.database` directly.
"""

from .core import database as _database

Base = _database.Base
ensure_legacy_schema = _database.ensure_legacy_schema
ensure_user_role_column = _database.ensure_user_role_column
get_db = _database.get_db
init_db_engine = _database.init_db_engine


def __getattr__(name: str):
    return getattr(_database, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_database)))


__all__ = [
    "Base",
    "DATABASE_URL",
    "SessionLocal",
    "engine",
    "ensure_legacy_schema",
    "ensure_user_role_column",
    "get_db",
    "init_db_engine",
]
