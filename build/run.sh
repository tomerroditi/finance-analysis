#!/bin/bash

echo "=================================================="
echo "     Finance Analysis App - Launcher"
echo "=================================================="

cd "$(dirname "$0")/.."

source .venv/bin/activate

PORT=$(python3 build/find_port.py)

echo "Starting on http://localhost:$PORT"
(sleep 2 && open "http://localhost:$PORT") &
uvicorn backend.main:app --host 127.0.0.1 --port "$PORT"
