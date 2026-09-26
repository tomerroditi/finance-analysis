"""Inputs to the savings-goal allocation engine.

Provides ``InputsMixin``: the goals in waterfall order, the per-month
realized surplus and goal-linked amounts derived from transactions (the
*context*), live investment backing, and the free-cash pool that predates
every goal. Mixed into ``SavingsGoalService`` (see ``core.py``).
"""

from typing import Any

import pandas as pd

from backend.constants.categories import PRIOR_WEALTH_TAG
from backend.constants.tables import TransactionsTableFields
from backend.models.savings_goal import (
    LINK_CONTRIBUTION,
    LINK_UTILIZATION,
    SavingsGoal,
)
from backend.services.bank_balance_service import BankBalanceService
from backend.services.cash_balance_service import CashBalanceService
from backend.services.investments import InvestmentsService
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

#: ``(source_table, unique_id, split_id)`` — identifies one analysis row.
_RowKey = tuple[Any, Any, int | None]

#: ``(goal_id, link_type, signed)`` — how one row counts toward a goal.
#: ``signed`` rows keep their direction (a refund nets against the purchases
#: it repays); the rest count by magnitude, as an explicit link always has.
_GoalLink = tuple[int, str, bool]


class InputsMixin:
    """Context-building and pool-input methods for ``SavingsGoalService``."""

    def _goals_in_order(self) -> list[SavingsGoal]:
        """Return every goal (active and closed) in waterfall order."""
        df = self.repo.get_all()
        if df.empty:
            return []
        ids = df.sort_values(["priority", "id"])["id"].tolist()
        return [self.repo.get(int(i)) for i in ids]

    def _investment_backing(self) -> dict[int, float]:
        """Value every goal's investment earmarks, as ``{goal_id: amount}``.

        A holding is valued live (``calculate_current_balance``), so an earmark
        tracks the market and falls to zero the moment the investment is
        closed — which is exactly what should happen when the user finally
        sells it and the proceeds show up as cash instead.

        Earmarks against one holding are resolved oldest first: explicit
        amounts take their share in creation order, and an earmark with no
        amount claims whatever is left. A holding that loses value therefore
        shortchanges the most recent claim rather than silently over-earmarking
        itself.

        Returns
        -------
        dict[int, float]
            Backing per goal. Goals with no earmarks are absent.
        """
        if self._backing_cache is not None:
            return self._backing_cache

        backings = self.repo.get_backings()
        totals: dict[int, float] = {}
        if backings.empty:
            self._backing_cache = totals
            return totals

        investments = InvestmentsService(self.db)
        for investment_id, group in backings.groupby("investment_id"):
            remaining = float(investments.calculate_current_balance(int(investment_id)))
            explicit = group[group["amount"].notna()]
            whole = group[group["amount"].isna()]
            for row in explicit.itertuples(index=False):
                take = min(float(row.amount), max(0.0, remaining))
                totals[int(row.goal_id)] = totals.get(int(row.goal_id), 0.0) + take
                remaining -= take
            for row in whole.itertuples(index=False):
                take = max(0.0, remaining)
                totals[int(row.goal_id)] = totals.get(int(row.goal_id), 0.0) + take
                remaining = 0.0

        self._backing_cache = totals
        return totals

    def _opening_free_cash(self) -> float:
        """Return the liquid money that existed before any transaction was tracked.

        Bank and cash *prior wealth* is exactly that opening balance — each
        account stores ``current balance - sum(its tracked transactions)`` —
        so walking the realized surplus forward from here reconstructs the
        liquid balance, the same way the net-worth chart does. Investment
        prior wealth is deliberately left out: money sitting in an investment
        is not free cash, which is also why transfers into one reduce the
        pool as they happen.

        Returns
        -------
        float
            Combined bank + cash prior wealth, ``0.0`` when neither is set up.
        """
        bank = BankBalanceService(self.db).get_total_prior_wealth()
        cash = CashBalanceService(self.db).get_total_prior_wealth()
        return float(bank) + float(cash)

    def _pool_before(self, month: tuple[int, int], context: dict[str, Any]) -> float:
        """Return the free cash at the start of ``month``, when no goal has started yet.

        Prior wealth walked forward through every month before ``month``,
        floored at zero month by month.

        Parameters
        ----------
        month : tuple
            ``(year, month)`` the pool is measured at the start of.
        context : dict
            The transaction context from :meth:`_build_context`.

        Returns
        -------
        float
            The pool, never negative.
        """
        free_cash = self._opening_free_cash()
        for month_seen in sorted(context["surplus"]):
            if month_seen >= month:
                break
            free_cash = max(0.0, free_cash + context["surplus"][month_seen])
        return free_cash

    def _build_context(self) -> dict[str, Any]:
        """Compute per-month surplus and per-month goal-linked amounts, memoised.

        Goal-linked transactions are pulled out of the surplus calculation
        before it runs, then reintroduced explicitly — a contribution consumes
        the pool, a utilization draws down what was set aside earlier. Leaving
        them in would deduct the same shekel twice.

        Returns
        -------
        dict
            ``surplus`` — ``{(year, month): float}``; ``direct`` and
            ``utilized`` — ``{(year, month): {goal_id: amount}}``.
        """
        if self._context_cache is not None:
            return self._context_cache
        self._context_cache = self._compute_context()
        return self._context_cache

    def _compute_context(self) -> dict[str, Any]:
        """Do the actual transaction scan behind :meth:`_build_context`."""
        df = self.transactions_service.get_data_for_analysis()
        empty: dict[str, Any] = {"surplus": {}, "direct": {}, "utilized": {}}
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

        keys = self._row_keys(df)
        goal_of = self._goal_by_transaction(df, keys)
        df["_goal_id"] = [goal_of.get(k, (None, None, False))[0] for k in keys]
        df["_link_type"] = [goal_of.get(k, (None, None, False))[1] for k in keys]
        df["_signed"] = [goal_of.get(k, (None, None, False))[2] for k in keys]

        # A card purchase only ever reaches the goals as money spent out of
        # one. The bank-side bill that paid for it is already inside the
        # surplus, so the purchase hands that amount back to the month it was
        # made in — otherwise the same shekel would leave both the pool and
        # the goal.
        is_card = df[source_col] == _CREDIT_CARD_SOURCE
        card_spent = df[is_card & (df["_link_type"] == LINK_UTILIZATION)]
        df = df[~is_card]

        linked = pd.concat([df[df["_goal_id"].notna()], card_spent])
        unlinked = df[df["_goal_id"].isna()]

        surplus: dict[tuple[int, int], float] = {}
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

        handed_back = card_spent.groupby(["_year", "_month"])[amount_col].sum()
        for (y, m), spent in handed_back.items():
            key = (int(y), int(m))
            surplus[key] = surplus.get(key, 0.0) - float(spent)

        direct: dict[tuple[int, int], dict[int, float]] = {}
        utilized: dict[tuple[int, int], dict[int, float]] = {}
        for _, row in linked.iterrows():
            key = (int(row["_year"]), int(row["_month"]))
            goal_id = int(row["_goal_id"])
            raw = float(row[amount_col])
            amount = -raw if row["_signed"] else abs(raw)
            bucket = direct if row["_link_type"] == LINK_CONTRIBUTION else utilized
            bucket.setdefault(key, {})
            bucket[key][goal_id] = bucket[key].get(goal_id, 0.0) + amount

        return {"surplus": surplus, "direct": direct, "utilized": utilized}

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
        """Map each linked transaction key to its ``(goal_id, link_type, signed)``.

        Explicit per-transaction links win over both category/tag rules, so a
        single correction on one transaction always beats the broad rule, and
        a utilization rule wins over a contribution rule on the same row.

        A utilization rule claims its rows from the goal's start month on.
        Spending that predates the goal was never paid for out of it, so it
        stays an ordinary expense of the month it happened in. When two goals'
        rules match one row, the goal higher in the waterfall takes it.

        Parameters
        ----------
        df : pd.DataFrame
            Analysis rows.
        keys : list
            :meth:`_row_keys` of ``df``, positionally aligned with it.

        Returns
        -------
        dict
            Row key -> ``(goal_id, link_type, signed)`` for every linked row.
        """
        mapping: dict[_RowKey, _GoalLink] = {}

        category_col = TransactionsTableFields.CATEGORY.value
        tag_col = TransactionsTableFields.TAG.value

        for goal in self._goals_in_order():
            if not goal.contribution_category:
                continue
            matches = df[category_col] == goal.contribution_category
            tags = self._split_tags(goal.contribution_tags)
            if tags and tags != [_ALL_TAGS] and tag_col in df.columns:
                matches &= df[tag_col].isin(tags)
            for key, matched in zip(keys, matches, strict=True):
                if matched:
                    mapping[key] = (goal.id, LINK_CONTRIBUTION, False)

        row_months = list(zip(df["_year"], df["_month"], strict=True))
        # Walked bottom-up so the goal higher in the waterfall writes last.
        for goal in reversed(self._goals_in_order()):
            if not goal.utilization_category:
                continue
            start = month_key(goal.start_month)
            matches = df[category_col] == goal.utilization_category
            tags = self._split_tags(goal.utilization_tags)
            if tags and tags != [_ALL_TAGS] and tag_col in df.columns:
                matches &= df[tag_col].isin(tags)
            for key, matched, row_month in zip(keys, matches, row_months, strict=True):
                if matched and (start is None or row_month >= start):
                    mapping[key] = (goal.id, LINK_UTILIZATION, True)

        links = self.repo.get_links()
        if not links.empty:
            for _, link in links.iterrows():
                if link["source_type"] == "split":
                    key = (None, None, int(link["source_id"]))
                    for candidate in keys:
                        if candidate[2] == key[2]:
                            mapping[candidate] = (
                                int(link["goal_id"]),
                                link["link_type"],
                                False,
                            )
                else:
                    for candidate in keys:
                        if candidate[0] == link["source_table"] and str(
                            candidate[1]
                        ) == str(link["source_id"]):
                            mapping[candidate] = (
                                int(link["goal_id"]),
                                link["link_type"],
                                False,
                            )
        return mapping

    @staticmethod
    def _split_tags(tags: str | None) -> list[str]:
        """Split the semicolon-separated tag string budgets also use."""
        if not tags:
            return []
        return [t.strip() for t in str(tags).split(";") if t.strip()]
