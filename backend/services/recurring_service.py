"""Recurring-charge (subscription) detection.

Pure heuristic over scraped transaction history — no open-banking merchant
feed required. Groups expense transactions by a normalized merchant label and
looks for a stable cadence (weekly/monthly/quarterly/annual) across at least
three occurrences. This powers the dashboard subscriptions view and feeds the
insights engine with "new subscription" / "price increase" signals.
"""

import re

import pandas as pd
from sqlalchemy.orm import Session

from backend.constants.categories import (
    CREDIT_CARDS,
    IGNORE_CATEGORY,
    INVESTMENTS_CATEGORY,
    LIABILITIES_CATEGORY,
    IncomeCategories,
)
from backend.repositories.transactions_repository import TransactionsRepository


class RecurringService:
    """Detect recurring charges from itemized transaction history."""

    # (name, expected period in days). Ordered shortest-first.
    _CADENCES = [
        ("weekly", 7),
        ("monthly", 30),
        ("quarterly", 91),
        ("annual", 365),
    ]
    # A median interval is accepted as a cadence when within this relative band.
    _CADENCE_TOLERANCE = 0.35
    # Relative amount change that counts as a price change.
    _PRICE_CHANGE_THRESHOLD = 0.10

    def __init__(self, db: Session):
        """Initialize the recurring service.

        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.db = db
        self.repo = TransactionsRepository(db)

    @staticmethod
    def _normalize(desc) -> str:
        """Normalize a transaction description into a merchant grouping key.

        Strips digits, punctuation and collapses whitespace so that
        ``"NETFLIX 1234"`` and ``"NETFLIX.COM 9981"`` group together. Hebrew
        and other unicode word characters are preserved.

        Parameters
        ----------
        desc : Any
            Raw transaction description.

        Returns
        -------
        str
            Normalized lowercase label, or empty string for non-strings.
        """
        if not isinstance(desc, str):
            return ""
        s = desc.lower()
        s = re.sub(r"\d+", " ", s)
        s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def _match_cadence(self, interval_days: float) -> tuple[str, int] | None:
        """Match a median interval to the closest known cadence.

        Parameters
        ----------
        interval_days : float
            Median number of days between occurrences.

        Returns
        -------
        tuple[str, int] or None
            ``(cadence_name, period_days)`` or None if no cadence fits.
        """
        best = None
        best_rel = self._CADENCE_TOLERANCE
        for name, days in self._CADENCES:
            rel = abs(interval_days - days) / days
            if rel < best_rel:
                best_rel = rel
                best = (name, days)
        return best

    def get_recurring(self) -> dict:
        """Detect recurring charges across all itemized expense transactions.

        Returns
        -------
        dict
            Dictionary with keys:

            - ``items`` – list of recurring-charge dicts, each with
              ``label``, ``normalized``, ``amount`` (median, positive),
              ``last_amount``, ``cadence``, ``period_days``,
              ``monthly_equivalent``, ``occurrences``, ``category``,
              ``first_date``, ``last_date``, ``next_expected_date``,
              ``status`` (``active`` / ``new`` / ``price_changed`` /
              ``ended``) and ``price_change`` (signed, 0 if none).
              Sorted by ``monthly_equivalent`` descending.
            - ``total_monthly`` – sum of ``monthly_equivalent`` across all
              non-ended items.
        """
        empty = {"items": [], "total_monthly": 0.0}

        df = self.repo.get_itemized_transactions()
        if df.empty:
            return empty

        exclude = [
            CREDIT_CARDS,
            IGNORE_CATEGORY,
            INVESTMENTS_CATEGORY,
            LIABILITIES_CATEGORY,
            *IncomeCategories._value2member_map_.keys(),
        ]
        df = df[~df["category"].isin(exclude)]
        df = df[df["amount"] < 0].copy()
        if df.empty:
            return empty

        df["date_parsed"] = pd.to_datetime(df["date"]).dt.normalize()
        df["norm"] = df["description"].apply(self._normalize)
        df = df[df["norm"] != ""]
        if df.empty:
            return empty

        today = pd.Timestamp.today().normalize()
        items: list[dict] = []

        for norm, group in df.groupby("norm"):
            group = group.sort_values("date_parsed")
            dates = group["date_parsed"].drop_duplicates().reset_index(drop=True)
            if len(dates) < 3:
                continue

            diffs = dates.diff().dropna().dt.days
            median_interval = float(diffs.median())
            cadence = self._match_cadence(median_interval)
            if cadence is None:
                continue
            cadence_name, period_days = cadence

            amounts = group["amount"].abs()
            amount = float(amounts.median())
            last_amount = float(abs(group.iloc[-1]["amount"]))
            first_date = dates.iloc[0]
            last_date = dates.iloc[-1]
            next_expected = last_date + pd.Timedelta(days=period_days)

            # Status: ended if overdue past 1.5 periods, new if it only
            # started within the last ~2 periods.
            age_since_last = (today - last_date).days
            age_since_first = (today - first_date).days
            status = "active"
            if age_since_last > period_days * 1.5:
                status = "ended"
            elif age_since_first <= period_days * 3:
                status = "new"

            # Price change: latest amount vs median of prior occurrences.
            price_change = 0.0
            prior = amounts.iloc[:-1]
            if len(prior) >= 1:
                prior_med = float(prior.median())
                if prior_med > 0 and abs(last_amount - prior_med) / prior_med > self._PRICE_CHANGE_THRESHOLD:
                    price_change = round(last_amount - prior_med, 2)
                    if status == "active":
                        status = "price_changed"

            label_mode = group["description"].mode()
            label = label_mode.iloc[0] if not label_mode.empty else norm
            cat_mode = group["category"].dropna().mode()
            category = cat_mode.iloc[0] if not cat_mode.empty else None

            monthly_equivalent = amount * 30.0 / period_days

            items.append({
                "label": label,
                "normalized": norm,
                "amount": round(amount, 2),
                "last_amount": round(last_amount, 2),
                "cadence": cadence_name,
                "period_days": period_days,
                "monthly_equivalent": round(monthly_equivalent, 2),
                "occurrences": int(len(group)),
                "category": category,
                "first_date": first_date.strftime("%Y-%m-%d"),
                "last_date": last_date.strftime("%Y-%m-%d"),
                "next_expected_date": next_expected.strftime("%Y-%m-%d"),
                "status": status,
                "price_change": price_change,
            })

        items.sort(key=lambda i: i["monthly_equivalent"], reverse=True)
        total_monthly = sum(i["monthly_equivalent"] for i in items if i["status"] != "ended")
        return {"items": items, "total_monthly": round(total_monthly, 2)}
