"""Demo-deployment entry point for the Finance Analysis API.

The Cloudflare Containers image (deploy/cloudflare/Dockerfile) runs this
module under uvicorn. On process start we seed the demo database into /tmp,
shift its dates so the data tracks today, and force demo mode so the public
demo is stocked with sample data.
"""

import os

# CRITICAL: Set env vars BEFORE any backend imports.
# AppConfig._base_user_dir is evaluated at class-definition time from FAD_USER_DIR.
# CORS_ORIGINS is read at middleware init time during `from backend.main import app`.
os.environ["FAD_USER_DIR"] = "/tmp/finance-analysis"
# In the deployed demo the Worker serves the frontend and the API from one
# origin, so cross-origin requests never happen and this default only matters
# when running the container locally against a Vite dev server. Override
# ``CORS_ORIGINS`` on the container if a cross-origin setup is ever needed —
# there is deliberately no wildcard fallback, so a misconfigured deployment
# fails closed (browsers refuse the cross-origin response) rather than
# silently accepting every origin.
os.environ.setdefault(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
)
# Skips the lifespan startup work in backend.main (migrations, keyring-backed
# credential migration) — the demo DB prepared below is already current.
os.environ.setdefault("FAD_DEMO_DEPLOYMENT", "1")

from backend.config import AppConfig  # noqa: E402
from backend.demo_setup import prepare_demo_database  # noqa: E402

config = AppConfig()
config.set_demo_mode(True)

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

# uvicorn is pointed at this `app` binding (see the Dockerfile CMD).
from backend.main import app  # noqa: E402

__all__ = ["app"]
