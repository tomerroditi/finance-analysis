"""The running month: how much of it the data has seen, and what it still owes.

Three surfaces ask the same questions about the month in progress — the
dashboard forecast, the budget Overview and the retirement plan's typical
month — and each used to answer them its own way. The Overview counted a bill
as still due from *today*, the forecast from the *last sync*, and the income
side from the day after today, so on a week-old scrape the two cards held back
different bills for the same month. Everything here is the one answer:

- **How far the data reaches** is the scrape audit trail, per account
  (:meth:`RunningMonth.read`), never the last transaction on file: a household
  that spent nothing for three days leaves the same gap at the end of the
  ledger as an account that stopped syncing three days ago, and only one of
  those is missing data.
- **Still due** (:func:`still_due`) is anything expected from the day the data
  reaches through month end, inclusive. A recurring charge or stream that was
  sighted has already rolled its next expected date into a later period, so a
  date in that window has not been seen — whether it falls before today on a
  stale sync or on the sync day itself.
- **A typical month** (:func:`typical`) is the median of the last
  :data:`TREND_MONTHS` complete months: complete, because the running month
  is exactly the one whose accounts are unevenly reported; the median,
  because one sold car or one wedding must not become the baseline.
"""

from dataclasses import dataclass
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from backend.constants.providers import Services

#: Complete months behind every median baseline. Six is long enough for a
#: median to mean something and short enough that a household whose income
#: changed last spring is not still described by what it earned before.
TREND_MONTHS = 6

#: ``(provider, account_name)`` — the pair the scraper writes into both the
#: credential row and every transaction it produces.
AccountKey = tuple[str, str]


def still_due(when: pd.Timestamp, edge: pd.Timestamp, month_end: pd.Timestamp) -> bool:
    """Whether something expected on ``when`` is still owed to the month.

    Parameters
    ----------
    when : pd.Timestamp
        The expected date.
    edge : pd.Timestamp
        The day the data reaches (the weakest sync, or today).
    month_end : pd.Timestamp
        Last day of the running month.

    Returns
    -------
    bool
        True when ``edge <= when <= month_end``.
    """
    return edge <= when <= month_end


def typical(
    months: list[dict[str, Any]],
    key: str,
    today: pd.Timestamp,
    count: int = TREND_MONTHS,
) -> float:
    """Return the median of ``key`` over the last ``count`` complete months.

    Parameters
    ----------
    months : list[dict]
        Monthly rows carrying ``month`` (``YYYY-MM``) and ``key``, oldest
        first — the shape of ``get_income_expenses_over_time``.
    key : str
        The figure to take the median of.
    today : pd.Timestamp
        Reference day; its month and anything after it are left out.
    count : int, optional
        How many complete months to read. Default :data:`TREND_MONTHS`.

    Returns
    -------
    float
        The median, or ``0.0`` with no complete month on record.
    """
    running = today.strftime("%Y-%m")
    recent = [m for m in months if m["month"] < running][-count:]
    if not recent:
        return 0.0
    return float(pd.Series([m[key] for m in recent]).median())


