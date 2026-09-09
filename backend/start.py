import sys
import subprocess

from app.core.config import settings
from app.core.integration import sanitize_integration_message


def main() -> None:
    migrate_timeout_s = settings.migrate_timeout_seconds

    # Run DB migrations for the main database.
    try:
        print(f"[start] Running migrations (timeout={migrate_timeout_s}s)...", flush=True)
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            check=True,
            timeout=migrate_timeout_s,
        )
        print("[start] Migrations complete.", flush=True)
    except subprocess.TimeoutExpired:
        print(
            "[start] ERROR: Alembic migrations timed out. "
            "If you are using an external database with an IP allowlist, add outbound IP ranges.",
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(1)
    except subprocess.CalledProcessError as exc:
        print(
            f"[start] ERROR: Alembic upgrade failed (exit code {exc.returncode}). "
            "Refusing to start with an unverified database schema.",
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(1) from exc

    # ── Ensure critical columns exist (handles schema drift) ──
    _ensure_schema_columns()

    import uvicorn

    port = settings.port
    print(f"[start] Starting server on 0.0.0.0:{port}...", flush=True)
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)


def _ensure_schema_columns():
    """Apply narrowly scoped compatibility repairs after migrations succeed."""
    from sqlalchemy import inspect as sa_inspect, text
    from app.core import database

    database.init_db_engine()

    # Map of table -> [(column_name, sql_type, default)]
    required_columns = {
        "companies": [
            ("address", "TEXT", None),
        ],
    }

    # Columns from enterprise migration that must be nullable (model doesn't include them)
    force_nullable = {
        "companies": ["country", "sectors"],
    }

    try:
        inspector = sa_inspect(database.engine)
        with database.engine.begin() as conn:
            for table, columns in required_columns.items():
                if table not in inspector.get_table_names():
                    continue
                existing = {c["name"] for c in inspector.get_columns(table)}
                for col_name, col_type, default in columns:
                    if col_name not in existing:
                        default_clause = f" DEFAULT {default}" if default else ""
                        sql = f'ALTER TABLE {table} ADD COLUMN {col_name} {col_type}{default_clause}'
                        conn.execute(text(sql))
                        print(f"[start] Added missing column {table}.{col_name}", flush=True)

            # Make enterprise-specific NOT NULL columns nullable
            for table, cols in force_nullable.items():
                if table not in inspector.get_table_names():
                    continue
                existing_cols = {c["name"]: c for c in inspector.get_columns(table)}
                for col_name in cols:
                    if col_name in existing_cols and existing_cols[col_name].get("nullable") is False:
                        conn.execute(text(f'ALTER TABLE {table} ALTER COLUMN {col_name} DROP NOT NULL'))
                        print(f"[start] Made {table}.{col_name} nullable", flush=True)
    except Exception as exc:
        print(
            f"[start] WARNING: schema column check failed: "
            f"{sanitize_integration_message(exc)}",
            file=sys.stderr,
            flush=True,
        )


if __name__ == "__main__":
    main()
