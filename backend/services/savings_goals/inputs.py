"""Transaction inputs of the savings-goal service.

Provides ``InputsMixin``: the goals in list order, and everything the
service reads off transactions (the *context*) — each month's realized
surplus for the yearly savings figure, the dated income and spending each
goal's rules and links claim, and the money moving through the bank and cash
accounts that free cash is measured against. Mixed into
``SavingsGoalService`` (see ``core.py``).
"""

from typing import Any

import pandas as pd

from backend.constants.categories import PRIOR_WEALTH_TAG
from backend.constants.tables import TransactionsTableFields
from backend.models.savings_goal import (
    GOAL_STATUS_CLOSED,
    LINK_CONTRIBUTION,
    LINK_UTILIZATION,
    SavingsGoal,
)
from backend.services.bank_balance_service import BankBalanceService
from backend.services.cash_balance_service import CashBalanceService
from backend.services.savings_goals.common import month_key
from backend.services.transaction_classification import transactions_masks

# Rows synthesised from prior-wealth balances are opening capital, not income.
# Counting them would hand one month an enormous phantom surplus.
_PRIOR_WEALTH_SOURCES = {"bank_balances", "investments"}

# Itemized credit-card rows duplicate the bank-side bill payment, and insurance
# rows are not cash flow. Same exclusion the cashflow analysis applies.
_CREDIT_CARD_SOURCE = "credit_card_transactions"
_SURPLUS_EXCLUDED_SOURCES = {_CREDIT_CARD_SOURCE, "insurance_transactions"}

_ALL_TAGS = "all_tags"

#: The accounts whose money goals and free cash divide between them.
_LIQUID_SOURCES = {"bank_transactions", "cash_transactions"}

#: ``(source_table, unique_id, split_id)`` — identifies one analysis row.
_RowKey = tuple[Any, Any, int | None]

#: ``(goal_id, link_type)`` — how one row counts toward a goal.
_GoalLink = tuple[int, str]


