"""Recurring-charge (subscription) and recurring-income detection.

Pure heuristic over scraped transaction history — no open-banking merchant
feed required. Groups transactions by a normalized merchant label and looks
for a stable cadence (monthly through annual) across at least three
occurrences. On the expense side this powers the dashboard subscriptions view
and feeds the insights engine with "new subscription" / "price increase"
signals; on the income side it tells the forecast which money is actually
*due* this month rather than merely typical of recent ones.

Detection only ever produces a *candidate*. A candidate becomes a recurring
charge the rest of the app acts on — committed spend in the budget overview,
the forecast's safe-to-spend, insight cards — only once the user confirms it
(:class:`~backend.repositories.recurring_decisions_repository.RecurringDecisionsRepository`).
Unconfirmed candidates are reported as ``pending`` so the UI can ask, and
dismissed ones are suppressed for good. Income streams carry no verdict — see
:meth:`RecurringService.get_recurring_income` for why the asymmetry is
deliberate.

The detection math itself — normalization, cadence bands, interval spread
and shape, anchoring, amount paths, confidence — is pure and lives in
:mod:`backend.services.recurring_detection`; this service loads the
transactions, applies verdicts and caches.
"""

import copy
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from backend.constants.categories import (
    CREDIT_CARDS,
    IGNORE_CATEGORY,
    INVESTMENTS_CATEGORY,
    LIABILITIES_CATEGORY,
    IncomeCategories,
)
from backend.errors import ValidationException
from backend.repositories.budget_repository import BudgetRepository
from backend.repositories.recurring_decisions_repository import (
    DECISIONS,
    PENDING,
    RecurringDecisionsRepository,
)
from backend.repositories.transactions import TransactionsRepository
from backend.services.recurring_detection import (
    INFLOW,
    OUTFLOW,
    detect_streams,
    normalize,
)
from backend.services.transaction_classification import income_mask
from backend.utils import data_cache


