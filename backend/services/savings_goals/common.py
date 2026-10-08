"""Shared constants and month helpers for the savings-goal engine.

Pure functions only — no database access — so every mixin of
``SavingsGoalService`` can use them without pulling in another's state.
"""

import math
from collections.abc import Iterator

import pandas as pd

from backend.models.savings_goal import GOAL_KIND_INVESTMENT, SavingsGoal

# Half an agora. Every amount the ledger reports is rounded to two decimals,
# but `funded` is accumulated by summing dozens of stored rows, so a goal that
# filled exactly can land a hair under its target through float error alone —
# reading as "100%, 0 to go" yet never achieved, and never auto-closing.
# Comparisons against a target absorb that with the same precision the rest of
# the payload is rounded to.
ROUNDING_EPSILON = 0.005


def is_investment_goal(goal: SavingsGoal) -> bool:
    """Whether a goal is filled by investment transfers rather than surplus."""
    return goal.kind == GOAL_KIND_INVESTMENT


def month_key(value: object) -> tuple[int, int] | None:
    """Parse ``YYYY-MM`` (or ``YYYY-MM-DD``) into a ``(year, month)`` tuple."""
    if not value or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        ts = pd.Timestamp(str(value)[:7] + "-01")
    except (ValueError, TypeError):
        return None
    return int(ts.year), int(ts.month)


def month_str(key: tuple[int, int]) -> str:
    """Render a ``(year, month)`` tuple as ``YYYY-MM``."""
    return f"{key[0]:04d}-{key[1]:02d}"


def same_amount(stored: float, computed: float) -> bool:
    """Check whether a recomputed allocation is the same money as the stored one.

    Compared with a tolerance rather than ``==``: allocations are the result
    of a float waterfall, so an identical ledger can reproduce to the last
    bit or a few ULPs away depending on summation order. Half an agora is
    far below anything the UI renders and far above that noise.

    Parameters
    ----------
    stored : float
        Amount currently on record.
    computed : float
        Amount the simulation just produced.

    Returns
    -------
    bool
        True when the two round to the same displayed value.
    """
    return abs(stored - computed) < ROUNDING_EPSILON


def iter_months(
    start: tuple[int, int], end: tuple[int, int]
) -> Iterator[tuple[int, int]]:
    """Yield every ``(year, month)`` from ``start`` through ``end`` inclusive."""
    year, month = start
    while (year, month) <= end:
        yield year, month
        month += 1
        if month > 12:
            year, month = year + 1, 1
