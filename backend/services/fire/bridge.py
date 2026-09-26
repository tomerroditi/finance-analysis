"""The bridge: how long the reference assumes a withdrawal portfolio must last.

The decumulation surface (`decumulation.py`) is read at one horizon `N`. For a
plan with no pension that is the plain wait from the last working month to the
statutory age. A pension claimed at 60 shortens it, but not in proportion to
what it pays — every rule below was recovered by experiment
(`research/zeke_retire_calc/experiments/bridge_weights.py`, `bridge_end.py`,
`post60*.py`; notes/18).

**Coverage.** `x` is the monthly pension the plan starts at 60 — net of the
national insurance and income tax it pays before the statutory age — divided
by the spending it has to carry from then on: the typed amounts of the expense rows
still running after the 60th birthday, less any non-salary income rows running
then. Annual rises are ignored, a gemel converted at 60 does not count, and
nothing claimed later (the rest of the pension, Bituach Leumi) enters at all.
Two plans with the same `x` read the same rate to five decimals whatever their
pension, spending, tactic or retirement age.

**The blend.** The bridge ends inside the window between 60 and the statutory
age, a fraction `1 - y(x)` of the way along it — the same fraction for a man's
seven-year window and a woman's five-year one. `y` is measured, not derived:
it starts at about `x/2` and is 0.907 just short of full coverage, where it
jumps to 1 (a pension that covers everything ends the bridge at 60).

**Past 60, the reference mixes an index into a duration.** A claim that is
still ahead is waited for (`claim - last working month`), but one already
behind the retirement contributes its month index *counted from today*, plus
one. So a man retiring at 63 reads the surface 27.4 years out if he is 36 today
and 22.8 if he is 41 — reproduced exactly across four birth dates, three
tactics and both genders. It is the reference's behaviour, so it is cloned.
"""

from __future__ import annotations

from backend.services.fire.decumulation import _Curve

COVERAGE_CURVE: list[tuple[float, float]] = [
    (0.0, 0.0),
    (0.02048, 0.010346),
    (0.051199, 0.026277),
    (0.076799, 0.039926),
    (0.102399, 0.05396),
    (0.153597, 0.083192),
    (0.204797, 0.114079),
    (0.307196, 0.181475),
    (0.511992, 0.34408),
    (0.716789, 0.558591),
    (0.767989, 0.623363),
    (0.819188, 0.693749),
    (0.870388, 0.770517),
    (0.921587, 0.854577),
    (0.952307, 0.908956),
]
"""`(x, y)` measured at retirement age 45, each `y` read off a run whose only
unknown was its own decumulation rate, inverted through the surface where it
is measured month by month. Checked at ages 40 and 50 and for a woman's
shorter window. `x` is on the **net** annuity: every probe here paid a small,
untaxed recognised annuity, whose net is its gross less the flat 4.25%
national-insurance contribution."""

_CURVE = _Curve(COVERAGE_CURVE)


def window_share(coverage: float) -> float:
    """`y(x)`: how much of the 60-to-statutory window a pension at 60 removes."""
    if coverage >= 1.0:
        return 1.0
    if coverage <= 0.0:
        return 0.0
    return _CURVE(coverage)


def bridge_months(
    last_working: int,
    month_60: int,
    month_statutory: int,
    claims_at_60: bool,
    coverage: float,
) -> float:
    """Horizon, in months, at which the decumulation surface is read.

    Month numbers count from today: `last_working` is the last month with pay,
    `month_60` / `month_statutory` the months the main person turns 60 and the
    statutory age. `claims_at_60` is whether the pension tactic starts anything
    at 60 (tactics `60` and `60-67`) — with an empty pension too.
    """

    def wait(claim: int) -> int:
        return claim - last_working if claim >= last_working else claim + 1

    if not claims_at_60:
        return float(wait(month_statutory))
    if month_60 < last_working <= month_statutory:
        window = month_statutory - last_working
    else:
        window = month_statutory - month_60
    return wait(month_60) + window * (1.0 - window_share(coverage))
