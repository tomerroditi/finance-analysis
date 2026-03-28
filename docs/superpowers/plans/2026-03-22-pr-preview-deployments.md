# PR Preview Deployments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-deploy every PR to a unique Vercel preview URL with demo data so multiple PRs can be inspected in parallel.

**Architecture:** Vercel serves the Vite frontend as static files and routes `/api/*` to a Python serverless function that wraps FastAPI via Mangum. Demo DB is copied to `/tmp` on cold start with demo mode forced. Routes that depend on unavailable packages (Playwright, keyring) are conditionally registered.

**Tech Stack:** Vercel, Mangum, FastAPI, GitHub Actions

**Spec:** `docs/superpowers/specs/2026-03-22-pr-preview-deployments-design.md`

---

## File Map

| Action | File | Purpose |
|--------|------|---------|
| Create | `api/index.py` | Mangum serverless adapter — seeds demo DB, forces demo mode, wraps FastAPI |
| Create | `api/requirements.txt` | Slim Python deps for serverless (no Playwright/keyring/uvicorn) |
| Create | `vercel.json` | Vercel routing + build config |
| Create | `.github/workflows/pr-preview.yml` | GitHub Actions workflow for auto-deploy |
| Modify | `backend/main.py` | Gate `scraping`, `credentials`, `testing` route registration behind try/except ImportError |

---

### Task 1: Gate Optional Route Registration in `backend/main.py`

Routes that import `keyring` (credentials, testing) or chain through scraper deps (scraping) must be conditionally registered so the app starts cleanly when those packages are absent.

**Files:**
- Modify: `backend/main.py:25-38` (imports) and `backend/main.py:167-176` (router registration)

- [ ] **Step 1: Modify route imports and registration**

In `backend/main.py`, change the imports of `credentials`, `scraping`, and `testing` from top-level to conditional registration. The other 10 route imports stay unchanged.

Replace the current import block:
```python
from backend.routes import (
    analytics,
    bank_balances,
    budget,
    cash_balances,
    credentials,
    insurance_accounts,
    investments,
    pending_refunds,
    scraping,
    tagging,
    tagging_rules,
    testing,
    transactions,
)
```

With:
```python
from backend.routes import (
    analytics,
    bank_balances,
    budget,
    cash_balances,
    insurance_accounts,
    investments,
    pending_refunds,
    tagging,
    tagging_rules,
    transactions,
)
```

Then replace the three `include_router` calls for `credentials`, `scraping`, and `testing` with conditional blocks:

```python
# Optional routes — gated for serverless where keyring/playwright are absent
try:
    from backend.routes import credentials
    app.include_router(credentials.router, prefix="/api/credentials", tags=["Credentials"])
except ImportError:
    pass

try:
    from backend.routes import scraping
    app.include_router(scraping.router, prefix="/api/scraping", tags=["Scraping"])
except ImportError:
    pass

try:
    from backend.routes import testing
    app.include_router(testing.router, prefix="/api/testing", tags=["Testing"])
except ImportError:
    pass
```

Place these after the existing unconditional `include_router` calls.

- [ ] **Step 2: Verify existing tests still pass**

Run: `poetry run pytest tests/backend/ -x -q`
Expected: All tests pass (the gating only activates when packages are missing — locally everything is installed).

- [ ] **Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat: gate optional routes for serverless compatibility

Conditionally register scraping, credentials, and testing routes
behind try/except ImportError so the app starts cleanly when
Playwright or keyring packages are absent (e.g. Vercel serverless)."
```

---

### Task 2: Create Vercel Serverless Adapter

**Files:**
- Create: `api/index.py`

- [ ] **Step 1: Create `api/index.py`**

```python
"""Vercel serverless adapter for Finance Analysis API.

Wraps the FastAPI application via Mangum for AWS Lambda-compatible
serverless execution. Seeds the demo database into /tmp on cold start
and forces demo mode so preview deployments use sample data.
"""

