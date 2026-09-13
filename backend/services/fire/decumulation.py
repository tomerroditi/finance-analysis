"""The reference's decumulation return — measured, not derived.

After retirement a withdrawal portfolio stops earning the return the user typed
and earns a much lower, confidence-derived one instead (notes/07). The
reference calls this a Trinity-study result at 75% equities; the underlying
formula is not recoverable from the outside, so this module ships the surface
**measured directly** off the calculator.

How it was measured: pin the retirement age, hand the plan a cash pile large
enough that the portfolio is never drawn, and read the portfolio's
post-retirement growth straight off the chart. 41 cells over five confidence
levels (`research/zeke_retire_calc/probe_trinity.py`).

The surface has a genuine **discontinuity at 60** — the rate falls to zero by
about age 54, stays there through 60, then jumps back to ~2.7% at 61 and
declines slowly. Retiring after 60 means there is no bridge left to fund before
the pension is reachable, so the constraint changes. Interpolation must
therefore never cross that boundary.
"""

from __future__ import annotations

import json
from bisect import bisect_left
from functools import lru_cache
from pathlib import Path

TABLE_PATH = Path(__file__).with_name("decumulation_table.json")
BRANCH_AGE = 60.5
"""Ages above this use the post-60 branch of the table."""


@lru_cache(maxsize=1)
def _table() -> dict[float, dict[float, float]]:
    raw = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
    return {float(rule): {float(age): rate for age, rate in ages.items()}
            for rule, ages in raw.items()}


def _interpolate(points: list[tuple[float, float]], x: float) -> float:
    """Linear interpolation with flat extrapolation past either end."""
    if not points:
        return 0.0
    if x <= points[0][0]:
        return points[0][1]
    if x >= points[-1][0]:
        return points[-1][1]
    index = bisect_left([p[0] for p in points], x)
    (x0, y0), (x1, y1) = points[index - 1], points[index]
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def _for_rule(rule: float, retire_age: float) -> float:
    ages = _table()[rule]
    post = retire_age > BRANCH_AGE
    branch = sorted((age, rate) for age, rate in ages.items()
                    if (age > BRANCH_AGE) == post)
    if not branch:
        branch = sorted(ages.items())
    return _interpolate(branch, retire_age)


def decumulation_return_pct(confidence: float, retire_age: float) -> float:
    """Real return a withdrawal portfolio earns after retirement.

    `confidence` is the `retireRule` field; the reference rejects anything below
    80, and the table covers 80-100 in steps of five.
    """
    rules = sorted(_table())
    confidence = min(max(confidence, rules[0]), rules[-1])
    if confidence in _table():
        return _for_rule(confidence, retire_age)
    index = bisect_left(rules, confidence)
    low, high = rules[index - 1], rules[index]
    low_rate = _for_rule(low, retire_age)
    high_rate = _for_rule(high, retire_age)
    weight = (confidence - low) / (high - low)
    return low_rate + (high_rate - low_rate) * weight
