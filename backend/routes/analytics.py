"""
Analytics API routes.

Provides endpoints for financial analysis and reporting.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.repositories.transactions_repository import TransactionsRepository

router = APIRouter()


@router.get("/overview")
async def get_overview(
    db: Session = Depends(get_database)
):
    """
    Get a financial overview including totals and latest data date.
    """
    repo = TransactionsRepository(db)
    
    # Get latest dates
    dates = []
    for table in repo.tables:
        date = repo.get_latest_date_from_table(table)
        if date:
            dates.append(date)
    
    # Get transaction counts
    all_transactions = repo.get_table()
    
    return {
        "latest_data_date": max(dates).isoformat() if dates else None,
        "total_transactions": len(all_transactions),
        "tables": repo.tables
    }


@router.get("/income-outcome")
async def get_income_outcome(
    year: Optional[int] = None,
    month: Optional[int] = None,
    db: Session = Depends(get_database)
):
    """
    Get income vs outcome analysis.
    
    Note: This is a simplified version - full implementation would
    integrate with the analysis services from the original app.
    """
    repo = TransactionsRepository(db)
    df = repo.get_table()
    
    if df.empty:
        return {
            "total_income": 0,
            "total_outcome": 0,
            "net": 0
        }
    
    # Simple income/outcome calculation based on amount sign
    income = df[df['amount'] > 0]['amount'].sum() if 'amount' in df.columns else 0
    outcome = abs(df[df['amount'] < 0]['amount'].sum()) if 'amount' in df.columns else 0
    
    return {
        "total_income": float(income),
        "total_outcome": float(outcome),
        "net": float(income - outcome)
    }


@router.get("/by-category")
async def get_expenses_by_category(
    db: Session = Depends(get_database)
):
    """
    Get expenses grouped by category.
    """
    repo = TransactionsRepository(db)
    df = repo.get_table()
    
    if df.empty or 'category' not in df.columns:
        return []
    
    # Filter to expenses only (negative amounts)
    expenses = df[df['amount'] < 0].copy() if 'amount' in df.columns else df
    
    # Group by category
    if not expenses.empty and 'category' in expenses.columns:
        grouped = expenses.groupby('category')['amount'].sum().abs()
        return [
            {"category": cat, "amount": float(amt)}
            for cat, amt in grouped.items()
            if cat is not None
        ]
    
    return []
