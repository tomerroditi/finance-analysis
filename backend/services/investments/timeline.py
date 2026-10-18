"""
One investment's value over time, resolved from its transactions and snapshots.

``ValuationTimeline`` is the single answer to "what was this holding worth on
date X": the latest snapshot on or before X, carried forward by the
transactions recorded after it, or — before the first snapshot — the negated
running sum of the transactions. It is pure (frames in, numbers out), so every
reader values a holding the same way.

A closed investment's zero is derived here rather than stored. It sits on the
last transaction date (the closure date when there are none), pushed forward to
the newest snapshot if one is later, and replaces any snapshot on that date.
Because it is computed from the transactions on every read, a transaction that
lands after the close — a sale's settlement, a re-dated or re-tagged row —
moves the zero with it, and nothing has to be kept in step on write.
"""

from bisect import bisect_right

import numpy as np
import pandas as pd

CLOSED_SOURCE = "closed"
"""``source`` of the derived zero a closed investment's snapshot list carries."""


class ValuationTimeline:
    """Snapshot-first valuation of one investment.

    Parameters
    ----------
    transactions : pd.DataFrame
        The investment's transactions (``date``, ``amount``; negative = deposit),
        opening-balance row included.
    snapshots : pd.DataFrame
        Its stored balance snapshots (``date``, ``balance``).
    is_closed : bool
        Whether the investment is closed.
    closed_date : str or None
        Closure date in ``YYYY-MM-DD`` format, used as the zero's date when the
        investment has no transactions and no snapshots.
    """

    def __init__(
        self,
        transactions: pd.DataFrame,
        snapshots: pd.DataFrame,
        is_closed: bool,
        closed_date: str | None,
    ) -> None:
        self.is_closed = bool(is_closed)
        self._txn_dates, self._cumulative = _running_balance(transactions)

        if snapshots.empty:
            points = {}
        else:
            points = {
                str(d): float(b)
                for d, b in zip(snapshots["date"], snapshots["balance"], strict=True)
            }
        self.closing_date = (
            _closing_date(self._txn_dates, points, closed_date)
            if self.is_closed
            else None
        )
        if self.closing_date is not None:
            points[self.closing_date] = 0.0
        self.snapshot_dates = sorted(points)
        self.snapshot_balances = np.array(
            [points[d] for d in self.snapshot_dates], dtype=float
        )

    @property
    def is_empty(self) -> bool:
        """Whether there is nothing to value: no transactions, no snapshots."""
        return self._txn_dates.size == 0 and not self.snapshot_dates

    @property
    def event_dates(self) -> list[str]:
        """Dates of the transactions, ascending (``YYYY-MM-DD``)."""
        return self._txn_dates.tolist()

    def value_at(self, as_of: str) -> float:
        """Return the balance on a date.

        Parameters
        ----------
        as_of : str
            Cut-off date (inclusive) in ``YYYY-MM-DD`` format.

        Returns
        -------
        float
            The latest snapshot on or before ``as_of`` plus the transactions
            after it, or the transaction-based balance when no snapshot
            precedes it.
        """
        idx = bisect_right(self.snapshot_dates, as_of) - 1
        if idx < 0:
            return self._flows(as_of)
        return float(self.snapshot_balances[idx]) + self._flows(
            as_of, after=self.snapshot_dates[idx]
        )

    def current_value(self, today: str) -> float:
        """Return the balance today; a closed investment is worth nothing.

        Parameters
        ----------
        today : str
            Today's date in ``YYYY-MM-DD`` format.

        Returns
        -------
        float
            ``0.0`` when closed, else :meth:`value_at` today.
        """
        return 0.0 if self.is_closed else self.value_at(today)

    def series(self, sample_dates: pd.DatetimeIndex) -> list[dict[str, float | str]]:
        """Sample the balance line, interpolating between snapshots.

        Between two snapshots the line is linear (a snapshot is an observation,
        and the market moved somewhere in between); past the newest snapshot it
        is that snapshot carried forward by the later transactions; before the
        first it is transaction-based.

        Parameters
        ----------
        sample_dates : pd.DatetimeIndex
            Dates to sample, ascending.

        Returns
        -------
        list[dict]
            ``{"date": "YYYY-MM-DD", "balance": float}`` per sample date.
        """
        snap_dates = np.array(self.snapshot_dates, dtype="datetime64[D]")
        out: list[dict[str, float | str]] = []
        for d in sample_dates:
            d_str = d.strftime("%Y-%m-%d")
            d64 = np.datetime64(d_str, "D")
            prev_idx = int(np.searchsorted(snap_dates, d64, side="right")) - 1
            next_idx = int(np.searchsorted(snap_dates, d64, side="left"))
            if prev_idx >= 0 and next_idx < snap_dates.size:
                prev_balance = float(self.snapshot_balances[prev_idx])
                total_days = int(
                    (snap_dates[next_idx] - snap_dates[prev_idx]).astype(int)
                )
                if total_days == 0:
                    balance = prev_balance
                else:
                    frac = int((d64 - snap_dates[prev_idx]).astype(int)) / total_days
                    balance = prev_balance + frac * (
                        float(self.snapshot_balances[next_idx]) - prev_balance
                    )
            else:
                balance = self.value_at(d_str)
            out.append({"date": d_str, "balance": balance})
        return out

    def _flows(self, as_of: str, after: str | None = None) -> float:
        """Return the balance the transactions in ``(after, as_of]`` imply.

        Parameters
        ----------
        as_of : str
            Cut-off date (inclusive) in ``YYYY-MM-DD`` format.
        after : str, optional
            Only transactions dated strictly after this date count.

        Returns
        -------
        float
            Their negated sum (a deposit of ``-1000`` adds ``1000``).
        """
        if self._txn_dates.size == 0:
            return 0.0
        end = int(np.searchsorted(self._txn_dates, as_of, side="right"))
        total = float(self._cumulative[end - 1]) if end > 0 else 0.0
        if after is not None:
            start = int(np.searchsorted(self._txn_dates, after, side="right"))
            total -= float(self._cumulative[start - 1]) if start > 0 else 0.0
        return total


