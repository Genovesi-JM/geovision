#!/usr/bin/env bash
# ==============================================================================
# GeoVision — Mac autonomous development entry point
# Double-click this file, or run:  ./START_AUTODEV_MAC.command
#
# Implements a controlled build/verify loop on the Mac toolchain (the only
# place iOS can actually be built). It never fabricates results: each check
# runs the real tool and its exit code decides pass/fail. Logs + a status
# report are written to automation/.
# ==============================================================================
set -uo pipefail

# Resolve repo root = directory of this script.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
MOBILE="$ROOT/mobile"
BACKEND="$ROOT/backend"
LOGDIR="$ROOT/automation/logs"
STAMP="$(date +%Y%m%d-%H%M%S)"
RUN_LOG="$LOGDIR/run-$STAMP.log"
STATUS="$ROOT/AUTODEV_STATUS.md"
BRANCH="autodev/mobile-build"
mkdir -p "$LOGDIR"

# ── PATH bootstrap ───────────────────────────────────────────────────────────
# A double-clicked .command runs under bash and may not inherit the PATH set in
# ~/.zshrc, so a valid Flutter install can be invisible. Source common profiles
# and add the well-known Flutter/Homebrew locations before preflight.
for prof in "$HOME/.zprofile" "$HOME/.zshrc" "$HOME/.bash_profile" "$HOME/.profile"; do
  [ -f "$prof" ] && . "$prof" >/dev/null 2>&1 || true
done
for p in \
  "/opt/homebrew/bin" "/usr/local/bin" \
  "$HOME/development/flutter/bin" "$HOME/flutter/bin" \
  "$HOME/fvm/default/bin" "/opt/flutter/bin"; do
  [ -d "$p" ] && case ":$PATH:" in *":$p:"*) ;; *) PATH="$p:$PATH";; esac
done
# Homebrew cask install location (versioned) — pick the newest if present.
for c in /opt/homebrew/Caskroom/flutter/*/flutter/bin /usr/local/Caskroom/flutter/*/flutter/bin; do
  [ -d "$c" ] && PATH="$c:$PATH"
done
export PATH

# Colours
B="\033[1m"; G="\033[32m"; Y="\033[33m"; RD="\033[31m"; N="\033[0m"
declare -a RESULTS

log()  { echo -e "$*" | tee -a "$RUN_LOG"; }
step() { log "\n${B}▶ $*${N}"; }
record(){ RESULTS+=("$1|$2|$3"); }  # name|status|detail

run() { # run "Name" cmd...  -> logs, records pass/fail, never aborts the whole loop
  local name="$1"; shift
  step "$name"
  if "$@" >>"$RUN_LOG" 2>&1; then
    log "${G}✓ $name${N}"; record "$name" "PASS" ""
    return 0
  else
    local code=$?
    log "${RD}✗ $name (exit $code)${N} — see $RUN_LOG"
    record "$name" "FAIL" "exit $code"
    return 1
  fi
}

need() { command -v "$1" >/dev/null 2>&1; }

# ── 0. Preflight ─────────────────────────────────────────────────────────────
step "Preflight — inspecting the Mac toolchain"
log "macOS: $(sw_vers -productVersion 2>/dev/null || echo unknown)  arch: $(uname -m)"
HAVE_FLUTTER=0; HAVE_XCODE=0; HAVE_ANDROID=0; HAVE_PY=0
need flutter && { HAVE_FLUTTER=1; log "flutter: $(flutter --version 2>/dev/null | head -1)"; } || log "${Y}flutter not found — install from https://docs.flutter.dev/get-started/install/macos${N}"
xcodebuild -version >/dev/null 2>&1 && { HAVE_XCODE=1; log "xcode: $(xcodebuild -version 2>/dev/null | head -1)"; } || log "${Y}Xcode not found/licensed — iOS build will be skipped${N}"
{ need sdkmanager || [ -n "${ANDROID_HOME:-}${ANDROID_SDK_ROOT:-}" ]; } && { HAVE_ANDROID=1; log "android sdk: ${ANDROID_HOME:-${ANDROID_SDK_ROOT:-detected}}"; } || log "${Y}Android SDK not found — Android build will be skipped${N}"
need python3 && { HAVE_PY=1; log "python: $(python3 --version 2>&1)"; } || log "${Y}python3 not found — backend tests skipped${N}"

if [ "$HAVE_FLUTTER" -eq 0 ]; then
  log "${RD}Flutter is required. Install it, then re-run this launcher.${N}"
  exit 1
fi

