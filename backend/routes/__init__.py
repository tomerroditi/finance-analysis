"""
API Routes Package

This package contains FastAPI route handlers.
"""

from backend.routes import (
    transactions,
    budget,
    tagging,
    credentials,
    scraping,
    investments,
    analytics,
    testing,
)

__all__ = [
    "transactions",
    "budget",
    "tagging",
    "credentials",
    "scraping",
    "investments",
    "analytics",
    "testing",
]