def _running_balance(transactions: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Build a date-ordered running balance for point-in-time lookups.

    Parameters
    ----------
    transactions : pd.DataFrame
        One investment's transactions.

    Returns
    -------
    tuple of np.ndarray
        ``(dates, cumulative)`` — ``dates`` are ``YYYY-MM-DD`` strings in
        ascending order (lexical order is chronological for that format) and
        ``cumulative[i]`` is the balance implied by every transaction up to and
        including ``dates[i]``. Rows with an unparseable date are dropped.
    """
    empty = (np.array([], dtype="<U10"), np.array([], dtype=float))
    if transactions.empty or "amount" not in transactions.columns:
        return empty

    dates = pd.to_datetime(transactions["date"], errors="coerce")
    amounts = pd.to_numeric(transactions["amount"], errors="coerce").fillna(0.0)
    valid = dates.notna()
    if not valid.any():
        return empty
    dates, amounts = dates[valid], amounts[valid]

    order = np.argsort(dates.to_numpy(), kind="stable")
    return (
        dates.dt.strftime("%Y-%m-%d").to_numpy().astype("<U10")[order],
        np.cumsum(-amounts.to_numpy(dtype=float)[order]),
    )


def _closing_date(
    txn_dates: np.ndarray, snapshots: dict[str, float], closed_date: str | None
) -> str | None:
    """Return the date a closed investment's zero belongs on.

    Parameters
    ----------
    txn_dates : np.ndarray
        Ascending transaction dates (``YYYY-MM-DD``).
    snapshots : dict[str, float]
        Stored snapshots by date.
    closed_date : str or None
        Closure date, the fallback when there are no transactions.

    Returns
    -------
    str or None
        The last transaction date (else ``closed_date``), pushed forward to
        the newest snapshot when one is later; ``None`` when there is nothing
        to date it by.
    """
    candidates = [str(txn_dates[-1]) if txn_dates.size else closed_date]
    if snapshots:
        candidates.append(max(snapshots))
    dated = [c for c in candidates if c]
    return max(dated) if dated else None
