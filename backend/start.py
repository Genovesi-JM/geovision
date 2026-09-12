import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from app.core.config import settings
from app.core.integration import sanitize_integration_message


_BACKEND_ROOT = Path(__file__).resolve().parent


def _run_migrations() -> None:
    """Upgrade the primary database or stop without starting the API."""

    migrate_timeout_s = settings.migrate_timeout_seconds
    try:
        print(f"[start] Running migrations (timeout={migrate_timeout_s}s)...", flush=True)
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            check=True,
            cwd=_BACKEND_ROOT,
            timeout=migrate_timeout_s,
            # Driver/configuration failures can embed the database URL in
            # either stream. Never forward migration output to runtime logs.
            capture_output=True,
        )
        print("[start] Migrations complete.", flush=True)
    except subprocess.TimeoutExpired:
        print(
            "[start] ERROR: Alembic migrations timed out. "
            "Refusing to start with an unverified database schema.",
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(1) from None
    except (subprocess.CalledProcessError, OSError):
        print(
            "[start] ERROR: Alembic upgrade failed. "
            "Refusing to start with an unverified database schema.",
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(1) from None

    # ── Ensure critical columns exist (handles schema drift) ──
    _ensure_schema_columns()


def _serve() -> None:
    """Start the portable ASGI process after database preparation."""

    import uvicorn

    port = settings.port
    print(f"[start] Starting server on 0.0.0.0:{port}...", flush=True)
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)


def _run_accounts_migrations() -> None:
    """Version the separate directory database without displaying its URL."""

    from sqlalchemy.engine import make_url

    primary = make_url(settings.database_url)
    accounts = make_url(settings.accounts_database_url)

    def database_identity(url):
        return (url.get_backend_name(), url.host, url.port or 5432, url.database)

    if database_identity(primary) == database_identity(accounts):
        raise SystemExit("Accounts database must be separate from the primary database.")
    if settings.is_deployed and accounts.get_backend_name() != "postgresql":
        raise SystemExit("Deployed accounts persistence requires PostgreSQL.")
    try:
        subprocess.run(
            [
                sys.executable, "-m", "alembic", "-c", "accounts_alembic.ini",
                "upgrade", "head",
            ],
            check=True,
            cwd=_BACKEND_ROOT,
            timeout=settings.migrate_timeout_seconds,
            env={**os.environ, "ACCOUNTS_DATABASE_URL": settings.accounts_database_url},
            # Driver errors can contain a host or user; only emit a safe status.
            capture_output=True,
        )
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
        print(
            "[start] Accounts migration failed; runtime rollout is stopped.",
            file=sys.stderr, flush=True,
        )
        raise SystemExit(1) from exc
    print("[start] Accounts migrations complete.", flush=True)


def _run_compatibility_bootstrap() -> None:
    """Prepare legacy/reference data once in the migration-job process."""

    from app.startup_bootstrap import run_compatibility_bootstrap

    run_compatibility_bootstrap(strict=True)


def _arguments(argv: Sequence[str]):
    parser = argparse.ArgumentParser(description="Start or migrate the GeoVision backend")
    parser.add_argument(
        "command",
        choices=("serve", "migrate"),
        default="serve",
        nargs="?",
        help="serve the API (default) or run the one-shot database migration job",
    )
    parser.add_argument(
        "--skip-migrations",
        action="store_true",
        help="serve without schema writes after a separate migration job has succeeded",
    )
    parsed = parser.parse_args(list(argv))
    if parsed.command == "migrate" and parsed.skip_migrations:
        parser.error("--skip-migrations is only valid with the serve command")
    return parsed


def main(argv: Sequence[str] = ()) -> None:
    """Run the default-compatible server or the one-shot migration command."""

    args = _arguments(argv)
    if args.command == "migrate":
        _run_migrations()
        _run_accounts_migrations()
        _run_compatibility_bootstrap()
        return

    run_migrations = settings.run_migrations_on_startup and not args.skip_migrations
    if run_migrations:
        _run_migrations()
        _run_accounts_migrations()
    else:
        # Legacy schema repair and seed operations are also database writes.
        # Disable them for horizontally scaled API replicas when migration
        # ownership has been delegated to a one-shot deployment job.
        settings.startup_compatibility_bootstrap = False
        print(
            "[start] Database migration delegated to an external job; "
            "starting a read-only API bootstrap.",
            flush=True,
        )
    _serve()


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
    main(sys.argv[1:])
