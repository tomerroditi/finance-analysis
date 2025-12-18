"""
Credentials API routes.

Provides endpoints for account credential management.
"""
from typing import Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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
                accounts.append({
                    "service": service,
                    "provider": provider,
                    "account_name": account_name
                })
    return accounts


@router.delete("/{service}/{provider}/{account_name}")
async def delete_credential(
    service: str,
    provider: str,
    account_name: str
):
    """Delete a credential."""
    repo = CredentialsRepository()
    credentials = repo.read_credentials_file()
    
    if credentials is None:
        raise HTTPException(status_code=404, detail="No credentials found")
    
    try:
        del credentials[service][provider][account_name]
        
        # Clean up empty structures
        if not credentials[service][provider]:
            del credentials[service][provider]
        if not credentials[service]:
            del credentials[service]
        
        repo.write_credentials_file(credentials)
        return {"status": "success"}
    except KeyError:
        raise HTTPException(status_code=404, detail="Credential not found")
