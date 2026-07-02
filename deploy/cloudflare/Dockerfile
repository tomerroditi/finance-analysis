# Backend image for the Cloudflare Containers demo deployment.
#
# Built by `wrangler deploy` / `wrangler dev` with the repo root as build
# context (see `image_build_context` in wrangler.jsonc). Runs the FastAPI app
# in demo mode via demo_app.py — the frontend is NOT served from here; it is
# uploaded as Workers static assets.

FROM python:3.12-slim

WORKDIR /app

# Demo-deployment dependency set: exactly what the backend imports at runtime
# when the keyring-backed credentials and Playwright scraping routes are
# absent (both are optional imports in backend/main.py and stay disabled
# because their dependencies are not installed). Versions track the pins in
# pyproject.toml.
RUN pip install --no-cache-dir \
    "fastapi>=0.109.0" \
    "uvicorn[standard]>=0.27.0" \
    "SQLAlchemy==2.0.29" \
    "pandas==2.2.3" \
    "numpy==1.26.4" \
    "PyYAML==6.0.1" \
    "python-dotenv>=1.0.0" \
    "pydantic>=2.0.0" \
    "httpx>=0.28.0"

COPY backend/ backend/
COPY demo_app.py ./

ENV FAD_USER_DIR=/tmp/finance-analysis

EXPOSE 8000

CMD ["uvicorn", "demo_app:app", "--host", "0.0.0.0", "--port", "8000"]
