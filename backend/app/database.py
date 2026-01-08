# backend/app/database.py — FINAL ESTÁVEL

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings

# Lazy initialization: do NOT create the engine/session at import time. Tests
# need to set `settings.database_url` before the engine is created. Call
# `init_db_engine()` early (in tests/conftest or in create_application()).

DATABASE_URL = None

# Will be set by init_db_engine()
engine = None
SessionLocal = None

Base = declarative_base()
Base.__allow_unmapped__ = True  # compatibilidade com models antigos


def init_db_engine(database_url: str | None = None) -> None:
    """Initialize the SQLAlchemy engine and SessionLocal singleton.

    This function is idempotent - calling it multiple times with the same
    URL is safe. Pass `database_url` to override `settings.database_url`.
    """
    global DATABASE_URL, engine, SessionLocal
    if database_url is None:
        database_url = settings.database_url
    if engine is not None and str(getattr(engine, 'url', None)) == database_url:
        # Already initialized with same URL
        return

    DATABASE_URL = database_url
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        echo=False,
    )

    SessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )


def get_db():
    # Ensure engine/session factory is initialized lazily
    if SessionLocal is None:
        init_db_engine()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_user_role_column() -> None:
    """Adds the role column if missing (legacy SQLite dev data)."""
    if engine is None:
        init_db_engine()
    inspector = inspect(engine)
    try:
        columns = [col["name"] for col in inspector.get_columns("users")]
    except Exception:
        return
    if "role" in columns:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'customer'"))


def ensure_legacy_schema() -> None:
    """Add a few legacy columns that older developer DB copies may lack.

    This is a small, idempotent compatibility shim used in tests/dev where an
    existing sqlite file has an older schema. We inspect existing columns and
    ALTER TABLE ADD COLUMN for the missing ones. This keeps create_application
    resilient when running against older DB files.
    """
    if engine is None:
        init_db_engine()
    inspector = inspect(engine)
    with engine.begin() as conn:
        # Users table: password_hash and is_active
        try:
            user_cols = [c["name"] for c in inspector.get_columns("users")]
        except Exception:
            user_cols = []

        if "password_hash" not in user_cols:
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN password_hash TEXT"))
            except Exception:
                # best-effort; ignore if fail
                pass

        if "is_active" not in user_cols:
            try:
                # SQLite uses INTEGER for booleans
                conn.execute(text("ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1"))
            except Exception:
                pass
        # created_at / updated_at timestamps (legacy DBs may lack them)
        if "created_at" not in user_cols:
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN created_at TEXT"))
            except Exception:
                pass
        if "updated_at" not in user_cols:
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN updated_at TEXT"))
            except Exception:
                pass

        # Products table: sku and is_active
        try:
            prod_cols = [c["name"] for c in inspector.get_columns("products")]
        except Exception:
            prod_cols = []

        if "sku" not in prod_cols:
            try:
                conn.execute(text("ALTER TABLE products ADD COLUMN sku TEXT"))
            except Exception:
                pass

        if "is_active" not in prod_cols:
            try:
                conn.execute(text("ALTER TABLE products ADD COLUMN is_active INTEGER DEFAULT 1"))
            except Exception:
                pass


# Initialize the engine by default outside of tests so imports have a usable DB connection.
if getattr(settings, "env", "dev") != "test":
    init_db_engine()
