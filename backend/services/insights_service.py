"""Rule-based financial insight cards.

Produces the short, actionable "insight" cards the dashboard shows — spending
spikes, new subscriptions, price increases, overspend pace, unusually large
transactions. Each insight is returned as a structured ``{code, severity,
data}`` object; the frontend maps ``code`` to a translated, interpolated
message so copy stays bilingual (en/he) without backend string formatting.

A card has to earn its slot: it must be **unexplained** and **material**.

*Unexplained* — money the user already planned to spend is not news. A project
budget is a deliberate lump of spending (a renovation *should* dwarf its own
history), a yearly envelope is deliberately lumpy across months (the annual
insurance premium lands in one of them), a category still inside its monthly
budget is behaving, and a confirmed recurring charge is a bill the user has
already told us to expect. Each rule below drops those before it fires.

*Material* — every floor scales with the household's own spending, so the same
200 does not shout at a 5,000/month budget and whisper at a 50,000 one.
"""

from dataclasses import dataclass

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
from backend.constants.categories import NON_EXPENSE_CATEGORIES
from backend.repositories.insight_dismissals_repository import (
    InsightDismissalsRepository,
)
from backend.repositories.transactions_repository import TransactionsRepository
from backend.services.analysis_service import AnalysisService
from backend.services.budget.core import BudgetService
from backend.services.pending_refunds_service import (
    PendingRefundsService,
    apply_refund_amount_adjustments,
)
from backend.services.recurring_service import RecurringService


@dataclass(frozen=True)
class _PlannedSpend:
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

    def is_long_envelope(self, category) -> bool:
        """True when ``category`` belongs to a project or yearly envelope.

        Both are budgets the user deliberately spreads unevenly over months,
        so a month-over-month comparison says nothing about them.
        """
        if not isinstance(category, str):
            return False
        return category in self.project_categories or category in self.yearly_categories

    def within_monthly_budget(self, category, spent: float) -> bool:
        """True when ``category`` has a monthly budget and ``spent`` is inside it."""
        if not isinstance(category, str):
            return False
        budget = self.monthly_budgets.get(category, 0.0)
        return budget > 0 and spent <= budget


