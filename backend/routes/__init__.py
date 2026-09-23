"""FastAPI route handlers, one router module per API resource."""

from backend.routes import (
    analytics,
    budget,
    investments,
    tagging,
    transactions,
)

__all__ = [
    "analytics",
    "budget",
    "investments",
    "tagging",
    "transactions",
]

# Optional routes — depend on keyring (not available in serverless)
try:
    from backend.routes import credentials, scraping, testing

    __all__ += ["credentials", "scraping", "testing"]
except ImportError:
    pass
