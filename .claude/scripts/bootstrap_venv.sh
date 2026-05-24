#!/usr/bin/env bash
# Bootstrap a Python venv with project dependencies if missing.
#
# Idempotent: exits 0 silently when the venv is already set up. Used by
# `npm run backend` to auto-heal worktrees that haven't been bootstrapped
# yet — the worktree creation flow only copies source files, not the
# .venv, so a freshly created worktree's `npm run backend` would otherwise
# fail with "sh: .venv/bin/activate: No such file or directory".
#
# Manual equivalent (per CLAUDE.md "Environment Setup"):
#   python3.12 -m venv .venv && source .venv/bin/activate \
#     && pip install poetry && poetry install --no-root
#
# Re-runs safely after a partial install — the "already bootstrapped" check
# looks for .venv/bin/uvicorn (a project dependency that exists only after a
# successful poetry install), so an interrupted bootstrap re-runs cleanly.

set -euo pipefail

# Run from the repo root regardless of where the script was invoked from.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

# Already bootstrapped — fast path, no output.
if [ -x .venv/bin/uvicorn ]; then
  exit 0
fi

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

# shellcheck disable=SC1091
source .venv/bin/activate

pip install --quiet --upgrade pip
pip install --quiet poetry
poetry install --no-root

echo "[bootstrap] Done. Starting backend..."
