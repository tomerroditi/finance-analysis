"""
Transactions API routes.

Provides endpoints for transaction CRUD operations.
"""

from datetime import date
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.constants.providers import Services
from backend.constants.tables import Tables
from backend.dependencies import get_database
from backend.errors import ValidationException
from backend.routes.schemas import ApiRequestModel
from backend.services.transactions_service import TransactionsService

router = APIRouter()

# Every accepted ``source``/``service`` identifier: both the table names and
# the service aliases the repository dispatches on. An unrecognized value used
# to reach the repository lookup, which returns ``None`` and was then
# dereferenced — a 500 for what is plainly a client mistake.
_VALID_SOURCES = frozenset(
    {
        Tables.CREDIT_CARD.value,
        Tables.BANK.value,
        Tables.CASH.value,
        Tables.MANUAL_INVESTMENT_TRANSACTIONS.value,
        Tables.INSURANCE.value,
        Services.CREDIT_CARD.value,
        Services.BANK.value,
        Services.CASH.value,
        Services.MANUAL_INVESTMENTS.value,
        Services.INSURANCE.value,
    }
)

# Splits are money slices of one transaction, so they must add up to it. Money
# is stored as a float, so allow a cent of accumulated rounding drift.
_SPLIT_SUM_TOLERANCE = 0.01


def _validate_source(source: str) -> str:
    """Reject a ``source`` the transactions repository cannot dispatch on.

    Parameters
    ----------
    source : str
        Table or service identifier supplied by the client.

    Returns
    -------
    str
        The unchanged ``source`` when it is recognized.

    Raises
    ------
    ValidationException
        If ``source`` is not a known table or service name.
    """
    if source not in _VALID_SOURCES:
        raise ValidationException(
            f"Invalid source: '{source}'. Valid sources: "
            + ", ".join(sorted(_VALID_SOURCES))
        )
    return source


class TransactionCreate(ApiRequestModel):
    date: date
    description: str
    amount: float
    account_name: str
    provider: Optional[str] = None
    account_number: Optional[str] = None
    category: Optional[str] = None
    tag: Optional[str] = None
    service: str  # 'cash' or 'manual_investments'


class TransactionUpdate(ApiRequestModel):
    date: Optional[str] = None
    account_name: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[float] = None
    category: Optional[str] = None
    tag: Optional[str] = None
    provider: Optional[str] = None
    source: str


class BulkTagUpdate(ApiRequestModel):
    transaction_ids: List[int]
    source: str
    category: Optional[str] = None
    tag: Optional[str] = None
    description: Optional[str] = None
    account_name: Optional[str] = None
    date: Optional[str] = None
    amount: Optional[float] = None


class SplitItem(ApiRequestModel):
    amount: float
    category: str
    tag: str


class SplitRequest(ApiRequestModel):
    source: str
    # A zero-slice split flipped the parent to ``split_parent`` with no
    # children, hiding the transaction from the merged view and every KPI.
    splits: List[SplitItem] = Field(..., min_length=1)


class StatusResponse(BaseModel):
    status: str


class LatestDateResponse(BaseModel):
    latest_date: Optional[str] = None


class UncategorizedCountResponse(BaseModel):
    count: int


@router.get("/")
def get_transactions(
    service: Optional[str] = Query(
        None, description="Filter by service: credit_card, bank, cash"
    ),
    include_split_parents: bool = Query(
        False, description="Whether to include split parents"
    ),
    db: Session = Depends(get_database),
) -> list[dict[str, Any]]:
    """Get all transactions, optionally filtered by service."""
    txn_service = TransactionsService(db)
    try:
        df = txn_service.get_merged_transactions(
            service=service,
            include_split_parents=include_split_parents,
            exclude_services=[Services.INSURANCE.value],
        )
    except ValueError as e:
        # Unknown / malformed `service` query param.
        raise HTTPException(status_code=400, detail=str(e))
    return df.to_dict(orient="records")