class InsightsService:
    """Derive insight cards from forecast, category trends and recurring data."""

    # Thresholds for surfacing an insight. The ``_SHARE`` floors are fractions
    # of the household's typical monthly outflow — an absolute shekel floor
    # alone is either deafening or mute depending on the budget's size.
    _CATEGORY_SPIKE_RATIO = 1.4
    _CATEGORY_SPIKE_MIN_DELTA = 200.0
    _CATEGORY_SPIKE_MIN_SHARE = 0.03
    _CATEGORY_BASELINE_MONTHS = 3
    _CATEGORY_MIN_HISTORY = 2
    _MAX_SPIKES = 2
    _LARGE_TXN_RATIO = 4.0
    _LARGE_TXN_MIN = 1000.0
    _LARGE_TXN_MIN_SHARE = 0.1
    _LARGE_TXN_HISTORY_MONTHS = 6
    _PRICE_CHANGE_MIN_DELTA = 20.0
    _PRICE_CHANGE_MIN_SHARE = 0.1
    _PACE_MIN_SHARE = 0.05
    _MAX_INSIGHTS = 6

    def __init__(self, db: Session):
        """Initialize the insights service.

        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.db = db
        self.analysis = AnalysisService(db)
        self.recurring = RecurringService(db)
        self.repo = TransactionsRepository(db)
        self.budget = BudgetService(db)
        self.dismissals = InsightDismissalsRepository(db)
        # Per-request memo: every rule below needs the forecast, the budget
        # rules or the recurring detection, and each is expensive enough that
        # recomputing it once per rule would be the dominant cost of the card.
        self._cache: dict = {}

    def get_insights(self) -> list[dict]:
        """Build the prioritized list of insight cards.

        Returns
        -------
        list[dict]
            Up to ``_MAX_INSIGHTS`` insight dicts, each with:

            - ``code`` – stable identifier the frontend maps to a message.
            - ``key`` – stable identity of *this* card, for dismissal.
            - ``severity`` – ``positive`` / ``info`` / ``warning``.
            - ``data`` – payload for message interpolation (amounts, labels).
        """
        insights: list[dict] = []
        insights.extend(self._pace_insight())

        spikes = self._category_spike_insights()
        insights.extend(spikes)
        insights.extend(self._recurring_insights())

        # One event, one card: the charge that blew up a category is the same
        # news the spike already delivered.
        spiked = {card["data"]["category"] for card in spikes}
        insights.extend(
            card
            for card in self._large_transaction_insight()
            if card["data"].get("category") not in spiked
        )

        # Order: warnings first, then info, then positive — most actionable up
        # top — and within a band the biggest sum of money first.
        severity_rank = {"warning": 0, "info": 1, "positive": 2}
        insights.sort(
            key=lambda i: (
                severity_rank.get(i["severity"], 1),
                -float(i["data"].get("amount") or 0.0),
            )
        )
        return insights[: self._MAX_INSIGHTS]

    def dismiss(self, key: str) -> dict:
        """Wave one insight card away.

        Parameters
        ----------
        key : str
            The card's ``key``, exactly as ``get_insights`` reported it.

        Returns
        -------
        dict
            ``{key, dismissed}``.
        """
        self.dismissals.dismiss(key)
        return {"key": key, "dismissed": True}

    def restore(self, key: str) -> dict:
        """Undo a dismissal, letting the card come back.

        Parameters
        ----------
        key : str
            The card's ``key``.

        Returns
        -------
        dict
            ``{key, dismissed}``.
        """
        self.dismissals.restore(key)
        return {"key": key, "dismissed": False}

    # ------------------------------------------------------------------
    # Shared, memoized inputs
    # ------------------------------------------------------------------

    def _dismissed(self) -> set[str]:
        """Insight keys the user has waved away (memoized)."""
        if "dismissed" not in self._cache:
            self._cache["dismissed"] = self.dismissals.get_keys()
        return self._cache["dismissed"]

    def _visible(self, cards: list[dict]) -> list[dict]:
        """Drop dismissed cards, before a rule's own cap picks winners.

        Filtering here rather than at the end means a dismissal frees the slot
        it occupied: wave away the top spike and the runner-up takes its place,
        instead of the strip simply getting shorter.
        """
        dismissed = self._dismissed()
        return [card for card in cards if card["key"] not in dismissed]

    def _forecast(self) -> dict:
        """This month's cash-flow forecast (memoized)."""
        if "forecast" not in self._cache:
            self._cache["forecast"] = self.analysis.get_cash_flow_forecast()
        return self._cache["forecast"]

    def _spending_baseline(self) -> float:
        """Typical monthly outflow, the yardstick every materiality floor uses."""
        forecast = self._forecast()
        baseline = float(forecast.get("avg_monthly_expenses") or 0.0)
        if baseline <= 0:
            baseline = float(forecast.get("expected_expenses") or 0.0)
        return max(baseline, 0.0)

    def _planned_spend(self) -> _PlannedSpend:
        """Categories and amounts the user's budget already accounts for."""
        if "planned" in self._cache:
            return self._cache["planned"]

        rules = self.budget.get_all_rules()
        today = pd.Timestamp.today()
        if rules.empty:
            planned = _PlannedSpend(frozenset(), frozenset(), {})
        else:
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
                for category, amount in month_rules.groupby(CATEGORY)[AMOUNT]
                .sum()
                .items()
            }
            planned = _PlannedSpend(projects, yearly, budgets)

        self._cache["planned"] = planned
        return planned

    def _recurring_summary(self) -> dict:
        """Recurring detection for this session (memoized — detection is costly)."""
        if "recurring" not in self._cache:
            self._cache["recurring"] = self.recurring.get_recurring()
        return self._cache["recurring"]

    def _confirmed_recurring_keys(self) -> set[str]:
        """Normalized merchant keys of charges the user confirmed as recurring."""
        if "recurring_keys" not in self._cache:
            self._cache["recurring_keys"] = {
                item["normalized"]
                for item in self._recurring_summary()["items"]
                if item.get("confirmation") == "confirmed" and item.get("normalized")
            }
        return self._cache["recurring_keys"]

    def _net_matched_refunds(self, df: pd.DataFrame) -> pd.DataFrame:
        """Net refunds matched to their purchase out of a transactions frame.

        Parameters
        ----------
        df : pd.DataFrame
            Transactions frame straight from the repository.

        Returns
        -------
        pd.DataFrame
            The frame with ``amount`` netted.
        """
        if "refund_adjustments" not in self._cache:
            self._cache["refund_adjustments"] = PendingRefundsService(
                self.db
            ).get_refund_amount_adjustments(exclude_open=True)
        return apply_refund_amount_adjustments(df, self._cache["refund_adjustments"])

    def _monthly_category_spend(self) -> list[dict]:
        """Monthly expense totals per category (memoized)."""
        if "by_category" not in self._cache:
            self._cache["by_category"] = (
                self.analysis.get_expenses_by_category_over_time()
            )
        return self._cache["by_category"]

    def _project_spend_this_month(self) -> float:
        """What the running month's project budgets have drawn so far."""
        planned = self._planned_spend()
        if not planned.project_categories:
            return 0.0
        current_month = pd.Timestamp.today().strftime("%Y-%m")
        current = next(
            (m for m in self._monthly_category_spend() if m["month"] == current_month),
            None,
        )
        if current is None:
            return 0.0
        return sum(
            amount
            for category, amount in current["categories"].items()
            if category in planned.project_categories
        )

    # ------------------------------------------------------------------
    # Rules
    # ------------------------------------------------------------------

    def _pace_insight(self) -> list[dict]:
        """Flag whether the month is on pace to over- or under-spend.

        A gap smaller than ``_PACE_MIN_SHARE`` of expected income is inside the
        forecast's own error bars, and a gap a running project accounts for is
        the user's own plan playing out — neither is worth a warning.
        """
        forecast = self._forecast()
        income = forecast["expected_income"]
        expenses = forecast["expected_expenses"]
        if income <= 0:
            return []

        floor = income * self._PACE_MIN_SHARE
        month = pd.Timestamp.today().strftime("%Y-%m")
        if expenses > income:
            gap = expenses - income
            if gap < floor or gap <= self._project_spend_this_month():
                return []
            return self._visible(
                [
                    {
                        "code": "overspendPace",
                        "key": f"overspendPace:{month}",
                        "severity": "warning",
                        "data": {"amount": round(gap, 2)},
                    }
                ]
            )
        if forecast["projected_net"] >= floor:
            return self._visible(
                [
                    {
                        "code": "onTrack",
                        "key": f"onTrack:{month}",
                        "severity": "positive",
                        "data": {"amount": forecast["projected_net"]},
                    }
                ]
            )
        return []

    def _category_spike_insights(self) -> list[dict]:
        """Flag categories whose current-month spend is well above their trend.

        Only categories that *have* a trend qualify: a project or yearly
        envelope is lumpy by design, and a category seen in fewer than
        ``_CATEGORY_MIN_HISTORY`` of the baseline months has no normal to
        deviate from. Spend still inside its monthly budget is not a spike
        either — the budget page already owns that conversation.
        """
        monthly = self._monthly_category_spend()
        if len(monthly) < 2:
            return []

        current_month = pd.Timestamp.today().strftime("%Y-%m")
        current = next((m for m in monthly if m["month"] == current_month), None)
        if current is None:
            return []

        prior = [m for m in monthly if m["month"] < current_month][
            -self._CATEGORY_BASELINE_MONTHS :
        ]
        if len(prior) < self._CATEGORY_MIN_HISTORY:
            return []

        planned = self._planned_spend()
        floor = max(
            self._CATEGORY_SPIKE_MIN_DELTA,
            self._spending_baseline() * self._CATEGORY_SPIKE_MIN_SHARE,
        )

        results = []
        for category, amount in current["categories"].items():
            if planned.is_long_envelope(category):
                continue
            prior_vals = [m["categories"].get(category, 0.0) for m in prior]
            if sum(1 for v in prior_vals if v > 0) < self._CATEGORY_MIN_HISTORY:
                continue
            # Median, not mean: one unusual month in the baseline should not
            # redefine "usual" — in either direction.
            baseline = float(pd.Series(prior_vals).median())
            if baseline <= 0:
                continue
            delta = amount - baseline
            if amount < baseline * self._CATEGORY_SPIKE_RATIO or delta < floor:
                continue
            if planned.within_monthly_budget(category, amount):
                continue
            results.append(
                {
                    "code": "categorySpike",
                    "key": f"categorySpike:{category}:{current_month}",
                    "severity": "warning",
                    "data": {
                        "category": category,
                        "percent": round((amount / baseline - 1) * 100),
                        "amount": round(amount, 2),
                    },
                    "_sort": delta,
                }
            )

        results.sort(key=lambda i: i.pop("_sort"), reverse=True)
        return self._visible(results)[: self._MAX_SPIKES]

    def _recurring_insights(self) -> list[dict]:
        """Surface confirmed subscriptions that are new or repriced.

        Also nudges the user when candidates are waiting to be reviewed —
        a detection nobody has ruled on yet is a question, not a finding, so
        it gets one card asking for the ruling rather than one card each.

        A price change has to be worth reading: detection reports any move
        past its own tolerance, but a few shekels on a small subscription is
        drift, not a decision to make.
        """
        summary = self._recurring_summary()
        month = pd.Timestamp.today().strftime("%Y-%m")
        results = []
        if summary["pending_count"]:
            results.append(
                {
                    "code": "recurringToReview",
                    "key": f"recurringToReview:{month}",
                    "severity": "info",
                    "data": {
                        "count": summary["pending_count"],
                        "amount": summary["pending_monthly"],
                    },
                }
            )
        for item in summary["items"]:
            if item["confirmation"] != "confirmed":
                continue
            subject = item.get("normalized") or item["label"]
            if item["status"] == "new":
                results.append(
                    {
                        "code": "newRecurring",
                        "key": f"newRecurring:{subject}",
                        "severity": "info",
                        "data": {
                            "label": item["label"],
                            "amount": item["amount"],
                            "cadence": item["cadence"],
                        },
                    }
                )
            elif item["status"] == "price_changed":
                delta = abs(item["price_change"])
                if delta < max(
                    self._PRICE_CHANGE_MIN_DELTA,
                    abs(item["amount"]) * self._PRICE_CHANGE_MIN_SHARE,
                ):
                    continue
                increased = item["price_change"] > 0
                code = "priceIncrease" if increased else "priceDecrease"
                results.append(
                    {
                        "code": code,
                        # The price itself is part of the identity: a dismissal
                        # covers this change, not the next one.
                        "key": f"{code}:{subject}:{item['last_amount']}",
                        "severity": "warning" if increased else "info",
                        "data": {
                            "label": item["label"],
                            "delta": delta,
                            "amount": item["last_amount"],
                        },
                    }
                )
        return self._visible(results)[:3]

    def _large_transaction_insight(self) -> list[dict]:
        """Flag an unusually large single expense in the current month.

        "Unusual" means unusual *for this household and this category*: a
        charge that no month in the trailing window matched, that no project
        or yearly envelope was opened for, and that is not a bill the user
        already confirmed as recurring (rent and insurance are large every
        time — that is the opposite of news).

        Refunds matched to their purchase are netted out first, on the same
        terms as every other spend surface. A charge that came back in full
        cost nothing and is not news either — before this it still fired a
        card, because the refund landed as its own positive row and the rule
        only ever looked at negative ones. The netting applies to the trailing
        history and the median too, so the comparison stays like for like.
        """
        df = self._net_matched_refunds(self.repo.get_itemized_transactions())
        if df.empty:
            return []

        df = df[~df["category"].isin(NON_EXPENSE_CATEGORIES)]
        df = df[df["amount"] < 0].copy()
        if df.empty:
            return []

        df["amount_abs"] = df["amount"].abs()
        median = float(df["amount_abs"].median())
        if median <= 0:
            return []

        df["date_parsed"] = pd.to_datetime(df["date"])
        month_start = pd.Timestamp.today().normalize().replace(day=1)
        next_month = month_start + pd.DateOffset(months=1)
        this_month = df[
            (df["date_parsed"] >= month_start) & (df["date_parsed"] < next_month)
        ]
        if this_month.empty:
            return []

        history = df[
            (df["date_parsed"] < month_start)
            & (
                df["date_parsed"]
                >= month_start - pd.DateOffset(months=self._LARGE_TXN_HISTORY_MONTHS)
            )
        ]
        planned = self._planned_spend()
        confirmed = self._confirmed_recurring_keys()
        floor = max(
            self._LARGE_TXN_MIN,
            self._spending_baseline() * self._LARGE_TXN_MIN_SHARE,
        )

        for _, row in this_month.sort_values("amount_abs", ascending=False).iterrows():
            amount = float(row["amount_abs"])
            if amount < floor or amount < median * self._LARGE_TXN_RATIO:
                # Sorted high to low — nothing further down can qualify.
                break
            category = row.get("category")
            if planned.is_long_envelope(category):
                continue
            if (
                RecurringService.normalize_description(row.get("description"))
                in confirmed
            ):
                continue
            peers = history.loc[history["category"] == category, "amount_abs"]
            if not peers.empty and amount <= float(peers.max()):
                continue
            # ``unique_id`` is per-table, so the source table is part of the
            # key — bank #5 and credit-card #5 are different charges.
            key = f"largeTransaction:{row.get('source')}:{row.get('unique_id')}"
            if key in self._dismissed():
                continue
            return [
                {
                    "code": "largeTransaction",
                    "key": key,
                    "severity": "info",
                    "data": {
                        "label": row.get("description") or category or "",
                        "amount": round(amount, 2),
                        "category": category if isinstance(category, str) else "",
                    },
                }
            ]
        return []
