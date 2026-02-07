"""
Transactions API routes.

Provides endpoints for transaction CRUD operations.
"""

from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.naming_conventions import PROTECTED_TAGS
from backend.repositories.transactions_repository import (
    ManualTransactionDTO,
    TransactionsRepository,
)
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
):
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
):
    """Create a new manual transaction."""
    repo = TransactionsRepository(db)
    service = TransactionsService(db)
    try:
        if data.service not in ["cash", "manual_investments"]:
            raise HTTPException(
                status_code=400,
                detail="Can only create cash or manual_investments transactions",
            )

        tx = ManualTransactionDTO(
            date=datetime.combine(data.date, datetime.min.time()),
            account_name=data.account_name,
            description=data.description,
            amount=data.amount,
            provider=data.provider,
            account_number=data.account_number,
            category=data.category if data.category != "" else None,
            tag=data.tag if data.tag != "" else None,
        )
        success = repo.add_transaction(tx, data.service)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to create transaction")

        # Sync prior wealth offset
        service.sync_prior_wealth_offset()

        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{unique_id}")
async def update_transaction(
    unique_id: str, data: TransactionUpdate, db: Session = Depends(get_database)
):
    """Update a transaction with source-based constraints."""
    repo = TransactionsRepository(db)
    try:
        target_repo = repo.get_repo_by_source(data.source)

        # Enforce constraints
        is_manual = data.source in ["cash", "manual_investment_transactions"]

        updates = {}
        if is_manual:
            if data.description is not None:
                updates["description"] = data.description
            if data.amount is not None:
                updates["amount"] = data.amount
            if data.provider is not None:
                updates["provider"] = data.provider

        # Everyone can update tagging
        if data.category is not None:
            updates["category"] = data.category if data.category != "" else None
        if data.tag is not None:
            updates["tag"] = data.tag if data.tag != "" else None

        if not updates:
            return {"status": "no_changes"}

        success = target_repo.update_transaction_by_unique_id(int(unique_id), updates)
        if not success:
            raise HTTPException(
                status_code=404, detail="Transaction not found or update failed"
            )
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{unique_id}")
async def delete_transaction(
    unique_id: str,
    source: str = Query(..., description="The source of the transaction"),
    db: Session = Depends(get_database),
):
    """Delete a transaction (only for manual entries)."""
    repo = TransactionsRepository(db)
    service = TransactionsService(db)
    try:
        if source not in ["cash_transactions", "manual_investment_transactions"]:
            raise HTTPException(
                status_code=403,
                detail=f"Deletion of {source} transactions is prohibited",
            )

        # Get the source-specific repository
        target_repo = repo.get_repo_by_source(source)

        # Look up the transaction in the source-specific table
        tx_record = db.execute(
            select(target_repo.model).where(
                target_repo.model.unique_id == int(unique_id)
            )
        ).scalar_one_or_none()

        if not tx_record:
            raise HTTPException(status_code=404, detail="Transaction not found")

        # Convert to dict for tag/account_name checks
        tx = {
            "tag": getattr(tx_record, "tag", None),
            "account_name": getattr(tx_record, "account_name", None),
        }

        # Protect "Prior Wealth" offset transactions from manual deletion
        if (
            tx
            and tx.get("tag") in PROTECTED_TAGS
            and tx.get("account_name") in PROTECTED_TAGS
        ):
            raise HTTPException(
                status_code=403,
                detail=f"Cannot manually delete system-generated {tx.get('tag')} transaction",
            )

        success = target_repo.delete_transaction_by_unique_id(unique_id)
        if not success:
            raise HTTPException(
                status_code=404, detail="Transaction not found or deletion failed"
            )

        # Sync prior wealth offset after deletion
        service.sync_prior_wealth_offset()

        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{unique_id}/split")
async def split_transaction(
    unique_id: int, data: SplitRequest, db: Session = Depends(get_database)
):
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
):
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
):
    """Apply tagging to multiple transactions of the same source."""
    repo = TransactionsRepository(db)
    try:
        tx_list = [
            {"unique_id": uid, "source": data.source} for uid in data.transaction_ids
        ]
        repo.bulk_update_tagging(
            tx_list,
            data.category if data.category != "" else None,
            data.tag if data.tag != "" else None,
        )
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{transaction_id}")
async def get_transaction(transaction_id: int, db: Session = Depends(get_database)):
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
):
    """Update category and tag for a transaction (Legacy support)."""
    repo = TransactionsRepository(db)
    try:
        repo.update_tagging_by_id(
            service,
            transaction_id,
            category if category != "" else None,
            tag if tag != "" else None,
        )
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/latest-date")
async def get_latest_data_date(db: Session = Depends(get_database)):
    """Get the latest transaction date across all tables."""
    repo = TransactionsRepository(db)
    dates = []
    for table in repo.tables:
        date = repo.get_latest_date_from_table(table)
        if date:
            dates.append(date)
    return {"latest_date": max(dates).isoformat() if dates else None}
