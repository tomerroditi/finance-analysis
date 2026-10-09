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
SPOUSE_INCREMENT = 1386.0
"""Bituach Leumi's 2026 individual allowance at the full 50% seniority increment
(1,838 x 1.5), from 80 (1,941 x 1.5), and the dependent-spouse increment
(924 x 1.5) — which the bridge pays only while the other spouse is under 60."""


def couple_bridge_months(
    last_working: int, horizon: int, spending: float, spouses: list[dict]
) -> float:
    """Horizon, in months, for a couple (notes/18 §6).

    The time from the last working month to the horizon (the older spouse's
    81) is cut at every spouse's 60th birthday and statutory age. Each phase
    needs the spending less the income running in its last month, floored at
    zero: pensions claimed at 60 (net of income tax, and of national insurance
    until the statutory age), and from the statutory age the rest of
    the pension and the old-age allowance — with the spouse increment while
    the other spouse is not yet 60. A phase needing the whole spending counts
    in full — every phase does when one-off income drives the spending below
    zero (`cx1_036`) — and any other counts its length times its need over
    the running mean of the needs up to and including it. The single-person rule is the same thing over two
    phases (`window_share`).

    Each spouse is a dict of `month_60`, `month_statutory`, `month_80` (months
    counted from today), `at_60` (net of the national-insurance contributions
    due until the statutory age), `at_60_past_statutory` (the same annuity
    once they stop), `at_statutory` (monthly amounts), `claims_at_60` — a
    spouse on tactic `67` cuts no phase at 60 — and `draws_allowance`, false
    for a spouse already past the statutory age today.
    """
    behind: set[int] = set()
    events = {last_working, horizon}
    for spouse in spouses:
        for key in ("month_60", "month_statutory"):
            if key == "month_60" and not spouse["claims_at_60"]:
                continue
            if spouse[key] < last_working:
                behind.add(spouse[key])
            elif spouse[key] < horizon:
                events.add(spouse[key])
    phases = [(month + 1, month) for month in sorted(behind)]
    if any(
        spouse["month_60"] == last_working and spouse["claims_at_60"]
        for spouse in spouses
    ):
        phases.append((0, last_working))
    phases += [(end - start, end) for start, end in pairwise(sorted(events))]
    months = 0.0
    needs: list[float] = []
    for length, end in phases:
        income = 0.0
        for spouse, other in zip(spouses, reversed(spouses), strict=True):
            if end > spouse["month_statutory"]:
                income += spouse["at_60_past_statutory"] + spouse["at_statutory"]
                if spouse.get("draws_allowance", True):
                    income += (
                        STATE_PENSION_AT_80
                        if end > spouse["month_80"]
                        else STATE_PENSION
                    )
                    if end <= other["month_60"]:
                        income += SPOUSE_INCREMENT
            elif end > spouse["month_60"]:
                income += spouse["at_60"]
        need = max(spending - income, 0.0)
        needs.append(need)
        mean = sum(needs) / len(needs)
        if need >= spending:
            months += length
        elif mean > 0:
            months += length * need / mean
    return months
