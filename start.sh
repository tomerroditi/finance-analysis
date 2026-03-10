#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"
source .venv/bin/activate

MODE="${1:-dev}"
PORT="${2:-8000}"

case "$MODE" in
  dev)
    echo "Starting in dev mode (backend :$PORT + frontend :5173)..."
    # Start backend in background
    uvicorn backend.main:app --reload --port "$PORT" &
    BACKEND_PID=$!
    # Start frontend
    trap "kill $BACKEND_PID 2>/dev/null; exit" INT TERM
    cd frontend && npm run dev
    ;;
  prod)
    echo "Building frontend..."
    cd frontend && npm run build && cd ..
    echo "Starting server on port $PORT..."
    uvicorn backend.main:app --host 0.0.0.0 --port "$PORT"
    ;;
  *)
    echo "Usage: ./start.sh [dev|prod] [port]"
    echo ""
    echo "  dev   - Run backend + frontend dev servers (default)"
    echo "  prod  - Build frontend, serve everything from backend"
    exit 1
    ;;
esac
