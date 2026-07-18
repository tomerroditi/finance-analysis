#!/usr/bin/env bash
#
# Single entry point for running the app locally.
#
#   ./start.sh              # dev: backend (hot-reload) + frontend dev server
#   ./start.sh remote       # dev servers bound to 0.0.0.0 + Tailscale CORS,
#                           # for phone/laptop access over the tailnet
#   ./start.sh prod         # prod: build frontend, serve everything from backend
#   ./start.sh prod 9000    # positional port still accepted (sets BACKEND_PORT)
#
# Ports are env-driven (BACKEND_PORT / FRONTEND_PORT), with non-clashing
# per-mode defaults so any two modes can run side by side:
#
#   mode     backend  frontend
#   dev      8000     5173
#   remote   8001     5174
#   prod     8080     (served by backend)
#
# This file is the single owner of those numbers — VS Code tasks
# (.vscode/tasks.json) call the same modes instead of repeating ports.
#
# The Python venv is auto-bootstrapped on first run (~90s, idempotent) via
# .claude/scripts/bootstrap_venv.sh — no manual setup step needed.

set -euo pipefail

cd "$(dirname "$0")"

MODE="${1:-dev}"
case "$MODE" in
  prod)   DEFAULT_BACKEND_PORT=8080 DEFAULT_FRONTEND_PORT=5173 ;;
  remote) DEFAULT_BACKEND_PORT=8001 DEFAULT_FRONTEND_PORT=5174 ;;
  *)      DEFAULT_BACKEND_PORT=8000 DEFAULT_FRONTEND_PORT=5173 ;;
esac
BACKEND_PORT="${2:-${BACKEND_PORT:-$DEFAULT_BACKEND_PORT}}"
FRONTEND_PORT="${FRONTEND_PORT:-$DEFAULT_FRONTEND_PORT}"

./.claude/scripts/bootstrap_venv.sh

# Run both dev servers; extra args are threaded to uvicorn/vite by the caller.
#   $1 - extra uvicorn args (e.g. "--host 0.0.0.0"), may be empty
#   $2 - extra vite args (e.g. "--host 0.0.0.0"), may be empty
run_dev_pair() {
  # shellcheck disable=SC2086  # word-splitting of the extra args is intended
  .venv/bin/uvicorn backend.main:app --reload \
    --reload-dir backend --reload-dir scraper --port "$BACKEND_PORT" $1 &
  BACKEND_PID=$!
  trap 'kill $BACKEND_PID 2>/dev/null; exit' INT TERM
  # shellcheck disable=SC2086
  cd frontend && PORT="$FRONTEND_PORT" BACKEND_PORT="$BACKEND_PORT" npm run dev -- $2
}

case "$MODE" in
  dev)
    echo "Starting in dev mode (backend :$BACKEND_PORT + frontend :$FRONTEND_PORT)..."
    run_dev_pair "" ""
    ;;
  remote)
    # Expose both servers on all interfaces and allow the tailnet origin in
    # CORS, so another device (phone, laptop) can use the dashboard. The
    # Tailscale IP is looked up from the CLI when available ('tailscale' on
    # PATH, or the macOS app bundle binary).
    ORIGINS="http://localhost:$FRONTEND_PORT,http://127.0.0.1:$FRONTEND_PORT"
    TS_BIN="$(command -v tailscale || true)"
    [ -z "$TS_BIN" ] && [ -x "/Applications/Tailscale.app/Contents/MacOS/Tailscale" ] \
      && TS_BIN="/Applications/Tailscale.app/Contents/MacOS/Tailscale"
    if [ -n "$TS_BIN" ] && TS_IP="$("$TS_BIN" ip -4 2>/dev/null | head -1)" && [ -n "$TS_IP" ]; then
      ORIGINS="$ORIGINS,http://$TS_IP:$FRONTEND_PORT"
      echo "Access from the tailnet at: http://$TS_IP:$FRONTEND_PORT"
    else
      echo "warning: tailscale CLI not found — remote origin not added to CORS" >&2
    fi
    export CORS_ORIGINS="${CORS_ORIGINS:-$ORIGINS}"
    echo "Starting in remote mode (backend :$BACKEND_PORT + frontend :$FRONTEND_PORT, host 0.0.0.0)..."
    run_dev_pair "--host 0.0.0.0" "--host 0.0.0.0"
    ;;
  prod)
    echo "Building frontend..."
    (cd frontend && npm run build)
    echo "Starting server on port $BACKEND_PORT..."
    .venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port "$BACKEND_PORT"
    ;;
  *)
    echo "Usage: ./start.sh [dev|remote|prod] [backend-port]"
    echo ""
    echo "  dev    - Run backend + frontend dev servers (default)"
    echo "  remote - Dev servers on 0.0.0.0 with Tailscale CORS (phone access)"
    echo "  prod   - Build frontend, serve everything from backend"
    echo ""
    echo "Ports (BACKEND_PORT/FRONTEND_PORT env override): dev 8000/5173,"
    echo "  remote 8001/5174, prod 8080"
    exit 1
    ;;
esac