class RecurringService:
    """Detect recurring charges and recurring income from transaction history.

    Parameters
    ----------
    db : Session
        SQLAlchemy session for database operations.
    """

    # Longest period still treated as "once a month" when working out what a
    # stream still owes the running month. The monthly band's own tolerance
    # reaches 35 days, and a 30-day period walks backwards through a 31-day
    # month, so the next expected date alone cannot answer the question.
    _MONTHLY_PERIOD_MAX_DAYS = 35

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = TransactionsRepository(db)
        self.decisions = RecurringDecisionsRepository(db)

    @staticmethod
    def normalize_description(desc: object) -> str:
        """Normalize a description exactly as detection groups it.

        Callers outside this service — the budget overview, which has to decide
        whether a transaction is one of these recurring charges — must group
        descriptions exactly the way detection did, so they normalise through
        here rather than reimplementing the rules.

        Parameters
        ----------
        desc : object
            Raw transaction description (any pandas cell value).

        Returns
        -------
        str
            Normalized lowercase label, or empty string for non-strings.
        """
        return normalize(desc)

    def get_recurring(
        self,
        today: date | pd.Timestamp | None = None,
        include_dismissed: bool = False,
    ) -> dict[str, Any]:
        """Detect recurring-charge candidates across itemized expenses.

        Every candidate carries the user's verdict on it. Nothing here is
        filtered by that verdict except dismissals, which are hidden unless
        asked for — the dashboard needs the pending ones precisely so it can
        ask. Callers that act on recurring charges want
        :meth:`get_confirmed_items` instead.

        Parameters
        ----------
        today : date or pd.Timestamp, optional
            Reference day for the ``new`` / ``ended`` status and the next
            expected date. Defaults to the current day; tests pin it so the
            verdict does not drift with the calendar.
        include_dismissed : bool, optional
            When True, candidates the user dismissed are listed too (so the
            UI can offer to restore one). Default False.

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
              ``ended``), ``price_change`` (signed, 0 if none),
              ``confirmation`` (``confirmed`` / ``pending`` / ``dismissed``),
              ``confidence`` (0..1, how much evidence backs the detection) and
              ``amount_kind`` (``fixed`` for a flat subscription, ``metered``
              for a consumption bill). Sorted by ``monthly_equivalent``
              descending.
            - ``total_monthly`` – sum of ``monthly_equivalent`` across
              **confirmed**, non-ended items. Pending candidates are not
              money the user has agreed is committed, so they are not in it.
            - ``pending_monthly`` – the same sum over pending candidates.
            - ``pending_count``, ``confirmed_count``, ``dismissed_count`` –
              how many candidates fell into each bucket, dismissed ones
              counted whether or not they were listed.
        """
        # Resolved before the cache key so an entry cannot outlive the day it
        # was computed for ("new"/"ended" status and the next expected date
        # all pivot on it).
        today = (
            pd.Timestamp.today() if today is None else pd.Timestamp(today)
        ).normalize()

        return copy.deepcopy(
            data_cache.cached(
                self.db,
                ("recurring.get_recurring", today, include_dismissed),
                lambda: self._detect_recurring(today, include_dismissed),
            )
        )

    def _detect_recurring(
        self, today: pd.Timestamp, include_dismissed: bool
    ) -> dict[str, Any]:
        """Run the detection behind :meth:`get_recurring`'s cache.

        Parameters
        ----------
        today : pd.Timestamp
            Normalized reference day.
        include_dismissed : bool
            Whether dismissed candidates are listed.

        Returns
        -------
        dict
            The summary documented on :meth:`get_recurring`.
        """
        empty: dict[str, Any] = {
            "items": [],
            "total_monthly": 0.0,
            "pending_monthly": 0.0,
            "pending_count": 0,
            "confirmed_count": 0,
            "dismissed_count": 0,
        }

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
        # Time-boxed project budgets (renovation, wedding…) are one-off arcs,
        # not ongoing commitments — keep them out of "recurring".
        exclude += BudgetRepository(self.db).read_project_category_names()

        df = df[~df["category"].isin(exclude)].copy()
        if df.empty:
            return empty

        streams = detect_streams(df, today, OUTFLOW)
        if not streams:
            return empty

        verdicts = self.decisions.get_all()
        items: list[dict[str, Any]] = []
        dismissed_count = 0
        for stream in streams:
            verdict = verdicts.get(stream["normalized"])
            confirmation = verdict.decision if verdict else PENDING
            if confirmation == "dismissed":
                dismissed_count += 1
                if not include_dismissed:
                    continue
            items.append({**stream, "confirmation": confirmation})

        live = [i for i in items if i["status"] != "ended"]
        total_monthly = sum(
            i["monthly_equivalent"] for i in live if i["confirmation"] == "confirmed"
        )
        pending_monthly = sum(
            i["monthly_equivalent"] for i in live if i["confirmation"] == PENDING
        )
        return {
            "items": items,
            "total_monthly": round(total_monthly, 2),
            "pending_monthly": round(pending_monthly, 2),
            "pending_count": sum(1 for i in items if i["confirmation"] == PENDING),
            "confirmed_count": sum(
                1 for i in items if i["confirmation"] == "confirmed"
            ),
            "dismissed_count": dismissed_count,
        }

    def get_recurring_income(
        self, today: date | pd.Timestamp | None = None
    ) -> dict[str, Any]:
        """Detect the household's repeating income streams.

        Salaries, allowances, benefits, a standing transfer — money that
        arrives on a schedule, found with the same cadence machinery that
        finds recurring charges (:func:`~backend.services.recurring_detection.detect_streams`), run over income
        rows instead of expense ones.

        Unlike a recurring *charge*, an income stream carries no user verdict.
        The confirm/dismiss flow exists because a false-positive charge
        silently shrinks safe-to-spend, and the user is the only one who can
        say whether a bill is really a commitment. A stream here is never
        trusted for more than its schedule: what it is worth comes from
        :func:`~backend.services.recurring_detection.expected_amount`, which reads a variable stream at its low end,
        so a false positive nudges the forecast rather than steering it.

        ``Ignore`` rows are out — that category marks transfers between the
        user's own accounts, and a standing transfer from savings into the
        current account is the single most metronomic thing in most histories
        while being no income at all.

        Parameters
        ----------
        today : date or pd.Timestamp, optional
            Reference day for the ``new`` / ``ended`` status and the next
            expected date. Defaults to the current day; tests pin it so the
            verdict does not drift with the calendar.

        Returns
        -------
        dict
            Dictionary with keys:

            - ``items`` – stream dicts shaped like :meth:`get_recurring`'s,
              minus ``confirmation``, plus ``expected_amount`` (what to plan
              around — see :func:`~backend.services.recurring_detection.expected_amount`). Sorted by
              ``monthly_equivalent`` descending.
            - ``total_monthly`` – sum of ``monthly_equivalent`` over the
              non-ended streams.
        """
        today = (
            pd.Timestamp.today() if today is None else pd.Timestamp(today)
        ).normalize()

        return copy.deepcopy(
            data_cache.cached(
                self.db,
                ("recurring.get_recurring_income", today),
                lambda: self._detect_income(today),
            )
        )

    def _detect_income(self, today: pd.Timestamp) -> dict[str, Any]:
        """Run the detection behind :meth:`get_recurring_income`'s cache.

        Parameters
        ----------
        today : pd.Timestamp
            Normalized reference day.

        Returns
        -------
        dict
            The summary documented on :meth:`get_recurring_income`.
        """
        empty: dict[str, Any] = {"items": [], "total_monthly": 0.0}

        df = self.repo.get_itemized_transactions()
        if df.empty:
            return empty

        df = df[income_mask(df) & (df["category"] != IGNORE_CATEGORY)]
        if df.empty:
            return empty

        streams = detect_streams(df, today, INFLOW)
        total_monthly = sum(
            s["monthly_equivalent"] for s in streams if s["status"] != "ended"
        )
        return {"items": streams, "total_monthly": round(total_monthly, 2)}

    def get_income_due_remaining(
        self, today: date | pd.Timestamp | None = None
    ) -> dict[str, Any]:
        """Return the recurring income still expected before the end of ``today``'s month.

        The income half of ``committed_remaining``: what the forecast may add
        to money already in hand without guessing. A monthly stream is due
        once a month, so what it still owes is its expected amount less
        whatever it has already paid this month — which also absorbs the drift
        of a 30-day period against a 31-day month, where the next expected date
        slides out of the month the payment will actually land in. Longer
        cadences have no such slack and are read straight off their next
        expected date.

        A stream that has gone quiet past its cadence is ``ended`` and owes
        nothing. One merely late still counts: the common reason a live
        monthly stream has not shown up yet is that the account behind it has
        not been scraped since it did.

        Parameters
        ----------
        today : date or pd.Timestamp, optional
            Reference day. Defaults to the current day.

        Returns
        -------
        dict
            Dictionary with keys:

            - ``amount`` – total still expected this month.
            - ``items`` – the contributing streams, each
              ``{label, normalized, amount, cadence, expected_date}``, largest
              first.
            - ``has_streams`` – whether any income stream is live at all.
              Distinct from ``amount > 0``: a salary already banked this month
              leaves nothing due while still being exactly the evidence a
              caller needs to prefer detection over a trend.
        """
        today = (
            pd.Timestamp.today() if today is None else pd.Timestamp(today)
        ).normalize()
        month_start = today.replace(day=1)
        month_end = today + pd.offsets.MonthEnd(0)

        streams = self.get_recurring_income(today=today)["items"]
        live = [s for s in streams if s["status"] != "ended"]
        if not live:
            return {"amount": 0.0, "items": [], "has_streams": False}

        received = self._income_received_this_month(month_start, today)

        items = []
        for stream in live:
            expected = float(stream["expected_amount"])
            next_expected = pd.Timestamp(stream["next_expected_date"])
            if stream["period_days"] <= self._MONTHLY_PERIOD_MAX_DAYS:
                due = expected - received.get(stream["normalized"], 0.0)
                expected_date = min(max(next_expected, today), month_end)
            elif today < next_expected <= month_end:
                due = expected
                expected_date = next_expected
            else:
                continue
            if due <= 0:
                continue
            items.append(
                {
                    "label": stream["label"],
                    "normalized": stream["normalized"],
                    "amount": round(due, 2),
                    "cadence": stream["cadence"],
                    "expected_date": expected_date.strftime("%Y-%m-%d"),
                }
            )

        items.sort(key=lambda i: i["amount"], reverse=True)
        return {
            "amount": round(sum(i["amount"] for i in items), 2),
            "items": items,
            "has_streams": True,
        }

    def _income_received_this_month(
        self, month_start: pd.Timestamp, today: pd.Timestamp
    ) -> dict[str, float]:
        """Sum the income banked so far this month, per stream key.

        Parameters
        ----------
        month_start : pd.Timestamp
            First day of the running month.
        today : pd.Timestamp
            Last day to count, inclusive.

        Returns
        -------
        dict[str, float]
            Normalized merchant key -> net inflow so far this month.
        """
        df = self.repo.get_itemized_transactions()
        if df.empty:
            return {}
        df = df[income_mask(df) & (df["category"] != IGNORE_CATEGORY)]
        if df.empty:
            return {}
        parsed = pd.to_datetime(df["date"]).dt.normalize()
        df = df[(parsed >= month_start) & (parsed <= today)]
        if df.empty:
            return {}
        df = df.assign(norm=df["description"].apply(normalize))
        totals = df.groupby("norm")["amount"].sum()
        return {k: float(v) for k, v in totals.items() if v > 0}

    def get_confirmed_items(
        self, today: date | pd.Timestamp | None = None
    ) -> list[dict[str, Any]]:
        """Return only the recurring charges the user has confirmed.

        The single entry point for everything that *acts* on a recurring
        charge — committed spend in the budget overview, the forecast's
        safe-to-spend, the insight cards. A candidate the user has not ruled
        on yet is a guess, and a guess must not move a number the user is
        budgeting against.

        Parameters
        ----------
        today : date or pd.Timestamp, optional
            Reference day, forwarded to :meth:`get_recurring`.

        Returns
        -------
        list[dict]
            Confirmed items, in the same shape :meth:`get_recurring` returns.
        """
        return [
            item
            for item in self.get_recurring(today)["items"]
            if item["confirmation"] == "confirmed"
        ]

    def set_decisions(
        self, decisions: list[dict[str, Any]]
    ) -> dict[str, list[dict[str, str]]]:
        """Record several verdicts at once (the "confirm all" path).

        A pure write. It deliberately does **not** run detection to check
        that each key is one detection currently produces, which is what it
        used to do — and what made every verdict cost a full detection pass,
        on a cache its own previous commit had just discarded, seconds of it
        on a real database.

        That check was also wrong on its own terms. A verdict is keyed by the
        normalized label precisely so it can outlive detection: it survives
        new charges, re-detection and amount drift, and a key detection does
        not produce *today* is exactly the case the design is for — the row
        waits, inert, until it does. Rejecting it turned a slightly stale
        list in the browser into a 404, which the card showed as the verdict
        springing back to "needs review". The sibling verdict endpoint,
        insight dismissal, has always stored its key without recomputing
        anything to justify it.

        Parameters
        ----------
        decisions : list[dict]
            Each entry ``{"normalized": str, "decision": str}``, plus the
            optional ``label`` / ``amount`` / ``cadence`` the client
            displayed when the user ruled. Those are stored for audit and
            read by nothing, so they are never worth computing server-side;
            omitted, they leave whatever the last verdict recorded.

        Returns
        -------
        dict
            ``{"updated": [...]}`` — the verdicts that were stored.

        Raises
        ------
        ValidationException
            If any ``decision`` is not one of the three accepted values, or
            any key is blank. Validated before anything is written, so a bad
            entry leaves the whole batch unapplied.
        """
        accepted = (*DECISIONS, PENDING)
        entries = []
        for entry in decisions:
            decision = entry["decision"]
            if decision not in accepted:
                raise ValidationException(
                    f"Invalid decision '{decision}'. "
                    f"Expected one of: {', '.join(accepted)}."
                )
            normalized = (entry.get("normalized") or "").strip()
            if not normalized:
                raise ValidationException(
                    "A verdict needs the normalized merchant key it applies to."
                )
            entries.append(
                {
                    "normalized": normalized,
                    "decision": decision,
                    "label": entry.get("label"),
                    "amount": entry.get("amount"),
                    "cadence": entry.get("cadence"),
                }
            )

        self.decisions.apply(entries)
        return {
            "updated": [
                {"normalized": e["normalized"], "decision": e["decision"]}
                for e in entries
            ]
        }