@router.post("/", response_model=StatusResponse)
def create_transaction(
    data: TransactionCreate, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Create a new manual transaction."""
    service = TransactionsService(db)
    try:
        service.create_transaction(data.model_dump(), data.service)
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


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
        ``{"status": "no_changes"}`` if nothing changed.
    """
    _validate_source(data.source)
    service = TransactionsService(db)
    try:
        updated = service.update_transaction(
            int(unique_id),
            data.source,
            data.model_dump(exclude={"source"}, exclude_none=True),
        )
        return {"status": "success" if updated else "no_changes"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{unique_id}", response_model=StatusResponse)
def delete_transaction(
    unique_id: str,
    source: str = Query(..., description="The source of the transaction"),
    db: Session = Depends(get_database),
) -> dict[str, str]:
    """Delete a transaction (only for manual entries)."""
    service = TransactionsService(db)
    try:
        service.delete_transaction(int(unique_id), source)
        return {"status": "success"}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


def _reject_unbalanced_splits(
    service: TransactionsService, unique_id: int, data: "SplitRequest"
) -> None:
    """Raise when the split slices don't add up to the parent transaction.

    Parameters
    ----------
    service : TransactionsService
        Service used to look the parent transaction up.
    unique_id : int
        Per-table ID of the transaction being split.
    data : SplitRequest
        The requested split, carrying ``source`` and the slice list.

    Raises
    ------
    ValidationException
        If the slice amounts differ from the parent amount by more than
        ``_SPLIT_SUM_TOLERANCE``.

    Notes
    -----
    A parent that cannot be resolved is left to the service call, which
    reports the missing-parent error with its own message.
    """
    try:
        parent = service.get_transaction(unique_id, data.source)
        parent_amount = float(parent["amount"])
    except (ValueError, KeyError, TypeError):
        return

    total = sum(split.amount for split in data.splits)
    if abs(total - parent_amount) > _SPLIT_SUM_TOLERANCE:
        raise ValidationException(
            f"Split amounts must sum to the transaction amount "
            f"({parent_amount:.2f}); got {total:.2f}"
        )


@router.post("/{unique_id}/split", response_model=StatusResponse)
def split_transaction(
    unique_id: int, data: SplitRequest, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Split a transaction into multiple parts.

    The slice amounts must add up to the parent amount (within a cent) —
    the same invariant the split modal enforces client-side. Without the
    server-side check a crafted payload silently inflated every total that
    reads the merged view.
    """
    _validate_source(data.source)
    service = TransactionsService(db)
    _reject_unbalanced_splits(service, unique_id, data)
    try:
        splits = [s.model_dump() for s in data.splits]
        service.split_transaction(unique_id, data.source, splits)
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{unique_id}/split", response_model=StatusResponse)
def revert_split(
    unique_id: int,
    source: str = Query(..., description="The source of the transaction"),
    db: Session = Depends(get_database),
) -> dict[str, str]:
    """Revert a transaction split."""
    _validate_source(source)
    service = TransactionsService(db)
    try:
        service.revert_split(unique_id, source)
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/bulk-tag", response_model=StatusResponse)
def bulk_tag_transactions(
    data: BulkTagUpdate, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Apply tagging and optional field updates to multiple transactions of the same source."""
    service = TransactionsService(db)
    try:
        service.bulk_tag_transactions(
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
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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
    txn_service = TransactionsService(db)
    try:
        transaction = txn_service.get_transaction(transaction_id, source)
        return transaction.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{transaction_id}/tag", response_model=StatusResponse)
def update_transaction_tag(
    transaction_id: str,
    category: str,
    tag: str,
    service: str = Query(..., description="Service: credit_card, bank, cash"),
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
        Service identifier (``credit_card``, ``bank``, ``cash``) used to
        target the correct table.
    """
    tx_service = TransactionsService(db)
    try:
        tx_service.update_tagging_by_id(service, transaction_id, category, tag)
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
