"""
Testing / development utility routes.

Provides endpoints for toggling demo mode, which switches the application
to an isolated environment (separate DB, credentials, and categories) to
allow safe testing without affecting production data.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from backend.config import AppConfig
from backend import database
from backend.database import get_db_context
from backend.demo_setup import DEMO_REFERENCE_DATE, prepare_demo_database
from backend.services.credentials_service import CredentialsService
from backend.services.tagging_service import CategoriesTagsService

router = APIRouter()

# Re-exported for backwards compatibility with tests/integrations that
# import this constant from the route module.
__all__ = ["DEMO_REFERENCE_DATE", "router"]


class DemoModeRequest(BaseModel):
    enabled: bool


@router.post("/toggle_demo_mode")
async def toggle_demo_mode(
    request: DemoModeRequest,
) -> dict[str, str | bool]:
    """Toggle the application's demo mode on or off.

    When enabled, the app switches to an isolated demo environment with a
    separate SQLite database, demo credentials, and demo categories. The
    database engine and credentials cache are reset so all subsequent
    requests use the demo environment. When disabling, the engine resets
    back to the production database.

    Parameters
    ----------
    request : DemoModeRequest
        ``enabled`` flag indicating the desired demo mode state.

    Returns
    -------
    dict
        ``{"status": "success", "demo_mode": bool}`` reflecting the new state.
    """
    config = AppConfig()

    # Only perform actions if the mode is actually changing
    if config.is_demo_mode != request.enabled:
        config.set_demo_mode(request.enabled)

        # Reset database engine to pick up new path
        database.reset_engine()

        CredentialsService.clear_cache()
        CategoriesTagsService.clear_cache()

        # If enabling demo mode, copy source DB then ensure schema is up-to-date
        if request.enabled:
            prepare_demo_database()

            with get_db_context() as demo_db:
                creds_service = CredentialsService(demo_db)
                creds_service.seed_demo_credentials()

    return {"status": "success", "demo_mode": config.is_demo_mode}


@router.get("/demo_mode_status")
async def get_demo_mode_status():
    """Get the current demo mode status."""
    return {"demo_mode": AppConfig().is_demo_mode}
