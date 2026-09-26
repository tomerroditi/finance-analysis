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
seven-year window and a woman's five-year one. `y = x / (2 - x)`: the window
is scaled by the uncovered need over the average of the need levels before
and after 60 (a pension that covers everything ends the bridge at 60).

**Past 60, the reference mixes an index into a duration.** A claim that is
still ahead is waited for (`claim - last working month`), but one already
behind the retirement contributes its month index *counted from today*, plus
one. So a man retiring at 63 reads the surface 27.4 years out if he is 36 today
and 22.8 if he is 41 — reproduced exactly across four birth dates, three
tactics and both genders. It is the reference's behaviour, so it is cloned.
"""

from __future__ import annotations

from itertools import pairwise


def window_share(coverage: float) -> float:
    """`y(x) = x / (2 - x)`: how much of the 60-to-statutory window a pension removes.

    Equivalently the window shrinks to `(E - P) / (E - P/2)` of itself: the
    uncovered need after 60 over the plain average of the need before and
    after it. Fitted to 14 measured points at 2e-4, which is their own
    measurement noise; full coverage ends the bridge at 60.
    """
    if coverage >= 1.0:
        return 1.0
    if coverage <= 0.0:
        return 0.0
    return coverage / (2.0 - coverage)


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


STATE_PENSION = 2757.0
STATE_PENSION_AT_80 = 2911.5
"""Bituach Leumi's 2026 individual allowance at the full 50% seniority increment
(1,838 x 1.5), and from 80 (1,941 x 1.5). The dependent-spouse increment does
not enter the bridge."""


def couple_bridge_months(
    last_working: int, horizon: int, spending: float, spouses: list[dict]
) -> float:
    """Horizon, in months, for a couple (notes/18 §6).

    The time from the last working month to the horizon (the younger spouse's
    81) is cut at every spouse's 60th birthday and statutory age. Each phase
    needs the spending less the income running at its end: pensions claimed
    at 60 (net), and from the statutory age the rest of the pension and the
    old-age allowance, floored at zero. A phase needing everything counts in
    full; a partly covered one counts its length times its need over the plain
    average of the non-zero needs. The single-person rule is the same
    averaging over two phases (`window_share`).

    Each spouse is a dict of `month_60`, `month_statutory`, `month_80` (months
    counted from today) and `at_60`, `at_statutory` (monthly amounts).
    """
    events = {last_working, horizon}
    for spouse in spouses:
        for key in ("month_60", "month_statutory"):
            if last_working < spouse[key] < horizon:
                events.add(spouse[key])
    cuts = sorted(events)
    phases = []
    for start, end in pairwise(cuts):
        income = 0.0
        for spouse in spouses:
            if end > spouse["month_60"]:
                income += spouse["at_60"]
            if end > spouse["month_statutory"]:
                income += spouse["at_statutory"]
                income += (
                    STATE_PENSION_AT_80 if end > spouse["month_80"] else STATE_PENSION
                )
        phases.append((end - start, max(spending - income, 0.0)))
    needs = [need for _, need in phases if need > 0]
    if not needs:
        return 0.0
    average = sum(needs) / len(needs)
    return sum(
        length if need >= spending else length * need / average
        for length, need in phases
    )
