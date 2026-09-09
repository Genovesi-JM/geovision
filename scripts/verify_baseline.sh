#!/usr/bin/env bash
set -euo pipefail

GEOVISION_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

find_backend_python() {
  local candidate
  for candidate in \
    "$GEOVISION_ROOT/backend/.venv/bin/python" \
    "$GEOVISION_ROOT/backend/.venv-test/bin/python" \
    "$(command -v python3 2>/dev/null || true)"; do
    if [[ -n "$candidate" && -x "$candidate" ]] && \
       "$candidate" -c 'import fastapi, pydantic_settings, pytest, sqlalchemy' >/dev/null 2>&1; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

find_flutter() {
  local candidate
  for candidate in \
    "$(command -v flutter 2>/dev/null || true)" \
    "${HOME}/development/flutter/bin/flutter" \
    "${HOME}/flutter/bin/flutter" \
    "${HOME}/fvm/default/bin/flutter" \
    "/opt/flutter/bin/flutter"; do
    if [[ -n "$candidate" && -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

GEOVISION_PYTHON="$(find_backend_python || true)"
if [[ -z "$GEOVISION_PYTHON" ]]; then
  printf 'No healthy backend Python environment found. Recreate backend/.venv and install backend/requirements.txt plus pytest.\n' >&2
  exit 1
fi

GEOVISION_FLUTTER="$(find_flutter || true)"
if [[ -z "$GEOVISION_FLUTTER" ]]; then
  printf 'Flutter was not found in PATH or a common macOS installation path.\n' >&2
  exit 1
fi

command -v npm >/dev/null 2>&1 || {
  printf 'npm is required for the browser test suite.\n' >&2
  exit 1
}

printf 'Backend tests with %s\n' "$GEOVISION_PYTHON"
(cd "$GEOVISION_ROOT/backend" && "$GEOVISION_PYTHON" -m pytest -q)

printf '\nWeb tests\n'
(cd "$GEOVISION_ROOT" && npm test -- --workers=1 --reporter=line)

printf '\nFlutter formatting, analysis and tests with %s\n' "$GEOVISION_FLUTTER"
GEOVISION_DART="$(dirname "$GEOVISION_FLUTTER")/dart"
(cd "$GEOVISION_ROOT/mobile" && \
  "$GEOVISION_DART" format --output=none --set-exit-if-changed lib test integration_test && \
  "$GEOVISION_FLUTTER" analyze && \
  "$GEOVISION_FLUTTER" test)

if [[ "${GEOVISION_BASELINE_BUILDS:-0}" == "1" ]]; then
  printf '\nAndroid debug build\n'
  (cd "$GEOVISION_ROOT/mobile" && "$GEOVISION_FLUTTER" build apk --debug)

  printf '\niOS simulator debug build\n'
  (cd "$GEOVISION_ROOT/mobile" && \
    "$GEOVISION_FLUTTER" build ios --simulator --debug --no-codesign)
fi

printf '\nGeoVision baseline checks passed.\n'
