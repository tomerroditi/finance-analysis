"""Vercel serverless entry point for Finance Analysis API.

Vercel natively supports FastAPI — it auto-detects the `app` variable.
No Mangum adapter needed. On cold start we seed the demo database into /tmp,
shift its dates so the data tracks today, and force demo mode so preview
deployments are stocked with sample data.
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

# Vercel auto-detects this `app` variable as the FastAPI application.
# lifespan is skipped (VERCEL env var guard) because it imports keyring.
from backend.main import app  # noqa: E402

__all__ = ["app"]
