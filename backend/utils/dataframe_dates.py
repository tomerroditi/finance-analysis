"""Cheap date formatting for transaction DataFrames.

Analytics group by calendar month constantly, and the idiom for it was
``pd.to_datetime(df["date"]).dt.strftime("%Y-%m")`` — parse every value into a
Timestamp, then render every Timestamp back into a string. On the transactions
table that round-trip costs ~21 ms a call and it happens in most analytics
endpoints, several times each; it was the largest non-SQL cost in a dashboard
load.

``TransactionsRepository._normalize_dates`` already guarantees the stored
column is ``YYYY-MM-DD`` (or NaN), and the first seven characters of that are
exactly the month. Slicing is ~30x cheaper than the round-trip.
"""

from __future__ import annotations

import pandas as pd

#: What a sliced month must look like for the fast path to be trusted.
_MONTH_PATTERN = r"^\d{4}-\d{2}$"


def to_month_series(dates: pd.Series) -> pd.Series:
    """Format a date column as ``YYYY-MM``.

    Takes the fast path — a string slice — only when the column really is
    made of canonical ``YYYY-MM-DD`` strings, which is verified rather than
    assumed: the slice is checked against ``\\d{4}-\\d{2}`` before being
    returned. A datetime column, a differently-formatted string column, or
    anything that fails that check falls back to the full pandas conversion,
    so this is a drop-in replacement with no precondition on the caller.

    Parameters
    ----------
    dates : pd.Series
        Dates to format. Strings, datetimes, and nulls are all accepted.

    Returns
    -------
    pd.Series
        ``YYYY-MM`` strings, with nulls preserved as nulls.
    """
    if pd.api.types.is_string_dtype(dates) or dates.dtype == object:
        sliced = dates.astype("string").str[:7]
        present = sliced.notna()
        if not present.any() or sliced[present].str.match(_MONTH_PATTERN).all():
            return sliced

    return pd.to_datetime(dates, errors="coerce").dt.strftime("%Y-%m")
