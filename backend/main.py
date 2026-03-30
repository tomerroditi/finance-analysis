"""
FastAPI main application entry point.

This module sets up the FastAPI application with CORS, routes, and exception handlers.
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.config import AppConfig
from backend.database import get_db_context, get_engine
from backend.errors import (
    EntityAlreadyExistsException,
    EntityNotFoundException,
    ValidationException,
)
from backend.models import Base
from backend.routes import (
    analytics,
    backup,
    bank_balances,
    budget,
    cash_balances,
    insurance_accounts,
    investments,
    liabilities,
    pending_refunds,
    retirement,
    tagging,
    tagging_rules,
    transactions,
)

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup/shutdown events."""
    # Skip startup migrations in serverless (demo DB is pre-built)
    if os.environ.get("VERCEL"):
        yield
        return

    from backend.repositories.credentials_repository import CredentialsRepository
    from backend.repositories.tagging_repository import (
        TaggingRepository,
        DEFAULT_CATEGORIES_PATH,
        DEFAULT_CATEGORIES_ICONS_PATH,
    )

    # Startup
    print("Starting Finance Analysis API...")
    Base.metadata.create_all(bind=get_engine())

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

        # Migrate credentials from YAML if DB table is empty
        creds_repo = CredentialsRepository(db)
        creds_repo.migrate_from_yaml(config.get_credentials_path())

    # Migrate: seed Investment.prior_wealth_amount from transactions
    # and clean up legacy manual_investments prior wealth offset transactions
    with get_db_context() as db:
        from sqlalchemy import text
        from backend.repositories.investments_repository import InvestmentsRepository
        from backend.repositories.transactions_repository import TransactionsRepository
        from backend.constants.categories import PRIOR_WEALTH_TAG, IncomeCategories
        from backend.constants.providers import Services
        from backend.constants.tables import TransactionsTableFields

        engine = get_engine()

        # 1. Add the column if not present (SQLite doesn't auto-add columns)
        with engine.connect() as conn:
            cols = [
                row[1]
                for row in conn.execute(text("PRAGMA table_info(investments)")).fetchall()
            ]
            if "prior_wealth_amount" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE investments ADD COLUMN prior_wealth_amount REAL NOT NULL DEFAULT 0.0"
                    )
                )
                conn.commit()

        investments_repo = InvestmentsRepository(db)
        txns_repo = TransactionsRepository(db)

        # 2. Seed prior_wealth_amount for every investment from its transactions
        investments_df = investments_repo.get_all_investments(include_closed=True)
        if not investments_df.empty:
            txns_df = txns_repo.get_table(Services.MANUAL_INVESTMENTS.value)
            for _, inv in investments_df.iterrows():
                if not txns_df.empty:
                    mask = (txns_df["category"] == inv["category"]) & (
                        txns_df["tag"] == inv["tag"]
                    )
                    inv_txns = txns_df[mask]
                    prior_wealth = (
                        -float(inv_txns["amount"].sum())
                        if not inv_txns.empty
                        else 0.0
                    )
                else:
                    prior_wealth = 0.0
                investments_repo.update_prior_wealth(int(inv["id"]), prior_wealth)

        # 3. Remove legacy manual_investments prior wealth offset transactions
        manual_inv_repo = txns_repo.manual_investments_repo
        inv_all_df = manual_inv_repo.get_table()
        if not inv_all_df.empty:
            tag_col = TransactionsTableFields.TAG.value
            cat_col = TransactionsTableFields.CATEGORY.value
            acct_col = TransactionsTableFields.ACCOUNT_NAME.value
            uid_col = TransactionsTableFields.UNIQUE_ID.value

            pw_mask = (
                (inv_all_df[tag_col] == PRIOR_WEALTH_TAG)
                & (inv_all_df[cat_col] == IncomeCategories.OTHER_INCOME.value)
                & (inv_all_df[acct_col] == PRIOR_WEALTH_TAG)
            )
            for _, row in inv_all_df[pw_mask].iterrows():
                manual_inv_repo.delete_transaction_by_unique_id(str(row[uid_col]))

    yield
    # Shutdown
    print("Shutting down Finance Analysis API...")


app = FastAPI(
    title="Finance Analysis API",
    description="API for personal finance tracking and analysis",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include routers
app.include_router(
    transactions.router, prefix="/api/transactions", tags=["Transactions"]
)
app.include_router(budget.router, prefix="/api/budget", tags=["Budget"])
app.include_router(tagging.router, prefix="/api/tagging", tags=["Tagging"])
app.include_router(investments.router, prefix="/api/investments", tags=["Investments"])
app.include_router(liabilities.router, prefix="/api/liabilities", tags=["Liabilities"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
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


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


# Serve frontend static build in production
_frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/assets", StaticFiles(directory=_frontend_dist / "assets"), name="static-assets")

    @app.exception_handler(404)
    async def spa_fallback(request: Request, exc):
        """Serve the React SPA for non-API 404s (client-side routing)."""
        if request.url.path.startswith("/api/"):
            detail = getattr(exc, "detail", "Not found")
            return JSONResponse(status_code=404, content={"detail": detail})
        file_path = _frontend_dist / request.url.path.lstrip("/")
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_frontend_dist / "index.html")
