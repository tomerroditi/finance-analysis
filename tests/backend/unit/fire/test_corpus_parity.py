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

COUPLE = "a couple's bridge — the one open question (notes/18 §6)"
LOTS = "synthetic FIFO/LIFO lot history (notes/13)"
CURVE = "coverage curve y(x) interpolated between its measured points"
RULE = "confidence off the measured grid (85.5 between 85 and 90)"
RESIDUE = "multi-feature residue under 0.1%, not yet traced"

KNOWN_GAPS: dict[str, tuple[float, str]] = {
    "cp2_empty_1985": (90483, COUPLE),  # 5.5402%
    "cp2_empty_1990": (23337, COUPLE),  # 1.3518%
    "cp2_empty_1995": (34345, COUPLE),  # 1.9291%
    "cp2_main_s10": (24911, COUPLE),  # 0.7504%
    "cp2_main_s30_1985": (162171, COUPLE),  # 4.9849%
    "cp2_main_s30_1995": (2850, COUPLE),  # 0.0858%
    "cp2_main_s50": (38525, COUPLE),  # 1.1842%
    "cp2_main_s90": (12697, COUPLE),  # 0.3903%
    "cp3_f1980": (274598, COUPLE),  # 16.8134%
    "cp3_f1988": (47115, COUPLE),  # 2.8387%
    "cp3_f2000": (69740, COUPLE),  # 3.8878%
    "cp3_m1985": (60730, COUPLE),  # 3.7184%
    "cp3_m1995": (43946, COUPLE),  # 2.4685%
    "cp3_mainfemale_1990": (32144, COUPLE),  # 1.8619%
    "cp4_1978_01": (280962, COUPLE),  # 17.2030%
    "cp4_1983_01": (93425, COUPLE),  # 5.7203%
    "cp4_1987_01": (36792, COUPLE),  # 2.1818%
    "cp4_1988_01": (24716, COUPLE),  # 1.4428%
    "cp4_1989_07": (6270, COUPLE),  # 0.3576%
    "cp4_1990_07": (4689, COUPLE),  # 0.2654%
    "cp4_1992_01": (26404, COUPLE),  # 1.4831%
    "cp4_1995_01": (43946, COUPLE),  # 2.4685%
    "cp4_2000_01": (84526, COUPLE),  # 4.7121%
    "cp_both": (84960, COUPLE),  # 1.7434%
    "cp_main_only": (31447, COUPLE),  # 0.9588%
    "cp_main_t67_partner_t60": (94617, COUPLE),  # 2.3286%
    "cp_partner_male": (31994, COUPLE),  # 0.9638%
    "cp_partner_older": (341908, COUPLE),  # 10.5098%
    "cp_partner_only": (77238, COUPLE),  # 2.3455%
    "cp_partner_t60": (94617, COUPLE),  # 3.8726%
    "cp_partner_younger": (4173, COUPLE),  # 0.1237%
    "cx1_000": (359883, COUPLE),  # 2.5916%
    "cx1_001": (198504, COUPLE),  # 2.2727%
    "cx1_004": (298228, COUPLE),  # 1.8772%
    "cx1_005": (56069, COUPLE),  # 1.4584%
    "cx1_011": (199680, COUPLE),  # 3.0998%
    "cx1_014": (198009, COUPLE),  # 1.7472%
    "cx1_017": (535833, COUPLE),  # 2.3376%
    "cx1_018": (81123, COUPLE),  # 0.6726%
    "cx1_019": (1352655, COUPLE),  # 11.8663%
    "cx1_020": (84, COUPLE),  # 0.0030%
    "cx1_026": (94937, COUPLE),  # 0.4539%
    "cx1_035": (4818, COUPLE),  # 0.0738%
    "cx1_036": (310761, COUPLE),  # 2.7962%
    "cx1_038": (2276600, COUPLE),  # 18.0557%
    "pf_mukeret4_order": (69837, COUPLE),  # 0.2466%
    "be_fem_s30": (63, CURVE),  # 0.0013%
    "be_fem_s70": (597, CURVE),  # 0.0126%
    "be_inc_fire": (740, CURVE),  # 0.0157%
    "be_inc_rent": (772, CURVE),  # 0.0156%
    "bw_t60_bal300k": (160, CURVE),  # 0.0046%
    "cx1_029": (746, CURVE),  # 0.0047%
    "cx1_022": (29942, LOTS),  # 0.2164%
    "cx1_028": (40054, LOTS),  # 0.4336%
    "lot_lifo_nodep": (632, LOTS),  # 0.0277%
    "pf_fifo": (681, LOTS),  # 0.0330%
    "pf_fifo_nodep": (1040, LOTS),  # 0.0482%
    "pf_lifo": (372, LOTS),  # 0.0187%
    "cx1_003": (92, RESIDUE),  # 0.0006%
    "cx1_008": (147, RESIDUE),  # 0.0010%
    "cx1_012": (44, RESIDUE),  # 0.0010%
    "cx1_015": (239, RESIDUE),  # 0.0015%
    "cx1_016": (4879, RESIDUE),  # 0.0888%
    "cx1_024": (499, RESIDUE),  # 0.0124%
    "cx1_032": (395, RESIDUE),  # 0.0102%
    "cx1_037": (117, RESIDUE),  # 0.0034%
    "crash_rule_frac": (1255, RULE),  # 0.0321%
}
"""Runs outside their tolerance, each bounded and named.

A bound is asserted, so a regression that widens a gap still fails, and a gap
that closes must leave the dict (`test_known_gap_is_still_open`). A named gap
is excused from `RELATIVE_TARGET` only if it is one of `OVER_TARGET`'s causes."""

OVER_TARGET = {COUPLE, LOTS}
"""Causes allowed past 0.1% — the open questions, not approximations."""

SURFACE_PROBES = parity.SURFACE_PROBES
"""The idle-portfolio probes that measure the surface. They park 1e9, so a
rate interpolated between cells to 1e-5 is a large number of shekels; they are
held to a relative bound instead."""

SURFACE_SAMPLE = 8
"""Replay every eighth surface probe. Each cell is already checked against the
shipped table directly (`test_decumulation_table`); the replays that remain
exercise the bridge rule across ~140 birth dates, which is what they add."""

SURFACE_RELATIVE = 2e-4
"""What reading the surface between its measured cells costs a probe that
lands off the grid — the post-60 cells past 23 years sit between whole years."""

def _charted() -> list[str]:
    names = parity.corpus(charted=True)
    probes = [n for n in names if n.startswith(SURFACE_PROBES)]
    return [n for n in names if not n.startswith(SURFACE_PROBES)] + probes[::SURFACE_SAMPLE]


CHARTED = _charted()


def _bound(report: parity.Report) -> float:
    relative = (SURFACE_RELATIVE if report.name.startswith(SURFACE_PROBES)
                else DISPLAY_PRECISION)
    return max(TOLERANCE, relative * report.scale)


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
