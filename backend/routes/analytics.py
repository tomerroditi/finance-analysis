"""
Analytics API routes.

Provides endpoints for financial analysis and reporting.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.repositories.transactions_repository import TransactionsRepository
from fad.app.naming_conventions import NonExpensesCategories, IncomeCategories

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
    
    # Filter to valid transactions (not Ignored)
    valid_df = df[df['category'] != NonExpensesCategories.IGNORE.value]
    
    # Calculate income: positive amounts in Salary/Other Income OR just all positive amounts (simpler)
    # Actually, the convention is usually that anything positive is income unless ignored.
    income = valid_df[valid_df['amount'] > 0]['amount'].sum() if 'amount' in valid_df.columns else 0
    
    # Calculate outcome: negative amounts that are NOT in Savings, Investments, or Liabilities
    # Since these are transfers, not expenses.
    non_expense_vals = [
        NonExpensesCategories.SAVINGS.value,
        NonExpensesCategories.INVESTMENTS.value,
        NonExpensesCategories.LIABILITIES.value
    ]
    
    outcome_mask = (valid_df['amount'] < 0) & (~valid_df['category'].isin(non_expense_vals))
    outcome = abs(valid_df[outcome_mask]['amount'].sum()) if 'amount' in valid_df.columns else 0
    
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
    
    # Filter to expenses: negative amounts excluding non-expense categories
    non_expense_vals = [
        NonExpensesCategories.SAVINGS.value,
        NonExpensesCategories.INVESTMENTS.value,
        NonExpensesCategories.LIABILITIES.value,
        NonExpensesCategories.IGNORE.value
    ]
    
    expense_mask = (df['amount'] < 0) & (~df['category'].isin(non_expense_vals))
    expenses = df[expense_mask].copy() if 'amount' in df.columns else df
    
    # Group by category
    if not expenses.empty and 'category' in expenses.columns:
        grouped = expenses.groupby('category')['amount'].sum().abs()
        return [
            {"category": cat, "amount": float(amt)}
            for cat, amt in grouped.items()
            if cat is not None
        ]
    
    return []


@router.get("/monthly-trend")
async def get_monthly_trend(
    db: Session = Depends(get_database)
):
    """
    Get monthly income and outcome trends.
    """
    repo = TransactionsRepository(db)
    df = repo.get_table()
    
    if df.empty or 'date' not in df.columns:
        return []
    
    # Convert date to month-year
    df['month'] = df['date'].dt.strftime('%Y-%m')
    
    # Calculate income and outcome per month respecting conventions
    trend = []
    non_expense_vals = [
        NonExpensesCategories.SAVINGS.value,
        NonExpensesCategories.INVESTMENTS.value,
        NonExpensesCategories.LIABILITIES.value,
        NonExpensesCategories.IGNORE.value
    ]
    
    for month, group in df.groupby('month'):
        income = group[group['amount'] > 0]['amount'].sum() if 'amount' in group.columns else 0
        
        outcome_mask = (group['amount'] < 0) & (~group['category'].isin(non_expense_vals))
        outcome = abs(group[outcome_mask]['amount'].sum()) if 'amount' in group.columns else 0
        
        trend.append({
            "month": month,
            "income": float(income),
            "outcome": float(outcome)
        })
    
    return sorted(trend, key=lambda x: x['month'])
