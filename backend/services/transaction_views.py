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
- **Expense**: on the bank view, everything else but ``Ignore`` — which
  deliberately includes ``Liabilities`` rows with negative amounts (debt
  payments are real money outflows). On the spending view, an expense
  category at any sign (a positive row is a refund) plus debt payments; the
  ``Credit Cards`` bill is left out.

``Ignore`` (a transfer between the household's own accounts) is in neither
view: when only one side of a transfer is tracked, counting it would book
the household's own money as spent or earned.

Insurance deposits and prior-wealth rows are never in a view, and a refund
matched to a purchase the view keeps is netted against it unless the caller
asks for every row at its own amount (``net_refunds=False``). A refund
whose purchase the view leaves out — a card purchase refunded to the bank, on
the bank view — stays as money back: the statement that paid the purchase is
still counted in full.
"""

from dataclasses import dataclass
from datetime import date

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


def _income_mask(df: pd.DataFrame) -> pd.Series:
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


def _investment_mask(df: pd.DataFrame) -> pd.Series:
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

    def between(self, start: date | None, end: date | None) -> "TransactionView":
        """Return the rows dated inside an inclusive window.

        Parameters
        ----------
        start, end : date | None
            Inclusive bounds; ``None`` leaves that side open.

        Returns
        -------
        TransactionView
            The same view narrowed to the window, its months narrowed alike.
        """
        parsed = pd.to_datetime(self.rows["date"])
        keep = pd.Series(True, index=self.rows.index)
        if start is not None:
            keep &= parsed >= pd.Timestamp(start)
        if end is not None:
            keep &= parsed <= pd.Timestamp(end)
        lo = pd.Timestamp(start).strftime("%Y-%m") if start is not None else None
        hi = pd.Timestamp(end).strftime("%Y-%m") if end is not None else None
        months = [
            m
            for m in self.months
            if (lo is None or m >= lo) and (hi is None or m <= hi)
        ]
        return TransactionView(rows=self.rows[keep], months=months)

    def totals(self) -> pd.Series:
        """Sum the whole view, signed the way the cards show it.

        Returns
        -------
        pd.Series
            ``income`` (money in), ``expenses`` (money out, positive) and
            ``investments`` (net deposits, positive).
        """
        amount = TransactionsTableFields.AMOUNT.value
        return pd.Series(
            {
                "income": float(self.income[amount].sum()),
                "expenses": -float(self.expenses[amount].sum()),
                "investments": -float(self.investments[amount].sum()),
            }
        )

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
        net_refunds: bool = True,
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
        net_refunds : bool, optional
            Net linked refunds against their purchases. ``False`` leaves every
            row at its own amount in its own month, and then no purchase is
            taken off for an open expectation either. Defaults to True.

        Returns
        -------
        TransactionView
            The classified bank view.
        """
        return self._view(
            "bank",
            exclude_pending_refunds,
            exclude_projects,
            exclude_liabilities,
            net_refunds,
        )

    def spending(
        self,
        exclude_pending_refunds: bool = True,
        exclude_projects: bool = False,
        exclude_liabilities: bool = False,
        net_refunds: bool = True,
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
        net_refunds : bool, optional
            As for :meth:`bank`. Defaults to True.

        Returns
        -------
        TransactionView
            The classified spending view.
        """
        return self._view(
            "spending",
            exclude_pending_refunds,
            exclude_projects,
            exclude_liabilities,
            net_refunds,
        )

    def tagged_prior_wealth(self) -> float:
        """Sum the bank and cash rows the user tagged as prior wealth.

        Such a row is money the household already had, landing in a tracked
        account — neither view's income. A stored bank or cash prior wealth
        is derived net of every transaction in the account, these rows
        included, so whatever totals the household's starting resources must
        add them back on top.

        Returns
        -------
        float
            The tagged rows' signed total; ``0.0`` when there are none.
        """
        df = self.repo.get_table()
        if df.empty:
            return 0.0
        tagged = df[
            (df[TransactionsTableFields.TAG.value] == PRIOR_WEALTH_TAG)
            & ~df[TransactionsTableFields.SOURCE.value].isin(
                [Tables.CREDIT_CARD.value, Tables.INSURANCE.value]
            )
        ]
        return float(tagged[TransactionsTableFields.AMOUNT.value].sum())

    def _view(
        self,
        name: str,
        exclude_pending_refunds: bool,
        exclude_projects: bool,
        exclude_liabilities: bool,
        net_refunds: bool,
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
                net_refunds,
            ),
            lambda: self._build(
                name,
                exclude_pending_refunds,
                exclude_projects,
                exclude_liabilities,
                net_refunds,
            ),
        )
        return TransactionView(rows=view.rows.copy(), months=list(view.months))

    def _build(
        self,
        name: str,
        exclude_pending_refunds: bool,
        exclude_projects: bool,
        exclude_liabilities: bool,
        net_refunds: bool,
    ) -> TransactionView:
        """Load, net, filter and classify one view's rows."""
        category_col = TransactionsTableFields.CATEGORY.value
        source_col = TransactionsTableFields.SOURCE.value

        df = self.repo.get_table()
        if df.empty:
            return TransactionView(
                rows=df.assign(**{_KIND: pd.Series(dtype=str)}), months=[]
            )

        left_out = [Tables.INSURANCE.value]
        if name == "bank":
            left_out.append(Tables.CREDIT_CARD.value)
        if net_refunds:
            adjustments = PendingRefundsService(self.db).get_refund_amount_adjustments(
                exclude_open=exclude_pending_refunds,
                exclude_tables=frozenset(left_out),
            )
            df = apply_refund_amount_adjustments(df, adjustments)

        if exclude_projects:
            projects = BudgetRepository(self.db).read_project_category_names()
            if projects:
                df = df[~df[category_col].isin(projects)]
        if exclude_liabilities:
            df = df[df[category_col] != LIABILITIES_CATEGORY]

        months = sorted(to_month_series(df["date"]).unique()) if not df.empty else []

        df = df[~df[source_col].isin(left_out)]
        df = df[df[TransactionsTableFields.TAG.value] != PRIOR_WEALTH_TAG]

        income = _income_mask(df)
        investment = _investment_mask(df)
        if name == "bank":
            expense = ~income & ~investment & (df[category_col] != IGNORE_CATEGORY)
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
