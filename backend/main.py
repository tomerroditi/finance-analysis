"""
FastAPI main application entry point.

Builds the app and wires together its middleware, routers, exception
handlers and the production frontend. ``backend.main:app`` is what uvicorn,
``index.py`` (Vercel) and ``build/app_entry.py`` (desktop bundle) serve.
"""

import logging
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from backend.exception_handlers import register_exception_handlers
from backend.router_registry import register_routers
from backend.runtime import is_vercel
from backend.spa import mount_frontend
from backend.startup import run_shutdown_tasks, run_startup_tasks
from backend.utils.json_response import SafeJSONResponse
from backend.utils.version import get_app_version

load_dotenv()

# Imported after ``load_dotenv`` on purpose: the security middlewares read
# CORS_ORIGINS, ALLOWED_HOSTS, TAILNET_ALLOWED_USERS and MAX_REQUEST_BYTES
# when their module is imported.
from backend.middleware import register_middleware  # noqa: E402

# Without a logging config, app loggers fall through to Python's last-resort
# WARNING handler and every logger.info is silently dropped. The packaged
# binary configures its own rotating file handler (build/app_entry.py), so
# only configure when not frozen.
if not getattr(sys, "frozen", False):
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

# One "setup plugin ..." line per autogenerate plugin on every startup, and
# the startup path never autogenerates.
logging.getLogger("alembic.runtime.plugins").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run startup migrations and seeding, then shut the scraper loop down on exit.

    Parameters
    ----------
    app : FastAPI
        The application being served.

    Yields
    ------
    None
        Control while the application serves requests.
    """
    # Skip startup migrations and scraper wiring in serverless (demo DB is
    # pre-built, and there's no keyring/browser to scrape with). This guard
    # MUST come before anything that transitively pulls in keyring-backed
    # code: `keyring` is intentionally absent from the Vercel requirements.txt,
    # so importing scraping_service here would crash cold start with
    # ModuleNotFoundError → FUNCTION_INVOCATION_FAILED. backend.startup keeps
    # those imports inside its functions for the same reason.
    if is_vercel():
        yield
        return

    run_startup_tasks()
    yield
    await run_shutdown_tasks()


# Only expose OpenAPI/Swagger docs outside of production. ``ENVIRONMENT=production``
# (or ``DISABLE_DOCS=1``) disables ``/docs``, ``/redoc`` and ``/openapi.json``
# so attackers cannot enumerate the API surface from a public deployment.
_environment = os.getenv("ENVIRONMENT", "development").lower()
_docs_disabled = _environment == "production" or os.getenv("DISABLE_DOCS") == "1"

app = FastAPI(
    title="Finance Analysis API",
    description="API for personal finance tracking and analysis",
    version=get_app_version(),
    lifespan=lifespan,
    # Payloads here are largely DataFrame-derived, and pandas renders SQL
    # NULL as NaN. Starlette's default JSONResponse dumps with
    # allow_nan=False, so one NaN 500s the whole endpoint. Render those as
    # null instead — see backend/utils/json_response.py.
    default_response_class=SafeJSONResponse,
    docs_url=None if _docs_disabled else "/docs",
    redoc_url=None if _docs_disabled else "/redoc",
    openapi_url=None if _docs_disabled else "/openapi.json",
    # Disable trailing-slash redirects. FastAPI's default 307 redirect uses an
    # absolute Location header pointing at the backend host, which breaks the
    # Vite dev proxy (the browser follows the absolute URL and trips CSP) and
    # forces clients to handle redirects. With this off, frontend callers must
    # match the route's exact slash form — see ``frontend/src/services/api.ts``.
    redirect_slashes=False,
)

register_middleware(app)

# Testing routes expose demo-mode toggling and DB reset helpers. They must
# never be reachable in production: ``ENABLE_TESTING_ROUTES=1`` or a non-
# production ``ENVIRONMENT`` is required to mount them.
register_routers(
    app,
    include_testing=(
        os.getenv("ENABLE_TESTING_ROUTES") == "1" or _environment != "production"
    ),
)

register_exception_handlers(app)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Report that the API process is up."""
    return {"status": "healthy"}


mount_frontend(app)
