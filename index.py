"""Vercel serverless entry point for Finance Analysis API.

Vercel natively supports FastAPI — it auto-detects the `app` variable.
No Mangum adapter needed. Seeds the demo database into /tmp on cold start
and forces demo mode so preview deployments use sample data.
"""

import os
import shutil

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

# Seed demo DB into /tmp before app startup
_demo_src = os.path.join(os.path.dirname(__file__), "backend", "resources", "demo_data.db")
_demo_dst = "/tmp/finance-analysis/demo_env/demo_data.db"
if not os.path.exists(_demo_dst):
    os.makedirs(os.path.dirname(_demo_dst), exist_ok=True)
    shutil.copy2(_demo_src, _demo_dst)

from backend.config import AppConfig  # noqa: E402

config = AppConfig()
config.set_demo_mode(True)

# Create any missing tables in the demo DB (e.g. insurance_transactions
# added after the demo DB was built). Safe — only creates missing tables.
from backend.database import get_engine  # noqa: E402
from backend.models import Base  # noqa: E402
Base.metadata.create_all(bind=get_engine())

# Vercel auto-detects this `app` variable as the FastAPI application.
# lifespan is skipped (VERCEL env var guard) because it imports keyring.
from backend.main import app  # noqa: E402

__all__ = ["app"]
