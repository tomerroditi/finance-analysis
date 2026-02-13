"""
FastAPI main application entry point.

This module sets up the FastAPI application with CORS, routes, and exception handlers.
"""

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.errors import (
    EntityAlreadyExistsException,
    EntityNotFoundException,
    ValidationException,
)
from backend.routes import (
    analytics,
    bank_balances,
    budget,
    credentials,
    investments,
    pending_refunds,
    scraping,
    tagging,
    tagging_rules,
    testing,
    transactions,
)

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup/shutdown events."""
    # Startup
    print("Starting Finance Analysis API...")
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
app.include_router(credentials.router, prefix="/api/credentials", tags=["Credentials"])
app.include_router(scraping.router, prefix="/api/scraping", tags=["Scraping"])
app.include_router(investments.router, prefix="/api/investments", tags=["Investments"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(testing.router, prefix="/api/testing", tags=["Testing"])
app.include_router(
    pending_refunds.router, prefix="/api/pending-refunds", tags=["Pending Refunds"]
)
app.include_router(
    tagging_rules.router, prefix="/api/tagging-rules", tags=["Tagging Rules"]
)
app.include_router(
    bank_balances.router, prefix="/api/bank-balances", tags=["Bank Balances"]
)


@app.exception_handler(EntityNotFoundException)
async def entity_not_found_exception_handler(
    request: Request, exc: EntityNotFoundException
):
    return JSONResponse(
        status_code=404,
        content={"detail": exc.message},
    )


@app.exception_handler(EntityAlreadyExistsException)
async def entity_already_exists_exception_handler(
    request: Request, exc: EntityAlreadyExistsException
):
    return JSONResponse(
        status_code=409,
        content={"detail": exc.message},
    )


@app.exception_handler(ValidationException)
async def validation_exception_handler(request: Request, exc: ValidationException):
    return JSONResponse(
        status_code=400,
        content={"detail": exc.message},
    )


@app.get("/")
async def root():
    """Root endpoint returning API info."""
    return {
        "name": "Finance Analysis API",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
