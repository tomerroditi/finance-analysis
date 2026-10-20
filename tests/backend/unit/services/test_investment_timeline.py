"""Tests for the pure ``ValuationTimeline`` resolving one investment's value."""

import pandas as pd
import pytest

from backend.services.investments.timeline import ValuationTimeline


def _txns(rows: list[tuple[object, float]]) -> pd.DataFrame:
    """Build a transactions frame from ``(date, amount)`` pairs."""
    return pd.DataFrame({"date": [r[0] for r in rows], "amount": [r[1] for r in rows]})


def _snaps(rows: list[tuple[str, float]]) -> pd.DataFrame:
    """Build a snapshots frame from ``(date, balance)`` pairs."""
    return pd.DataFrame({"date": [r[0] for r in rows], "balance": [r[1] for r in rows]})


def _timeline(
    txns: list[tuple[object, float]] | None = None,
    snaps: list[tuple[str, float]] | None = None,
    is_closed: bool = False,
    closed_date: str | None = None,
) -> ValuationTimeline:
    """Build a timeline from row lists."""
    return ValuationTimeline(
        _txns(txns or []), _snaps(snaps or []), is_closed, closed_date
    )


class TestValueFromTransactions:
    """Without snapshots the value is the negated running sum of the flows."""

    def test_unordered_rows_sum_in_date_order(self):
        """Storage order does not change the balance at any date."""
        tl = _timeline([("2024-03-01", -300.0), ("2024-01-01", -1000.0), ("2024-02-01", 250.0)])

        assert tl.value_at("2023-12-31") == 0.0
        assert tl.value_at("2024-01-01") == pytest.approx(1000.0)
        assert tl.value_at("2024-02-01") == pytest.approx(750.0)
        assert tl.value_at("2024-12-31") == pytest.approx(1050.0)

    def test_same_day_rows_land_on_the_same_side(self):
        """Several rows on one day are all in or all out of the cut-off."""
        tl = _timeline([("2024-01-10", -500.0), ("2024-01-10", -250.0), ("2024-01-10", 100.0)])

        assert tl.value_at("2024-01-09") == 0.0
        assert tl.value_at("2024-01-10") == pytest.approx(650.0)

    def test_undated_rows_are_dropped(self):
        """A row with a missing or unparseable date is excluded, not raised."""
        tl = _timeline(
            [("2024-01-01", -1000.0), (float("nan"), -9999.0), ("not-a-date", -9999.0)]
        )

        assert tl.value_at("2024-06-01") == pytest.approx(1000.0)

    def test_empty_is_worth_nothing(self):
        """No transactions and no snapshots values at zero and reports empty."""
        tl = _timeline()

        assert tl.is_empty
        assert tl.value_at("2024-01-01") == 0.0


class TestSnapshotFirst:
    """A snapshot overrides the flows before it and is carried by those after."""

    def test_snapshot_carried_forward_by_later_flows(self):
        """The latest snapshot plus the transactions after it."""
        tl = _timeline(
            [("2024-01-01", -1000.0), ("2024-02-01", -500.0), ("2024-03-01", 200.0)],
            [("2024-01-31", 1200.0)],
        )

        assert tl.value_at("2024-01-15") == pytest.approx(1000.0)
        assert tl.value_at("2024-01-31") == pytest.approx(1200.0)
        assert tl.value_at("2024-02-01") == pytest.approx(1700.0)
        assert tl.value_at("2024-03-15") == pytest.approx(1500.0)

    def test_series_interpolates_between_snapshots(self):
        """Between two snapshots the line is linear."""
        tl = _timeline(snaps=[("2024-01-01", 1000.0), ("2024-01-11", 2000.0)])

        series = tl.series(pd.to_datetime(["2024-01-01", "2024-01-06", "2024-01-11"]))

        assert [p["balance"] for p in series] == pytest.approx([1000.0, 1500.0, 2000.0])


class TestClosingZero:
    """A closed investment's zero is derived from its data."""

    def test_zero_sits_on_the_last_transaction(self):
        """The zero lands on the last transaction date and stops the carry."""
        tl = _timeline(
            [("2024-01-01", -1000.0), ("2024-02-01", 1100.0)],
            is_closed=True,
            closed_date="2024-01-20",
        )

        assert tl.closing_date == "2024-02-01"
        assert tl.value_at("2024-01-15") == pytest.approx(1000.0)
        assert tl.value_at("2024-02-01") == 0.0
        assert tl.value_at("2024-12-31") == 0.0
        assert tl.current_value("2024-12-31") == 0.0

    def test_zero_follows_a_later_snapshot(self):
        """A snapshot after the last transaction pushes the zero onto its date."""
        tl = _timeline(
            [("2024-01-01", -1000.0)],
            [("2024-03-01", 1300.0)],
            is_closed=True,
            closed_date="2024-01-01",
        )

        assert tl.closing_date == "2024-03-01"
        assert tl.snapshot_dates == ["2024-03-01"]
        assert tl.value_at("2024-03-01") == 0.0

    def test_zero_falls_back_to_the_closed_date(self):
        """With no transactions or snapshots the closure date dates the zero."""
        tl = _timeline(is_closed=True, closed_date="2024-05-05")

        assert tl.closing_date == "2024-05-05"
        assert tl.snapshot_dates == ["2024-05-05"]

    def test_open_investment_has_no_zero(self):
        """An open investment keeps its stored snapshots only."""
        tl = _timeline([("2024-01-01", -1000.0)], [("2024-02-01", 1100.0)])

        assert tl.closing_date is None
        assert tl.snapshot_dates == ["2024-02-01"]
        assert tl.current_value("2024-03-01") == pytest.approx(1100.0)
