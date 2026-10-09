"""Shared constants and month helpers for the savings-goal service.

Pure functions only — no database access — so every mixin of
``SavingsGoalService`` can use them without pulling in another's state.
"""

import math
from collections.abc import Iterator

import pandas as pd

# Half an agora. Every amount reported is rounded to two decimals, but a goal's
# totals are summed from many entries and transactions, so a goal that filled
# exactly can land a hair under its target through float error alone —
# reading as "100%, 0 to go" yet never achieved. Comparisons absorb that with
# the same precision the payload is rounded to.
ROUNDING_EPSILON = 0.005


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
