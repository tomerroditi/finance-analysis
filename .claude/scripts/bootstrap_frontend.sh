#!/usr/bin/env bash
# Bootstrap (and keep in sync) the frontend's node_modules.
#
# The frontend counterpart of bootstrap_venv.sh. Wired in as the `predev`
# npm lifecycle hook in frontend/package.json, so `npm run dev` — and
# therefore the VS Code "Frontend" task and ./start.sh — self-heals a fresh
# checkout/worktree instead of dying with `sh: vite: command not found`.
# Git worktrees only carry source files, never node_modules/.
#
# Two responsibilities, same as the venv script:
#   1. Install deps when node_modules is missing (first run).
#   2. Re-install when package-lock.json changed since the last install
#      (git pull / branch switch / merge that added a package), so an
#      existing node_modules can't sail past a presence-only check and then
#      crash on a missing import.
#
# Uses `npm ci`, never `npm install`: ci installs exactly what the lockfile
# says and does not rewrite it. A plain `npm install` on this machine prunes
# the other platforms' optional binaries (@esbuild/linux-*, @rollup/*) out of
# the lockfile, which breaks Vercel's Linux build — see
# .claude/rules/frontend_pwa.md "Lockfile hygiene".
#
# Staleness is a single SHA-256 of package-lock.json compared to a stamp
# written after the last successful install (node_modules/.deps-lock-hash),
# so a warm start costs milliseconds. The stamp is written only after a
# successful install, so an interrupted run retries instead of reporting
# "up to date".

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT/frontend"

LOCK_FILE="package-lock.json"
STAMP_FILE="node_modules/.deps-lock-hash"
# vite is a direct dependency that only exists after a successful install,
# so its presence doubles as the "install completed" marker.
MARKER="node_modules/.bin/vite"

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

# Fast path: deps present AND lockfile unchanged since the last install.
if [ -x "$MARKER" ] && [ -n "$current_hash" ] && [ "$current_hash" = "$stored_hash" ]; then
  exit 0
fi

if ! command -v npm >/dev/null 2>&1; then
  cat >&2 <<'EOF'
[bootstrap] ERROR: npm not found on PATH.

Install Node.js (https://nodejs.org or `brew install node`) and re-run.
EOF
  exit 1
fi

if [ ! -x "$MARKER" ]; then
  echo "[bootstrap] No frontend/node_modules in this worktree (or previous install was interrupted)."
  echo "[bootstrap] Installing frontend dependencies — runs once per worktree."
else
  echo "[bootstrap] package-lock.json changed since last install — syncing dependencies..."
fi

npm ci --no-audit --no-fund

new_hash="$(hash_lock 2>/dev/null || true)"
[ -n "$new_hash" ] && printf '%s\n' "$new_hash" > "$STAMP_FILE"

echo "[bootstrap] Done."
