# PR Preview Deployments

Auto-deploy every pull request to a unique Vercel preview URL so multiple PRs can be inspected in parallel using demo data.

## Architecture

```
GitHub PR opened/updated
  -> GitHub Actions workflow
    -> Build frontend (Vite)
    -> Deploy to Vercel (preview)
      -> Static frontend served from dist/
      -> /api/* routed to Python serverless function
        -> Mangum adapter wraps FastAPI app
        -> Demo DB copied to /tmp on cold start
        -> Demo mode auto-enabled (no toggle needed)
```

Each PR gets a unique `*.vercel.app` URL. Vercel manages the lifecycle — previews are created on deploy and cleaned up automatically.

## File Changes

### New Files

#### `vercel.json`

Vercel project configuration. Routes `/api/*` to the serverless function, serves frontend static build for everything else.

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

Vercel automatically serves static files from `outputDirectory` and falls back to `index.html` for SPA routing. The `rewrites` rule sends `/api/*` to the serverless function.

#### `api/index.py`

Mangum adapter that runs FastAPI as a Vercel serverless function. On cold start, copies the pre-built demo DB to `/tmp` and forces demo mode.

```python
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

from mangum import Mangum
from backend.config import AppConfig
from backend.main import app

config = AppConfig()
config.set_demo_mode(True)

handler = Mangum(app, lifespan="off")
```

Key decisions:
- **Import order is critical:** `FAD_USER_DIR` and `CORS_ORIGINS` must be set before any backend import, because `AppConfig._base_user_dir` is a class variable evaluated at import time, and CORS middleware reads `CORS_ORIGINS` during `app` construction
- `CORS_ORIGINS=*` allows all preview URLs without per-PR configuration
- Demo DB is copied before `app` import so the DB file exists when any import side-effect tries to access it
- `lifespan="off"` skips FastAPI startup migrations since the demo DB is pre-built with all data

#### `api/requirements.txt`

Slim dependency list excluding scraper packages (Playwright, httpx) to stay under Vercel's 250MB function size limit.

```
fastapi>=0.109.0
SQLAlchemy==2.0.29
pandas==2.2.3
numpy==1.26.4
PyYAML==6.0.1
python-dotenv>=1.0.0
mangum>=0.18.0
pydantic>=2.0.0
```

Excluded from serverless: `uvicorn` (Mangum replaces it), `alembic` (pre-built demo DB), `playwright`, `httpx`, `keyring` (scraping/credentials routes gated).

#### `.github/workflows/pr-preview.yml`

GitHub Actions workflow that deploys a Vercel preview on every PR.

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

### Existing File Changes

#### `backend/main.py`

No changes needed. The static file serving and SPA fallback already exist but are bypassed in Vercel (routing handled by `vercel.json`). The lifespan is skipped via Mangum's `lifespan="off"`.

#### `backend/config.py`

No changes needed. `FAD_USER_DIR` env var override already supported.

#### Conditional Route Registration in `backend/main.py`

Three routes import `keyring` through their dependency chains (`CredentialsRepository` → `import keyring`): `credentials`, `scraping`, and `testing`. These must be conditionally registered:

```python
# In backend/main.py — replace unconditional imports with:
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

This ensures the app starts cleanly when `keyring` is absent. All other routes (transactions, analytics, budget, etc.) use only standard library + pandas/SQLAlchemy and will work fine.

**Scope of change:** Only the `scraping`, `credentials`, and `testing` routers are gated. The remaining 9 routers are imported and registered unconditionally as before.

## Testing Strategy

Iterate locally before touching CI:

1. **`vercel link`** — connect repo to a Vercel project (one-time)
2. **`vercel dev`** — run the serverless function locally, verify API + demo DB + frontend
3. **`vercel deploy`** — deploy a one-off preview from your machine, get a real `*.vercel.app` URL to verify end-to-end
4. **Fix any issues** (import errors, size limits, routing) and repeat steps 2-3
5. **Add the GitHub Actions workflow** only after manual deploy works
6. **Open one test PR** to confirm the automation posts a comment with a working link

This avoids merge-to-main iteration entirely. Steps 1-4 are the implementation phase; steps 5-6 are the final validation.

## Setup (One-Time)

1. Create a Vercel project linked to the GitHub repo
2. Add GitHub secrets: `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`
3. Disable Vercel's automatic GitHub integration (we deploy via CLI in the workflow to avoid duplicate deployments)

## Limitations

- **Ephemeral storage:** Demo DB in `/tmp` resets on cold start. Any changes made during inspection are lost. This is intentional for PR previews.
- **Cold start latency:** First API request after idle period takes 1-2 seconds.
- **No scraping:** Scraper endpoints will fail gracefully (import errors or dummy responses). Not needed for UI inspection.
- **Function size limit:** If pandas+numpy exceed 250MB, fallback is to use a Docker-based Vercel function (increases cold start but removes size limit).
- **Single concurrent writer:** SQLite in `/tmp` is fine for single-user demo inspection but not for concurrent users hitting the same function instance.

## Success Criteria

- Every PR automatically gets a comment with a working preview URL
- Preview shows the full app UI with demo data loaded
- Multiple PRs can be inspected simultaneously (each has its own Vercel deployment)
- No impact on existing development workflow or CI pipeline
