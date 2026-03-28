#!/usr/bin/env bash
# Start the app with remote access via Tailscale.
# Detects your Tailscale IP and configures CORS + host binding automatically.
# Usage: ./start-remote.sh

set -e

TAILSCALE_IP=$(tailscale ip -4 2>/dev/null || true)

if [ -z "$TAILSCALE_IP" ]; then
  echo "Error: Could not detect Tailscale IP. Is Tailscale running?"
  exit 1
fi

echo "Tailscale IP: $TAILSCALE_IP"
echo "Access the app at: http://$TAILSCALE_IP:5173"
echo ""

export CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5173,http://$TAILSCALE_IP:5173"

# Start backend
source .venv/bin/activate
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Start frontend
cd frontend
npm run dev -- --host 0.0.0.0 &
FRONTEND_PID=$!
cd ..

# Cleanup on exit
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT

echo ""
echo "Both servers running. Press Ctrl+C to stop."
wait
