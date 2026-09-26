"""Every recorded reference run, replayed once and checked on every series.

Each fixture in `research/zeke_retire_calc/fixtures` is a real answer from the
reference calculator: the form that was submitted and the monthly series it
charted. This module replays each one through our engine at the reference's own
retirement month, with **nothing** fitted or supplied, and compares all of it —
the asset chart, the income and expense charts (a closed decomposition of every
shekel in and out, notes/16), and net worth — in every month to age 81.

One replay per fixture serves every assertion about it; the corpus is a few
hundred runs, and replaying each once per module is what used to dominate the
suite's time.
"""

from __future__ import annotations

import pytest

import parity

TOLERANCE = 15.0
"""Shekels, on any series in any month. The reference prints one decimal, and
over 533 months of compounding that rounding alone reaches a few shekels on a
seven-figure balance."""

DISPLAY_PRECISION = 1e-7
"""The same rounding, relative to the run's peak net worth: a surface probe that
parks 1e9 in a portfolio carries tens of shekels of it."""

RELATIVE_TARGET = 0.001
"""The acceptance bar: no run may be off by more than 0.1% of its peak net worth
on any series in any month — known gaps included."""

KNOWN_GAPS: dict[str, tuple[float, str]] = {}
"""Runs outside `TOLERANCE`, each bounded and named.

A bound is asserted, so a regression that widens a gap still fails, and a gap
that closes must leave the dict (`test_known_gap_is_still_open`)."""

CHARTED = parity.corpus(charted=True)


def _bound(report: parity.Report) -> float:
    return max(TOLERANCE, DISPLAY_PRECISION * report.scale)


@pytest.fixture(scope="module")
def reports() -> dict[str, parity.Report]:
    """Lazily replayed fixtures, shared by every test in the module."""
    return {}


def _report(reports: dict[str, parity.Report], name: str) -> parity.Report:
    if name not in reports:
        reports[name] = parity.diff(name)
    return reports[name]


class TestCorpusParity:
    """The engine reproduces every recorded run."""

    @pytest.mark.parametrize("name", CHARTED)
    def test_every_series_matches(self, reports, name):
        """Assets, income, expenses and net worth agree in every month."""
        report = _report(reports, name)
        assert report.error is None, report.error
        assert not report.unmapped, f"{name}: rows the harness cannot map {report.unmapped}"
        assert report.months[0] == report.months[1], (
            f"{name}: horizon of {report.months[0]} months, reference {report.months[1]}")
        worst = max(report.series, key=lambda s: s.worst)
        where = (f"{worst.chart} {worst.label!r} month {worst.worst_month}: "
                 f"reference {worst.reference:,.2f} vs ours {worst.ours:,.2f}")
        assert report.relative < RELATIVE_TARGET, (
            f"{name}: off by {report.relative:.4%} of peak net worth — {where}")
        bound, why = KNOWN_GAPS.get(name, (_bound(report), ""))
        assert report.worst < bound, (
            f"{name}: worst gap {report.worst:,.2f} exceeds {bound:,.2f} — {where}"
            + (f" (known gap: {why})" if why else ""))

    @pytest.mark.parametrize("name", CHARTED)
    def test_the_two_sides_balance(self, reports, name):
        """Our decomposition closes every month, exactly as the reference's does.

        An internal identity rather than a comparison: every shekel booked as
        coming in is booked going somewhere, which is what turns a missing row
        into a mismatch instead of a silent loss.
        """
        result = _report(reports, name).result
        for record in result.months:
            assert sum(record.incomes.values()) == pytest.approx(
                sum(record.expenses.values()), abs=1e-6), (
                f"{name}: month {record.index} does not balance")

    @pytest.mark.parametrize("name", sorted(KNOWN_GAPS))
    def test_known_gap_is_still_open(self, reports, name):
        """A gap that has closed must leave `KNOWN_GAPS`, or it hides a regression."""
        report = _report(reports, name)
        assert report.worst >= _bound(report), (
            f"{name} now matches to {report.worst:.2f} — remove it from KNOWN_GAPS")
