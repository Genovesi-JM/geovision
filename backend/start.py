import os
import sys
import subprocess


def main() -> None:
    # Run DB migrations for the main database.
    subprocess.check_call([sys.executable, "-m", "alembic", "upgrade", "head"])

    import uvicorn

    port = int(os.environ.get("PORT", "8010"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
