#!/usr/bin/env bash
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MOBILE_DIR="$ROOT_DIR/mobile"
FAILURES=0
WARNINGS=0

pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'BLOCK %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
warn() { printf 'WARN  %s\n' "$1"; WARNINGS=$((WARNINGS + 1)); }

check_url() {
  local label="$1"
  local url="$2"
  local expected="$3"
  local code
  code="$(curl -L -sS --max-time 15 -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || true)"
  if [[ "$code" == "$expected" ]]; then
    pass "$label returned HTTP $code"
  else
    fail "$label returned HTTP ${code:-unreachable}; expected $expected"
  fi
}

printf 'GeoVision production readiness\n\n'

check_url "Public website" "https://geovisionops.com/" "200"
check_url "Privacy page" "https://geovisionops.com/privacy.html" "200"
check_url "Terms page" "https://geovisionops.com/terms.html" "200"
check_url "Production API health" "https://api.geovisionops.com/health" "200"

if grep -q '"GV_DEMO_MODE": "false"' "$MOBILE_DIR/dart_defines/production.json" && \
   grep -q '"GV_API_BASE_URL": "https://api.geovisionops.com"' "$MOBILE_DIR/dart_defines/production.json"; then
  pass "Mobile production build disables demo data and targets the production API"
else
  fail "Mobile production configuration is not safe for release"
fi

if [[ -s "$MOBILE_DIR/android/key.properties" ]]; then
  pass "Android release signing configuration exists"
else
  fail "Android release keystore configuration is missing"
fi

if grep -Eq 'DEVELOPMENT_TEAM = [A-Z0-9]+' "$MOBILE_DIR/ios/Runner.xcodeproj/project.pbxproj"; then
  pass "Apple development team is configured"
else
  fail "Apple development team/signing is not configured"
fi

if grep -q '"GV_PUSH_PROVIDER": "mock"' "$MOBILE_DIR/dart_defines/production.json"; then
  warn "Push notifications remain disabled/mock in production"
else
  pass "Production push provider is configured"
fi

if grep -q '"GV_MAP_PROVIDER": "demo"' "$MOBILE_DIR/dart_defines/production.json"; then
  warn "Maps remain in demo mode in production"
else
  pass "Production map provider is configured"
fi

printf '\nResult: %d blocker(s), %d warning(s)\n' "$FAILURES" "$WARNINGS"
if (( FAILURES > 0 )); then
  exit 1
fi
