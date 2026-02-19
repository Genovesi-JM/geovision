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

        # Documents table: ensure columns match the model
        try:
            doc_cols = [c["name"] for c in inspector.get_columns("documents")]
        except Exception:
            doc_cols = []

        if doc_cols:
            _doc_adds = {
                "file_path": "ALTER TABLE documents ADD COLUMN file_path TEXT",
                "uploaded_by": "ALTER TABLE documents ADD COLUMN uploaded_by TEXT",
            }
            for col, ddl in _doc_adds.items():
                if col not in doc_cols:
                    try:
                        conn.execute(text(ddl))
                    except Exception:
                        pass
            # Make enterprise-specific NOT NULL columns nullable so the model can insert
            _doc_nullable = [
                "ALTER TABLE documents ALTER COLUMN original_filename DROP NOT NULL",
                "ALTER TABLE documents ALTER COLUMN file_extension DROP NOT NULL",
                "ALTER TABLE documents ALTER COLUMN storage_path DROP NOT NULL",
                "ALTER TABLE documents ALTER COLUMN storage_provider DROP NOT NULL",
                "ALTER TABLE documents ALTER COLUMN download_blocked DROP NOT NULL",
                "ALTER TABLE documents ALTER COLUMN download_blocked SET DEFAULT false",
                "ALTER TABLE documents ALTER COLUMN file_size_bytes SET DEFAULT 0",
            ]
            for ddl in _doc_nullable:
                try:
                    conn.execute(text(ddl))
                except Exception:
                    pass

        # Audit log table: ensure columns match the model
        try:
            audit_cols = [c["name"] for c in inspector.get_columns("audit_log")]
        except Exception:
            audit_cols = []

        if audit_cols:
            _audit_adds = {
                "user_email": "ALTER TABLE audit_log ADD COLUMN user_email TEXT",
                "ip_address": "ALTER TABLE audit_log ADD COLUMN ip_address VARCHAR(45)",
                "user_agent": "ALTER TABLE audit_log ADD COLUMN user_agent VARCHAR(500)",
            }
            for col, ddl in _audit_adds.items():
                if col not in audit_cols:
                    try:
                        conn.execute(text(ddl))
                    except Exception:
                        pass

        # Sites table: ensure columns match the model
        try:
            site_cols = [c["name"] for c in inspector.get_columns("sites")]
        except Exception:
            site_cols = []

        if site_cols:
            _site_adds = {
                "country": "ALTER TABLE sites ADD COLUMN country VARCHAR(100) DEFAULT 'Angola'",
                "province": "ALTER TABLE sites ADD COLUMN province VARCHAR(100)",
                "municipality": "ALTER TABLE sites ADD COLUMN municipality VARCHAR(100)",
                "latitude": "ALTER TABLE sites ADD COLUMN latitude NUMERIC(10,6)",
                "longitude": "ALTER TABLE sites ADD COLUMN longitude NUMERIC(10,6)",
                "area_hectares": "ALTER TABLE sites ADD COLUMN area_hectares NUMERIC(12,2)",
                "sector": "ALTER TABLE sites ADD COLUMN sector VARCHAR(50)",
                "description": "ALTER TABLE sites ADD COLUMN description TEXT",
            }
            for col, ddl in _site_adds.items():
                if col not in site_cols:
                    try:
                        conn.execute(text(ddl))
                    except Exception:
                        pass

        # Datasets table: ensure columns match the model
        try:
            ds_cols = [c["name"] for c in inspector.get_columns("datasets")]
        except Exception:
            ds_cols = []

        if ds_cols:
            _ds_adds = {
                "company_id": "ALTER TABLE datasets ADD COLUMN company_id VARCHAR(36)",
                "site_id": "ALTER TABLE datasets ADD COLUMN site_id VARCHAR(36)",
                "description": "ALTER TABLE datasets ADD COLUMN description TEXT",
                "source_tool": "ALTER TABLE datasets ADD COLUMN source_tool VARCHAR(50)",
                "data_type": "ALTER TABLE datasets ADD COLUMN data_type VARCHAR(50) DEFAULT 'drone_imagery'",
                "source": "ALTER TABLE datasets ADD COLUMN source VARCHAR(100)",
                "sector": "ALTER TABLE datasets ADD COLUMN sector VARCHAR(50)",
                "capture_date": "ALTER TABLE datasets ADD COLUMN capture_date TIMESTAMP",
                "metadata_json": "ALTER TABLE datasets ADD COLUMN metadata_json TEXT DEFAULT '{}'",
                "storage_path": "ALTER TABLE datasets ADD COLUMN storage_path TEXT",
                "file_count": "ALTER TABLE datasets ADD COLUMN file_count INTEGER DEFAULT 0",
                "total_size_bytes": "ALTER TABLE datasets ADD COLUMN total_size_bytes INTEGER DEFAULT 0",
                "processed_at": "ALTER TABLE datasets ADD COLUMN processed_at TIMESTAMP",
            }
            for col, ddl in _ds_adds.items():
                if col not in ds_cols:
                    try:
                        conn.execute(text(ddl))
                    except Exception:
                        pass

        # Payments table: ensure columns match the model
        try:
            pay_cols = [c["name"] for c in inspector.get_columns("payments")]
        except Exception:
            pay_cols = []

        if pay_cols:
            _pay_adds = {
                "company_id": "ALTER TABLE payments ADD COLUMN company_id VARCHAR(36)",
                "order_id": "ALTER TABLE payments ADD COLUMN order_id VARCHAR(36)",
                "amount": "ALTER TABLE payments ADD COLUMN amount INTEGER DEFAULT 0",
                "currency": "ALTER TABLE payments ADD COLUMN currency VARCHAR(5) DEFAULT 'AOA'",
                "provider": "ALTER TABLE payments ADD COLUMN provider VARCHAR(30) DEFAULT ''",
                "description": "ALTER TABLE payments ADD COLUMN description TEXT",
                "idempotency_key": "ALTER TABLE payments ADD COLUMN idempotency_key VARCHAR(100)",
                "provider_reference": "ALTER TABLE payments ADD COLUMN provider_reference VARCHAR(200)",
                "metadata_json": "ALTER TABLE payments ADD COLUMN metadata_json TEXT DEFAULT '{}'",
                "expires_at": "ALTER TABLE payments ADD COLUMN expires_at TIMESTAMP",
            }
            for col, ddl in _pay_adds.items():
                if col not in pay_cols:
                    try:
                        conn.execute(text(ddl))
                    except Exception:
                        pass

        # Shop products table: multi-currency price columns
        try:
            sp_cols = [c["name"] for c in inspector.get_columns("shop_products")]
        except Exception:
            sp_cols = []

        if sp_cols:
            _sp_adds = {
                "price_usd": "ALTER TABLE shop_products ADD COLUMN price_usd INTEGER DEFAULT 0",
                "price_eur": "ALTER TABLE shop_products ADD COLUMN price_eur INTEGER DEFAULT 0",
            }
            for col, ddl in _sp_adds.items():
                if col not in sp_cols:
                    try:
                        conn.execute(text(ddl))
                    except Exception:
                        pass

        # Orders table: company_id + site_id columns
        try:
            order_cols = [c["name"] for c in inspector.get_columns("orders")]
        except Exception:
            order_cols = []

        if order_cols:
            _order_adds = {
                "company_id": "ALTER TABLE orders ADD COLUMN company_id VARCHAR(36)",
                "site_id": "ALTER TABLE orders ADD COLUMN site_id VARCHAR(36)",
            }
            for col, ddl in _order_adds.items():
                if col not in order_cols:
                    try:
                        conn.execute(text(ddl))
                    except Exception:
                        pass

        # Order items table: extended columns
        try:
            oi_cols = [c["name"] for c in inspector.get_columns("order_items")]
        except Exception:
            oi_cols = []

        if oi_cols:
            _oi_adds = {
                "product_type": "ALTER TABLE order_items ADD COLUMN product_type VARCHAR(30)",
                "tax_rate": "ALTER TABLE order_items ADD COLUMN tax_rate NUMERIC(5,4) DEFAULT 0.14",
                "tax_amount": "ALTER TABLE order_items ADD COLUMN tax_amount NUMERIC(12,2) DEFAULT 0",
                "status": "ALTER TABLE order_items ADD COLUMN status VARCHAR(30) DEFAULT 'pending'",
                "scheduled_date": "ALTER TABLE order_items ADD COLUMN scheduled_date TIMESTAMP",
            }
            for col, ddl in _oi_adds.items():
                if col not in oi_cols:
                    try:
                        conn.execute(text(ddl))
                    except Exception:
                        pass


# Initialize the engine by default outside of tests so imports have a usable DB connection.
if getattr(settings, "env", "dev") != "test":
    init_db_engine()
