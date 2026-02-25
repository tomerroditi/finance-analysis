"""
Testing / development utility routes.

Provides endpoints for toggling demo mode, which switches the application
to an isolated environment (separate DB, credentials, and categories) to
allow safe testing without affecting production data.
"""

from sqlalchemy import inspect, text

from fastapi import APIRouter
from pydantic import BaseModel

from backend.config import AppConfig
from backend import database
from backend.database import get_db_context
from backend.services.credentials_service import CredentialsService
from backend.models import Base

router = APIRouter()


def _sync_missing_columns(engine) -> None:
    """Add columns present in ORM models but missing from the physical DB.

    ``create_all`` only creates new tables; it does not alter existing ones.
    This fills the gap for SQLite (which has no full ALTER support) by
    running ``ALTER TABLE ... ADD COLUMN`` for each missing column.
    """
    inspector = inspect(engine)
    for table_name, table in Base.metadata.tables.items():
        if not inspector.has_table(table_name):
            continue
        existing = {col["name"] for col in inspector.get_columns(table_name)}
        for column in table.columns:
            if column.name not in existing:
                col_type = column.type.compile(engine.dialect)
                with engine.connect() as conn:
                    conn.execute(
                        text(f"ALTER TABLE {table_name} ADD COLUMN {column.name} {col_type}")
                    )
                    conn.commit()


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

        # If enabling demo mode, ensure the database schema exists and seed credentials
        if request.enabled:
            engine = database.get_engine()
            Base.metadata.create_all(bind=engine)
            _sync_missing_columns(engine)

            # Use a fresh session from the NEW engine (demo DB) — the old
            # Depends(get_database) session still points at the production DB.
            with get_db_context() as demo_db:
                creds_service = CredentialsService(demo_db)
                creds_service.seed_demo_credentials()

    return {"status": "success", "demo_mode": config.is_demo_mode}


@router.get("/demo_mode_status")
async def get_demo_mode_status():
    """Get the current demo mode status."""
    return {"demo_mode": AppConfig().is_demo_mode}
