from fastapi import APIRouter
from pydantic import BaseModel

from backend.config import AppConfig
from backend import database
from backend.repositories.credentials_repository import CredentialsRepository
from backend.services.credentials_service import CredentialsService
from backend.models import Base

router = APIRouter()


class TestModeRequest(BaseModel):
    enabled: bool


@router.post("/toggle_test_mode")
async def toggle_test_mode(request: TestModeRequest) -> dict[str, str | bool]:
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

        # Reset credentials repository to pick up new path
        repo = CredentialsRepository()
        repo.credentials_path = config.get_credentials_path()
        CredentialsService.clear_cache()

        # If enabling test mode, ensure the database schema exists and seed credentials
        if request.enabled:
            engine = database.get_engine()
            Base.metadata.create_all(bind=engine)

            creds_service = CredentialsService()
            creds_service.seed_test_credentials()

    return {"status": "success", "test_mode": config.is_test_mode}


@router.get("/test_mode_status")
async def get_test_mode_status():
    """Get the current test mode status."""
    return {"test_mode": AppConfig().is_test_mode}
