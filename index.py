"""Vercel serverless entry point for Finance Analysis API.

Vercel natively supports FastAPI — it auto-detects the `app` variable.
No Mangum adapter needed. On cold start we seed the demo database into /tmp,
shift its dates so the data tracks today, and pin demo mode process-wide so
preview deployments are stocked with sample data.
"""

import os

# CRITICAL: Set env vars BEFORE any backend imports.
# AppConfig._base_user_dir is evaluated at class-definition time from FAD_USER_DIR.
# CORS_ORIGINS is read at middleware init time during `from backend.main import app`.
os.environ["FAD_USER_DIR"] = "/tmp/finance-analysis"
# Default to the deployed Vercel URL when available. We deliberately avoid a
# wildcard fallback so a misconfigured deployment fails closed (browsers will
# simply refuse cross-origin requests) rather than silently accepting every
# origin. Override ``CORS_ORIGINS`` in Vercel project settings to pin a
# specific domain.
_vercel_url = os.environ.get("VERCEL_URL")
if _vercel_url and "CORS_ORIGINS" not in os.environ:
    os.environ["CORS_ORIGINS"] = f"https://{_vercel_url}"
else:
    os.environ.setdefault(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
os.environ.setdefault("VERCEL", "1")
# Fail closed: without this, ENVIRONMENT defaults to "development" and the
# public deployment would expose /docs and /openapi.json. The testing router
# (demo-mode status/prepare/reset) must stay mounted — the demo UI uses it —
# so it is explicitly re-enabled; the prepare and reset routes no-op under
# the forced-mode pin.
os.environ.setdefault("ENVIRONMENT", "production")
os.environ.setdefault("ENABLE_TESTING_ROUTES", "1")
# Per-visitor demo sandboxes: each browser gets its own copy of the demo DB
# (keyed by X-FAD-Demo-Session) that is mirrored to Vercel Blob after every
# write when BLOB_READ_WRITE_TOKEN is configured. See backend/demo_sessions.py.
os.environ.setdefault("FAD_DEMO_SESSIONS", "1")

from backend.config import AppConfig  # noqa: E402
from backend.demo_setup import prepare_demo_database  # noqa: E402

config = AppConfig()
# Pin demo mode for the whole process. A contextvar set here would not reach
# the threads that serve requests, and this deployment is a single shared
# demo instance where no client may opt out — so the pin is the correct
# expression of the requirement, and it makes the demo routes no-op cleanly.
AppConfig._forced_mode = True
os.makedirs(config.get_user_dir(), exist_ok=True)

# Copy the frozen demo DB into /tmp, sync any missing schema, and shift every
# date column to be relative to today. Without this step the demo data stays
# anchored to DEMO_REFERENCE_DATE (Feb 2026) — current-month features like
# budget alerts then have nothing to fire against.
prepare_demo_database()

# Backfill hishtalmut investments. The frozen demo DB was built before the
# auto-sync from insurance accounts existed, so its three hishtalmut policies
# have no linked Investment records. Idempotent (matches by policy_id).
from backend.database import get_db_context  # noqa: E402
from backend.services.investments_service import InvestmentsService  # noqa: E402

with get_db_context() as _db:
    InvestmentsService(_db).backfill_from_insurance_accounts()

# Materialize the savings-goal allocation ledger once, here, so every
# sandbox cloned below already carries it. Otherwise each new visitor's
# first budget load (a dozen parallel month requests) would rebuild it
# concurrently on a fresh file. Best-effort: a failure here must never
# take the whole function down.
from backend.services.savings_goal_service import SavingsGoalService  # noqa: E402

try:
    with get_db_context() as _db:
        SavingsGoalService(_db).ensure_allocations()
except Exception:  # pragma: no cover - defensive at cold start
    import logging

    logging.getLogger(__name__).exception("Could not pre-compute demo allocations")

# Freeze the prepared shared DB as the template every visitor sandbox is
# cloned from. Must happen before the first request: the shared copy is
# still writable by header-less clients (curl), the template is not.
from backend.demo_sessions import snapshot_template  # noqa: E402

snapshot_template()

# Vercel auto-detects this `app` variable as the FastAPI application.
# lifespan is skipped (VERCEL env var guard) because it imports keyring.
from backend.main import app  # noqa: E402

__all__ = ["app"]