@dataclass(frozen=True)
class RunningMonth:
    """The month containing ``today``, and how far each account has reported it.

    Attributes
    ----------
    today : pd.Timestamp
        Reference day, normalized.
    edges : dict[AccountKey, pd.Timestamp]
        The day each scraped account is synced through. An account with no
        credential (cash, manual entry) is absent: the user types it in, so
        it is never behind.
    """

    today: pd.Timestamp
    edges: dict[AccountKey, pd.Timestamp]

    @classmethod
    def read(cls, db: Session, today: Any = None) -> "RunningMonth":
        """Read the running month's sync edges from the scrape audit trail.

        Insurance is excluded on the same grounds the budget's freshness badge
        excludes it (``useBudgetFreshness``): it is scraped but produces no
        budget transactions, so a stale insurance sync says nothing about how
        complete the month is. An account that has *never* synced is skipped
        rather than treated as infinitely stale — it contributed nothing to
        any baseline either, so counting it would project spending no month in
        the history ever contained.

        Parameters
        ----------
        db : Session
            Database session.
        today : date or pd.Timestamp, optional
            Reference day. Defaults to the current day. A clock-skewed scrape
            row cannot observe past it.

        Returns
        -------
        RunningMonth
            The running month and its per-account edges.
        """
        from backend.services.scraping_history_service import ScrapingHistoryService

        day = pd.Timestamp.today() if today is None else pd.Timestamp(today)
        day = day.normalize()
        edges: dict[AccountKey, pd.Timestamp] = {}
        for entry in ScrapingHistoryService(db).get_last_scrape_dates():
            if entry["service"] == Services.INSURANCE.value:
                continue
            if not entry["last_scrape_date"]:
                continue
            key = (entry["provider"], entry["account_name"])
            synced = min(pd.Timestamp(entry["last_scrape_date"]).normalize(), day)
            # Two credentials on one key would be odd, but the weaker link is
            # the honest answer for the transactions they share.
            edges[key] = min(edges[key], synced) if key in edges else synced
        return cls(today=day, edges=edges)

    @property
    def month_start(self) -> pd.Timestamp:
        """Return the first day of the running month."""
        return self.today.replace(day=1)

    @property
    def month_end(self) -> pd.Timestamp:
        """Return the last day of the running month."""
        return self.today + pd.offsets.MonthEnd(0)

    @property
    def days_in_month(self) -> int:
        """Return the length of the running month."""
        return int(self.today.days_in_month)

    @property
    def observed_through(self) -> pd.Timestamp | None:
        """Return the weakest sync edge, or None when nothing is scraped."""
        return min(self.edges.values()) if self.edges else None

    @property
    def edge(self) -> pd.Timestamp:
        """Return the day the household's data reaches — the weakest link."""
        observed = self.observed_through
        return observed if observed is not None else self.today

    def is_due(self, when: pd.Timestamp) -> bool:
        """Whether something expected on ``when`` is still owed this month."""
        return still_due(pd.Timestamp(when), self.edge, self.month_end)

    def charges_due(self, confirmed: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """List the confirmed recurring charges still due this month.

        Parameters
        ----------
        confirmed : list[dict]
            ``RecurringService.get_confirmed_items()`` — an unreviewed guess
            must never hold money back.

        Returns
        -------
        list[dict]
            ``{label, amount, expected_date}`` per charge, soonest first.
        """
        due = []
        for item in confirmed:
            expected = item.get("next_expected_date")
            if item.get("status") == "ended" or not expected:
                continue
            if not self.is_due(pd.Timestamp(expected)):
                continue
            due.append(
                {
                    "label": item.get("label") or item.get("normalized") or "",
                    "amount": round(float(item.get("amount") or 0.0), 2),
                    "expected_date": str(expected),
                }
            )
        due.sort(key=lambda charge: charge["expected_date"])
        return due

    def unobserved_days(self, edge: pd.Timestamp | None) -> int:
        """Count the days of the running month an account has not reported.

        Parameters
        ----------
        edge : pd.Timestamp or None
            The day it is synced through. None means it is not scraped at all
            and is therefore current by definition.

        Returns
        -------
        int
            Days from the edge to month end.
        """
        if edge is None:
            return self.days_in_month - int(self.today.day)
        if edge < self.month_start:
            return self.days_in_month
        return self.days_in_month - int(edge.day)

    def project(
        self, monthly_baseline: float, shares: dict[AccountKey, float]
    ) -> float:
        """Project a monthly baseline over each account's own unsynced days.

        The household's typical month is split across the accounts that
        produced it (``shares``), and each slice is projected over the days
        *that* account has not reported. A card synced to the 23rd contributes
        seven days; a bank synced to the 5th contributes twenty-five. Rolling
        both into one household-wide window is what made the two
        indistinguishable — and the correction for it (subtracting what the
        fresher account had already reported inside the shared window) let a
        big card purchase cancel out the stale bank's missing direct debits,
        which is a different wrong answer.

        Shares sum to 1, so when every account is equally fresh this collapses
        exactly to ``baseline / days_in_month * unobserved_days``. With no
        history to split (a first month, an empty database), it falls back to
        that whole-household form against the weakest link.

        Parameters
        ----------
        monthly_baseline : float
            Typical spend for a whole month, on the basis being projected.
        shares : dict[AccountKey, float]
            Each account's share of that baseline, summing to 1.

        Returns
        -------
        float
            Projected spend for the rest of the month.
        """
        if monthly_baseline <= 0:
            return 0.0
        daily = monthly_baseline / self.days_in_month
        if not shares:
            return daily * self.unobserved_days(self.observed_through)
        return sum(
            daily * share * self.unobserved_days(self.edges.get(key))
            for key, share in shares.items()
        )
