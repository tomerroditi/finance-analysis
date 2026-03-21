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