class InputsMixin:
    """Goal order and transaction inputs for ``SavingsGoalService``."""

    def _goals_in_order(self) -> list[SavingsGoal]:
        """Return every goal (active and closed) in list order."""
        df = self.repo.get_all()
        if df.empty:
            return []
        ids = df.sort_values(["priority", "id"])["id"].tolist()
        return [self.repo.get(int(i)) for i in ids]

    def _opening_liquid(self) -> float:
        """Return the bank and cash money that predates every tracked transaction.

        Each account stores ``current balance - sum(its tracked
        transactions)`` as its prior wealth, so this plus every bank and cash
        transaction up to a date is what the accounts held on that date.

        Returns
        -------
        float
            Combined bank and cash prior wealth, ``0.0`` when none is set up.
        """
        bank = BankBalanceService(self.db).get_total_prior_wealth()
        cash = CashBalanceService(self.db).get_total_prior_wealth()
        return float(bank) + float(cash)

    def _build_context(self) -> dict[str, Any]:
        """Read everything the service needs off transactions, memoised.

        Returns
        -------
        dict
            ``surplus`` — ``{(year, month): float}``, income less spending and
            investing of the rows no goal claims; ``direct`` (income a goal
            claims) and ``utilized`` (spending paid out of a goal, refunds
            netted) — ``{(year, month): {goal_id: amount}}``; ``invested`` —
            ``{(year, month): float}``, the net money moved into investments
            outside any goal (withdrawals negative), which the surplus already
            took out; ``events`` — ``[(date, goal_id, link_type, amount)]``,
            the dated rows behind ``direct`` and ``utilized``; and ``liquid``
            — ``{(year, month): float}``, the net of every bank and cash
            transaction that month.
        """
        if self._context_cache is not None:
            return self._context_cache
        self._context_cache = self._compute_context()
        return self._context_cache

    def _compute_context(self) -> dict[str, Any]:
        """Do the actual transaction scan behind :meth:`_build_context`."""
        df = self.transactions_service.get_data_for_analysis()
        empty: dict[str, Any] = {
            "surplus": {},
            "direct": {},
            "utilized": {},
            "invested": {},
            "events": [],
            "liquid": {},
        }
        if df.empty:
            return empty

        source_col = TransactionsTableFields.SOURCE.value
        date_col = TransactionsTableFields.DATE.value
        amount_col = TransactionsTableFields.AMOUNT.value
        tag_col = TransactionsTableFields.TAG.value

        # Card rows stay in the frame for now: they never enter the surplus,
        # but a card purchase can still be paid for out of a goal (below).
        df = df[
            ~df[source_col].isin(
                (_SURPLUS_EXCLUDED_SOURCES - {_CREDIT_CARD_SOURCE})
                | _PRIOR_WEALTH_SOURCES
            )
        ]
        if tag_col in df.columns:
            df = df[df[tag_col] != PRIOR_WEALTH_TAG]
        if df.empty:
            return empty

        df = df.copy()
        parsed = pd.to_datetime(df[date_col], errors="coerce")
        df = df[parsed.notna()]
        if df.empty:
            return empty
        parsed = parsed[parsed.notna()]
        df["_year"] = parsed.dt.year.astype(int)
        df["_month"] = parsed.dt.month.astype(int)
        df["_date"] = parsed.dt.strftime("%Y-%m-%d")

        liquid_rows = df[df[source_col].isin(_LIQUID_SOURCES)]
        liquid = {
            (int(y), int(m)): float(v)
            for (y, m), v in liquid_rows.groupby(["_year", "_month"])[amount_col]
            .sum()
            .items()
        }

        keys = self._row_keys(df)
        goal_of = self._goal_by_transaction(df, keys)
        df["_goal_id"] = [goal_of.get(k, (None, None))[0] for k in keys]
        df["_link_type"] = [goal_of.get(k, (None, None))[1] for k in keys]

        # A card purchase only ever reaches the goals as money spent out of
        # one. The bank-side bill that paid for it is already inside the
        # surplus, so the purchase hands that amount back to the month it was
        # made in — otherwise the same shekel would count against both the
        # month and the goal.
        is_card = df[source_col] == _CREDIT_CARD_SOURCE
        card_spent = df[is_card & (df["_link_type"] == LINK_UTILIZATION)]
        df = df[~is_card]

        linked = pd.concat([df[df["_goal_id"].notna()], card_spent])
        unlinked = df[df["_goal_id"].isna()]

        surplus: dict[tuple[int, int], float] = {}
        invested: dict[tuple[int, int], float] = {}
        if not unlinked.empty:
            masks = transactions_masks(unlinked)
            income = (
                unlinked[masks["income"]].groupby(["_year", "_month"])[amount_col].sum()
            )
            expenses = (
                unlinked[masks["expenses"]]
                .groupby(["_year", "_month"])[amount_col]
                .sum()
            )
            investments = (
                unlinked[masks["investments"]]
                .groupby(["_year", "_month"])[amount_col]
                .sum()
            )
            # Expenses and investments are negative in the raw convention, so
            # summing all three straight through already nets them out.
            combined = income.add(expenses, fill_value=0).add(investments, fill_value=0)
            surplus = {(int(y), int(m)): float(v) for (y, m), v in combined.items()}
            invested = {
                (int(y), int(m)): -float(v) for (y, m), v in investments.items()
            }

        handed_back = card_spent.groupby(["_year", "_month"])[amount_col].sum()
        for (y, m), spent in handed_back.items():
            key = (int(y), int(m))
            surplus[key] = surplus.get(key, 0.0) - float(spent)

        direct: dict[tuple[int, int], dict[int, float]] = {}
        utilized: dict[tuple[int, int], dict[int, float]] = {}
        events: list[tuple[str, int, str, float]] = []
        for _, row in linked.iterrows():
            key = (int(row["_year"]), int(row["_month"]))
            goal_id = int(row["_goal_id"])
            raw = float(row[amount_col])
            # Income counts as it arrives and spending by what it cost, so a
            # refund nets against the purchase it repays.
            if row["_link_type"] == LINK_CONTRIBUTION:
                bucket, amount = direct, raw
            else:
                bucket, amount = utilized, -raw
            bucket.setdefault(key, {})
            bucket[key][goal_id] = bucket[key].get(goal_id, 0.0) + amount
            events.append((row["_date"], goal_id, row["_link_type"], amount))

        return {
            "surplus": surplus,
            "direct": direct,
            "utilized": utilized,
            "invested": invested,
            "events": events,
            "liquid": liquid,
        }

    @staticmethod
    def _row_keys(df: pd.DataFrame) -> list[_RowKey]:
        """Build ``(source_table, unique_id, split_id)`` keys for each row.

        ``unique_id`` is a per-table auto-increment, so it only identifies a
        transaction when paired with its table — see
        ``.claude/rules/backend_repositories.md``.
        """
        source_col = TransactionsTableFields.SOURCE.value
        uid_col = TransactionsTableFields.UNIQUE_ID.value
        split_col = TransactionsTableFields.SPLIT_ID.value
        splits = (
            df[split_col] if split_col in df.columns else pd.Series([None] * len(df))
        )
        return [
            (src, uid, None if pd.isna(sid) else int(sid))
            for src, uid, sid in zip(df[source_col], df[uid_col], splits, strict=True)
        ]

    def _goal_by_transaction(
        self, df: pd.DataFrame, keys: list[_RowKey]
    ) -> dict[_RowKey, _GoalLink]:
        """Map each linked transaction key to its ``(goal_id, link_type)``.

        Explicit per-transaction links win over both category/tag rules, so a
        single correction on one transaction always beats the broad rule, and
        a utilization rule wins over a contribution rule on the same row.

        Rules claim rows from the goal's start month through the month it
        closed in (a closed goal's rules stop there). Spending that predates
        the goal was never paid for out of it, so it stays an ordinary expense
        of the month it happened in. When two goals' rules match one row, the
        goal higher in the list takes it.

        Parameters
        ----------
        df : pd.DataFrame
            Analysis rows.
        keys : list
            :meth:`_row_keys` of ``df``, positionally aligned with it.

        Returns
        -------
        dict
            Row key -> ``(goal_id, link_type)`` for every linked row.
        """
        mapping: dict[_RowKey, _GoalLink] = {}

        category_col = TransactionsTableFields.CATEGORY.value
        tag_col = TransactionsTableFields.TAG.value

        row_months = list(zip(df["_year"], df["_month"], strict=True))
        for goal in self._goals_in_order():
            if not goal.contribution_category:
                continue
            matches = df[category_col] == goal.contribution_category
            tags = self._split_tags(goal.contribution_tags)
            if tags and tags != [_ALL_TAGS] and tag_col in df.columns:
                matches &= df[tag_col].isin(tags)
            span = self._claim_span(goal)
            for key, matched, row_month in zip(keys, matches, row_months, strict=True):
                if matched and self._in_span(row_month, span):
                    mapping.setdefault(key, (goal.id, LINK_CONTRIBUTION))

        # Walked bottom-up so the goal higher in the list writes last.
        for goal in reversed(self._goals_in_order()):
            if not goal.utilization_category:
                continue
            span = self._claim_span(goal)
            matches = df[category_col] == goal.utilization_category
            tags = self._split_tags(goal.utilization_tags)
            if tags and tags != [_ALL_TAGS] and tag_col in df.columns:
                matches &= df[tag_col].isin(tags)
            for key, matched, row_month in zip(keys, matches, row_months, strict=True):
                if matched and self._in_span(row_month, span):
                    mapping[key] = (goal.id, LINK_UTILIZATION)

        links = self.repo.get_links()
        if not links.empty:
            month_of = dict(zip(keys, row_months, strict=True))
            spans = {g.id: self._claim_span(g) for g in self._goals_in_order()}
            for _, link in links.iterrows():
                goal_id = int(link["goal_id"])
                span = spans.get(goal_id, (None, None))
                if link["source_type"] == "split":
                    split_id = int(link["source_id"])
                    matched = [c for c in keys if c[2] == split_id]
                else:
                    matched = [
                        c
                        for c in keys
                        if c[0] == link["source_table"]
                        and str(c[1]) == str(link["source_id"])
                    ]
                for candidate in matched:
                    if self._in_span(month_of[candidate], span):
                        mapping[candidate] = (goal_id, link["link_type"])
        return mapping

    @staticmethod
    def _claim_span(
        goal: SavingsGoal,
    ) -> tuple[tuple[int, int] | None, tuple[int, int] | None]:
        """Return the first and last month a goal's rules and links claim rows in."""
        last = (
            month_key(goal.closed_month) if goal.status == GOAL_STATUS_CLOSED else None
        )
        return month_key(goal.start_month), last

    @staticmethod
    def _in_span(
        month: tuple[int, int],
        span: tuple[tuple[int, int] | None, tuple[int, int] | None],
    ) -> bool:
        """Whether ``month`` falls inside a goal's claim span."""
        first, last = span
        return (first is None or month >= first) and (last is None or month <= last)

    @staticmethod
    def _split_tags(tags: str | None) -> list[str]:
        """Split the semicolon-separated tag string budgets also use."""
        if not tags:
            return []
        return [t.strip() for t in str(tags).split(";") if t.strip()]
