"""
FastAPI main application entry point.

This module sets up the FastAPI application with CORS, routes, and exception handlers.
"""

import asyncio
import logging
import math
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.config import AppConfig
from backend.database import get_db_context, get_engine
from backend.errors import (
    BadRequestException,
    EntityAlreadyExistsException,
    EntityNotFoundException,
    ValidationException,
)
from backend.models import Base
from backend.utils import auth
from backend.routes import (
    analytics,
    backup,
    bank_balances,
    budget,
    budget_month_overrides,
    cash_balances,
    insurance_accounts,
    investments,
    liabilities,
    onboarding,
    pending_refunds,
    rates,
    retirement,
    savings_goals,
    tagging,
    tagging_rules,
    transactions,
    updates,
    version as version_route,
)
from backend.utils.version import get_app_version

load_dotenv()

# Dev/uvicorn runs previously had no logging config at all — app loggers fell
# through to Python's last-resort WARNING handler and every logger.info was
# silently dropped. The packaged binary configures its own rotating file
# handler (build/app_entry.py), so only configure when not frozen.
if not getattr(sys, "frozen", False):
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup/shutdown events."""
    # Skip startup migrations and scraper wiring in serverless (demo DB is
    # pre-built, and there's no keyring/browser to scrape with). This guard
    # MUST come before any import that transitively pulls in keyring-backed
    # code: `keyring` is intentionally absent from the Vercel requirements.txt,
    # so importing scraping_service here would crash cold start with
    # ModuleNotFoundError → FUNCTION_INVOCATION_FAILED.
    if os.environ.get("VERCEL"):
        yield
        return

    # Capture the running event loop so synchronous scraping routes (executed
    # in a threadpool worker thread with no loop of their own) can launch
    # scraper coroutines on it via run_coroutine_threadsafe. Without this,
    # asyncio.create_task raised "no running event loop" and the scrape never
    # started. See backend.services.scraping_service._launch_adapter.
    from backend.services.scraping_service import set_main_loop

    set_main_loop(asyncio.get_running_loop())

    from backend.repositories.credentials_repository import CredentialsRepository
    from backend.repositories.tagging_repository import (
        TaggingRepository,
        DEFAULT_CATEGORIES_PATH,
        DEFAULT_CATEGORIES_ICONS_PATH,
    )

    # Startup
    logger.info("Starting Finance Analysis API...")
    Base.metadata.create_all(bind=get_engine())

    # Apply pending Alembic migrations. ``create_all`` only creates missing
    # tables — it never adds columns to existing ones — so without this every
    # schema change after the initial install silently fails to land and the
    # ORM raises "no such column" on first query. The Alembic env wires the
    # URL to ``get_database_url()`` so this runs against the same DB the app
    # uses, and every migration is idempotent (each inspects the schema before
    # altering), so it's safe on fresh installs too.
    from alembic import command
    from alembic.config import Config

    if getattr(sys, "frozen", False):
        alembic_ini = Path(getattr(sys, "_MEIPASS", "")) / "alembic.ini"
    else:
        alembic_ini = Path(__file__).resolve().parent.parent / "alembic.ini"

    if alembic_ini.is_file():
        command.upgrade(Config(str(alembic_ini)), "head")
    else:
        logger.warning(
            "alembic.ini not found at %s — skipping migrations", alembic_ini
        )

    # Seed categories and migrate credentials
    with get_db_context() as db:
        config = AppConfig()

        # Seed categories from YAML if DB table is empty
        tagging_repo = TaggingRepository(db)
        user_categories_path = config.get_categories_path()
        categories_path = (
            user_categories_path
            if os.path.exists(user_categories_path)
            else DEFAULT_CATEGORIES_PATH
        )
        tagging_repo.seed_from_yaml(categories_path, DEFAULT_CATEGORIES_ICONS_PATH)

        # Migrate credentials from YAML if DB table is empty (also removes
        # the legacy plaintext YAML), then encrypt any credential rows
        # written before at-rest field encryption existed.
        creds_repo = CredentialsRepository(db)
        creds_repo.migrate_from_yaml(config.get_credentials_path())
        creds_repo.encrypt_plaintext_rows()

    yield
    # Shutdown
    logger.info("Shutting down Finance Analysis API...")


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

# Configure CORS. A wildcard origin (``*``) may never be combined with
# ``allow_credentials=True`` — browsers reject such responses, and the
# combination would also permit any site to read authenticated responses.
_cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]
_cors_allow_credentials = "*" not in _cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_allow_credentials,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
)


# Cap request body size to mitigate memory-exhaustion DoS. 10 MB comfortably
# covers any JSON payload this app exchanges while blocking multi-GB bodies.
_MAX_REQUEST_BYTES = int(os.getenv("MAX_REQUEST_BYTES", str(10 * 1024 * 1024)))


# Methods that may carry a body. Bodiless methods skip the streaming path so
# a plain GET never waits on a request-body message.
_BODY_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@app.middleware("http")
async def limit_request_size(request: Request, call_next):
    """Reject requests whose body exceeds ``MAX_REQUEST_BYTES``.

    A declared ``Content-Length`` is checked up front. Chunked bodies carry
    no such header, so their bytes are counted while the body is consumed and
    the request is aborted the moment the cap is passed — previously they
    bypassed the check entirely and were buffered and parsed in full.
    """
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid Content-Length header"},
            )
        if declared > _MAX_REQUEST_BYTES:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body too large"},
            )
        return await call_next(request)

    if request.method not in _BODY_METHODS:
        return await call_next(request)

    chunks: list[bytes] = []
    received = 0
    async for chunk in request.stream():
        received += len(chunk)
        if received > _MAX_REQUEST_BYTES:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body too large"},
            )
        chunks.append(chunk)

    # Hand the buffered body to the rest of the stack: Starlette's
    # BaseHTTPMiddleware replays ``_body`` to the downstream app when it is
    # set, so consuming the stream here stays invisible to the endpoint.
    request._body = b"".join(chunks)
    return await call_next(request)


# Host-header allowlist — blocks DNS-rebinding attacks, where a malicious
# website re-points its own domain at 127.0.0.1 so the victim's browser can
# reach this API "same-origin" (CORS never kicks in). Such requests arrive
# from loopback but carry the attacker's hostname in the Host header.
# Extra hostnames (Tailscale name, LAN IP) come from the ALLOWED_HOSTS env
# var; "*" disables the check (used behind trusted proxies, e.g. Vercel).
_allowed_hosts = auth.build_allowed_hosts()


@app.middleware("http")
async def enforce_host_allowlist(request: Request, call_next):
    """Reject requests whose Host header is not on the allowlist."""
    if os.environ.get("VERCEL"):
        return await call_next(request)
    if not auth.host_allowed(request.headers.get("host"), _allowed_hosts):
        return JSONResponse(
            status_code=400,
            content={"detail": "Invalid Host header"},
        )
    return await call_next(request)


# Token auth for remote clients. Loopback connections (the desktop app,
# dev servers, the Vite proxy) are trusted; anything else — e.g. a phone
# hitting `./start.sh prod` bound beyond localhost — must present
# `Authorization: Bearer <token>` on /api requests. The token comes from
# FAD_API_TOKEN or `<user-dir>/api_token` (generated by start.sh when
# exposing); with no token configured, remote clients are denied outright.
# /api/* is guarded plus the OpenAPI/docs endpoints: the static SPA shell
# contains no data (and the frontend picks the token up from a one-time
# `?apiToken=` URL parameter), but the schema enumerates every route, and
# docs stay enabled whenever ENVIRONMENT isn't "production" — which includes
# `./start.sh remote`, where the server is bound to 0.0.0.0.
_DOC_PATHS = frozenset({"/openapi.json", "/docs", "/redoc"})


def _needs_remote_token(path: str) -> bool:
    """Return whether ``path`` is guarded by the remote-client token check."""
    return (
        path.startswith("/api/")
        or path in _DOC_PATHS
        or path.startswith("/docs/")
    )


@app.middleware("http")
async def require_token_for_remote_clients(request: Request, call_next):
    """Require a bearer token on /api and docs requests from non-local clients."""
    if (
        os.environ.get("VERCEL")
        or not _needs_remote_token(request.url.path)
        or request.method == "OPTIONS"
    ):
        return await call_next(request)
    client_host = request.client.host if request.client else None
    if auth.is_trusted_client(client_host):
        return await call_next(request)
    supplied = auth.extract_bearer_token(request.headers.get("authorization"))
    if auth.token_matches(supplied, auth.get_api_token()):
        return await call_next(request)
    return JSONResponse(
        status_code=401,
        content={"detail": "Remote access requires a valid API token"},
    )


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Apply conservative security headers to every response."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Permissions-Policy",
        "geolocation=(), microphone=(), camera=(), payment=()",
    )
    # HSTS is only meaningful over HTTPS; emit it when the request was TLS.
    if request.url.scheme == "https":
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )
    return response


# Include routers
app.include_router(
    transactions.router, prefix="/api/transactions", tags=["Transactions"]
)
app.include_router(budget.router, prefix="/api/budget", tags=["Budget"])
app.include_router(
    budget_month_overrides.router,
    prefix="/api/budget-month-overrides",
    tags=["Budget Month Overrides"],
)
app.include_router(tagging.router, prefix="/api/tagging", tags=["Tagging"])
app.include_router(investments.router, prefix="/api/investments", tags=["Investments"])
app.include_router(liabilities.router, prefix="/api/liabilities", tags=["Liabilities"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(rates.router, prefix="/api/rates", tags=["Rates"])
app.include_router(backup.router, prefix="/api/backups", tags=["Backups"])
app.include_router(
    pending_refunds.router, prefix="/api/pending-refunds", tags=["Pending Refunds"]
)
app.include_router(
    tagging_rules.router, prefix="/api/tagging-rules", tags=["Tagging Rules"]
)
app.include_router(
    bank_balances.router, prefix="/api/bank-balances", tags=["Bank Balances"]
)
app.include_router(
    cash_balances.router, prefix="/api/cash-balances", tags=["Cash Balances"]
)
app.include_router(
    insurance_accounts.router,
    prefix="/api/insurance-accounts",
    tags=["Insurance Accounts"],
)
app.include_router(
    retirement.router,
    prefix="/api/retirement",
    tags=["Retirement"],
)
app.include_router(
    savings_goals.router,
    prefix="/api/savings-goals",
    tags=["Savings Goals"],
)
app.include_router(
    onboarding.router,
    prefix="/api/onboarding",
    tags=["Onboarding"],
)
app.include_router(version_route.router, prefix="/api/version", tags=["Version"])
app.include_router(updates.router, prefix="/api/updates", tags=["Updates"])

# In-app uninstall is macOS-only. The route file itself is platform-aware
# and 400s on non-darwin, but we register it everywhere so the OpenAPI
# schema is stable across platforms.
try:
    from backend.routes import uninstall as uninstall_route

    app.include_router(uninstall_route.router, prefix="/api/uninstall", tags=["Uninstall"])
except ImportError:
    pass

# Optional routes — gated for serverless where keyring is absent
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

# Testing routes expose demo-mode toggling and DB reset helpers. They must
# never be reachable in production: ``ENABLE_TESTING_ROUTES=1`` or a non-
# production ``ENVIRONMENT`` is required to mount them.
_enable_testing_routes = (
    os.getenv("ENABLE_TESTING_ROUTES") == "1" or _environment != "production"
)
if _enable_testing_routes:
    try:
        from backend.routes import testing
        app.include_router(testing.router, prefix="/api/testing", tags=["Testing"])
    except ImportError:
        pass


@app.exception_handler(EntityNotFoundException)
async def entity_not_found_exception_handler(
    request: Request, exc: EntityNotFoundException
):
    """Return a 404 JSON response for EntityNotFoundException."""
    return JSONResponse(
        status_code=404,
        content={"detail": exc.message},
    )


@app.exception_handler(EntityAlreadyExistsException)
async def entity_already_exists_exception_handler(
    request: Request, exc: EntityAlreadyExistsException
):
    """Return a 409 JSON response for EntityAlreadyExistsException."""
    return JSONResponse(
        status_code=409,
        content={"detail": exc.message},
    )


@app.exception_handler(ValidationException)
async def validation_exception_handler(request: Request, exc: ValidationException):
    """Return a 400 JSON response for ValidationException."""
    return JSONResponse(
        status_code=400,
        content={"detail": exc.message},
    )


@app.exception_handler(BadRequestException)
async def bad_request_exception_handler(request: Request, exc: BadRequestException):
    """Return a 400 JSON response for BadRequestException."""
    return JSONResponse(
        status_code=400,
        content={"detail": exc.message},
    )


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    request: Request, exc: RequestValidationError
):
    """422 handler that survives non-finite floats in the invalid input.

    Request models reject ``NaN``/``Infinity`` (``allow_inf_nan=False`` on
    ``ApiRequestModel``), but the default handler echoes the offending input
    back in the error body — and ``json.dumps`` cannot serialize a non-finite
    float, turning the 422 into a 500. Stringify those values instead.
    """

    def sanitize(value):
        if isinstance(value, float) and not math.isfinite(value):
            return repr(value)
        if isinstance(value, dict):
            return {k: sanitize(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [sanitize(v) for v in value]
        return value

    return JSONResponse(
        status_code=422,
        content={"detail": sanitize(jsonable_encoder(exc.errors()))},
    )


@app.exception_handler(OverflowError)
async def overflow_error_handler(request: Request, exc: OverflowError):
    """Map ``OverflowError`` to ``422 Unprocessable Entity``.

    SQLite INTEGER is 64-bit signed (max 2**63 - 1). When a path parameter
    exceeds that, SQLAlchemy raises ``OverflowError`` while binding the
    statement. Treat it as a client input problem rather than a server bug
    so the schemathesis fuzz job stays clean.
    """
    return JSONResponse(
        status_code=422,
        content={"detail": "Numeric path parameter exceeds supported range"},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Swallow unexpected exceptions with a generic 500 response.

    Individual routes wrap ``ValueError`` / ``BadRequestException`` with their
    own ``HTTPException(detail=str(e))`` calls, which is fine for messages the
    service layer intentionally surfaced. Anything that reaches this handler
    is an unhandled bug — returning ``str(exc)`` would leak stack frames,
    SQL fragments, file paths, or secrets present in the exception message.
    The real detail is kept in the server log for operators to inspect.
    """
    logger.exception(
        "Unhandled exception handling %s %s", request.method, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


# Serve frontend static build in production.
#
# Two layouts to support:
#   1. Dev / pip-install / Vercel  → frontend/dist sits next to backend/
#                                    in the repo tree.
#   2. PyInstaller-frozen bundle   → frontend/dist lives inside
#                                    sys._MEIPASS (the temp dir the
#                                    bootloader extracts into at launch).
#
# We probe the frozen path first when sys.frozen is set and fall back to
# the source-tree path so unit tests that import ``backend.main`` from a
# checkout still work without setting any env var.
def _resolve_frontend_dist() -> Path:
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", ""))
        bundled = meipass / "frontend" / "dist"
        if bundled.is_dir():
            return bundled
    return Path(__file__).parent.parent / "frontend" / "dist"


_frontend_dist = _resolve_frontend_dist()
if _frontend_dist.is_dir():
    app.mount("/assets", StaticFiles(directory=_frontend_dist / "assets"), name="static-assets")

    _frontend_dist_resolved = _frontend_dist.resolve()

    @app.exception_handler(404)
    async def spa_fallback(request: Request, exc):
        """Serve the React SPA for non-API 404s (client-side routing).

        Resolves the requested path and verifies it lives inside the frontend
        dist directory before serving to prevent path traversal (e.g.
        ``GET /../../etc/passwd``).
        """
        if request.url.path.startswith("/api/"):
            detail = getattr(exc, "detail", "Not found")
            return JSONResponse(status_code=404, content={"detail": detail})

        index_html = _frontend_dist_resolved / "index.html"
        requested = request.url.path.lstrip("/")
        if not requested:
            return FileResponse(index_html)

        candidate = (_frontend_dist_resolved / requested).resolve()
        try:
            candidate.relative_to(_frontend_dist_resolved)
        except ValueError:
            return FileResponse(index_html)

        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index_html)
