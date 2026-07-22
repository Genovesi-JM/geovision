#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
MOBILE="$ROOT/mobile"
API_URL="${GV_API_BASE_URL:-http://127.0.0.1:8010}"
BACKEND_LOG="${TMPDIR:-/tmp}/geovision-backend.log"

if curl --max-time 2 --silent --fail "$API_URL/health" >/dev/null 2>&1 ||
   curl --max-time 2 --silent --fail "$API_URL/ai/status" >/dev/null 2>&1; then
  BACKEND_PID=""
  echo "GeoVision backend already running at $API_URL"
else
  if [ -x "$BACKEND/.venv-test/bin/uvicorn" ]; then
    UVICORN="$BACKEND/.venv-test/bin/uvicorn"
  elif [ -x "$BACKEND/.venv/bin/uvicorn" ]; then
    UVICORN="$BACKEND/.venv/bin/uvicorn"
  else
    echo "Backend environment missing. Run 'make backend-run' once."
    exit 1
  fi

  echo "Starting GeoVision backend..."
  (cd "$BACKEND" && "$UVICORN" app.main:app --host 0.0.0.0 --port 8010 >"$BACKEND_LOG" 2>&1) &
  BACKEND_PID=$!
  trap 'if [ -n "${BACKEND_PID:-}" ]; then kill "$BACKEND_PID" 2>/dev/null || true; fi' EXIT INT TERM

  for _ in {1..30}; do
    if curl --max-time 2 --silent --fail "$API_URL/ai/status" >/dev/null 2>&1; then
      break
    fi
    sleep 0.5
  done

  if ! curl --max-time 2 --silent --fail "$API_URL/ai/status" >/dev/null; then
    echo "Backend did not become ready. See $BACKEND_LOG"
    exit 1
  fi
fi

echo "GAIA backend ready. Starting the mobile app..."
cd "$MOBILE"
flutter run \
  --dart-define=GV_FLAVOR=dev \
  --dart-define=GV_API_BASE_URL="$API_URL"
