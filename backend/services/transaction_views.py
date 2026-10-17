"""The household's transactions, read one of two ways and classified once.

A **bank view** is what the tracked accounts did: bank and cash rows, with a
credit-card statement counted as the one bank debit that paid it. A
**spending view** is purchases one by one: card purchases included, the
bank-side ``Credit Cards`` bill left out. ``CONTEXT.md`` defines both; this
module is the only place their rules live, so a figure computed from a view
cannot drift from another figure computed from the same view.

Every row of a view is **income**, **expense** or **investment** (see
``.claude/rules/kpi_calculations.md``):

- **Income**: category in ``IncomeCategories``, or ``Liabilities`` with a
  positive amount (loan receipt).
- **Investment**: category is exactly ``Investments``.
- **Expense**: on the bank view, everything else — which deliberately
  includes ``Liabilities`` rows with negative amounts (debt payments are real
  money outflows). On the spending view, an expense category at any sign (a
  positive row is a refund) plus debt payments; ``Ignore`` and the
  ``Credit Cards`` bill are left out.

Insurance deposits and prior-wealth rows are never in a view, and a refund
matched to its purchase is always netted against it.
"""

from dataclasses import dataclass

import pandas as pd
from sqlalchemy.orm import Session

from backend.constants.categories import (
    CREDIT_CARDS,
    IGNORE_CATEGORY,
    INVESTMENTS_CATEGORY,
    LIABILITIES_CATEGORY,
    PRIOR_WEALTH_TAG,
    IncomeCategories,
)
from backend.constants.tables import Tables, TransactionsTableFields
from backend.repositories.budget_repository import BudgetRepository
from backend.repositories.transactions import TransactionsRepository
from backend.services.pending_refunds_service import (
    PendingRefundsService,
    apply_refund_amount_adjustments,
)
from backend.utils import data_cache
from backend.utils.dataframe_dates import to_month_series

INCOME_CATEGORY_VALUES: list[str] = [c.value for c in IncomeCategories]

#: Categories that are never spending: money in, money moved into
#: investments, debt, internal transfers (``Ignore``) and the bank-side card
#: bill (its purchases are itemized on the card itself).
NON_EXPENSE_CATEGORIES: list[str] = [
    INVESTMENTS_CATEGORY,
    LIABILITIES_CATEGORY,
    CREDIT_CARDS,
    IGNORE_CATEGORY,
    *INCOME_CATEGORY_VALUES,
]

INCOME = "income"
EXPENSE = "expense"
INVESTMENT = "investment"

_KIND = "kind"
_MONTH = "month"


def income_mask(df: pd.DataFrame) -> pd.Series:
    """Return a boolean mask of income rows.

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
    """Return a boolean mask of investment rows (category is exactly ``Investments``).

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
    """Return the income/investments/expenses masks of the bank-view rules.

    Parameters
    ----------
    df : pd.DataFrame
        Transactions frame with ``category`` and ``amount`` columns.

    Returns
    -------
    dict[str, pd.Series]
        Keys ``"income"``, ``"investments"``, ``"expenses"`` mapping to
        boolean Series aligned with ``df``. Expenses is the complement of the
        other two.
    """
    income = income_mask(df)
    investments = investment_mask(df)
    return {
        "income": income,
        "investments": investments,
        "expenses": ~income & ~investments,
    }


@dataclass(frozen=True)
class TransactionView:
    """One view's classified rows.

    Attributes
    ----------
    rows : pd.DataFrame
        Every row the view keeps, refund-netted, with a ``kind`` column of
        ``"income"``, ``"expense"`` or ``"investment"``.
    months : list[str]
        Every ``YYYY-MM`` the household has any transaction in (after the
        view's options), so a month whose only rows the view leaves out — a
        card-only month on the bank view — still reports zeros.
    """

    rows: pd.DataFrame
    months: list[str]

    @property
    def income(self) -> pd.DataFrame:
        """Income rows (positive = money in; a negative row is a reversal)."""
        return self.rows[self.rows[_KIND] == INCOME]

    @property
    def expenses(self) -> pd.DataFrame:
        """Expense rows (negative = money out; a positive row is a refund)."""
        return self.rows[self.rows[_KIND] == EXPENSE]

    @property
    def investments(self) -> pd.DataFrame:
        """Investment rows (negative = a deposit into an investment)."""
        return self.rows[self.rows[_KIND] == INVESTMENT]

    def monthly(self) -> pd.DataFrame:
        """Per-month totals, signed the way the cards show them.

        Returns
        -------
        pd.DataFrame
            Indexed by ``YYYY-MM`` over :attr:`months`, ascending, with columns
            ``income`` (money in), ``expenses`` (money out, positive) and
            ``investments`` (net deposits, positive). Months with no rows of a
            kind read zero.
        """
        if self.rows.empty:
            zeros = [0.0] * len(self.months)
            return pd.DataFrame(
                {"income": zeros, "expenses": zeros, "investments": zeros},
                index=pd.Index(self.months, name=_MONTH),
            )
        totals = (
            self.rows.assign(**{_MONTH: to_month_series(self.rows["date"])})
            .pivot_table(
                index=_MONTH,
                columns=_KIND,
                values=TransactionsTableFields.AMOUNT.value,
                aggfunc="sum",
                fill_value=0.0,
            )
            .reindex(index=self.months, columns=[INCOME, EXPENSE, INVESTMENT])
            .fillna(0.0)
        )
        return pd.DataFrame(
            {
                "income": totals[INCOME],
                "expenses": -totals[EXPENSE],
                "investments": -totals[INVESTMENT],
            },
            index=pd.Index(self.months, name=_MONTH),
        )


