"""
Transactions API routes.

Provides endpoints for transaction CRUD operations.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.repositories.transactions_repository import TransactionsRepository

router = APIRouter()


@router.get("/")
async def get_transactions(
    service: Optional[str] = Query(None, description="Filter by service: credit_card, bank, cash"),
    db: Session = Depends(get_database)
):
    """Get all transactions, optionally filtered by service."""
    repo = TransactionsRepository(db)
    try:
        df = repo.get_table(service=service)
        return df.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{transaction_id}")
async def get_transaction(
    transaction_id: int,
    db: Session = Depends(get_database)
):
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
    db: Session = Depends(get_database)
):
    """Update category and tag for a transaction."""
    repo = TransactionsRepository(db)
    try:
        if service == "credit_card":
            repo.cc_repo.update_tagging_by_id(transaction_id, category, tag)
        elif service == "bank":
            repo.bank_repo.update_tagging_by_id(transaction_id, category, tag)
        elif service == "cash":
            repo.cash_repo.update_tagging_by_id(transaction_id, category, tag)
        else:
            raise HTTPException(status_code=400, detail="Invalid service")
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/latest-date")
async def get_latest_data_date(
    db: Session = Depends(get_database)
):
    """Get the latest transaction date across all tables."""
    repo = TransactionsRepository(db)
    dates = []
    for table in repo.tables:
        date = repo.get_latest_date_from_table(table)
        if date:
            dates.append(date)
    return {"latest_date": max(dates).isoformat() if dates else None}
