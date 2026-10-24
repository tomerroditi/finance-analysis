"""Tests for the running month: sync edges, the still-due window, baselines."""

import pandas as pd
import pytest

from backend.services.running_month import (
    RunningMonth,
    still_due,
    typical,
)

TODAY = pd.Timestamp("2026-03-19")


def _charge(expected: str, amount: float = 100.0, status: str = "active") -> dict:
    """One confirmed recurring item as ``get_confirmed_items`` returns it."""
    return {
        "label": f"BILL {expected}",
        "normalized": f"bill {expected}",
        "amount": amount,
        "next_expected_date": expected,
        "status": status,
    }


class TestStillDue:
    """One window decides what the month still owes."""

    def test_window_runs_from_the_edge_through_month_end(self):
        """Both ends are inclusive."""
        end = pd.Timestamp("2026-03-31")
        edge = pd.Timestamp("2026-03-10")
        assert still_due(edge, edge, end)
        assert still_due(end, edge, end)
        assert not still_due(pd.Timestamp("2026-03-09"), edge, end)
        assert not still_due(pd.Timestamp("2026-04-01"), edge, end)


class TestChargesDue:
    """Committed charges are read off the edge the data reaches, not today."""

    def test_a_bill_a_stale_sync_has_not_shown_is_still_due(self):
        """Expected after the last sync but before today: unseen, so owed."""
        running = RunningMonth(
            today=TODAY, edges={("leumi", "acct"): pd.Timestamp("2026-03-10")}
        )
        due = running.charges_due([_charge("2026-03-15")])
        assert [c["expected_date"] for c in due] == ["2026-03-15"]

    def test_a_bill_due_today_on_a_current_sync_is_still_due(self):
        """A sighted charge rolls on, so one expected today has not landed."""
        running = RunningMonth(today=TODAY, edges={})
        assert [c["amount"] for c in running.charges_due([_charge("2026-03-19")])] == [
            100.0
        ]

    def test_before_the_edge_and_after_month_end_are_not_due(self):
        """Outside the window nothing is held back."""
        running = RunningMonth(today=TODAY, edges={})
        assert running.charges_due([_charge("2026-03-18"), _charge("2026-04-02")]) == []

    def test_an_ended_charge_is_never_due(self):
        """A charge detection calls ended owes nothing, whatever its date."""
        running = RunningMonth(today=TODAY, edges={})
        assert running.charges_due([_charge("2026-03-25", status="ended")]) == []

    def test_charges_come_soonest_first(self):
        """The Overview lists them in the order they will land."""
        running = RunningMonth(today=TODAY, edges={})
        due = running.charges_due([_charge("2026-03-28"), _charge("2026-03-21")])
        assert [c["expected_date"] for c in due] == ["2026-03-21", "2026-03-28"]


class TestProjection:
    """A baseline is projected over each account's own unsynced days."""

    def test_equal_freshness_collapses_to_the_calendar_share(self):
        """Shares sum to 1, so one edge for everyone is the plain form."""
        edge = pd.Timestamp("2026-03-19")
        running = RunningMonth(today=TODAY, edges={("a", "1"): edge, ("b", "2"): edge})
        projected = running.project(3100.0, {("a", "1"): 0.25, ("b", "2"): 0.75})
        assert projected == pytest.approx(100.0 * 12)

    def test_each_account_contributes_its_own_gap(self):
        """A stale bank and a current card are two different holes."""
        running = RunningMonth(
            today=TODAY,
            edges={
                ("card", "1"): pd.Timestamp("2026-03-19"),
                ("bank", "2"): pd.Timestamp("2026-03-05"),
            },
        )
        projected = running.project(3100.0, {("card", "1"): 0.5, ("bank", "2"): 0.5})
        assert projected == pytest.approx(50.0 * 12 + 50.0 * 26)

    def test_an_unscraped_account_is_current(self):
        """No credential means the user types it in; it is never behind."""
        running = RunningMonth(today=TODAY, edges={})
        assert running.unobserved_days(None) == 12

    def test_an_edge_before_the_month_leaves_the_whole_month_unseen(self):
        """A sync last month has reported nothing of this one."""
        running = RunningMonth(today=TODAY, edges={})
        assert running.unobserved_days(pd.Timestamp("2026-02-20")) == 31


class TestTypical:
    """A typical month is the median of complete months."""

    def test_the_running_month_is_left_out(self):
        """A half-reported month is not evidence of a typical one."""
        months = [
            {"month": "2026-01", "income": 10.0},
            {"month": "2026-02", "income": 20.0},
            {"month": "2026-03", "income": 1.0},
        ]
        assert typical(months, "income", TODAY) == 15.0

    def test_one_windfall_does_not_move_the_median(self):
        """The month the household sold a car is not its typical month."""
        months = [{"month": f"2025-{m:02d}", "income": 100.0} for m in range(7, 12)]
        months.append({"month": "2025-12", "income": 100_000.0})
        assert typical(months, "income", TODAY) == 100.0

    def test_only_the_last_count_months_are_read(self):
        """Older months fall out of the window."""
        months = [{"month": f"2025-{m:02d}", "income": float(m)} for m in range(1, 13)]
        assert typical(months, "income", TODAY, count=3) == 11.0

    def test_no_complete_month_means_no_baseline(self):
        """A first month has nothing to be typical of."""
        assert typical([{"month": "2026-03", "income": 5.0}], "income", TODAY) == 0.0