# ── 1. Safe git checkpoint ───────────────────────────────────────────────────
step "Git checkpoint on branch '$BRANCH'"
if need git && [ -d "$ROOT/.git" ]; then
  git rev-parse --abbrev-ref HEAD >>"$RUN_LOG" 2>&1
  git stash list >>"$RUN_LOG" 2>&1
  if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
    git switch "$BRANCH" >>"$RUN_LOG" 2>&1 || log "${Y}Could not switch branch (uncommitted work preserved).${N}"
  else
    git switch -c "$BRANCH" >>"$RUN_LOG" 2>&1 || log "${Y}Could not create branch (uncommitted work preserved).${N}"
  fi
  log "On branch: $(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
else
  log "${Y}Not a git repo yet. Run: git init && git add -A && git commit -m 'baseline' — continuing without VCS.${N}"
fi

# ── 2. Materialise iOS/Android platform folders if missing ───────────────────
cd "$MOBILE"
if [ ! -f "$MOBILE/ios/Runner.xcodeproj/project.pbxproj" ] || [ ! -f "$MOBILE/android/app/build.gradle" ]; then
  run "flutter create (generate ios/android)" flutter create --platforms=ios,android --org com.geovision --project-name geovision .
fi

# ── 3. Dependencies + localisation codegen ──────────────────────────────────
run "flutter pub get" flutter pub get
run "flutter gen-l10n" flutter gen-l10n || true

# ── 4. Static analysis + formatting ─────────────────────────────────────────
run "dart format (check)" dart format --output=none --set-exit-if-changed lib test integration_test
run "flutter analyze" flutter analyze

# ── 5. Unit + widget tests ──────────────────────────────────────────────────
run "flutter test" flutter test --reporter expanded

# ── 6. Backend tests (best-effort) ──────────────────────────────────────────
if [ "$HAVE_PY" -eq 1 ] && [ -d "$BACKEND" ]; then
  step "Backend: venv + pytest"
  PYTHON_BIN="$(command -v python3.12 || command -v python3.11 || command -v python3)"
  ( cd "$BACKEND" \
    && "$PYTHON_BIN" -m venv .venv >>"$RUN_LOG" 2>&1 \
    && . .venv/bin/activate \
    && pip install -q -r requirements.deploy.txt pytest >>"$RUN_LOG" 2>&1 \
    && pytest -q >>"$RUN_LOG" 2>&1 )
  if [ $? -eq 0 ]; then log "${G}✓ Backend tests${N}"; record "Backend pytest" "PASS" ""; else log "${Y}△ Backend tests failed/partial (see log)${N}"; record "Backend pytest" "WARN" "see log"; fi
fi

# ── 7. iOS Simulator build ──────────────────────────────────────────────────
if [ "$HAVE_XCODE" -eq 1 ]; then
  run "iOS Simulator build (debug, no codesign)" flutter build ios --simulator --debug
else
  record "iOS Simulator build" "SKIP" "Xcode not available"
fi

# ── 8. Android debug build ──────────────────────────────────────────────────
if [ "$HAVE_ANDROID" -eq 1 ]; then
  run "Android debug APK" flutter build apk --debug
else
  record "Android debug build" "SKIP" "Android SDK not available"
fi

# ── 9. Write status report ──────────────────────────────────────────────────
step "Writing $STATUS"
{
  echo "# GeoVision — AUTODEV status"
  echo ""
  echo "_Generated: $(date)_  ·  run log: \`automation/logs/run-$STAMP.log\`"
  echo ""
  echo "| Check | Result | Detail |"
  echo "|-------|--------|--------|"
  for r in "${RESULTS[@]}"; do
    IFS='|' read -r n s d <<< "$r"
    echo "| $n | $s | $d |"
  done
  echo ""
  echo "Branch: \`$BRANCH\`. Re-run: \`./START_AUTODEV_MAC.command\` or \`make autodev\`."
} > "$STATUS"

# ── 10. Summary ─────────────────────────────────────────────────────────────
step "Summary"
FAILED=0
for r in "${RESULTS[@]}"; do
  IFS='|' read -r n s d <<< "$r"
  case "$s" in
    PASS) log "  ${G}PASS${N}  $n";;
    FAIL) log "  ${RD}FAIL${N}  $n ($d)"; FAILED=1;;
    WARN) log "  ${Y}WARN${N}  $n ($d)";;
    SKIP) log "  ${Y}SKIP${N}  $n ($d)";;
  esac
done
log "\nStatus report: $STATUS"
if [ "$FAILED" -eq 1 ]; then
  log "${Y}Some checks failed. Fixes go on '$BRANCH'; details in the run log.${N}"
else
  log "${G}All executable checks passed.${N}"
fi

# Offer to launch the app in the iOS Simulator.
if [ "$HAVE_XCODE" -eq 1 ]; then
  log "\nTo launch the app now:  cd mobile && flutter run --dart-define=GV_FLAVOR=dev"
fi