import os
import shutil

# CRITICAL: Set env vars BEFORE any backend imports.
# AppConfig._base_user_dir is evaluated at class-definition time from FAD_USER_DIR.
# CORS_ORIGINS is read at middleware init time during `from backend.main import app`.
os.environ["FAD_USER_DIR"] = "/tmp/finance-analysis"
os.environ["CORS_ORIGINS"] = "*"

# Seed demo DB into /tmp before app startup
_demo_src = os.path.join(os.path.dirname(__file__), "..", "backend", "resources", "demo_data.db")
_demo_dst = "/tmp/finance-analysis/demo_env/demo_data.db"
if not os.path.exists(_demo_dst):
    os.makedirs(os.path.dirname(_demo_dst), exist_ok=True)
    shutil.copy2(_demo_src, _demo_dst)

from mangum import Mangum  # noqa: E402
from backend.config import AppConfig  # noqa: E402
from backend.main import app  # noqa: E402

config = AppConfig()
config.set_demo_mode(True)

# lifespan="off" is required: the lifespan handler in main.py imports
# CredentialsRepository which depends on keyring (not available in serverless).
handler = Mangum(app, lifespan="off")
```

- [ ] **Step 2: Commit**

```bash
git add api/index.py
git commit -m "feat: add Vercel serverless adapter for FastAPI

Mangum wrapper that seeds demo DB to /tmp on cold start and forces
demo mode for PR preview deployments."
```

---

### Task 3: Create Vercel Requirements File

**Files:**
- Create: `api/requirements.txt`

- [ ] **Step 1: Create `api/requirements.txt`**

```
fastapi>=0.109.0
SQLAlchemy==2.0.29
pandas==2.2.3
numpy==1.26.4
PyYAML==6.0.1
python-dotenv>=1.0.0
mangum>=0.18.0
pydantic>=2.0.0
pyarrow>=15.0.0
```

Note: `pyarrow` is needed by pandas for some operations. Excluded packages: `uvicorn` (Mangum replaces it), `alembic` (pre-built demo DB), `playwright`, `httpx`, `keyring` (gated routes).

- [ ] **Step 2: Commit**

```bash
git add api/requirements.txt
git commit -m "feat: add slim requirements for Vercel serverless function

