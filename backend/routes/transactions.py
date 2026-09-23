"""
Transactions API routes.

Provides endpoints for transaction CRUD operations.
"""

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.constants.providers import Services
from backend.dependencies import get_database
from backend.routes.schemas import ApiRequestModel, StatusResponse
from backend.services.transactions_service import TransactionsService

router = APIRouter()


class TransactionCreate(ApiRequestModel):
    """Request body for creating a manual (cash or investment) transaction."""

    date: date
    description: str
    amount: float
    account_name: str
    provider: str | None = None
    account_number: str | None = None
    category: str | None = None
    tag: str | None = None
    service: str  # 'cash' or 'manual_investments'


class TransactionUpdate(ApiRequestModel):
    """Partial update of a transaction; ``source`` selects the table."""

    date: str | None = None
    account_name: str | None = None
    description: str | None = None
    amount: float | None = None
    category: str | None = None
    tag: str | None = None
    provider: str | None = None
    source: str


class BulkTagUpdate(ApiRequestModel):
    """Request body for tagging/editing several transactions of one source."""

    transaction_ids: list[int]
    source: str
    category: str | None = None
    tag: str | None = None
    description: str | None = None
    account_name: str | None = None
    date: str | None = None
    amount: float | None = None


class SplitItem(ApiRequestModel):
    """One slice of a split transaction."""

    amount: float
    category: str
    tag: str


class SplitRequest(ApiRequestModel):
    """Request body for splitting a transaction into slices."""

    source: str
    # A zero-slice split flipped the parent to ``split_parent`` with no
    # children, hiding the transaction from the merged view and every KPI.
    splits: list[SplitItem] = Field(..., min_length=1)


class LatestDateResponse(BaseModel):
    """Latest transaction date across all tables, or ``None`` when empty."""

    latest_date: str | None = None


class UncategorizedCountResponse(BaseModel):
    """Number of transactions still missing a category."""

    count: int


@router.get("/")
def get_transactions(
    service: str | None = Query(
        None, description="Filter by service: credit_card, bank, cash"
    ),
    include_split_parents: bool = Query(
        False, description="Whether to include split parents"
    ),
    db: Session = Depends(get_database),
) -> list[dict[str, Any]]:
    """Get all transactions, optionally filtered by service."""
    df = TransactionsService(db).get_merged_transactions(
        service=service,
        include_split_parents=include_split_parents,
        exclude_services=[Services.INSURANCE.value],
    )
    return df.to_dict(orient="records")


@router.post("/", response_model=StatusResponse)
def create_transaction(
    data: TransactionCreate, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Create a new manual transaction."""
    TransactionsService(db).create_transaction(data.model_dump(), data.service)
    return {"status": "success"}


@router.put("/{unique_id}", response_model=StatusResponse)
def update_transaction(
    unique_id: str, data: TransactionUpdate, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Update editable fields of a transaction.

    The set of editable fields depends on the transaction source: scraped
    transactions (bank, credit_card) allow only category/tag edits, while
    manual entries (cash, manual_investments) allow description and amount
    edits as well.

    Parameters
    ----------
    unique_id : str
        Transaction ID as a string.
    data : TransactionUpdate
        Fields to update plus the ``source`` (e.g. ``credit_card``, ``bank``,
        ``cash``) used to determine which table to update.

    Returns
    -------
    dict
        ``{"status": "success"}`` if any field was updated,
        ``{"status": "no_changes"}`` if nothing changed. A ``unique_id``
        that does not exist in ``source`` is a 404.
    """
    updated = TransactionsService(db).update_transaction(
        unique_id,
        data.source,
        data.model_dump(exclude={"source"}, exclude_none=True),
    )
    return {"status": "success" if updated else "no_changes"}


@router.delete("/{unique_id}", response_model=StatusResponse)
def delete_transaction(
    unique_id: str,
    source: str = Query(..., description="The source of the transaction"),
    db: Session = Depends(get_database),
) -> dict[str, str]:
    """Delete a transaction (only for manual entries)."""
    TransactionsService(db).delete_transaction(unique_id, source)
    return {"status": "success"}


@router.post("/{unique_id}/split", response_model=StatusResponse)
def split_transaction(
    unique_id: int, data: SplitRequest, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Split a transaction into multiple parts.

    The service rejects slices that don't add up to the parent amount
    (``ValidationException`` → 400) and a parent that doesn't exist
    (``EntityNotFoundException`` → 404).
    """
    splits = [s.model_dump() for s in data.splits]
    TransactionsService(db).split_transaction(unique_id, data.source, splits)
    return {"status": "success"}


@router.delete("/{unique_id}/split", response_model=StatusResponse)
def revert_split(
    unique_id: int,
    source: str = Query(..., description="The source of the transaction"),
    db: Session = Depends(get_database),
) -> dict[str, str]:
    """Revert a transaction split."""
    TransactionsService(db).revert_split(unique_id, source)
    return {"status": "success"}


@router.post("/bulk-tag", response_model=StatusResponse)
def bulk_tag_transactions(
    data: BulkTagUpdate, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Apply tagging and optional field updates to multiple transactions of the same source."""
    TransactionsService(db).bulk_tag_transactions(
        data.transaction_ids,
        data.source,
        data.category,
        data.tag,
        data.description,
        data.account_name,
        data.date,
        data.amount,
    )
    return {"status": "success"}


@router.get("/latest-date", response_model=LatestDateResponse)
def get_latest_data_date(
    db: Session = Depends(get_database),
) -> dict[str, str | None]:
    """Get the latest transaction date across all tables."""
    service = TransactionsService(db)
    latest = service.get_latest_data_date()
    return {"latest_date": latest.isoformat() if latest else None}


@router.get("/uncategorized-count", response_model=UncategorizedCountResponse)
def get_uncategorized_count(
    db: Session = Depends(get_database),
) -> dict[str, int]:
    """Count uncategorized transactions (for the sidebar badge)."""
    service = TransactionsService(db)
    return {"count": service.count_uncategorized()}


@router.get("/{transaction_id}")
def get_transaction(
    transaction_id: int,
    source: str = Query(
        ..., description="Source table (unique_id is per-table), e.g. bank_transactions"
    ),
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Get a specific transaction by its per-table ID and source table."""
    return TransactionsService(db).get_transaction(transaction_id, source).to_dict()


@router.put("/{transaction_id}/tag", response_model=StatusResponse)
def update_transaction_tag(
    transaction_id: str,
    category: str,
    tag: str,
    service: str = Query(
        ..., description="Source table or service alias, e.g. bank_transactions / banks"
    ),
    db: Session = Depends(get_database),
) -> dict[str, str]:
    """Update the category and tag of a single transaction.

    Legacy endpoint retained for backwards compatibility; prefer the
    general ``PUT /{unique_id}`` endpoint for new integrations.

    Parameters
    ----------
    transaction_id : str
        Transaction ID as a string.
    category : str
        Category to assign.
    tag : str
        Tag to assign within the category.
    service : str
        Table name (``credit_card_transactions``) or service alias
        (``credit_cards``) used to target the correct table.
    """
    TransactionsService(db).update_tagging_by_id(service, transaction_id, category, tag)
    return {"status": "success"}
