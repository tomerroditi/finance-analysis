#!/usr/bin/env bash
#
# Single entry point for running the app locally.
#
#   ./start.sh              # dev: backend (hot-reload) + frontend dev server
#   ./start.sh prod         # prod: build frontend, serve everything from backend
#   ./start.sh prod 9000    # positional port still accepted (sets BACKEND_PORT)
#
# Ports are env-driven, with mode-dependent defaults:
#   BACKEND_PORT            # uvicorn port (also wired into the Vite /api proxy)
#                           #   dev default: 8000, prod default: 8080 — so a
#                           #   prod build can run beside a dev backend
#   FRONTEND_PORT=5173      # Vite dev server port (dev mode only)
#
# (The VS Code Tailscale remote tasks use 8001/5174 for the same reason —
# see .vscode/tasks.json.)
#
# The Python venv is auto-bootstrapped on first run (~90s, idempotent) via
# .claude/scripts/bootstrap_venv.sh — no manual setup step needed.

set -euo pipefail

cd "$(dirname "$0")"

MODE="${1:-dev}"
if [ "$MODE" = "prod" ]; then
  DEFAULT_BACKEND_PORT=8080
else
  DEFAULT_BACKEND_PORT=8000
fi
BACKEND_PORT="${2:-${BACKEND_PORT:-$DEFAULT_BACKEND_PORT}}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

./.claude/scripts/bootstrap_venv.sh

case "$MODE" in
  dev)
    echo "Starting in dev mode (backend :$BACKEND_PORT + frontend :$FRONTEND_PORT)..."
    .venv/bin/uvicorn backend.main:app --reload \
      --reload-dir backend --reload-dir scraper --port "$BACKEND_PORT" &
    BACKEND_PID=$!
    trap 'kill $BACKEND_PID 2>/dev/null; exit' INT TERM
    cd frontend && PORT="$FRONTEND_PORT" BACKEND_PORT="$BACKEND_PORT" npm run dev
    ;;
  prod)
    echo "Building frontend..."
    (cd frontend && npm run build)
    echo "Starting server on port $BACKEND_PORT..."
    .venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port "$BACKEND_PORT"
    ;;
  *)
    echo "Usage: ./start.sh [dev|prod] [backend-port]"
    echo ""
    echo "  dev   - Run backend + frontend dev servers (default)"
    echo "  prod  - Build frontend, serve everything from backend"
    echo ""
    echo "Ports: BACKEND_PORT (dev default 8000, prod default 8080),"
    echo "       FRONTEND_PORT (default 5173)"
    exit 1
    ;;
esac
