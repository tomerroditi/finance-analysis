#!/usr/bin/env bash
set -euo pipefail

echo "==> Installing Poetry"
pip install --user poetry

echo "==> Installing Python dependencies"
poetry config virtualenvs.in-project true
poetry install --no-root

echo "==> Installing frontend dependencies"
cd frontend
npm install
cd ..

echo "==> Creating user data directory"
mkdir -p "${HOME}/.finance-analysis"

echo ""
echo "Setup complete."
echo ""
echo "Start the app with:"
echo "  poetry run python .claude/scripts/with_server.py -- sleep infinity"
echo ""
echo "Or run servers separately:"
echo "  Backend:  poetry run uvicorn backend.main:app --reload --host 0.0.0.0"
echo "  Frontend: cd frontend && npm run dev -- --host 0.0.0.0"
echo ""
echo "Tip: enable Demo Mode in the UI (top-right toggle) to use the seeded demo DB."
echo ""
echo "To run the scraper in this environment, install Chromium first:"
echo "  poetry run playwright install --with-deps chromium"
