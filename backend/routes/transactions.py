"""
Transactions API routes.

Provides endpoints for transaction CRUD operations.
"""

from datetime import date
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.repositories.transactions_repository import TransactionsRepository
from backend.services.transactions_service import TransactionsService

router = APIRouter()


class TransactionCreate(BaseModel):
    date: date
    description: str
    amount: float
    account_name: str
    provider: Optional[str] = None
    account_number: Optional[str] = None
    category: Optional[str] = None
    tag: Optional[str] = None
    service: str  # 'cash' or 'manual_investments'


class TransactionUpdate(BaseModel):
    description: Optional[str] = None
    amount: Optional[float] = None
    category: Optional[str] = None
    tag: Optional[str] = None
    provider: Optional[str] = None
    source: str


class BulkTagUpdate(BaseModel):
    transaction_ids: List[int]
    source: str
    category: Optional[str]
    tag: Optional[str]


class SplitItem(BaseModel):
    amount: float
    category: str
    tag: str


class SplitRequest(BaseModel):
    source: str
    splits: List[SplitItem]


@router.get("/")
async def get_transactions(
    service: Optional[str] = Query(
        None, description="Filter by service: credit_card, bank, cash"
    ),
    include_split_parents: bool = Query(
        False, description="Whether to include split parents"
    ),
    db: Session = Depends(get_database),
) -> list[dict[str, Any]]:
    """Get all transactions, optionally filtered by service."""
    repo = TransactionsRepository(db)
    try:
        df = repo.get_table(
            service=service, include_split_parents=include_split_parents
        )
        return df.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/")
async def create_transaction(
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


@router.put("/{unique_id}")
async def update_transaction(
    unique_id: str, data: TransactionUpdate, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Update a transaction with source-based constraints."""
    service = TransactionsService(db)
    try:
        updated = service.update_transaction(
            int(unique_id),
            data.source,
            data.model_dump(exclude={"source"}, exclude_none=True),
        )
        return {"status": "success" if updated else "no_changes"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{unique_id}")
async def delete_transaction(
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


@router.post("/{unique_id}/split")
async def split_transaction(
    unique_id: int, data: SplitRequest, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Split a transaction into multiple parts."""
    repo = TransactionsRepository(db)
    try:
        splits = [s.model_dump() for s in data.splits]
        success = repo.split_transaction(unique_id, data.source, splits)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to split transaction")
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{unique_id}/split")
async def revert_split(
    unique_id: int,
    source: str = Query(..., description="The source of the transaction"),
    db: Session = Depends(get_database),
) -> dict[str, str]:
    """Revert a transaction split."""
    repo = TransactionsRepository(db)
    try:
        success = repo.revert_split(unique_id, source)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to revert split")
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bulk-tag")
async def bulk_tag_transactions(
    data: BulkTagUpdate, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Apply tagging to multiple transactions of the same source."""
    service = TransactionsService(db)
    try:
        service.bulk_tag_transactions(
            data.transaction_ids, data.source, data.category, data.tag
        )
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{transaction_id}")
async def get_transaction(
    transaction_id: int, db: Session = Depends(get_database)
) -> dict[str, Any]:
    """Get a specific transaction by ID."""
    repo = TransactionsRepository(db)
    try:
        transaction = repo.get_transaction_by_id(transaction_id)
        return transaction.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{transaction_id}/tag")
async def update_transaction_tag(
    transaction_id: str,
    category: str,
    tag: str,
    service: str = Query(..., description="Service: credit_card, bank, cash"),
    db: Session = Depends(get_database),
) -> dict[str, str]:
    """Update category and tag for a transaction (Legacy support)."""
    tx_service = TransactionsService(db)
    try:
        tx_service.update_tagging_by_id(service, transaction_id, category, tag)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/latest-date")
async def get_latest_data_date(
    db: Session = Depends(get_database),
) -> dict[str, str | None]:
    """Get the latest transaction date across all tables."""
    service = TransactionsService(db)
    latest = service.get_latest_data_date()
    return {"latest_date": latest.isoformat() if latest else None}
