"""The decumulation surface — the author's formula, solved the reference's way.

`test_corpus_parity` asserts every recorded run; these tests cover the surface
itself: its shape, the author's worked examples, and that the recovered solver
(`decumulation.py`, notes/18 §1) reproduces every cell measured straight off
the reference (`research/zeke_retire_calc/surface_cells.json`).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import parity
import surface_read
from backend.services.fire.decumulation import decumulation_return_pct

CELLS = Path(parity.__file__).with_name("surface_cells.json")

MEASUREMENT = 2e-7
"""Percentage points: the worst any measured cell sits from the solver, at the
level of the idle-portfolio reading itself."""


def _cells() -> list[tuple[float, float, float]]:
    raw = json.loads(CELLS.read_text(encoding="utf-8"))["bridge_years"]
    return [(float(rule), float(bridge), rate)
            for rule, row in raw.items() for bridge, rate in row.items()]


class TestSurfaceShape:
    """What the reference assumes a drawn-down portfolio earns."""

    def test_higher_confidence_gives_a_lower_return(self):
        """Demanding more certainty must assume less growth."""
        rates = [decumulation_return_pct(c, 22.0) for c in (80, 85, 90, 95, 100)]
        assert rates == sorted(rates, reverse=True)

    def test_a_longer_bridge_supports_a_higher_return(self):
        """Up to about 40 years, the longer the bridge the more growth is assumed."""
        rates = [decumulation_return_pct(85, bridge) for bridge in (15, 20, 25, 30, 35)]
        assert rates == sorted(rates)

    def test_a_short_bridge_assumes_almost_no_growth(self):
        """Below about 14 years the exact rate is negative; the solver creeps toward zero."""
        for bridge in (7.0, 10.0, 12.0, 13.0):
            assert decumulation_return_pct(85, bridge) < 0.01

    def test_confidence_outside_the_field_is_clamped(self):
        """The reference rejects confidence under 80; we clamp rather than crash."""
        assert decumulation_return_pct(50, 22.0) == decumulation_return_pct(80, 22.0)
        assert decumulation_return_pct(120, 22.0) == decumulation_return_pct(100, 22.0)


class TestAuthorsFormula:
    """The closed form behind the surface (blog: "אלגוריתם למשיכות משתנות")."""

    @pytest.mark.parametrize(("confidence", "years", "quoted"), [
        (85, 40, 2.95), (85, 27, 2.608), (90, 22, 1.77)])
    def test_reproduces_the_worked_examples_in_the_post(self, confidence, years, quoted):
        """The post's own three numbers, to the digits it prints."""
        assert decumulation_return_pct(confidence, years) == pytest.approx(
            quoted, abs=0.5 * 10 ** -(len(str(quoted).split(".")[1])))

    def test_the_early_stop_lifts_the_rate_near_the_knee(self):
        """At 14.5 years (rule 85) the exact root is 0.057%; the reference stops at 0.0906%."""
        assert decumulation_return_pct(85, 14.5) == pytest.approx(0.090590, abs=MEASUREMENT)


class TestSolverIsTheMeasurements:
    """The recovered solver reproduces every cell read off the reference."""

    def test_every_measured_cell(self):
        """All levels, every bridge measured, off-grid confidences included."""
        misses = [(rule, bridge, rate, decumulation_return_pct(rule, bridge))
                  for rule, bridge, rate in _cells()
                  if abs(decumulation_return_pct(rule, bridge) - max(rate, 0.0)) > MEASUREMENT]
        assert not misses, misses[:5]

    def test_levels_off_the_measured_grid(self):
        """Confidence 82 and 87, measured monthly through the knee and never fitted."""
        checked = 0
        for name in parity.corpus(["sff_r82_", "sff_r87_"]):
            reading = surface_read.measured_rate(name)
            if reading is None:
                continue
            rule = float(name[5:].split("_")[0])
            months = int(name.split("_m")[1])
            assert decumulation_return_pct(rule, months / 12) == pytest.approx(
                reading[0], abs=MEASUREMENT), name
            checked += 1
        assert checked > 100

    def test_both_probe_designs_measure_the_same_surface(self):
        """Whole-year cells read pre-60 and through the post-60 rule agree.

        `surface_fine` reaches fractional bridges through the reference's
        post-60 rule (bridge.py); where it lands on a whole year the ordinary
        pre-60 probe measured the same cell, and the two must be one number.
        """
        pairs = 0
        for name in parity.corpus(["sff_r"]):
            rule = name.split("_r")[1].split("_")[0]
            months = int(name.split("_m")[1])
            twin = f"sf_r{rule}_n{months}"
            if months % 12 or not parity.exists(twin):
                continue
            fine, _ = surface_read.measured_rate(name)
            coarse, _ = surface_read.measured_rate(twin)
            assert fine == pytest.approx(coarse, abs=1e-6), (name, twin)
            pairs += 1
        assert pairs, "no cell was measured both ways"
