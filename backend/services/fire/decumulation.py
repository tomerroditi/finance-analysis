"""The reference's decumulation return: the author's formula, solved his way.

After retirement a withdrawal portfolio stops earning the return the user typed
and earns a much lower, confidence-derived one instead (notes/07). The author
describes how (blog post "אלגוריתם למשיכות משתנות מתיק השקעות"): an empirical
fit to the updated Trinity tables at 75% equities gives a safe withdrawal rate
`w = 379 / (confidence^0.6 * years^0.5)` percent, and the real return is the one
at which level withdrawals at that rate, taken at the start of each year,
exhaust the portfolio in exactly `years`, found by Newton-Raphson.

The reference's Newton-Raphson is what users see, early stop included, so it is
reproduced step for step (notes/18 §1): it iterates on

    f(r) = (r / w) (1 + r)^(years - 1) - ((1 + r)^years - 1)

from r = 5% and returns the first iterate at which |f| < 1e-4, floored at zero.
`f` has a root at zero as well as at the true rate, so where `w * years < 1`
(too short a horizon to need any growth) the iteration creeps down toward zero
and stops short of it, and near `w * years = 1` it stops well short of the true
root. That early stop is the "drift" the measured surface showed: a sawtooth up
to 0.05 points in the 12-18 year knee, jumping wherever the iteration count
changes. It reproduces all ~1,900 cells measured off the reference, at every
confidence level including off-grid ones, to 2e-7 points
(`research/zeke_retire_calc/surface_cells.json`).
"""

from __future__ import annotations

from functools import lru_cache

SWR_CONSTANT = 379.0
"""`SWR% = 379 / (confidence^0.6 * years^0.5)`: the author's empirical fit to
the updated Trinity tables at 75% equities. The constant is backed out of the
post's three worked examples (378.99, 379.01, 379.01)."""

START = 0.05
"""The reference's first guess."""

TOLERANCE = 1e-4
"""The residual at which the reference stops: every measured cell stopped at
|f| <= 9.97e-5, and every step it took continued from |f| >= 1.0015e-4."""

MAX_STEPS = 200

MIN_CONFIDENCE, MAX_CONFIDENCE = 80.0, 100.0
"""The reference rejects confidence below 80; out-of-range input is clamped
rather than refused."""


@lru_cache(maxsize=65536)
def decumulation_return_pct(confidence: float, bridge_years: float) -> float:
    """Real return a withdrawal portfolio earns after retirement, in percent.

    `confidence` is the `retireRule` field (the reference rejects anything
    below 80). `bridge_years` is the horizon `bridge.bridge_months` works out.
    """
    if bridge_years <= 0:
        return 0.0
    confidence = min(max(confidence, MIN_CONFIDENCE), MAX_CONFIDENCE)
    withdrawal = SWR_CONSTANT / (confidence**0.6 * bridge_years**0.5) / 100
    rate = START
    for _ in range(MAX_STEPS):
        growth = 1 + rate
        before_last = growth ** (bridge_years - 1)
        residual = rate / withdrawal * before_last - (growth * before_last - 1)
        if abs(residual) < TOLERANCE:
            break
        slope = (before_last + rate * (bridge_years - 1) * before_last / growth) / (
            withdrawal
        ) - bridge_years * before_last
        rate -= residual / slope
    return max(rate, 0.0) * 100
