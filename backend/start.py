import os
import sys
import subprocess


def main() -> None:
    migrate_timeout_s = int(os.environ.get("MIGRATE_TIMEOUT", "120"))

    # Run DB migrations for the main database.
    # Important: if the DB is unreachable (common when an external DB requires IP allowlisting),
    # Alembic can hang for a long time. Failing fast gives actionable Render logs.
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
            "If you are using an external database with an IP allowlist, add Render outbound IP ranges.",
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(1)
    except subprocess.CalledProcessError as exc:
        print(
            f"[start] ERROR: Alembic migrations failed with exit code {exc.returncode}.",
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(exc.returncode)

    import uvicorn

    port = int(os.environ.get("PORT", "8010"))
    print(f"[start] Starting server on 0.0.0.0:{port}...", flush=True)
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
