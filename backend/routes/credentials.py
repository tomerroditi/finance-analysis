"""Credentials API routes.

Provides endpoints for account credential management.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.constants.providers import LoginFields
from backend.dependencies import get_database
from backend.services.bank_balance_service import BankBalanceService
from backend.services.credentials_service import CredentialsService

router = APIRouter()


class CredentialCreate(BaseModel):
    service: str
    provider: str
    account_name: str
    credentials: Dict[str, Any]


@router.get("/")
async def get_credentials(
    db: Session = Depends(get_database),
) -> dict[str, dict[str, list[str]]]:
    """Return all stored credentials, omitting passwords.

    Returns
    -------
    dict
        Nested structure ``{service: {provider: [account_names]}}``
        e.g. ``{"banks": {"hapoalim": ["main"]}, "credit_cards": {...}}``.
    """
    service = CredentialsService(db)
    return service.get_safe_credentials()


@router.get("/accounts")
async def get_accounts(
    db: Session = Depends(get_database),
) -> list[dict[str, str]]:
    """Get a list of all configured accounts."""
    service = CredentialsService(db)
    return service.get_accounts_list()


@router.get("/{service}/{provider}/{account_name}")
async def get_credential_details(
    service: str,
    provider: str,
    account_name: str,
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Get details for a specific credential."""
    creds_service = CredentialsService(db)
    filtered = creds_service.get_scraper_credentials(service, provider, account_name)
    if not filtered or service not in filtered or provider not in filtered[service]:
        raise HTTPException(status_code=404, detail="Credential not found")
    return filtered[service][provider][account_name]


@router.get("/providers")
async def get_providers() -> dict[str, list[str]]:
    """Get all supported providers."""
    return CredentialsService.get_available_providers()


@router.post("/")
async def create_credential(
    credential: CredentialCreate,
    db: Session = Depends(get_database),
) -> dict[str, str]:
    """Create or update a credential."""
    creds_service = CredentialsService(db)
    creds_service.save_credentials({
        credential.service: {
            credential.provider: {
                credential.account_name: credential.credentials
            }
        }
    })
    return {"status": "success"}


@router.get("/fields/{provider}")
async def get_provider_fields(provider: str) -> dict[str, List[str]]:
    """Get the required fields for a provider login."""
    fields = LoginFields.get_fields(provider)
    return {"fields": fields}


@router.delete("/{service}/{provider}/{account_name}")
async def delete_credential(
    service: str,
    provider: str,
    account_name: str,
    db: Session = Depends(get_database),
) -> dict[str, str]:
    """Delete a stored credential and clean up associated data.

    For bank accounts, also removes the stored balance record for that account.

    Parameters
    ----------
    service : str
        Service type (``banks``, ``credit_cards``).
    provider : str
        Provider identifier (e.g. ``hapoalim``, ``isracard``).
    account_name : str
        Account name as stored in credentials.

    Raises
    ------
    HTTPException
        404 if the credential does not exist.
    """
    creds_service = CredentialsService(db)
    try:
        creds_service.delete_credential(service, provider, account_name)
        if service == "banks":
            balance_service = BankBalanceService(db)
            balance_service.delete_for_account(provider, account_name)
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
