"""Credentials API routes.

Provides endpoints for account credential management.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.constants.providers import LoginFields, Services
from backend.dependencies import get_database
from backend.services.bank_balance_service import BankBalanceService
from backend.services.credentials_service import CredentialsService

router = APIRouter()


class CredentialCreate(BaseModel):
    service: str
    provider: str
    account_name: str
    credentials: Dict[str, Any]


class StatusResponse(BaseModel):
    status: str


class ProviderFieldsResponse(BaseModel):
    fields: List[str]


class DeleteAccountResponse(BaseModel):
    """Result of disconnecting an account."""

    status: str
    transactions_deleted: int


@router.get("/")
def get_credentials(
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
def get_accounts(
    db: Session = Depends(get_database),
) -> list[dict[str, str]]:
    """Get a list of all configured accounts."""
    service = CredentialsService(db)
    return service.get_accounts_list()


@router.get("/{service}/{provider}/{account_name}")
def get_credential_details(
    service: str,
    provider: str,
    account_name: str,
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Get details for a specific credential, with secret values masked.

    Sensitive fields (password, OTP tokens) are replaced with a sentinel —
    plaintext secrets are never returned by the API. Sending the sentinel
    back on save keeps the stored value.
    """
    creds_service = CredentialsService(db)
    fields = creds_service.get_masked_credentials(service, provider, account_name)
    if not fields:
        raise HTTPException(status_code=404, detail="Credential not found")
    return fields


@router.get("/providers")
def get_providers() -> dict[str, list[str]]:
    """Get all supported providers."""
    return CredentialsService.get_available_providers()


@router.post("/", response_model=StatusResponse)
def create_credential(
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


@router.get("/fields/{provider}", response_model=ProviderFieldsResponse)
def get_provider_fields(provider: str) -> dict[str, List[str]]:
    """Get the required fields for a provider login."""
    fields = LoginFields.get_fields(provider)
    return {"fields": fields}


@router.delete(
    "/{service}/{provider}/{account_name}",
    response_model=DeleteAccountResponse,
)
def delete_credential(
    service: str,
    provider: str,
    account_name: str,
    delete_data: bool = Query(
        False,
        description=(
            "Also delete the account's transactions and everything "
            "referencing them. Defaults to false — the connection is removed "
            "but the history is kept."
        ),
    ),
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Disconnect an account, optionally deleting its stored data too.

    Two distinct outcomes, because "delete this account" is ambiguous:

    - ``delete_data=false`` (default) — remove only the connection and its
      saved password. Transactions, the bank balance (and with it the
      account's prior wealth) and the scrape history are all kept, so
      reconnecting resumes where it left off.
    - ``delete_data=true`` — additionally delete the account's transactions
      along with their splits, pending refunds, refund links, source notes
      and budget month overrides, plus the bank balance and scrape history.
      Reconnecting then starts with a fresh one-year backfill.

    Previously the balance row was dropped unconditionally while the
    transactions were kept, which destroyed the account's prior wealth and
    left net worth inconsistent with the history it was derived from.

    Parameters
    ----------
    service : str
        Service type (``banks``, ``credit_cards``).
    provider : str
        Provider identifier (e.g. ``hapoalim``, ``isracard``).
    account_name : str
        Account name as stored in credentials.
    delete_data : bool
        Whether to delete the account's stored data as well.

    Raises
    ------
    HTTPException
        404 if the credential does not exist.
    """
    creds_service = CredentialsService(db)
    try:
        result = creds_service.delete_credential(
            service, provider, account_name, delete_data=delete_data
        )
        # The balance row carries `prior_wealth_amount`, so it may only be
        # dropped when the transactions it was derived from go too.
        if delete_data and service == Services.BANK.value:
            BankBalanceService(db).delete_for_account(provider, account_name)
        return {
            "status": "success",
            "transactions_deleted": result.get("transactions_deleted", 0),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
