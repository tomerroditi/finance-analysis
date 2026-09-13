"""Recurring-charge (subscription) detection.

Pure heuristic over scraped transaction history — no open-banking merchant
feed required. Groups expense transactions by a normalized merchant label and
looks for a stable cadence (weekly/monthly/quarterly/annual) across at least
three occurrences. This powers the dashboard subscriptions view and feeds the
insights engine with "new subscription" / "price increase" signals.

Detection only ever produces a *candidate*. A candidate becomes a recurring
charge the rest of the app acts on — committed spend in the budget overview,
the forecast's safe-to-spend, insight cards — only once the user confirms it
(:class:`~backend.repositories.recurring_decisions_repository.RecurringDecisionsRepository`).
Unconfirmed candidates are reported as ``pending`` so the UI can ask, and
dismissed ones are suppressed for good.
"""

import re
from datetime import date

import pandas as pd
from sqlalchemy.orm import Session

from backend.constants.categories import (
    CREDIT_CARDS,
    IGNORE_CATEGORY,
    INVESTMENTS_CATEGORY,
    LIABILITIES_CATEGORY,
    IncomeCategories,
)
from backend.errors import EntityNotFoundException, ValidationException
from backend.repositories.recurring_decisions_repository import (
    DECISIONS,
    PENDING,
    RecurringDecisionsRepository,
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
    # Gaps between occurrences must be regular: std/median below this. Filters
    # out frequent but irregular shopping (groceries, cafes).
    _MAX_INTERVAL_CV = 0.5
    # A subscription charges roughly the same amount each time. At least
    # ``_MIN_AMOUNT_CONSISTENCY`` of the charges must fall within
    # ``_AMOUNT_BAND`` of the median amount (robust to one legitimate price step).
    _AMOUNT_BAND = 0.20
    _MIN_AMOUNT_CONSISTENCY = 0.6
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
        self.decisions = RecurringDecisionsRepository(db)

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

    @staticmethod
    def normalize_description(desc) -> str:
        """Public entry point to the merchant grouping key.

        Callers outside this service — the budget overview, which has to decide
        whether a transaction is one of these recurring charges — must group
        descriptions exactly the way detection did, so they normalise through
        here rather than reimplementing the rules.

        Parameters
        ----------
        desc : Any
            Raw transaction description.

        Returns
        -------
        str
            Normalized lowercase label, or empty string for non-strings.
        """
        return RecurringService._normalize(desc)

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

    def get_recurring(
        self,
        today: date | pd.Timestamp | None = None,
        include_dismissed: bool = False,
    ) -> dict:
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
              ``ended``), ``price_change`` (signed, 0 if none) and
              ``confirmation`` (``confirmed`` / ``pending`` / ``dismissed``).
              Sorted by ``monthly_equivalent`` descending.
            - ``total_monthly`` – sum of ``monthly_equivalent`` across
              **confirmed**, non-ended items. Pending candidates are not
              money the user has agreed is committed, so they are not in it.
            - ``pending_monthly`` – the same sum over pending candidates.
            - ``pending_count``, ``confirmed_count``, ``dismissed_count`` –
              how many candidates fell into each bucket, dismissed ones
              counted whether or not they were listed.
        """
        empty = {
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
        from backend.services.budget_service import ProjectBudgetService

        exclude += ProjectBudgetService(self.db).get_all_projects_names()

        df = df[~df["category"].isin(exclude)].copy()
        if df.empty:
            return empty

        df["date_parsed"] = pd.to_datetime(df["date"]).dt.normalize()
        df["norm"] = df["description"].apply(self._normalize)
        df = df[df["norm"] != ""]
        if df.empty:
            return empty

        today = (
            pd.Timestamp.today() if today is None else pd.Timestamp(today)
        ).normalize()
        verdicts = self.decisions.get_all()
        items: list[dict] = []
        dismissed_count = 0

        for norm, group in df.groupby("norm"):
            # Net same-day charges and refunds: sum signed amounts per day, then
            # keep only net-outflow days as charge occurrences. A same-day (or
            # same-statement-day) refund shrinks the charge; a fully-refunded day
            # drops out entirely instead of masquerading as a recurring hit.
            daily_net = group.groupby("date_parsed")["amount"].sum().sort_index()
            charges = daily_net[daily_net < 0]
            if len(charges) < 3:
                continue

            dates = charges.index.to_series().reset_index(drop=True)
            # Net charge magnitudes (positive), aligned to date order.
            amounts = pd.Series(-charges.to_numpy())

            diffs = dates.diff().dropna().dt.days
            median_interval = float(diffs.median())
            if median_interval <= 0:
                continue

            # Regular cadence: the gaps themselves must be consistent, not just
            # their median. A merchant visited at random intervals (groceries)
            # has a high spread and is rejected here.
            interval_cv = float(diffs.std(ddof=0)) / median_interval
            if interval_cv > self._MAX_INTERVAL_CV:
                continue

            cadence = self._match_cadence(median_interval)
            if cadence is None:
                continue
            cadence_name, period_days = cadence

            # Stable price: most charges must cluster near the median net amount.
            # Variable-amount spend (a basket of groceries, one-off vendors with
            # wildly different invoices) is rejected here.
            amount = float(amounts.median())
            if amount <= 0:
                continue
            within_band = float((amounts.sub(amount).abs() <= amount * self._AMOUNT_BAND).mean())
            if within_band < self._MIN_AMOUNT_CONSISTENCY:
                continue

            last_amount = float(amounts.iloc[-1])
            first_date = dates.iloc[0]
            last_date = dates.iloc[-1]
            next_expected = last_date + pd.Timedelta(days=period_days)

            # Status: ended if overdue past 1.5 periods, new if it only
            # started within the last 3 periods.
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

            verdict = verdicts.get(norm)
            confirmation = verdict.decision if verdict else PENDING
            if confirmation == "dismissed":
                dismissed_count += 1
                if not include_dismissed:
                    continue

            items.append({
                "label": label,
                "normalized": norm,
                "amount": round(amount, 2),
                "last_amount": round(last_amount, 2),
                "cadence": cadence_name,
                "period_days": period_days,
                "monthly_equivalent": round(monthly_equivalent, 2),
                "occurrences": int(len(charges)),
                "category": category,
                "first_date": first_date.strftime("%Y-%m-%d"),
                "last_date": last_date.strftime("%Y-%m-%d"),
                "next_expected_date": next_expected.strftime("%Y-%m-%d"),
                "status": status,
                "price_change": price_change,
                "confirmation": confirmation,
            })

        items.sort(key=lambda i: i["monthly_equivalent"], reverse=True)
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

    def get_confirmed_items(
        self, today: date | pd.Timestamp | None = None
    ) -> list[dict]:
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

    def set_decision(
        self,
        normalized: str,
        decision: str,
        today: date | pd.Timestamp | None = None,
    ) -> dict:
        """Record the user's verdict on one detected candidate.

        Parameters
        ----------
        normalized : str
            Normalized merchant key, exactly as detection reported it.
        decision : str
            ``'confirmed'``, ``'dismissed'``, or ``'pending'`` to undo a
            previous verdict and put the candidate back up for review.
        today : date or pd.Timestamp, optional
            Reference day, forwarded to detection when looking the candidate
            up.

        Returns
        -------
        dict
            ``{normalized, decision}``.

        Raises
        ------
        ValidationException
            If ``decision`` is not one of the three accepted values.
        EntityNotFoundException
            If no detected candidate carries that key. Confirming something
            detection never produced would create a verdict nothing can ever
            act on, which reads to the user as the click having done nothing.
        """
        if decision not in (*DECISIONS, PENDING):
            raise ValidationException(
                f"Invalid decision '{decision}'. "
                f"Expected one of: {', '.join((*DECISIONS, PENDING))}."
            )

        candidate = next(
            (
                item
                for item in self.get_recurring(today, include_dismissed=True)["items"]
                if item["normalized"] == normalized
            ),
            None,
        )
        if candidate is None:
            raise EntityNotFoundException(
                f"No detected recurring charge named '{normalized}'."
            )

        if decision == PENDING:
            self.decisions.clear(normalized)
        else:
            self.decisions.set_decision(
                normalized,
                decision,
                label=candidate["label"],
                amount=candidate["amount"],
                cadence=candidate["cadence"],
            )
        return {"normalized": normalized, "decision": decision}

    def set_decisions(
        self, decisions: list[dict], today: date | pd.Timestamp | None = None
    ) -> dict:
        """Record several verdicts at once (the "confirm all" path).

        Parameters
        ----------
        decisions : list[dict]
            Each entry ``{"normalized": str, "decision": str}``.
        today : date or pd.Timestamp, optional
            Reference day, forwarded to :meth:`set_decision`.

        Returns
        -------
        dict
            ``{"updated": [...]}`` — the verdicts that were stored.
        """
        return {
            "updated": [
                self.set_decision(entry["normalized"], entry["decision"], today)
                for entry in decisions
            ]
        }
