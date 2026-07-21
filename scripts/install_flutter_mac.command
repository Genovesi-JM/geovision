#!/usr/bin/env bash
# ==============================================================================
# GeoVision — one-click Flutter installer for macOS (no Homebrew required)
# Clones the Flutter stable SDK to ~/development/flutter, adds it to PATH in
# both ~/.zshrc and ~/.bash_profile, and runs an initial `flutter --version`
# (which downloads the bundled Dart SDK on first run).
#
# Safe + idempotent: if Flutter is already present it just re-uses it.
# Total download is roughly 1 GB; allow several minutes on first run.
# ==============================================================================
set -uo pipefail
B="\033[1m"; G="\033[32m"; Y="\033[33m"; RD="\033[31m"; N="\033[0m"
say(){ echo -e "$*"; }

DEST="$HOME/development/flutter"
BIN="$DEST/bin"

say "${B}▶ GeoVision Flutter installer${N}"
say "macOS $(sw_vers -productVersion 2>/dev/null)  ·  arch $(uname -m)"

if command -v flutter >/dev/null 2>&1; then
  say "${G}✓ Flutter already on PATH:${N} $(flutter --version 2>/dev/null | head -1)"
  exit 0
fi

if ! command -v git >/dev/null 2>&1; then
  say "${RD}git not found.${N} Install the Xcode command-line tools first:  xcode-select --install"
  say "Then double-click this installer again."
  exit 1
fi

if [ ! -x "$BIN/flutter" ]; then
  say "${B}▶ Cloning Flutter stable → $DEST${N}  (this is the ~1 GB step)"
  mkdir -p "$HOME/development"
  git clone --depth 1 -b stable https://github.com/flutter/flutter.git "$DEST" || {
    say "${RD}Clone failed.${N} Check your internet connection and re-run."; exit 1; }
else
  say "${Y}△ Flutter folder already exists at $DEST — reusing it.${N}"
fi

# Persist PATH for zsh (default) and bash.
LINE='export PATH="$HOME/development/flutter/bin:$PATH"'
for rc in "$HOME/.zshrc" "$HOME/.bash_profile"; do
  touch "$rc"
  grep -qF "$LINE" "$rc" 2>/dev/null || printf '\n# Flutter (GeoVision)\n%s\n' "$LINE" >> "$rc"
done
export PATH="$BIN:$PATH"

say "${B}▶ First run — downloading the bundled Dart SDK…${N}"
"$BIN/flutter" --version || { say "${RD}flutter --version failed.${N}"; exit 1; }

say "${B}▶ flutter doctor${N}"
"$BIN/flutter" doctor || true

say ""
say "${G}✓ Flutter installed.${N}  Now double-click ${B}START_AUTODEV_MAC.command${N} to build GeoVision,"
say "  or run:  cd \"$HOME/geovision\" && ./START_AUTODEV_MAC.command"
