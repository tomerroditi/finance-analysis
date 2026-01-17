from fastapi import APIRouter
from pydantic import BaseModel

from backend.config import AppConfig
from backend import database
from backend.repositories.credentials_repository import CredentialsRepository
from backend.services.credentials_service import CredentialsService
from backend.errors import EntityNotFoundException
from backend.naming_conventions import Fields
from backend.models import Base

router = APIRouter()


class TestModeRequest(BaseModel):
    enabled: bool


@router.post("/toggle_test_mode")
async def toggle_test_mode(request: TestModeRequest):
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
        # Since it's a singleton, we need to force re-initialization or update its path
        repo = CredentialsRepository()
        repo.credentials_path = config.get_credentials_path()
        CredentialsService.clear_cache()

        # If enabling test mode, ensure the database schema exists
        if request.enabled:
            engine = database.get_engine()
            Base.metadata.create_all(bind=engine)

            # Seed dummy credentials for testing
            creds_service = CredentialsService()

            def ensure_dummy_cred(service, provider, account, creds_payload):
                try:
                    creds_service.repository.get_credentials(service, provider, account)
                except EntityNotFoundException:
                    service_creds = creds_service.credentials
                    if service not in service_creds:
                        service_creds[service] = {}
                    if provider not in service_creds[service]:
                        service_creds[service][provider] = {}

                    # Convert to field format expected by service
                    formatted_creds = {}
                    if "username" in creds_payload:
                        formatted_creds[Fields.USERNAME.value] = creds_payload[
                            "username"
                        ]
                    if "password" in creds_payload:
                        formatted_creds[Fields.PASSWORD.value] = creds_payload[
                            "password"
                        ]
                    if "otpLongTermToken" in creds_payload:
                        formatted_creds["otpLongTermToken"] = creds_payload[
                            "otpLongTermToken"
                        ]
                    elif "email" in creds_payload:  # specific for dummy_tfa
                        formatted_creds[Fields.EMAIL.value] = creds_payload["email"]
                        formatted_creds[Fields.PHONE_NUMBER.value] = creds_payload.get(
                            "phoneNumber", ""
                        )

                    # Fallback for simple case if fields match directly
                    if not formatted_creds:
                        formatted_creds = creds_payload

                    service_creds[service][provider][account] = formatted_creds
                    creds_service.save_credentials(service_creds)

            # Seeding Test Accounts

            # Banks
            ensure_dummy_cred(
                "banks",
                "test_bank",
                "Test Bank",
                {"username": "test", "password": "password"},
            )
            ensure_dummy_cred(
                "banks",
                "test_bank_2fa",
                "Test Bank 2FA",
                {
                    "email": "test@example.com",
                    "password": "password",
                    "phoneNumber": "12345678",
                },
            )

            # Credit Cards
            ensure_dummy_cred(
                "credit_cards",
                "test_credit_card",
                "Test Credit Card",
                {"username": "test", "password": "password"},
            )
            ensure_dummy_cred(
                "credit_cards",
                "test_credit_card_2fa",
                "Test Credit Card 2FA",
                {
                    "email": "test@example.com",
                    "password": "password",
                    "phoneNumber": "12345678",
                },
            )

    return {"status": "success", "test_mode": config.is_test_mode}


@router.get("/test_mode_status")
async def get_test_mode_status():
    """Get the current test mode status."""
    return {"test_mode": AppConfig().is_test_mode}
