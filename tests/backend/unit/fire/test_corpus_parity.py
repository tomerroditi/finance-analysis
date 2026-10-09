"""Every recorded reference run, replayed once and checked on every series.

Each fixture in `research/zeke_retire_calc/fixtures` is a real answer from the
reference calculator: the form that was submitted and the monthly series it
charted. This module replays each one through our engine at the reference's own
retirement month, with **nothing** fitted or supplied, and compares all of it —
the asset chart, the income and expense charts (a closed decomposition of every
shekel in and out, notes/16), and net worth — in every month to age 81.

One replay per fixture serves every assertion about it; the corpus is a couple
of thousand runs, and replaying each once per module is what used to dominate
the suite's time.
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

LOTS = "synthetic FIFO/LIFO lot history: tens of shekels on 8-24M portfolios (notes/13)"
CURVE = "coverage curve y(x) interpolated between its measured points"
RESIDUE = "multi-feature residue under 0.1%, not yet traced"

KNOWN_GAPS: dict[str, tuple[float, str]] = {
    "cp6_g108_e20k": (22, RESIDUE),  # 0.0005%
    "cx1_000": (1404, RESIDUE),  # 0.0101%
    "cx1_020": (36, RESIDUE),  # 0.0013%
    "cx1_035": (1192, RESIDUE),  # 0.0183%
    "cx2_001": (295, RESIDUE),  # 0.0034%
    "cx2_002": (1239, RESIDUE),  # 0.0120%
    "cx2_021": (85, RESIDUE),  # 0.0006%
    "cx2_025": (5459, RESIDUE),  # 0.0460%
    "cx2_033": (263, RESIDUE),  # 0.0027%
    "cx2_037": (29, RESIDUE),  # 0.0002%
    "cx2_041": (898, RESIDUE),  # 0.0231%
    "cx2_042": (130, RESIDUE),  # 0.0011%
    "cx2_044": (73, RESIDUE),  # 0.0009%
    "lt2_fifo_p90": (27, LOTS),  # 0.0002%
    "lt2_lifo_p20": (22, LOTS),  # 0.0002%
    "lt2_lifo_p50": (22, LOTS),  # 0.0002%
    "lt2_lifo_p70": (29, LOTS),  # 0.0002%
    "lt2_lifo_p70_big": (34, LOTS),  # 0.0001%
    "lt2_lifo_p70_fee": (22, LOTS),  # 0.0002%
    "lt2_lifo_p70_r8": (38, LOTS),  # 0.0003%
    "lt2_lifo_p90": (29, LOTS),  # 0.0002%
    "tx2_couple_nostack": (46, RESIDUE),  # 0.0003%
    "tx2_couple_stack": (75, RESIDUE),  # 0.0004%
}
"""Runs outside their tolerance, each bounded and named.

A bound is asserted, so a regression that widens a gap still fails, and a gap
that closes must leave the dict (`test_known_gap_is_still_open`). A named gap
is excused from `RELATIVE_TARGET` only if it is one of `OVER_TARGET`'s causes."""

OVER_TARGET: set[str] = set()
"""Causes allowed past 0.1% — none are open."""

SURFACE_PROBES = parity.SURFACE_PROBES
"""The idle-portfolio probes that measure the surface. They park 1e9, so they
carry tens of shekels of display rounding — `DISPLAY_PRECISION` covers it."""

SURFACE_SAMPLE = 8
"""Replay every eighth surface probe. Each cell is already checked against the
recovered solver directly (`test_decumulation_table`); the replays that remain
exercise the bridge rule across ~140 birth dates, which is what they add."""

def _charted() -> list[str]:
    names = parity.corpus(charted=True)
    probes = [n for n in names if n.startswith(SURFACE_PROBES)]
    return [n for n in names if not n.startswith(SURFACE_PROBES)] + probes[::SURFACE_SAMPLE]


CHARTED = _charted()


def _bound(report: parity.Report) -> float:
    return max(TOLERANCE, DISPLAY_PRECISION * report.scale)


class TestCorpusParity:
    """The engine reproduces every recorded run."""

    @pytest.mark.parametrize("name", CHARTED)
    def test_every_series_matches(self, name):
        """Assets, income, expenses and net worth agree in every month.

        Also asserts our own decomposition closes every month, exactly as the
        reference's does — an identity rather than a comparison: every shekel
        booked as coming in is booked going somewhere, which is what turns a
        missing row into a mismatch instead of a silent loss. Both ride on the
        one replay.
        """
        report = parity.diff(name)
        assert report.error is None, report.error
        assert not report.unmapped, f"{name}: rows the harness cannot map {report.unmapped}"
        assert report.months[0] == report.months[1], (
            f"{name}: horizon of {report.months[0]} months, reference {report.months[1]}")
        for record in report.result.months:
            assert sum(record.incomes.values()) == pytest.approx(
                sum(record.expenses.values()), abs=1e-6), (
                f"{name}: month {record.index} does not balance")
        worst = max(report.series, key=lambda s: s.worst)
        where = (f"{worst.chart} {worst.label!r} month {worst.worst_month}: "
                 f"reference {worst.reference:,.2f} vs ours {worst.ours:,.2f}")
        bound, why = KNOWN_GAPS.get(name, (_bound(report), ""))
        if why not in OVER_TARGET:
            assert report.relative < RELATIVE_TARGET, (
                f"{name}: off by {report.relative:.4%} of peak net worth — {where}")
        assert report.worst < bound, (
            f"{name}: worst gap {report.worst:,.2f} exceeds {bound:,.2f} — {where}"
            + (f" (known gap: {why})" if why else ""))

    @pytest.mark.parametrize("name", sorted(KNOWN_GAPS))
    def test_known_gap_is_still_open(self, name):
        """A gap that has closed must leave `KNOWN_GAPS`, or it hides a regression."""
        report = parity.diff(name)
        assert report.worst >= _bound(report), (
            f"{name} now matches to {report.worst:.2f} — remove it from KNOWN_GAPS")
