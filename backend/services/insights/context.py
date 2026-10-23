"""The shared, per-request inputs every insight rule reads.

A card has to earn its slot: it must be **unexplained** and **material**.

*Unexplained* — money the user already planned to spend is not news. A project
budget is a deliberate lump of spending (a renovation *should* dwarf its own
history), a yearly envelope is deliberately lumpy across months (the annual
insurance premium lands in one of them), a category still inside its monthly
budget is behaving, and a confirmed recurring charge is a bill the user has
already told us to expect. ``PlannedSpend``, ``envelope_rows`` and
``confirmed_recurring_keys`` are how a rule asks about each.

*Material* — every floor scales with the household's own spending
(``spending_baseline``), so the same 200 does not shout at a 5,000/month budget
and whisper at a 50,000 one.
"""

from dataclasses import dataclass
from functools import cached_property
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from backend.constants.budget import (
    AMOUNT,
    CATEGORY,
    MONTH,
    PERIOD_MONTHLY,
    PERIOD_PROJECT,
    PERIOD_TYPE,
    PERIOD_YEARLY,
    TOTAL_BUDGET,
    YEAR,
)
from backend.repositories.insight_dismissals_repository import (
    InsightDismissalsRepository,
)
from backend.services.analysis import AnalysisService
from backend.services.budget import ledger
from backend.services.budget.core import BudgetService
from backend.services.recurring_service import RecurringService
from backend.services.transaction_views import TransactionViews

Card = dict[str, Any]
RowKey = tuple[Any, Any, Any]


@dataclass(frozen=True)
class PlannedSpend:
    """The spending the user has already committed to, by category.

    Attributes
    ----------
    project_categories : frozenset[str]
        Categories owned by a project budget (open or closed).
    yearly_categories : frozenset[str]
        Categories claimed by a yearly envelope for the running year.
    monthly_budgets : dict[str, float]
        Category -> total budgeted for the running month across its monthly
        rules. ``Total Budget`` is excluded: it is a roll-up, not a category.
    """

    project_categories: frozenset[str]
    yearly_categories: frozenset[str]
    monthly_budgets: dict[str, float]

    @classmethod
    def from_rules(cls, rules: pd.DataFrame, today: pd.Timestamp) -> "PlannedSpend":
        """Read the planned spend for ``today``'s month off the budget rules.

        Parameters
        ----------
        rules : pd.DataFrame
            Every budget rule, as ``BudgetService.get_all_rules`` returns them.
        today : pd.Timestamp
            Fixes the running year and month.

        Returns
        -------
        PlannedSpend
            The categories and amounts the budget already accounts for.
        """
        if rules.empty:
            return cls(frozenset(), frozenset(), {})
        projects = frozenset(
            rules.loc[rules[PERIOD_TYPE] == PERIOD_PROJECT, CATEGORY].dropna()
        )
        yearly = frozenset(
            rules.loc[
                (rules[PERIOD_TYPE] == PERIOD_YEARLY) & (rules[YEAR] == today.year),
                CATEGORY,
            ].dropna()
        )
        month_rules = rules.loc[
            (rules[PERIOD_TYPE] == PERIOD_MONTHLY)
            & (rules[YEAR] == today.year)
            & (rules[MONTH] == today.month)
            & (rules[CATEGORY] != TOTAL_BUDGET)
        ]
        budgets = {
            str(category): float(amount)
            for category, amount in month_rules.groupby(CATEGORY)[AMOUNT].sum().items()
        }
        return cls(projects, yearly, budgets)

    def is_long_envelope(self, category: object) -> bool:
        """Return whether ``category`` belongs to a project or yearly envelope.

        Both are budgets the user deliberately spreads unevenly over months,
        so a month-over-month comparison says nothing about them.
        """
        if not isinstance(category, str):
            return False
        return category in self.project_categories or category in self.yearly_categories

    def within_monthly_budget(self, category: object, spent: float) -> bool:
        """Return whether ``category`` has a monthly budget ``spent`` fits inside."""
        if not isinstance(category, str):
            return False
        budget = self.monthly_budgets.get(category, 0.0)
        return budget > 0 and spent <= budget


