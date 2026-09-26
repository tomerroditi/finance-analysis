"""The reference's decumulation return: the author's formula, plus measured drift.

After retirement a withdrawal portfolio stops earning the return the user typed
and earns a much lower, confidence-derived one instead (notes/07). The author
describes how (blog post "אלגוריתם למשיכות משתנות מתיק השקעות"): an empirical
fit to the updated Trinity tables at 75% equities gives a safe withdrawal rate
`379 / (confidence^0.6 * years^0.5)` percent, and the real return is the one at
which level withdrawals at that rate, taken at the start of each year, exhaust
the portfolio in exactly `years` — zero when `1/years` already exceeds it.

That reproduces every cell measured off the reference past ~22 years to ~1e-5.
The reference solves it numerically, and its answer drifts slightly above the
exact root — up to 0.05 points in the 14-16 year knee, a sawtooth with a
one-year period. The drift is taken from ~1,650 cells measured straight off the
reference (`experiments/surface*.py`): every month from 7 to 23 years for
confidence 80/85/90/95/100 (all of rule 85), whole years beyond.
`build_decumulation_table.py` rebuilds the cells. Levels between those five
interpolate the drift, not the rate (notes/18 §1).
"""

from __future__ import annotations

import json
from bisect import bisect_left, bisect_right
from functools import lru_cache
from pathlib import Path

TABLE_PATH = Path(__file__).with_name("decumulation_table.json")


class _Curve:
    """Monotone cubic (Fritsch-Carlson PCHIP) through the measured cells."""

    def __init__(self, points: list[tuple[float, float]]) -> None:
        points = sorted(points)
        self.xs = [x for x, _ in points]
        self.ys = [y for _, y in points]
        self.slopes = self._slopes()

    def _slopes(self) -> list[float]:
        xs, ys = self.xs, self.ys
        if len(xs) < 2:
            return [0.0] * len(xs)
        widths = [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
        secants = [(ys[i + 1] - ys[i]) / widths[i] for i in range(len(xs) - 1)]
        slopes = [secants[0]] + [0.0] * (len(xs) - 2) + [secants[-1]]
        for i in range(1, len(xs) - 1):
            if secants[i - 1] * secants[i] <= 0:
                continue  # a local extremum: flat, so the curve cannot overshoot
            left = 2 * widths[i] + widths[i - 1]
            right = widths[i] + 2 * widths[i - 1]
            slopes[i] = (left + right) / (left / secants[i - 1] + right / secants[i])
        return slopes

    def __call__(self, x: float) -> float:
        xs, ys, slopes = self.xs, self.ys, self.slopes
        if x <= xs[0]:
            return ys[0]
        if x >= xs[-1]:
            return ys[-1]
        i = bisect_right(xs, x) - 1
        width = xs[i + 1] - xs[i]
        t = (x - xs[i]) / width
        t2, t3 = t * t, t * t * t
        return (
            ys[i] * (2 * t3 - 3 * t2 + 1)
            + slopes[i] * width * (t3 - 2 * t2 + t)
            + ys[i + 1] * (-2 * t3 + 3 * t2)
            + slopes[i + 1] * width * (t3 - t2)
        )


DENSE = 10
"""A level with at least this many measured cells carries its own residual
curve; sparser levels (82, 87) are held-out checks of the formula instead."""

SWR_CONSTANT = 379.0
"""`SWR% = 379 / (confidence^0.6 * years^0.5)`: the author's empirical fit to
the updated Trinity tables at 75% equities (blog: "אלגוריתם למשיכות משתנות").
The constant is backed out of the post's three worked examples (378.99,
379.01, 379.01) and reproduces every measured cell past ~22 years to ~1e-5."""


@lru_cache(maxsize=4096)
def formula_rate(confidence: float, years: float) -> float:
    """Return the author's closed form: the safe withdrawal rate as a real return.

    The withdrawal rate is converted with the annual annuity-due identity —
    level withdrawals at the start of each year that exhaust the portfolio in
    exactly `years` — and a horizon too short to need any growth earns zero
    ("ניתן לכל היותר להתבסס על הצמדה למדד").
    """
    if years <= 0:
        return 0.0
    withdrawal = SWR_CONSTANT / (confidence**0.6 * years**0.5) / 100
    if withdrawal * years <= 1.0:
        return 0.0

    def rate_withdrawn(rate: float) -> float:
        return rate / ((1 + rate) * (1 - (1 + rate) ** -years))

    low, high = 0.0, 1.0
    for _ in range(100):
        mid = (low + high) / 2
        if rate_withdrawn(mid) < withdrawal:
            low = mid
        else:
            high = mid
    return (low + high) / 2 * 100


@lru_cache(maxsize=1)
def _residuals() -> dict[float, _Curve]:
    """`measured - formula` per densely measured level, as a curve in years.

    The reference solves the formula numerically and its answer drifts from
    the exact root near the zero floor — a sawtooth with a one-year period,
    up to 0.05 points at 14-15 years and under 1e-5 past 22. The measured
    cells carry that drift; the curve spreads it between them.
    """
    raw = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
    out = {}
    for rule, row in raw["bridge_years"].items():
        if len(row) < DENSE:
            continue
        points = [
            (float(bridge), rate - formula_rate(float(rule), float(bridge)))
            for bridge, rate in row.items()
        ]
        out[float(rule)] = (_Curve(points), max(x for x, _ in points))
    return out


def _residual(rule: float, bridge: float) -> float:
    curve, last = _residuals()[rule]
    return 0.0 if bridge > last else curve(bridge)


def decumulation_return_pct(confidence: float, bridge_years: float) -> float:
    """Real return a withdrawal portfolio earns after retirement.

    `confidence` is the `retireRule` field (80-100; the reference rejects
    anything outside). `bridge_years` is the horizon `bridge.bridge_months`
    works out. The author's formula, plus the measured drift of the
    reference's own solver, interpolated between measured levels.
    """
    residuals = _residuals()
    rules = sorted(residuals)
    confidence = min(max(confidence, rules[0]), rules[-1])
    if confidence in residuals:
        drift = _residual(confidence, bridge_years)
    else:
        index = bisect_left(rules, confidence)
        low, high = rules[index - 1], rules[index]
        weight = (confidence - low) / (high - low)
        drift = _residual(low, bridge_years) + weight * (
            _residual(high, bridge_years) - _residual(low, bridge_years)
        )
    return max(formula_rate(confidence, bridge_years) + drift, 0.0)
