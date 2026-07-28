#!/usr/bin/env bash
# Bootstrap (and keep in sync) a Python venv with project dependencies.
#
# Used by `npm run backend` and `./start.sh` to auto-heal checkouts/worktrees
# that haven't been bootstrapped yet — the worktree creation flow only copies
# source files, not the .venv.
#
# Two responsibilities:
#   1. Create the venv + install deps when it's missing (first run, ~90s).
#   2. Re-sync deps when poetry.lock has changed since the last install
#      (e.g. after a git pull / branch switch / merge that added a package).
#      Without this, an existing venv that already has `uvicorn` would sail
#      past a presence-only check and silently run with stale dependencies —
#      the exact failure mode where a newly added dep (e.g. `cryptography`)
#      is missing and the backend crashes on import at startup.
#
# Staleness is detected by hashing poetry.lock and comparing to a stamp
# written after the last successful install (.venv/.deps-lock-hash). The
# fast path is a single file hash (milliseconds), so a warm start stays
# effectively instant — poetry is only invoked when the lock actually moved.
#
# Manual equivalent (per CLAUDE.md "Environment Setup"):
#   python3.12 -m venv .venv && source .venv/bin/activate \
#     && pip install poetry && poetry install --no-root
#
# Re-runs safely after a partial install — the venv-present check looks for
# .venv/bin/uvicorn (a project dependency that exists only after a successful
# poetry install), and the lock-hash stamp is written only after a successful
# install, so an interrupted bootstrap re-runs cleanly.

set -euo pipefail

# Run from the repo root regardless of where the script was invoked from.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

LOCK_FILE="poetry.lock"
STAMP_FILE=".venv/.deps-lock-hash"

# Portable SHA-256 of poetry.lock. Empty output if the lock or a hash tool is
# missing — an empty hash never matches the stamp, so we fall through to a
# (re)install rather than trusting a possibly-stale venv.
hash_lock() {
  [ -f "$LOCK_FILE" ] || return 0
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$LOCK_FILE" | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$LOCK_FILE" | awk '{print $1}'
  fi
}

current_hash="$(hash_lock 2>/dev/null || true)"
stored_hash=""
[ -f "$STAMP_FILE" ] && stored_hash="$(cat "$STAMP_FILE" 2>/dev/null || true)"

# Fast path: venv present AND lock unchanged since the last install.
if [ -x .venv/bin/uvicorn ] && [ -n "$current_hash" ] && [ "$current_hash" = "$stored_hash" ]; then
  exit 0
fi

if [ ! -x .venv/bin/uvicorn ]; then
  echo "[bootstrap] No .venv found in this worktree (or previous bootstrap was interrupted)."
  echo "[bootstrap] Setting up the backend environment — this takes ~90s and only runs once per worktree."

  if ! command -v python3.12 >/dev/null 2>&1; then
    cat >&2 <<'EOF'
[bootstrap] ERROR: python3.12 not found on PATH.

This project requires Python 3.12 (see CLAUDE.md). Install it with:
  brew install python@3.12       # macOS

Then re-run `npm run backend`.
EOF
    exit 1
  fi

  # Create the venv if missing — keep an existing partial venv if present so
  # we don't lose any in-progress poetry state.
  if [ ! -d .venv ]; then
    python3.12 -m venv .venv
  fi
else
  echo "[bootstrap] poetry.lock changed since last install — syncing dependencies..."
fi

# shellcheck disable=SC1091
source .venv/bin/activate

# poetry lives inside the venv; a fresh venv (or one predating this check)
# needs it installed before we can run the install.
pip install --quiet --upgrade pip
command -v poetry >/dev/null 2>&1 || pip install --quiet poetry
poetry install --no-root

# Record the lock hash only after a successful install so an interrupted run
# leaves the stamp stale (forcing a retry) rather than falsely "up to date".
new_hash="$(hash_lock 2>/dev/null || true)"
[ -n "$new_hash" ] && printf '%s\n' "$new_hash" > "$STAMP_FILE"

echo "[bootstrap] Done."
