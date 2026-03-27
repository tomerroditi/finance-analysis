"""
API Routes Package

This package contains FastAPI route handlers.
"""

from backend.routes import (
    transactions,
    budget,
    tagging,
    investments,
    analytics,
)

__all__ = [
    "transactions",
    "budget",
    "tagging",
    "investments",
    "analytics",
]

# Optional routes — depend on keyring (not available in serverless)
try:
    from backend.routes import credentials, scraping, testing  # noqa: F401
    __all__ += ["credentials", "scraping", "testing"]
except ImportError:
    pass
