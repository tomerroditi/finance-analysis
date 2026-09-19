#!/usr/bin/env bash
#
# Single entry point for running the app locally.
#
#   ./start.sh              # dev: backend (hot-reload) + frontend dev server
#   ./start.sh prod         # prod: build frontend, serve everything from backend,
#                           # share it on the tailnet via `tailscale serve`, and
#                           # auto-pull + redeploy whenever the branch moves
#   ./start.sh prod 9000    # positional port still accepted (sets BACKEND_PORT)
#
# Ports are env-driven (BACKEND_PORT / FRONTEND_PORT), with non-clashing
# per-mode defaults so both modes can run side by side:
#
#   mode     backend  frontend
#   dev      8000     5173
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
  prod) DEFAULT_BACKEND_PORT=8080 DEFAULT_FRONTEND_PORT=5173 ;;
  *)    DEFAULT_BACKEND_PORT=8000 DEFAULT_FRONTEND_PORT=5173 ;;
esac
BACKEND_PORT="${2:-${BACKEND_PORT:-$DEFAULT_BACKEND_PORT}}"
FRONTEND_PORT="${FRONTEND_PORT:-$DEFAULT_FRONTEND_PORT}"

./.claude/scripts/bootstrap_venv.sh

# Windows venvs put executables in Scripts/ instead of bin/.
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) VENV_BIN=".venv/Scripts" ;;
  *)                    VENV_BIN=".venv/bin" ;;
esac

# Run both dev servers.
run_dev_pair() {
  "$VENV_BIN/uvicorn" backend.main:app --reload \
    --reload-dir backend --reload-dir scraper --port "$BACKEND_PORT" &
  BACKEND_PID=$!
  trap 'kill $BACKEND_PID 2>/dev/null; exit' INT TERM
  cd frontend && PORT="$FRONTEND_PORT" BACKEND_PORT="$BACKEND_PORT" npm run dev
}

case "$MODE" in
  dev)
    echo "Starting in dev mode (backend :$BACKEND_PORT + frontend :$FRONTEND_PORT)..."
    run_dev_pair
    ;;
  prod)
    # Localhost-only by default. Exposing beyond this machine requires an
    # explicit BIND_HOST override, which turns on bearer-token auth for
    # remote clients and a Host-header allowlist (DNS-rebinding guard).
    BIND_HOST="${BIND_HOST:-127.0.0.1}"
    export ENVIRONMENT="${ENVIRONMENT:-production}"
    # The Demo Mode toggle lives in the testing router; keep it mounted.
    export ENABLE_TESTING_ROUTES="${ENABLE_TESTING_ROUTES:-1}"
    if [ "$BIND_HOST" != "127.0.0.1" ] && [ "$BIND_HOST" != "localhost" ]; then
      TOKEN="$("$VENV_BIN/python" -c 'from backend.utils.auth import get_or_create_api_token; print(get_or_create_api_token())')"
      if [ -z "${ALLOWED_HOSTS:-}" ]; then
        # Best-effort: allow this machine's own addresses in the Host check.
        HOST_IPS="$( { hostname -I 2>/dev/null || ipconfig getifaddr en0 2>/dev/null; } | tr ' ' '\n' | grep -v '^$' | paste -sd, - )"
        export ALLOWED_HOSTS="localhost,127.0.0.1${HOST_IPS:+,$HOST_IPS}"
      fi
      echo "Exposed on $BIND_HOST — remote devices need the API token."
      echo "Open:  http://<this-machine-ip>:$BACKEND_PORT/?apiToken=$TOKEN"
      echo "Allowed hosts: $ALLOWED_HOSTS (override with ALLOWED_HOSTS env)"
    fi
    # Serve, share on the tailnet, and follow the branch (auto-pull +
    # redeploy on every new commit) — see .claude/scripts/prod_server.py.
    exec "$VENV_BIN/python" .claude/scripts/prod_server.py --host "$BIND_HOST" --port "$BACKEND_PORT"
    ;;
  *)
    echo "Usage: ./start.sh [dev|prod] [backend-port]"
    echo ""
    echo "  dev  - Run backend + frontend dev servers (default)"
    echo "  prod - Build frontend and serve everything from backend; shares it on"
    echo "         the tailnet via 'tailscale serve' and auto-pulls + redeploys"
    echo "         new commits (PROD_AUTO_PULL=0 / PROD_POLL_SECONDS to tune)"
    echo ""
    echo "Ports (BACKEND_PORT/FRONTEND_PORT env override): dev 8000/5173, prod 8080"
    exit 1
    ;;
esac
