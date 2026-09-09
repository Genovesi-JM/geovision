#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
RUN_DIR="$(mktemp -d "${TMPDIR:-/tmp}/geovision-e2e.XXXXXX")"
DATABASE_URL="sqlite:///$RUN_DIR/geovision-e2e.db"

if [[ -x "$BACKEND_DIR/.venv-test/bin/python" ]]; then
  PYTHON_BIN="$BACKEND_DIR/.venv-test/bin/python"
elif [[ -x "$BACKEND_DIR/.venv/bin/python" ]] && \
     "$BACKEND_DIR/.venv/bin/python" -c 'import alembic, pydantic_settings, uvicorn' >/dev/null 2>&1; then
  PYTHON_BIN="$BACKEND_DIR/.venv/bin/python"
else
  PYTHON_BIN="python3"
fi

export ENV=test
export DATABASE_URL
export SECRET_KEY="geovision-browser-tests-only"
export CORS_ORIGINS="http://127.0.0.1:8001,http://localhost:8001"

cd "$BACKEND_DIR"
"$PYTHON_BIN" -m alembic upgrade head
exec "$PYTHON_BIN" -m uvicorn app.main:app --host 127.0.0.1 --port 8010