def row_keys(rows: pd.DataFrame) -> list[RowKey]:
    """Return each row's ``(source, unique_id, split_id)`` identity.

    ``unique_id`` is per-table and a split shares its parent's, so all three
    are needed to name one row.
    """
    split_ids = (
        [None if pd.isna(s) else int(s) for s in rows["split_id"]]
        if "split_id" in rows.columns
        else [None] * len(rows)
    )
    return list(zip(rows["source"], rows["unique_id"], split_ids, strict=True))


class InsightContext:
    """Everything the insight rules read, computed at most once per request.

    Every rule needs the forecast, the budget rules or the recurring
    detection, and each is expensive enough that recomputing it once per rule
    would be the dominant cost of the strip — so each input is a cached
    property. A test replaces one by assigning it on the instance
    (``ctx.forecast = {...}``) before a rule reads it.

    Parameters
    ----------
    db : Session
        SQLAlchemy session for database operations.
    today : pd.Timestamp | None
        The day the strip is built for; defaults to today.
    """

    def __init__(self, db: Session, today: pd.Timestamp | None = None) -> None:
        self.db = db
        self.today = (today if today is not None else pd.Timestamp.today()).normalize()
        self.month = self.today.strftime("%Y-%m")
        self.dismissals = InsightDismissalsRepository(db)

    @cached_property
    def analysis(self) -> AnalysisService:
        """Return the analysis service behind the forecast and category trends."""
        return AnalysisService(self.db)

    @cached_property
    def recurring(self) -> RecurringService:
        """Return the recurring-charge detector."""
        return RecurringService(self.db)

    @cached_property
    def views(self) -> TransactionViews:
        """Return the refund-netted transaction views."""
        return TransactionViews(self.db)

    @cached_property
    def budget(self) -> BudgetService:
        """Return the budget service behind the rules and the claim ledger."""
        return BudgetService(self.db)

    @cached_property
    def forecast(self) -> dict[str, Any]:
        """Return this month's cash-flow forecast."""
        return self.analysis.get_cash_flow_forecast()

    @cached_property
    def spending_baseline(self) -> float:
        """Return the typical monthly outflow every materiality floor scales by."""
        baseline = float(self.forecast.get("avg_monthly_expenses") or 0.0)
        if baseline <= 0:
            baseline = float(self.forecast.get("expected_expenses") or 0.0)
        return max(baseline, 0.0)

    @cached_property
    def planned(self) -> PlannedSpend:
        """Return the categories and amounts the budget already accounts for."""
        return PlannedSpend.from_rules(self.budget.get_all_rules(), self.today)

    @cached_property
    def envelope_rows(self) -> set[RowKey]:
        """Return the rows a project or yearly envelope owns.

        Read off the budget ledger, so it is tag- and override-aware: a yearly
        rule on one tag of a category leaves its siblings unexplained.
        """
        claims = ledger.of_kind(
            self.budget.get_claims(), ledger.KIND_PROJECT, ledger.KIND_YEARLY
        )
        return set(row_keys(claims))

    @cached_property
    def recurring_summary(self) -> dict[str, Any]:
        """Return recurring detection for this request."""
        return self.recurring.get_recurring()

    @cached_property
    def confirmed_recurring_keys(self) -> set[str]:
        """Return the merchant keys of charges the user confirmed as recurring."""
        return {
            item["normalized"]
            for item in self.recurring_summary["items"]
            if item.get("confirmation") == "confirmed" and item.get("normalized")
        }

    @cached_property
    def monthly_category_spend(self) -> list[dict[str, Any]]:
        """Return monthly expense totals per category."""
        return self.analysis.get_expenses_by_category_over_time()

    @cached_property
    def project_spend_this_month(self) -> float:
        """Return what the running month's project budgets have drawn so far."""
        projects = self.planned.project_categories
        if not projects:
            return 0.0
        current = next(
            (m for m in self.monthly_category_spend if m["month"] == self.month),
            None,
        )
        if current is None:
            return 0.0
        return sum(
            amount
            for category, amount in current["categories"].items()
            if category in projects
        )

    @cached_property
    def dismissed(self) -> set[str]:
        """Return the insight keys the user has waved away."""
        return self.dismissals.get_keys()

    def visible(self, cards: list[Card]) -> list[Card]:
        """Drop dismissed cards, before a rule's own cap picks winners.

        Filtering here rather than at the end means a dismissal frees the slot
        it occupied: wave away the top spike and the runner-up takes its place,
        instead of the strip simply getting shorter.
        """
        return [card for card in cards if card["key"] not in self.dismissed]
