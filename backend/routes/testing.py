from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.config import AppConfig
from backend import database
from backend.dependencies import get_database
from backend.services.credentials_service import CredentialsService
from backend.models import Base

router = APIRouter()


class TestModeRequest(BaseModel):
    enabled: bool


@router.post("/toggle_test_mode")
async def toggle_test_mode(
    request: TestModeRequest,
    db: Session = Depends(get_database),
) -> dict[str, str | bool]:
    """
    Toggle the application's test mode.

    When enabled, the application switches to a separate test environment
    (database, credentials, categories).
    """
    config = AppConfig()

    # Only perform actions if the mode is actually changing
    if config.is_test_mode != request.enabled:
        config.set_test_mode(request.enabled)

        # Reset database engine to pick up new path
        database.reset_engine()

        CredentialsService.clear_cache()

        # If enabling test mode, ensure the database schema exists and seed credentials
        if request.enabled:
            engine = database.get_engine()
            Base.metadata.create_all(bind=engine)

            creds_service = CredentialsService(db)
            creds_service.seed_test_credentials()

    return {"status": "success", "test_mode": config.is_test_mode}


@router.get("/test_mode_status")
async def get_test_mode_status():
    """Get the current test mode status."""
    return {"test_mode": AppConfig().is_test_mode}