Excludes Playwright, keyring, uvicorn, and alembic to stay under
Vercel's 250MB function size limit."
```

---

### Task 4: Create Vercel Project Configuration

**Files:**
- Create: `vercel.json`

- [ ] **Step 1: Create `vercel.json`**

```json
{
  "buildCommand": "cd frontend && npm ci && npm run build",
  "outputDirectory": "frontend/dist",
  "rewrites": [
    { "source": "/api/(.*)", "destination": "/api/index.py" }
  ],
  "functions": {
    "api/index.py": {
      "runtime": "@vercel/python@4.0",
      "maxDuration": 30
    }
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add vercel.json
git commit -m "feat: add Vercel project configuration

Routes /api/* to Python serverless function, serves frontend
static build for everything else with SPA fallback."
```

---

### Task 5: Local Verification with Vercel CLI

This task requires user interaction — it validates the setup before adding CI.

- [ ] **Step 1: Install Vercel CLI**

Run: `npm install -g vercel`

- [ ] **Step 2: Link project to Vercel**

Run: `vercel link`

Follow prompts to create or select a Vercel project. This creates `.vercel/` (already in `.gitignore` by default).

- [ ] **Step 3: Test locally with `vercel dev`**

Run: `vercel dev`

Verify:
- Frontend loads at the URL shown in terminal
- Navigate to the app — it should show the dashboard with demo data
- Open browser devtools Network tab, confirm `/api/analytics/overview` returns 200 with demo data
- If import errors appear in terminal, check which package is missing from `api/requirements.txt`

- [ ] **Step 4: Deploy a test preview**

Run: `vercel deploy`

This creates a one-off preview deployment. Verify:
- The returned `*.vercel.app` URL loads the frontend
- API calls work (check Network tab for `/api/*` requests)
- Demo data is visible in the dashboard

- [ ] **Step 5: Debug and fix**

If the function exceeds 250MB:
- Check `vercel inspect <deployment-url>` for function size
- Remove `pyarrow` from requirements if possible
- If still over, switch to Docker runtime in `vercel.json`:
  ```json
  "functions": {
    "api/index.py": {
      "runtime": "@vercel/python@4.0",
      "maxDuration": 30,
      "memory": 1024
    }
  }
  ```
  Or as a last resort, use a `Dockerfile` for the function (removes the 250MB limit).

If CORS errors appear:
- Verify `CORS_ORIGINS=*` is set in `api/index.py` before the app import
- Check browser console for the exact error

- [ ] **Step 6: Commit any fixes**

```bash
git add -A
git commit -m "fix: adjustments from Vercel deployment testing"
```

---

### Task 6: Add GitHub Actions Workflow

Only proceed after Task 5 succeeds (manual deploy works).

**Files:**
- Create: `.github/workflows/pr-preview.yml`

- [ ] **Step 1: Create the workflow file**

```yaml
name: PR Preview

on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  pull-requests: write

jobs:
  deploy-preview:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
          cache-dependency-path: frontend/package-lock.json

      - name: Install Vercel CLI
        run: npm install -g vercel

      - name: Pull Vercel Environment
        run: vercel pull --yes --environment=preview --token=${{ secrets.VERCEL_TOKEN }}
        env:
          VERCEL_ORG_ID: ${{ secrets.VERCEL_ORG_ID }}
          VERCEL_PROJECT_ID: ${{ secrets.VERCEL_PROJECT_ID }}

      - name: Build
        run: vercel build --token=${{ secrets.VERCEL_TOKEN }}
        env:
          VERCEL_ORG_ID: ${{ secrets.VERCEL_ORG_ID }}
          VERCEL_PROJECT_ID: ${{ secrets.VERCEL_PROJECT_ID }}

      - name: Deploy Preview
        id: deploy
        run: |
          url=$(vercel deploy --prebuilt --token=${{ secrets.VERCEL_TOKEN }})
          echo "url=$url" >> "$GITHUB_OUTPUT"
        env:
          VERCEL_ORG_ID: ${{ secrets.VERCEL_ORG_ID }}
          VERCEL_PROJECT_ID: ${{ secrets.VERCEL_PROJECT_ID }}

      - name: Comment PR
        uses: marocchino/sticky-pull-request-comment@v2
        with:
          header: preview
          message: |
            **Preview Deployment** | [Open Preview](${{ steps.deploy.outputs.url }})
            Commit: `${{ github.event.pull_request.head.sha }}`
            > Demo data only. DB resets on cold start.
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/pr-preview.yml
git commit -m "feat: add GitHub Actions workflow for PR preview deployments

Auto-deploys every PR to Vercel and posts a sticky comment with
the preview URL."
```

---

### Task 7: Configure GitHub Secrets and Validate

- [ ] **Step 1: Add GitHub secrets**

In the GitHub repo settings → Secrets and variables → Actions, add:
- `VERCEL_TOKEN` — from https://vercel.com/account/tokens
- `VERCEL_ORG_ID` — from `.vercel/project.json` after `vercel link`
- `VERCEL_PROJECT_ID` — from `.vercel/project.json` after `vercel link`

- [ ] **Step 2: Disable Vercel's GitHub integration**

In Vercel project settings → Git, disconnect or disable automatic deployments to avoid duplicate deploys (we deploy via CLI in the workflow).

- [ ] **Step 3: Open a test PR**

Push the branch and open a PR. Verify:
- The workflow runs successfully
- A comment appears on the PR with a working preview link
- The preview URL loads the app with demo data

- [ ] **Step 4: Merge to main**

Once validated, merge the PR. All future PRs will automatically get preview deployments.
