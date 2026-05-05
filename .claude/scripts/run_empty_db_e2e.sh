#!/usr/bin/env bash
#
# Run the empty-database e2e smoke spec.
#
# Boots the backend against a fresh, throw-away FAD_USER_DIR so the SQLite
# database starts empty, boots the frontend dev server, and runs the
# `e2e/empty-state.spec.ts` suite in opt-in mode (E2E_EMPTY_DB=1). The
# tmpdir is removed when the script exits regardless of outcome.
#
# This is the regression gate for "every page renders without crashing
# on a fresh install". See .claude/rules/testing.md and
# frontend/e2e/empty-state.spec.ts.
#
# Usage:
#     bash .claude/scripts/run_empty_db_e2e.sh

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$repo_root"

tmp_user_dir="$(mktemp -d -t finance-analysis-empty-XXXXXX)"
trap 'rm -rf "$tmp_user_dir"' EXIT

echo "Empty-DB e2e: using FAD_USER_DIR=$tmp_user_dir"

export FAD_USER_DIR="$tmp_user_dir"
export E2E_EMPTY_DB=1

exec python .claude/scripts/with_server.py -- \
    bash -c 'cd frontend && npx playwright test e2e/empty-state.spec.ts'
