"""Shared income/investment/expense classification for transaction frames.

Single source of truth for the category masks described in
``.claude/rules/kpi_calculations.md``. Previously this logic was duplicated
across AnalysisService, TransactionsService, and (inline, twice)
BudgetService — any change to the Liabilities-override rule needed four
edits and the copies could drift.

Classification rules
--------------------
- **Income**: category in ``IncomeCategories``, or ``Liabilities`` with a
  positive amount (loan receipt).
- **Investment**: category is exactly ``Investments``.
- **Expense**: everything else — which deliberately includes ``Liabilities``
  rows with negative amounts (debt payments are real money outflows).
"""

import pandas as pd

from backend.constants.categories import (
    CREDIT_CARDS,
    IGNORE_CATEGORY,
    INVESTMENTS_CATEGORY,
    LIABILITIES_CATEGORY,
    IncomeCategories,
)

INCOME_CATEGORY_VALUES: list[str] = [c.value for c in IncomeCategories]

# Categories excluded when selecting expense rows by category (budget views,
# category breakdowns). Note: intentionally excludes the bank-side
# ``Credit Cards`` bill category — itemized CC purchases carry the real
# category detail (see kpi_calculations.md → "Credit Card Deduplication").
# ``Ignore`` is excluded too: it marks internal transfers and CC bill
# summaries, which are not spending and must never consume budget.
EXPENSE_EXCLUDED_CATEGORIES: list[str] = [
    INVESTMENTS_CATEGORY,
    LIABILITIES_CATEGORY,
    CREDIT_CARDS,
    IGNORE_CATEGORY,
    *INCOME_CATEGORY_VALUES,
]

# The base non-expense set used when partitioning a frame into
# expenses/investments/income/liabilities groups (no Credit Cards here —
# the partition keys on category type, not on CC dedup).
NON_EXPENSE_BASE_CATEGORIES: list[str] = [
    INVESTMENTS_CATEGORY,
    LIABILITIES_CATEGORY,
    *INCOME_CATEGORY_VALUES,
]


def income_mask(df: pd.DataFrame) -> pd.Series:
    """Boolean mask of income rows.

    A row is income if its category is in ``IncomeCategories``, or its
    category is ``Liabilities`` with a positive amount (loan receipt).

    Parameters
    ----------
    df : pd.DataFrame
        Transactions frame with at least ``category`` and ``amount`` columns.

    Returns
    -------
    pd.Series
        Boolean Series aligned with ``df``.
    """
    return df["category"].isin(INCOME_CATEGORY_VALUES) | (
        (df["category"] == LIABILITIES_CATEGORY) & (df["amount"] > 0)
    )


def investment_mask(df: pd.DataFrame) -> pd.Series:
    """Boolean mask of investment rows (category is exactly ``Investments``).

    Parameters
    ----------
    df : pd.DataFrame
        Transactions frame with at least a ``category`` column.

    Returns
    -------
    pd.Series
        Boolean Series aligned with ``df``.
    """
    return df["category"] == INVESTMENTS_CATEGORY


def transactions_masks(df: pd.DataFrame) -> dict[str, pd.Series]:
    """Income/investments/expenses masks for a transactions frame.

    Parameters
    ----------
    df : pd.DataFrame
        Transactions frame with ``category`` and ``amount`` columns.

    Returns
    -------
    dict[str, pd.Series]
        Keys ``"income"``, ``"investments"``, ``"expenses"`` mapping to
        boolean Series aligned with ``df``. Expenses is the complement of
        the other two — so negative-amount ``Liabilities`` rows (debt
        payments) land in expenses.
    """
    income = income_mask(df)
    investments = investment_mask(df)
    return {
        "income": income,
        "investments": investments,
        "expenses": ~income & ~investments,
    }
