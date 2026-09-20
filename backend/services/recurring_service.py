"""Recurring-charge (subscription) detection.

Pure heuristic over scraped transaction history — no open-banking merchant
feed required. Groups expense transactions by a normalized merchant label and
looks for a stable cadence (monthly through annual) across at least three
occurrences. This powers the dashboard subscriptions view and feeds the
insights engine with "new subscription" / "price increase" signals.

Detection only ever produces a *candidate*. A candidate becomes a recurring
charge the rest of the app acts on — committed spend in the budget overview,
the forecast's safe-to-spend, insight cards — only once the user confirms it
(:class:`~backend.repositories.recurring_decisions_repository.RecurringDecisionsRepository`).
Unconfirmed candidates are reported as ``pending`` so the UI can ask, and
dismissed ones are suppressed for good.
"""

import copy
import re
from datetime import date

import numpy as np
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
from backend.utils import data_cache


class RecurringService:
    """Detect recurring charges from itemized transaction history."""

    # Cadences we recognise, as ``(name, period_days, tolerance)``. Tolerance is
    # per-cadence and tight enough that the bands never touch: a gap that falls
    # between two cadences (45 days, say) is not a cadence at all and is
    # rejected rather than rounded to the nearer one. The old single ±35% band
    # made "monthly" mean anything from 19.5 to 40.5 days, which is where most
    # of the false positives lived. ``period_days`` stays an integer — it is
    # also the step for the next-expected date and the new/ended windows.
    # Nothing below a month is a billing cadence. Weekly and fortnightly bands
    # only ever matched habits — the Monday coffee, the Friday supermarket run
    # — which is the pattern most easily mistaken for a subscription, so a gap
    # shorter than about 25 days is now no cadence at all.
    _CADENCES = [
        ("monthly", 30, 0.18),
        # Israeli utilities (water, electricity, arnona) bill every two months.
        # With no band of their own they landed inside the old quarterly band,
        # which reported their monthly cost a third of what it really is.
        ("bimonthly", 61, 0.15),
        ("quarterly", 91, 0.15),
        ("semiannual", 182, 0.12),
        ("annual", 365, 0.10),
    ]
    # Minimum sightings before a cadence is believable. Three is a full period
    # observed twice over — and for the longest bands it is already three years
    # of history.
    _MIN_OCCURRENCES = 3
    # Gaps must be regular, measured with a *robust* spread — median absolute
    # deviation over the median — rather than the standard deviation. One
    # skipped period (a subscription paused for a month) no longer rejects an
    # otherwise metronomic charge, while genuinely scattered gaps still do.
    #
    # This is the gate that does the real work, and the threshold is measured
    # rather than guessed: across the demo history every genuine commitment
    # (streaming, gym, childcare, internet, electricity, water, arnona,
    # national insurance, quarterly home insurance) scores at most 0.133, while
    # the tightest piece of ordinary shopping scores 0.208. 0.15 sits in that
    # gap. The old standard-deviation gate at 0.5 was nowhere near it.
    _MAX_INTERVAL_MAD_CV = 0.15
    # How near the same day of the month a charge has to land to count as
    # anchored. This only scores a candidate, it never rejects one: real bills
    # slip by five or six days around weekends and month ends, and a tolerance
    # wide enough to allow that covers a third of the month, which
    # discriminates nothing.
    _ANCHOR_TOLERANCE_DAYS = 3
    # Acceptance path 1 — a fixed-price subscription: nearly every charge sits
    # on the same amount.
    _AMOUNT_BAND = 0.15
    _MIN_AMOUNT_CONSISTENCY = 0.75
    # Acceptance path 2 — a metered bill (electricity, water): the amount swings
    # with consumption, so it gets a much wider band, paid for with a stricter
    # cadence. Without this path, tightening path 1 enough to drop the false
    # positives would have dropped every utility bill with them.
    _VARIABLE_AMOUNT_BAND = 0.50
    _MIN_VARIABLE_AMOUNT_CONSISTENCY = 0.75
    _VARIABLE_MAX_INTERVAL_MAD_CV = 0.12
    # When the amount carries no evidence, the schedule has to be demonstrated
    # more times. Three evenly spaced charges are trivially "regular" whatever
    # they cost — that is how an annual back-to-school run and a yearly hotel
    # booking got in as subscriptions. Six sightings on an exact schedule are
    # a commitment; the fixed-price path keeps the lower floor because there
    # the repeated amount is evidence in its own right.
    _MIN_METERED_OCCURRENCES = 6
    # A charge that skips most of the periods its history spans is not really on
    # that cadence, however evenly spaced the few sightings were.
    _MIN_COVERAGE = 0.5
    # Relative amount change that counts as a price change.
    _PRICE_CHANGE_THRESHOLD = 0.10
    # Spread of the middle half of the gaps. A robust median absolute deviation
    # reads a strictly alternating rhythm (26, 34, 26, 34 days) as *perfectly*
    # regular, because most gaps sit exactly on the median — this notices the
    # split. It is scored rather than gated: a genuine bimonthly payment can
    # alternate too, so the candidate is ranked down, not thrown away.
    _INTERVAL_SHAPE_REFERENCE = 0.60
    # How the confidence score weighs the five kinds of evidence. Sums to 1.
    _CONFIDENCE_WEIGHTS = {
        "regularity": 0.25,
        "shape": 0.15,
        "anchor": 0.20,
        "amount": 0.25,
        "evidence": 0.15,
    }

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
        """Match a median interval to a known cadence, or reject it.

        Each cadence carries its own tolerance and the bands do not overlap, so
        an interval either falls inside one of them or is not a cadence. When
        two bands could both claim it, the closer one wins.

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
        best_rel = None
        for name, days, tolerance in self._CADENCES:
            rel = abs(interval_days - days) / days
            if rel > tolerance:
                continue
            if best_rel is None or rel < best_rel:
                best_rel = rel
                best = (name, days)
        return best

    @staticmethod
    def _interval_spread(diffs: pd.Series, median_interval: float) -> float:
        """Robust coefficient of variation of the gaps between charges.

        Median absolute deviation over the median, rather than std over the
        median: a single outlying gap — one skipped billing period — leaves
        this near zero, while gaps that are scattered throughout push it up.

        Parameters
        ----------
        diffs : pd.Series
            Gaps between consecutive charges, in days.
        median_interval : float
            Median of those gaps.

        Returns
        -------
        float
            Robust spread, 0 for perfectly even gaps.
        """
        mad = float((diffs - median_interval).abs().median())
        return mad / median_interval

    @staticmethod
    def _interval_shape(diffs: pd.Series, median_interval: float) -> float:
        """Interquartile spread of the gaps, over their median.

        Complements :meth:`_interval_spread`, which a strictly alternating
        rhythm fools: with half the gaps long and half short, most still sit on
        the median and the absolute deviation reads zero. The quartiles pull
        apart instead.

        Parameters
        ----------
        diffs : pd.Series
            Gaps between consecutive charges, in days.
        median_interval : float
            Median of those gaps.

        Returns
        -------
        float
            Interquartile range over the median, 0 for identical gaps.
        """
        iqr = float(diffs.quantile(0.75) - diffs.quantile(0.25))
        return iqr / median_interval

    #: Days in an average month, the cycle day-of-month anchoring wraps around.
    _MONTH_CYCLE_DAYS = 30.44

    @classmethod
    def _anchor_score(cls, dates: pd.Series) -> float:
        """Fraction of charges landing on one day of the month.

        Distance is circular — the 1st and the 30th are two days apart, not
        twenty-nine — so a bill that slips over a month boundary still reads as
        anchored. Every observed day is tried as the anchor and the
        best-supported one wins, because the median day is the wrong reference
        when the charges straddle the wrap point.

        Parameters
        ----------
        dates : pd.Series
            Charge dates, ascending.

        Returns
        -------
        float
            Share of charges within the anchor tolerance, 0..1.
        """
        positions = dates.dt.day.astype(float)
        best = 0.0
        for candidate in positions.unique():
            deviation = (positions - candidate).abs()
            deviation = np.minimum(deviation, cls._MONTH_CYCLE_DAYS - deviation)
            best = max(best, float((deviation <= cls._ANCHOR_TOLERANCE_DAYS).mean()))
        return best

    @staticmethod
    def _amount_consistency(
        amounts: pd.Series, median_amount: float, band: float
    ) -> float:
        """Share of charges sitting within ``band`` of the median amount.

        Parameters
        ----------
        amounts : pd.Series
            Net charge magnitudes (positive).
        median_amount : float
            Median of those magnitudes.
        band : float
            Relative half-width of the accepted band.

        Returns
        -------
        float
            Share within the band, 0..1.
        """
        return float((amounts.sub(median_amount).abs() <= median_amount * band).mean())

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
    ) -> dict:
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

        verdicts = self.decisions.get_all()
        items: list[dict] = []
        dismissed_count = 0

        # Net same-day charges and refunds: sum signed amounts per merchant-day,
        # then keep only net-outflow days as charge occurrences. A same-day (or
        # same-statement-day) refund shrinks the charge; a fully-refunded day
        # drops out entirely instead of masquerading as a recurring hit.
        #
        # One grouping over both keys rather than a per-merchant groupby nested
        # inside the merchant loop: pandas charges a fixed ~1 ms to set up each
        # groupby, and with ~950 merchant labels that overhead *was* the
        # detection pass. Sorting the MultiIndex once also leaves every
        # merchant's days in date order, so the per-merchant sort goes away too.
        daily_by_norm = df.groupby(["norm", "date_parsed"])["amount"].sum().sort_index()
        # Positional row indices per merchant, for the few candidates that
        # survive far enough to need their description and category.
        rows_by_norm = df.groupby("norm").indices

        for norm, norm_daily in daily_by_norm.groupby(level=0):
            daily_net = norm_daily.droplevel(0)
            charges = daily_net[daily_net < 0]
            if len(charges) < self._MIN_OCCURRENCES:
                continue

            dates = charges.index.to_series().reset_index(drop=True)
            # Net charge magnitudes (positive), aligned to date order.
            amounts = pd.Series(-charges.to_numpy())

            diffs = dates.diff().dropna().dt.days
            median_interval = float(diffs.median())
            if median_interval <= 0:
                continue

            cadence = self._match_cadence(median_interval)
            if cadence is None:
                continue
            cadence_name, period_days = cadence

            # Regular gaps: the intervals themselves must be consistent, not
            # just their median. A merchant visited at scattered intervals
            # (groceries, cafés) is rejected here.
            interval_spread = self._interval_spread(diffs, median_interval)
            if interval_spread > self._MAX_INTERVAL_MAD_CV:
                continue

            # How tightly the charges hold one day of the month. Scored, never
            # gated; see the constant.
            anchor = self._anchor_score(dates)

            amount = float(amounts.median())
            if amount <= 0:
                continue

            # Two ways to qualify: a fixed-price subscription, or a metered bill
            # whose amount moves but whose schedule is exact. See the constants.
            fixed_consistency = self._amount_consistency(
                amounts, amount, self._AMOUNT_BAND
            )
            is_fixed = fixed_consistency >= self._MIN_AMOUNT_CONSISTENCY
            metered_consistency = self._amount_consistency(
                amounts, amount, self._VARIABLE_AMOUNT_BAND
            )
            is_metered = (
                metered_consistency >= self._MIN_VARIABLE_AMOUNT_CONSISTENCY
                and interval_spread <= self._VARIABLE_MAX_INTERVAL_MAD_CV
                and len(charges) >= self._MIN_METERED_OCCURRENCES
            )
            if not (is_fixed or is_metered):
                continue

            # Coverage: how many of the periods this history spans actually
            # carry a charge. Three sightings across two years are not monthly,
            # however evenly spaced those three happened to be.
            span_days = float((dates.iloc[-1] - dates.iloc[0]).days)
            expected_periods = span_days / period_days + 1
            coverage = len(charges) / expected_periods if expected_periods > 0 else 0.0
            if coverage < self._MIN_COVERAGE:
                continue

            amount_kind = "fixed" if is_fixed else "metered"
            amount_score = fixed_consistency if is_fixed else metered_consistency
            interval_shape = self._interval_shape(diffs, median_interval)
            weights = self._CONFIDENCE_WEIGHTS
            confidence = round(
                weights["regularity"]
                * max(0.0, 1.0 - interval_spread / self._MAX_INTERVAL_MAD_CV)
                + weights["shape"]
                * max(0.0, 1.0 - interval_shape / self._INTERVAL_SHAPE_REFERENCE)
                + weights["anchor"] * anchor
                + weights["amount"] * amount_score
                + weights["evidence"]
                * min(1.0, len(charges) / (2 * self._MIN_OCCURRENCES)),
                2,
            )

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

            group = df.take(rows_by_norm[norm])
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
                "confidence": confidence,
                "amount_kind": amount_kind,
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
            If no detected candidate carries that key.
        """
        return self.set_decisions(
            [{"normalized": normalized, "decision": decision}], today
        )["updated"][0]

    def set_decisions(
        self, decisions: list[dict], today: date | pd.Timestamp | None = None
    ) -> dict:
        """Record several verdicts at once (the "confirm all" path).

        Every verdict is validated before any of them is written, and the
        whole batch lands in one commit. Both matter for how fast the card
        answers a click: detection runs once for the batch rather than once
        per entry, and a single commit invalidates the derived-read cache
        once instead of *n* times — applying eight verdicts one at a time
        meant eight full detection passes, which is what made "confirm all"
        take seconds.

        Parameters
        ----------
        decisions : list[dict]
            Each entry ``{"normalized": str, "decision": str}``.
        today : date or pd.Timestamp, optional
            Reference day, forwarded to detection when looking candidates up.

        Returns
        -------
        dict
            ``{"updated": [...]}`` — the verdicts that were stored.

        Raises
        ------
        ValidationException
            If any ``decision`` is not one of the three accepted values.
        EntityNotFoundException
            If any key names no detected candidate. Confirming something
            detection never produced would create a verdict nothing can ever
            act on, which reads to the user as the click having done nothing.
        """
        accepted = (*DECISIONS, PENDING)
        for entry in decisions:
            if entry["decision"] not in accepted:
                raise ValidationException(
                    f"Invalid decision '{entry['decision']}'. "
                    f"Expected one of: {', '.join(accepted)}."
                )

        candidates = {
            item["normalized"]: item
            for item in self.get_recurring(today, include_dismissed=True)["items"]
        }

        entries = []
        for entry in decisions:
            candidate = candidates.get(entry["normalized"])
            if candidate is None:
                raise EntityNotFoundException(
                    f"No detected recurring charge named '{entry['normalized']}'."
                )
            entries.append({
                "normalized": entry["normalized"],
                "decision": entry["decision"],
                "label": candidate["label"],
                "amount": candidate["amount"],
                "cadence": candidate["cadence"],
            })

        self.decisions.apply(entries)
        return {
            "updated": [
                {"normalized": e["normalized"], "decision": e["decision"]}
                for e in entries
            ]
        }
