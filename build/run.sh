#!/bin/bash

echo "=================================================="
echo "     Finance Analysis App - Launcher"
echo "=================================================="

cd "$(dirname "$0")/.."

# Activate environment
source .venv/bin/activate

# Launch FastAPI server (serves both API and frontend)
open http://localhost:8765
uvicorn backend.main:app --host 127.0.0.1 --port 8765
