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
"""

import copy
import re
from datetime import date
from typing import Any, ClassVar

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
from backend.errors import ValidationException
from backend.repositories.budget_repository import BudgetRepository
from backend.repositories.recurring_decisions_repository import (
    DECISIONS,
    PENDING,
    RecurringDecisionsRepository,
)
from backend.repositories.transactions import TransactionsRepository
from backend.services.transaction_classification import income_mask
from backend.utils import data_cache

#: Which side of zero counts as an occurrence, for :meth:`_detect_streams`.
OUTFLOW = "outflow"
INFLOW = "inflow"


class RecurringService:
    """Detect recurring charges and recurring income from transaction history.

    Parameters
    ----------
    db : Session
        SQLAlchemy session for database operations.
    """

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
    _CADENCES: ClassVar[list[tuple[str, int, float]]] = [
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
    # gap.
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
    # What a stream whose amount moves is worth planning around: a low
    # quantile of its recent occurrences rather than their middle. Half the
    # months coming in under the projection is the wrong failure mode for a
    # number the user spends against, and the quarter-point costs little —
    # across the demo history it reads a varying allowance about 15% under its
    # median. The window is six occurrences: long enough to see the spread,
    # short enough that a stream which has since grown is not held to what it
    # paid two years ago.
    _EXPECTED_AMOUNT_QUANTILE = 0.25
    _EXPECTED_AMOUNT_WINDOW = 6
    # Longest period still treated as "once a month" when working out what a
    # stream still owes the running month. The monthly band's own tolerance
    # reaches 35 days, and a 30-day period walks backwards through a 31-day
    # month, so the next expected date alone cannot answer the question.
    _MONTHLY_PERIOD_MAX_DAYS = 35
    # Spread of the middle half of the gaps. A robust median absolute deviation
    # reads a strictly alternating rhythm (26, 34, 26, 34 days) as *perfectly*
    # regular, because most gaps sit exactly on the median — this notices the
    # split. It is scored rather than gated: a genuine bimonthly payment can
    # alternate too, so the candidate is ranked down, not thrown away.
    _INTERVAL_SHAPE_REFERENCE = 0.60
    # How the confidence score weighs the five kinds of evidence. Sums to 1.
    _CONFIDENCE_WEIGHTS: ClassVar[dict[str, float]] = {
        "regularity": 0.25,
        "shape": 0.15,
        "anchor": 0.20,
        "amount": 0.25,
        "evidence": 0.15,
    }
    #: Days in an average month, the cycle day-of-month anchoring wraps around.
    _MONTH_CYCLE_DAYS = 30.44

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = TransactionsRepository(db)
        self.decisions = RecurringDecisionsRepository(db)

    @staticmethod
    def _normalize(desc: object) -> str:
        """Normalize a transaction description into a merchant grouping key.

        Strips digits, punctuation and collapses whitespace so that
        ``"NETFLIX 1234"`` and ``"NETFLIX.COM 9981"`` group together. Hebrew
        and other unicode word characters are preserved.

        Parameters
        ----------
        desc : object
            Raw transaction description (any pandas cell value).

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
        return re.sub(r"\s+", " ", s).strip()

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
        """Return the robust coefficient of variation of the gaps between charges.

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
        """Return the interquartile spread of the gaps, over their median.

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

    @classmethod
    def _anchor_score(cls, dates: pd.Series) -> float:
        """Score the fraction of charges landing on one day of the month.

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
        """Return the share of charges sitting within ``band`` of the median amount.

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

        streams = self._detect_streams(df, today, OUTFLOW)
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

    def _detect_streams(
        self, df: pd.DataFrame, today: pd.Timestamp, direction: str
    ) -> list[dict[str, Any]]:
        """Find the repeating money streams in a transactions frame.

        The cadence machinery both recurring *charges* and recurring *income*
        are built on. ``direction`` picks which side of zero counts as an
        occurrence and how a candidate qualifies on its amount — see
        :meth:`_qualifies_on_amount`.

        Parameters
        ----------
        df : pd.DataFrame
            Rows already narrowed to the side being detected (expense rows for
            ``OUTFLOW``, income rows for ``INFLOW``), carrying ``date``,
            ``description``, ``amount`` and ``category`` columns.
        today : pd.Timestamp
            Normalized reference day, for the ``new`` / ``ended`` verdict.
        direction : str
            ``OUTFLOW`` or ``INFLOW``.

        Returns
        -------
        list[dict]
            Stream dicts as documented on :meth:`get_recurring`'s ``items``,
            minus ``confirmation`` — a verdict is the caller's business —
            sorted by ``monthly_equivalent`` descending.
        """
        df = df.copy()
        df["date_parsed"] = pd.to_datetime(df["date"]).dt.normalize()
        df["norm"] = df["description"].apply(self._normalize)
        df = df[df["norm"] != ""]
        if df.empty:
            return []

        inflow = direction == INFLOW
        streams: list[dict[str, Any]] = []

        # Net same-day charges and refunds: sum signed amounts per merchant-day,
        # then keep only net-outflow days as charge occurrences. A same-day (or
        # same-statement-day) refund shrinks the charge; a fully-refunded day
        # drops out entirely instead of masquerading as a recurring hit. The
        # same netting on the income side makes a same-day reversal cancel the
        # deposit it undoes.
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
            charges = daily_net[daily_net > 0] if inflow else daily_net[daily_net < 0]
            if len(charges) < self._MIN_OCCURRENCES:
                continue

            dates = charges.index.to_series().reset_index(drop=True)
            # Net magnitudes (positive), aligned to date order.
            magnitudes = charges.to_numpy()
            amounts = pd.Series(magnitudes if inflow else -magnitudes)

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

            qualified = self._qualifies_on_amount(
                amounts, amount, interval_spread, len(charges), direction
            )
            if qualified is None:
                continue
            amount_kind, amount_score = qualified

            # Coverage: how many of the periods this history spans actually
            # carry a charge. Three sightings across two years are not monthly,
            # however evenly spaced those three happened to be.
            span_days = float((dates.iloc[-1] - dates.iloc[0]).days)
            expected_periods = span_days / period_days + 1
            coverage = len(charges) / expected_periods if expected_periods > 0 else 0.0
            if coverage < self._MIN_COVERAGE:
                continue

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
                if (
                    prior_med > 0
                    and abs(last_amount - prior_med) / prior_med
                    > self._PRICE_CHANGE_THRESHOLD
                ):
                    price_change = round(last_amount - prior_med, 2)
                    if status == "active":
                        status = "price_changed"

            group = df.take(rows_by_norm[norm])
            label_mode = group["description"].mode()
            label = label_mode.iloc[0] if not label_mode.empty else norm
            cat_mode = group["category"].dropna().mode()
            category = cat_mode.iloc[0] if not cat_mode.empty else None

            monthly_equivalent = amount * 30.0 / period_days

            streams.append(
                {
                    "label": label,
                    "normalized": norm,
                    "amount": round(amount, 2),
                    "expected_amount": round(
                        self._expected_amount(amounts, amount, amount_kind), 2
                    ),
                    "last_amount": round(last_amount, 2),
                    "cadence": cadence_name,
                    "period_days": period_days,
                    "monthly_equivalent": round(monthly_equivalent, 2),
                    "occurrences": len(charges),
                    "category": category,
                    "first_date": first_date.strftime("%Y-%m-%d"),
                    "last_date": last_date.strftime("%Y-%m-%d"),
                    "next_expected_date": next_expected.strftime("%Y-%m-%d"),
                    "status": status,
                    "price_change": price_change,
                    "confidence": confidence,
                    "amount_kind": amount_kind,
                }
            )

        streams.sort(key=lambda i: i["monthly_equivalent"], reverse=True)
        return streams

    def _qualifies_on_amount(
        self,
        amounts: pd.Series,
        median_amount: float,
        interval_spread: float,
        occurrences: int,
        direction: str,
    ) -> tuple[str, float] | None:
        """Decide whether a candidate's amounts back up its schedule.

        Outflows have two ways in — a flat subscription price, or a metered
        bill whose amount swings but whose schedule is exact (see the
        constants). Inflows get a third: a **variable** income. A salary with
        overtime, a reserve-duty allowance, a benefit recomputed every month —
        these arrive on a metronome and vary by a multiple, so no amount band
        admits them. Demanding one only ever *dropped* income, and income the
        forecast drops is income it quietly assumes will never arrive.

        Losing that gate is safe here because nothing is inferred from a
        variable stream's amount: it is projected at :meth:`_expected_amount`'s
        conservative low quantile rather than its median, so the schedule is
        what earns the stream its place and the amount can only understate it.
        The schedule in exchange has to be exact — the metered path's tighter
        spread and higher evidence bar, with no amount evidence to trade
        against them.

        Parameters
        ----------
        amounts : pd.Series
            Net magnitudes (positive), in date order.
        median_amount : float
            Median of those magnitudes.
        interval_spread : float
            Robust spread of the gaps, from :meth:`_interval_spread`.
        occurrences : int
            How many times the stream was seen.
        direction : str
            ``OUTFLOW`` or ``INFLOW``.

        Returns
        -------
        tuple[str, float] or None
            ``(amount_kind, amount_score)`` where ``amount_kind`` is one of
            ``fixed`` / ``metered`` / ``variable``, or None when the candidate
            does not qualify on any path.
        """
        fixed_consistency = self._amount_consistency(
            amounts, median_amount, self._AMOUNT_BAND
        )
        if fixed_consistency >= self._MIN_AMOUNT_CONSISTENCY:
            return "fixed", fixed_consistency

        metered_consistency = self._amount_consistency(
            amounts, median_amount, self._VARIABLE_AMOUNT_BAND
        )
        exact_schedule = (
            interval_spread <= self._VARIABLE_MAX_INTERVAL_MAD_CV
            and occurrences >= self._MIN_METERED_OCCURRENCES
        )
        if (
            metered_consistency >= self._MIN_VARIABLE_AMOUNT_CONSISTENCY
            and exact_schedule
        ):
            return "metered", metered_consistency
        if direction == INFLOW and exact_schedule:
            return "variable", metered_consistency
        return None

    def _expected_amount(
        self, amounts: pd.Series, median_amount: float, amount_kind: str
    ) -> float:
        """Return the amount one more occurrence of a stream is worth planning around.

        A stream whose amount holds still is worth its median. One that swings
        is worth its **low** end: a forecast spends this number, and guessing
        an inflow too high (a safe-to-spend figure built on money that never
        arrives) costs far more than guessing it too low. Only the recent
        window counts — a stream that has grown should not be planned around
        what it paid two years ago.

        Parameters
        ----------
        amounts : pd.Series
            Net magnitudes (positive), in date order.
        median_amount : float
            Median of those magnitudes.
        amount_kind : str
            ``fixed`` / ``metered`` / ``variable``.

        Returns
        -------
        float
            Amount to expect from the next occurrence.
        """
        if amount_kind == "fixed":
            return median_amount
        recent = amounts.tail(self._EXPECTED_AMOUNT_WINDOW)
        return float(recent.quantile(self._EXPECTED_AMOUNT_QUANTILE))

    def get_recurring_income(
        self, today: date | pd.Timestamp | None = None
    ) -> dict[str, Any]:
        """Detect the household's repeating income streams.

        Salaries, allowances, benefits, a standing transfer — money that
        arrives on a schedule, found with the same cadence machinery that
        finds recurring charges (:meth:`_detect_streams`), run over income
        rows instead of expense ones.

        Unlike a recurring *charge*, an income stream carries no user verdict.
        The confirm/dismiss flow exists because a false-positive charge
        silently shrinks safe-to-spend, and the user is the only one who can
        say whether a bill is really a commitment. A stream here is never
        trusted for more than its schedule: what it is worth comes from
        :meth:`_expected_amount`, which reads a variable stream at its low end,
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
              around — see :meth:`_expected_amount`). Sorted by
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

        streams = self._detect_streams(df, today, INFLOW)
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
        df = df.assign(norm=df["description"].apply(self._normalize))
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

    def set_decision(
        self,
        normalized: str,
        decision: str,
        label: str | None = None,
        amount: float | None = None,
        cadence: str | None = None,
    ) -> dict[str, str]:
        """Record the user's verdict on one candidate.

        Parameters
        ----------
        normalized : str
            Normalized merchant key, exactly as detection reported it.
        decision : str
            ``'confirmed'``, ``'dismissed'``, or ``'pending'`` to undo a
            previous verdict and put the candidate back up for review.
        label, amount, cadence : optional
            What the candidate read as when the user ruled on it, kept
            alongside the verdict for audit. See :meth:`set_decisions`.

        Returns
        -------
        dict
            ``{normalized, decision}``.

        Raises
        ------
        ValidationException
            If ``decision`` is not one of the three accepted values, or the
            key is blank.
        """
        return self.set_decisions(
            [
                {
                    "normalized": normalized,
                    "decision": decision,
                    "label": label,
                    "amount": amount,
                    "cadence": cadence,
                }
            ]
        )["updated"][0]

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
