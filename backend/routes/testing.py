from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from backend.config import AppConfig
from backend import database
from backend.repositories.credentials_repository import CredentialsRepository
from backend.services.credentials_service import CredentialsService
from backend.models import Base

router = APIRouter()


class DemoModeRequest(BaseModel):
    enabled: bool


def _db_is_empty(engine) -> bool:
    """Check whether the demo database has any transaction data."""
    with engine.connect() as conn:
        try:
            result = conn.execute(
                text("SELECT COUNT(*) FROM credit_card_transactions")
            )
            return result.scalar() == 0
        except Exception:
            return True


@router.post("/toggle_demo_mode")
async def toggle_demo_mode(request: DemoModeRequest) -> dict[str, str | bool]:
    """
    Toggle the application's demo mode.

    When enabled, the application switches to a separate demo environment
    (database, credentials, categories) with pre-loaded sample data.
    """
    config = AppConfig()

    # Only perform actions if the mode is actually changing
    if config.is_demo_mode != request.enabled:
        config.set_demo_mode(request.enabled)

        # Reset database engine to pick up new path
        database.reset_engine()

        # Reset credentials repository to pick up new path
        repo = CredentialsRepository()
        repo.credentials_path = config.get_credentials_path()
        CredentialsService.clear_cache()

        # If enabling demo mode, ensure the database schema exists and seed data
        if request.enabled:
            engine = database.get_engine()
            Base.metadata.create_all(bind=engine)

            creds_service = CredentialsService()
            creds_service.seed_test_credentials()

            # Seed demo data only if the database is empty (first activation)
            if _db_is_empty(engine):
                from backend.demo.seed_demo_data import seed_all_demo_data

                session_factory = database.get_session_factory()
                db = session_factory()
                try:
                    seed_all_demo_data(db)
                finally:
                    db.close()

    return {"status": "success", "demo_mode": config.is_demo_mode}


@router.get("/demo_mode_status")
async def get_demo_mode_status():
    """Get the current demo mode status."""
    return {"demo_mode": AppConfig().is_demo_mode}
