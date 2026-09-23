"""Pure detection math behind recurring charges and recurring income.

No database access: every function here works on values and frames it is
handed, so the heuristic can be reasoned about (and tested) without a
session. :class:`~backend.services.recurring_service.RecurringService` loads
the transactions, applies the user's verdicts and caches the result; this
module decides what *is* a repeating money stream.

A stream is a normalized merchant label seen at least
:data:`MIN_OCCURRENCES` times on one of the :data:`CADENCES`, with regular
gaps (:func:`interval_spread`), and amounts that back up the schedule
(:func:`qualifies_on_amount`). Each one carries a :func:`confidence` score and
the amount worth planning around (:func:`expected_amount`).
"""

import re
from typing import Any

import numpy as np
import pandas as pd

#: Which side of zero counts as an occurrence, for :func:`detect_streams`.
OUTFLOW = "outflow"
INFLOW = "inflow"

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
CADENCES: list[tuple[str, int, float]] = [
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
MIN_OCCURRENCES = 3
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
MAX_INTERVAL_MAD_CV = 0.15
# How near the same day of the month a charge has to land to count as
# anchored. This only scores a candidate, it never rejects one: real bills
# slip by five or six days around weekends and month ends, and a tolerance
# wide enough to allow that covers a third of the month, which
# discriminates nothing.
ANCHOR_TOLERANCE_DAYS = 3
# Acceptance path 1 — a fixed-price subscription: nearly every charge sits
# on the same amount.
AMOUNT_BAND = 0.15
MIN_AMOUNT_CONSISTENCY = 0.75
# Acceptance path 2 — a metered bill (electricity, water): the amount swings
# with consumption, so it gets a much wider band, paid for with a stricter
# cadence. Without this path, tightening path 1 enough to drop the false
# positives would have dropped every utility bill with them.
VARIABLE_AMOUNT_BAND = 0.50
MIN_VARIABLE_AMOUNT_CONSISTENCY = 0.75
VARIABLE_MAX_INTERVAL_MAD_CV = 0.12
# When the amount carries no evidence, the schedule has to be demonstrated
# more times. Three evenly spaced charges are trivially "regular" whatever
# they cost — that is how an annual back-to-school run and a yearly hotel
# booking got in as subscriptions. Six sightings on an exact schedule are
# a commitment; the fixed-price path keeps the lower floor because there
# the repeated amount is evidence in its own right.
MIN_METERED_OCCURRENCES = 6
# A charge that skips most of the periods its history spans is not really on
# that cadence, however evenly spaced the few sightings were.
MIN_COVERAGE = 0.5
# Relative amount change that counts as a price change.
PRICE_CHANGE_THRESHOLD = 0.10
# What a stream whose amount moves is worth planning around: a low
# quantile of its recent occurrences rather than their middle. Half the
# months coming in under the projection is the wrong failure mode for a
# number the user spends against, and the quarter-point costs little —
# across the demo history it reads a varying allowance about 15% under its
# median. The window is six occurrences: long enough to see the spread,
# short enough that a stream which has since grown is not held to what it
# paid two years ago.
EXPECTED_AMOUNT_QUANTILE = 0.25
EXPECTED_AMOUNT_WINDOW = 6
# Spread of the middle half of the gaps. A robust median absolute deviation
# reads a strictly alternating rhythm (26, 34, 26, 34 days) as *perfectly*
# regular, because most gaps sit exactly on the median — this notices the
# split. It is scored rather than gated: a genuine bimonthly payment can
# alternate too, so the candidate is ranked down, not thrown away.
INTERVAL_SHAPE_REFERENCE = 0.60
# How the confidence score weighs the five kinds of evidence. Sums to 1.
CONFIDENCE_WEIGHTS: dict[str, float] = {
    "regularity": 0.25,
    "shape": 0.15,
    "anchor": 0.20,
    "amount": 0.25,
    "evidence": 0.15,
}
#: Days in an average month, the cycle day-of-month anchoring wraps around.
MONTH_CYCLE_DAYS = 30.44


def normalize(desc: object) -> str:
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


def match_cadence(interval_days: float) -> tuple[str, int] | None:
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
    for name, days, tolerance in CADENCES:
        rel = abs(interval_days - days) / days
        if rel > tolerance:
            continue
        if best_rel is None or rel < best_rel:
            best_rel = rel
            best = (name, days)
    return best


def interval_spread(diffs: pd.Series, median_interval: float) -> float:
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


def interval_shape(diffs: pd.Series, median_interval: float) -> float:
    """Return the interquartile spread of the gaps, over their median.

    Complements :func:`interval_spread`, which a strictly alternating
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


def anchor_score(dates: pd.Series) -> float:
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
        deviation = np.minimum(deviation, MONTH_CYCLE_DAYS - deviation)
        best = max(best, float((deviation <= ANCHOR_TOLERANCE_DAYS).mean()))
    return best


def amount_consistency(amounts: pd.Series, median_amount: float, band: float) -> float:
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


def qualifies_on_amount(
    amounts: pd.Series,
    median_amount: float,
    spread: float,
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
    variable stream's amount: it is projected at :func:`expected_amount`'s
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
    spread : float
        Robust spread of the gaps, from :func:`interval_spread`.
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
    fixed_consistency = amount_consistency(amounts, median_amount, AMOUNT_BAND)
    if fixed_consistency >= MIN_AMOUNT_CONSISTENCY:
        return "fixed", fixed_consistency

    metered_consistency = amount_consistency(
        amounts, median_amount, VARIABLE_AMOUNT_BAND
    )
    exact_schedule = (
        spread <= VARIABLE_MAX_INTERVAL_MAD_CV
        and occurrences >= MIN_METERED_OCCURRENCES
    )
    if metered_consistency >= MIN_VARIABLE_AMOUNT_CONSISTENCY and exact_schedule:
        return "metered", metered_consistency
    if direction == INFLOW and exact_schedule:
        return "variable", metered_consistency
    return None


def expected_amount(
    amounts: pd.Series, median_amount: float, amount_kind: str
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
    recent = amounts.tail(EXPECTED_AMOUNT_WINDOW)
    return float(recent.quantile(EXPECTED_AMOUNT_QUANTILE))


def confidence(
    spread: float,
    shape: float,
    anchor: float,
    amount_score: float,
    occurrences: int,
) -> float:
    """Score how much evidence backs a detected stream.

    A weighted sum (:data:`CONFIDENCE_WEIGHTS`) of five kinds of evidence:
    gap regularity, gap shape, day-of-month anchoring, amount stability and
    how many times the stream was seen.

    Parameters
    ----------
    spread : float
        Robust spread of the gaps, from :func:`interval_spread`.
    shape : float
        Interquartile spread of the gaps, from :func:`interval_shape`.
    anchor : float
        Day-of-month anchoring, from :func:`anchor_score`.
    amount_score : float
        Amount consistency from :func:`qualifies_on_amount`.
    occurrences : int
        How many times the stream was seen.

    Returns
    -------
    float
        Confidence in ``0..1``, rounded to two decimals.
    """
    weights = CONFIDENCE_WEIGHTS
    return round(
        weights["regularity"] * max(0.0, 1.0 - spread / MAX_INTERVAL_MAD_CV)
        + weights["shape"] * max(0.0, 1.0 - shape / INTERVAL_SHAPE_REFERENCE)
        + weights["anchor"] * anchor
        + weights["amount"] * amount_score
        + weights["evidence"] * min(1.0, occurrences / (2 * MIN_OCCURRENCES)),
        2,
    )


def detect_streams(
    df: pd.DataFrame, today: pd.Timestamp, direction: str
) -> list[dict[str, Any]]:
    """Find the repeating money streams in a transactions frame.

    The cadence machinery both recurring *charges* and recurring *income*
    are built on. ``direction`` picks which side of zero counts as an
    occurrence and how a candidate qualifies on its amount — see
    :func:`qualifies_on_amount`.

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
        Stream dicts as documented on ``RecurringService.get_recurring``'s
        ``items``, minus ``confirmation`` — a verdict is the caller's
        business — sorted by ``monthly_equivalent`` descending.
    """
    df = df.copy()
    df["date_parsed"] = pd.to_datetime(df["date"]).dt.normalize()
    df["norm"] = df["description"].apply(normalize)
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
        if len(charges) < MIN_OCCURRENCES:
            continue

        dates = charges.index.to_series().reset_index(drop=True)
        # Net magnitudes (positive), aligned to date order.
        magnitudes = charges.to_numpy()
        amounts = pd.Series(magnitudes if inflow else -magnitudes)

        diffs = dates.diff().dropna().dt.days
        median_interval = float(diffs.median())
        if median_interval <= 0:
            continue

        cadence = match_cadence(median_interval)
        if cadence is None:
            continue
        cadence_name, period_days = cadence

        # Regular gaps: the intervals themselves must be consistent, not
        # just their median. A merchant visited at scattered intervals
        # (groceries, cafés) is rejected here.
        spread = interval_spread(diffs, median_interval)
        if spread > MAX_INTERVAL_MAD_CV:
            continue

        # How tightly the charges hold one day of the month. Scored, never
        # gated; see the constant.
        anchor = anchor_score(dates)

        amount = float(amounts.median())
        if amount <= 0:
            continue

        qualified = qualifies_on_amount(
            amounts, amount, spread, len(charges), direction
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
        if coverage < MIN_COVERAGE:
            continue

        score = confidence(
            spread,
            interval_shape(diffs, median_interval),
            anchor,
            amount_score,
            len(charges),
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
                and abs(last_amount - prior_med) / prior_med > PRICE_CHANGE_THRESHOLD
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
                    expected_amount(amounts, amount, amount_kind), 2
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
                "confidence": score,
                "amount_kind": amount_kind,
            }
        )

    streams.sort(key=lambda i: i["monthly_equivalent"], reverse=True)
    return streams
