import os
import sys
import subprocess


def main() -> None:
    migrate_timeout_s = int(os.environ.get("MIGRATE_TIMEOUT", "120"))

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
            f"[start] WARNING: Alembic upgrade failed (exit code {exc.returncode}). "
            "Attempting to stamp head and ensure tables exist...",
            file=sys.stderr,
            flush=True,
        )
        # Tables may already exist from a previous deployment.
        # Stamp alembic to head so it knows the DB is current.
        try:
            subprocess.run(
                [sys.executable, "-m", "alembic", "stamp", "head"],
                check=True,
                timeout=30,
            )
            print("[start] Stamped DB to head.", flush=True)
        except Exception as stamp_err:
            print(f"[start] WARNING: alembic stamp also failed: {stamp_err}", file=sys.stderr, flush=True)

        # Ensure all tables exist (create any missing ones)
        try:
            from app.database import engine, Base
            from app import models  # noqa: F401 — registers all models
            Base.metadata.create_all(bind=engine)
            print("[start] Ensured all tables exist via create_all.", flush=True)
        except Exception as create_err:
            print(f"[start] ERROR: create_all failed: {create_err}", file=sys.stderr, flush=True)
            raise SystemExit(1)

    import uvicorn

    port = int(os.environ.get("PORT", "8010"))
    print(f"[start] Starting server on 0.0.0.0:{port}...", flush=True)
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
