"""Rule-based financial insight cards.

Produces the short, actionable "insight" cards the dashboard shows — spending
spikes, new subscriptions, price increases, overspend pace, unusually large
transactions. Each insight is returned as a structured ``{code, severity,
data}`` object; the frontend maps ``code`` to a translated, interpolated
message so copy stays bilingual (en/he) without backend string formatting.
"""

import pandas as pd
from sqlalchemy.orm import Session

from backend.constants.categories import NON_EXPENSE_CATEGORIES
from backend.repositories.transactions_repository import TransactionsRepository
from backend.services.analysis_service import AnalysisService
from backend.services.recurring_service import RecurringService


class InsightsService:
    """Derive insight cards from forecast, category trends and recurring data."""

    # Thresholds for surfacing an insight.
    _CATEGORY_SPIKE_RATIO = 1.4
    _CATEGORY_SPIKE_MIN_DELTA = 200.0
    _LARGE_TXN_RATIO = 4.0
    _LARGE_TXN_MIN = 1000.0
    _MAX_INSIGHTS = 8

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

    def get_insights(self) -> list[dict]:
        """Build the prioritized list of insight cards.

        Returns
        -------
        list[dict]
            Up to ``_MAX_INSIGHTS`` insight dicts, each with:

            - ``code`` – stable identifier the frontend maps to a message.
            - ``severity`` – ``positive`` / ``info`` / ``warning``.
            - ``data`` – payload for message interpolation (amounts, labels).
        """
        insights: list[dict] = []
        insights.extend(self._pace_insight())
        insights.extend(self._category_spike_insights())
        insights.extend(self._recurring_insights())
        insights.extend(self._large_transaction_insight())

        # Order: warnings first, then info, then positive — most actionable up top.
        severity_rank = {"warning": 0, "info": 1, "positive": 2}
        insights.sort(key=lambda i: severity_rank.get(i["severity"], 1))
        return insights[: self._MAX_INSIGHTS]

    def _pace_insight(self) -> list[dict]:
        """Flag whether the month is on pace to over- or under-spend."""
        forecast = self.analysis.get_cash_flow_forecast()
        income = forecast["expected_income"]
        expenses = forecast["expected_expenses"]
        if income <= 0:
            return []
        if expenses > income:
            return [{
                "code": "overspendPace",
                "severity": "warning",
                "data": {"amount": round(expenses - income, 2)},
            }]
        if forecast["projected_net"] > 0:
            return [{
                "code": "onTrack",
                "severity": "positive",
                "data": {"amount": forecast["projected_net"]},
            }]
        return []

    def _category_spike_insights(self) -> list[dict]:
        """Flag categories whose current-month spend is well above their trend."""
        monthly = self.analysis.get_expenses_by_category_over_time()
        if len(monthly) < 2:
            return []

        current_month = pd.Timestamp.today().strftime("%Y-%m")
        current = next((m for m in monthly if m["month"] == current_month), None)
        if current is None:
            return []

        prior = [m for m in monthly if m["month"] < current_month][-3:]
        if not prior:
            return []

        results = []
        for category, amount in current["categories"].items():
            prior_vals = [m["categories"].get(category, 0.0) for m in prior]
            if not prior_vals:
                continue
            avg = sum(prior_vals) / len(prior_vals)
            if avg <= 0:
                continue
            delta = amount - avg
            if amount >= avg * self._CATEGORY_SPIKE_RATIO and delta >= self._CATEGORY_SPIKE_MIN_DELTA:
                results.append({
                    "code": "categorySpike",
                    "severity": "warning",
                    "data": {
                        "category": category,
                        "percent": round((amount / avg - 1) * 100),
                        "amount": round(amount, 2),
                    },
                    "_sort": delta,
                })

        results.sort(key=lambda i: i.pop("_sort"), reverse=True)
        return results[:2]

    def _recurring_insights(self) -> list[dict]:
        """Surface newly detected subscriptions and price changes."""
        results = []
        for item in self.recurring.get_recurring()["items"]:
            if item["status"] == "new":
                results.append({
                    "code": "newRecurring",
                    "severity": "info",
                    "data": {
                        "label": item["label"],
                        "amount": item["amount"],
                        "cadence": item["cadence"],
                    },
                })
            elif item["status"] == "price_changed":
                increased = item["price_change"] > 0
                results.append({
                    "code": "priceIncrease" if increased else "priceDecrease",
                    "severity": "warning" if increased else "info",
                    "data": {
                        "label": item["label"],
                        "delta": abs(item["price_change"]),
                        "amount": item["last_amount"],
                    },
                })
        return results[:3]

    def _large_transaction_insight(self) -> list[dict]:
        """Flag an unusually large single expense in the current month."""
        df = self.repo.get_itemized_transactions()
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
        current_month = pd.Timestamp.today().strftime("%Y-%m")
        this_month = df[df["date_parsed"].dt.strftime("%Y-%m") == current_month]
        if this_month.empty:
            return []

        top = this_month.loc[this_month["amount_abs"].idxmax()]
        if top["amount_abs"] >= median * self._LARGE_TXN_RATIO and top["amount_abs"] >= self._LARGE_TXN_MIN:
            return [{
                "code": "largeTransaction",
                "severity": "info",
                "data": {
                    "label": top.get("description") or top.get("category") or "",
                    "amount": round(float(top["amount_abs"]), 2),
                },
            }]
        return []
