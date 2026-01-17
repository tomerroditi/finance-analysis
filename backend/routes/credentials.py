"""
Credentials API routes.

Provides endpoints for account credential management.
"""

from typing import Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import AppConfig
from backend.naming_conventions import LoginFields, bank_providers, cc_providers
from backend.repositories.credentials_repository import CredentialsRepository

router = APIRouter()


class CredentialCreate(BaseModel):
    service: str
    provider: str
    account_name: str
    credentials: Dict[str, Any]


@router.get("/")
async def get_credentials():
    """Get all stored credentials (without passwords)."""
    repo = CredentialsRepository()
    credentials = repo.read_credentials_file()
    if credentials is None:
        return {}

    # Remove sensitive data before returning
    safe_credentials = {}
    for service, providers in credentials.items():
        safe_credentials[service] = {}
        for provider, accounts in providers.items():
            safe_credentials[service][provider] = list(accounts.keys())

    return safe_credentials


@router.get("/accounts")
async def get_accounts():
    """Get a list of all configured accounts."""
    repo = CredentialsRepository()
    credentials = repo.read_credentials_file()
    if credentials is None:
        return []

    accounts = []
    for service, providers in credentials.items():
        for provider, account_dict in providers.items():
            for account_name in account_dict.keys():
                accounts.append(
                    {
                        "service": service,
                        "provider": provider,
                        "account_name": account_name,
                    }
                )
    return accounts


@router.get("/{service}/{provider}/{account_name}")
async def get_credential_details(service: str, provider: str, account_name: str):
    """Get details for a specific credential."""
    repo = CredentialsRepository()
    creds = repo.get_credentials(service, provider, account_name)
    if not creds:
        raise HTTPException(status_code=404, detail="Credential not found")
    return creds


@router.get("/providers")
async def get_providers():
    """Get all supported providers."""
    is_test = AppConfig().is_test_mode

    # Filter based on mode
    banks = [p for p in bank_providers if ("test_" in p) == is_test]
    ccs = [p for p in cc_providers if ("test_" in p) == is_test]

    return {"banks": banks, "credit_cards": ccs}


@router.post("/")
async def create_credential(credential: CredentialCreate):
    """Create or update a credential."""
    repo = CredentialsRepository()
    repo.save_credentials(
        service=credential.service,
        provider=credential.provider,
        account_name=credential.account_name,
        credentials=credential.credentials,
    )
    return {"status": "success"}


@router.get("/fields/{provider}")
async def get_provider_fields(provider: str):
    """Get the required fields for a provider login."""
    fields = LoginFields.get_fields(provider)
    return {"fields": fields}


@router.delete("/{service}/{provider}/{account_name}")
async def delete_credential(service: str, provider: str, account_name: str):
    """Delete a credential."""
    repo = CredentialsRepository()
    credentials = repo.read_credentials_file()

    if credentials is None:
        raise HTTPException(status_code=404, detail="No credentials found")

    # Delete from YAML
    del credentials[service][provider][account_name]

    # Clean up empty structures
    if not credentials[service][provider]:
        del credentials[service][provider]
    if not credentials[service]:
        del credentials[service]

    repo.write_credentials_file(credentials)

    # Delete from Keyring (best effort)
    for key in ["password", "secret", "otp_key"]:
        keyring_key = f"{service}_{provider}_{account_name}_{key}"
        repo.delete_password_from_keyring(keyring_key)

    return {"status": "success"}
