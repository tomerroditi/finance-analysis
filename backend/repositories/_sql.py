"""Small helpers shared by the repositories: IN-list chunking, ORM -> pandas."""

from collections.abc import Iterator, Sequence
from typing import Any

import pandas as pd

# SQLite caps bound parameters per statement (999 on older builds); long
# ``IN (...)`` lists are split into slices of this size.
IN_CHUNK = 500


def chunked[T](values: Sequence[T], size: int = IN_CHUNK) -> Iterator[list[T]]:
    """Yield ``values`` in slices small enough for a SQL ``IN`` clause.

    Parameters
    ----------
    values : Sequence[T]
        Values to split.
    size : int, optional
        Maximum slice length. Defaults to ``IN_CHUNK``.

    Yields
    ------
    list[T]
        Consecutive slices of ``values``; nothing when ``values`` is empty.
    """
    for start in range(0, len(values), size):
        yield list(values[start : start + size])


def orm_to_dict(record: Any) -> dict[str, Any]:
    """Return an ORM instance's loaded attributes as a plain dict.

    Parameters
    ----------
    record : Any
        A SQLAlchemy ORM instance.

    Returns
    -------
    dict[str, Any]
        Its ``__dict__`` without SQLAlchemy's ``_sa_instance_state``.
    """
    return {k: v for k, v in record.__dict__.items() if k != "_sa_instance_state"}


def orm_rows_to_frame(
    records: Sequence[Any], columns: list[str] | None = None
) -> pd.DataFrame:
    """Build a DataFrame from ORM instances.

    Parameters
    ----------
    records : Sequence[Any]
        SQLAlchemy ORM instances of one model.
    columns : list[str] or None, optional
        Columns of the empty frame returned when ``records`` is empty; a
        column-less frame when omitted.

    Returns
    -------
    pd.DataFrame
        One row per record, one column per loaded attribute.
    """
    if not records:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame([orm_to_dict(r) for r in records])
