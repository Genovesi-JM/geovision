#!/usr/bin/env bash
set -euo pipefail

phase33_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

find_backend_python() {
  local candidate
  for candidate in \
    "${phase33_root}/backend/.venv/bin/python" \
    "${phase33_root}/backend/.venv-test/bin/python" \
    "$(command -v python3 2>/dev/null || true)"; do
    if [[ -n "${candidate}" && -x "${candidate}" ]] && \
       "${candidate}" -c 'import fastapi, pydantic_settings, pytest, sqlalchemy' \
         >/dev/null 2>&1; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done
  return 1
}

phase33_python="$(find_backend_python || true)"
if [[ -z "${phase33_python}" ]]; then
  printf 'No healthy backend Python environment was found.\n' >&2
  exit 1
fi

printf 'Phase 33 baseline: backend, browser, Flutter, Android, and iOS\n'
GEOVISION_BASELINE_BUILDS=1 "${phase33_root}/scripts/verify_baseline.sh"

printf '\nNamed security release gate\n'
(
  cd "${phase33_root}/backend"
  "${phase33_python}" -m pytest -q --strict-markers -m security_regression
)

printf '\nAlembic graph\n'
(
  cd "${phase33_root}/backend"
  "${phase33_python}" -m alembic heads
  if [[ -n "${GEOVISION_MIGRATION_TEST_DATABASE_URL:-}" ]]; then
    GEOVISION_MIGRATION_TEST_DATABASE_URL="${GEOVISION_MIGRATION_TEST_DATABASE_URL}" \
      "${phase33_python}" -m pytest -q tests/test_migration_release_gate.py
  else
    printf 'WARN  GEOVISION_MIGRATION_TEST_DATABASE_URL is unset; PostgreSQL/PostGIS migration rehearsal is delegated to CI.\n'
  fi
)

printf '\nCanonical backend container\n'
docker build \
  --file "${phase33_root}/backend/Dockerfile" \
  --tag geovision-backend:phase33 \
  "${phase33_root}/backend"

if [[ -n "${GEOVISION_STAGING_API_URL:-}" ]]; then
  printf '\nStaging smoke\n'
  "${phase33_root}/scripts/staging_smoke.sh"
else
  printf '\nWARN  GEOVISION_STAGING_API_URL is unset; no live staging smoke was claimed.\n'
fi

printf '\nAvailable Phase 33 local checks passed. Warnings above remain open release evidence.\n'