class TransactionViews:
    """Reads the household's transactions as a bank view or a spending view.

    Each view is memoised through ``data_cache`` by its options, so the
    dashboard asking for the same view from several cards pays for it once,
    and any write invalidates it.

    Parameters
    ----------
    db : Session
        SQLAlchemy session for database operations.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = TransactionsRepository(db)

    def bank(
        self,
        exclude_pending_refunds: bool = True,
        exclude_projects: bool = False,
        exclude_liabilities: bool = False,
    ) -> TransactionView:
        """Return what the tracked accounts did, card statements as one bank debit.

        Parameters
        ----------
        exclude_pending_refunds : bool, optional
            Also take a purchase still awaiting its refund off what it cost
            (the cards' "Pending Refunds Excluded" chip). Matched refunds are
            netted either way. Defaults to True.
        exclude_projects : bool, optional
            Leave out every row in a project-budget category. Defaults to False.
        exclude_liabilities : bool, optional
            Leave out every ``Liabilities`` row — loan receipts and debt
            payments alike. Defaults to False.

        Returns
        -------
        TransactionView
            The classified bank view.
        """
        return self._view(
            "bank", exclude_pending_refunds, exclude_projects, exclude_liabilities
        )

    def spending(
        self,
        exclude_pending_refunds: bool = True,
        exclude_projects: bool = False,
        exclude_liabilities: bool = False,
    ) -> TransactionView:
        """Return purchases one by one, card bills left out.

        Parameters
        ----------
        exclude_pending_refunds : bool, optional
            As for :meth:`bank`. Defaults to True.
        exclude_projects : bool, optional
            As for :meth:`bank`. Defaults to False.
        exclude_liabilities : bool, optional
            As for :meth:`bank`. Defaults to False.

        Returns
        -------
        TransactionView
            The classified spending view.
        """
        return self._view(
            "spending", exclude_pending_refunds, exclude_projects, exclude_liabilities
        )

    def _view(
        self,
        name: str,
        exclude_pending_refunds: bool,
        exclude_projects: bool,
        exclude_liabilities: bool,
    ) -> TransactionView:
        """Build (or reuse) one view; see :meth:`bank` for the options."""
        view = data_cache.cached(
            self.db,
            (
                "transaction_views",
                name,
                exclude_pending_refunds,
                exclude_projects,
                exclude_liabilities,
            ),
            lambda: self._build(
                name, exclude_pending_refunds, exclude_projects, exclude_liabilities
            ),
        )
        return TransactionView(rows=view.rows.copy(), months=list(view.months))

    def _build(
        self,
        name: str,
        exclude_pending_refunds: bool,
        exclude_projects: bool,
        exclude_liabilities: bool,
    ) -> TransactionView:
        """Load, net, filter and classify one view's rows."""
        category_col = TransactionsTableFields.CATEGORY.value
        source_col = TransactionsTableFields.SOURCE.value

        df = self.repo.get_table()
        if df.empty:
            return TransactionView(
                rows=df.assign(**{_KIND: pd.Series(dtype=str)}), months=[]
            )

        adjustments = PendingRefundsService(self.db).get_refund_amount_adjustments(
            exclude_open=exclude_pending_refunds
        )
        df = apply_refund_amount_adjustments(df, adjustments)

        if exclude_projects:
            projects = BudgetRepository(self.db).read_project_category_names()
            if projects:
                df = df[~df[category_col].isin(projects)]
        if exclude_liabilities:
            df = df[df[category_col] != LIABILITIES_CATEGORY]

        months = sorted(to_month_series(df["date"]).unique()) if not df.empty else []

        left_out = [Tables.INSURANCE.value]
        if name == "bank":
            left_out.append(Tables.CREDIT_CARD.value)
        df = df[~df[source_col].isin(left_out)]
        df = df[df[TransactionsTableFields.TAG.value] != PRIOR_WEALTH_TAG]

        income = income_mask(df)
        investment = investment_mask(df)
        if name == "bank":
            expense = ~income & ~investment
        else:
            expense = ~df[category_col].isin(NON_EXPENSE_CATEGORIES) | (
                (df[category_col] == LIABILITIES_CATEGORY) & (df["amount"] < 0)
            )

        kind = pd.Series(None, index=df.index, dtype=object)
        kind[expense] = EXPENSE
        kind[investment] = INVESTMENT
        kind[income] = INCOME
        rows = df.assign(**{_KIND: kind})
        return TransactionView(rows=rows[rows[_KIND].notna()], months=list(months))
