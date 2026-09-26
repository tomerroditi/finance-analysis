"""The decumulation surface — the reference's Trinity-style haircut, measured.

`test_corpus_parity` asserts every recorded run; these tests cover the surface
itself: its shape, and that the shipped table is the measurements it claims to
be (`build_decumulation_table.py`, notes/18).
"""

from __future__ import annotations

import json

import pytest

import parity
import surface_read
from backend.services.fire import decumulation
from backend.services.fire.decumulation import TABLE_PATH, decumulation_return_pct


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

    def test_a_short_bridge_assumes_no_growth(self):
        """Below about 14 years the rate is floored at zero (withdrawals of 1/N)."""
        for bridge in (7.0, 10.0, 12.0, 13.0):
            assert decumulation_return_pct(85, bridge) < 0.01

    def test_the_surface_is_not_monotone_past_forty_years(self):
        """Rule 80 peaks at a 40-year bridge and falls after it — an empirical
        surface, not a formula, which is why it is shipped measured."""
        peak = decumulation_return_pct(80, 40.0)
        assert decumulation_return_pct(80, 35.0) < peak > decumulation_return_pct(80, 45.0)

    def test_confidence_below_the_table_is_clamped(self):
        """The reference rejects confidence under 80; we clamp rather than crash."""
        assert decumulation_return_pct(50, 22.0) == decumulation_return_pct(80, 22.0)


class TestAuthorsFormula:
    """The closed form behind the surface (blog: "אלגוריתם למשיכות משתנות")."""

    @pytest.mark.parametrize(("confidence", "years", "quoted"), [
        (85, 40, 2.95), (85, 27, 2.608), (90, 22, 1.77)])
    def test_reproduces_the_worked_examples_in_the_post(self, confidence, years, quoted):
        """The post's own three numbers, to the digits it prints."""
        assert decumulation.formula_rate(confidence, years) == pytest.approx(
            quoted, abs=0.5 * 10 ** -(len(str(quoted).split(".")[1])))

    def test_matches_every_measured_cell_past_the_knee(self):
        """Past 24 years the measured surface is the formula to within 0.002."""
        raw = json.loads(TABLE_PATH.read_text(encoding="utf-8"))["bridge_years"]
        for rule, row in raw.items():
            for bridge, rate in row.items():
                if float(bridge) >= 24:
                    assert decumulation.formula_rate(float(rule), float(bridge)) == (
                        pytest.approx(rate, abs=2e-3)), (rule, bridge)

    def test_a_short_horizon_earns_nothing(self):
        """Where withdrawing 1/N already beats the safe rate, the return is 0."""
        assert decumulation.formula_rate(85, 12) == 0.0


class TestTableIsTheMeasurements:
    """The shipped file reproduces the probes it was built from."""

    def test_every_cell_is_returned_as_measured(self):
        """Formula plus measured drift passes through each cell exactly."""
        raw = json.loads(TABLE_PATH.read_text(encoding="utf-8"))["bridge_years"]
        for rule, row in raw.items():
            if len(row) < decumulation.DENSE:
                continue  # held-out levels, predicted rather than stored
            for bridge, rate in row.items():
                assert decumulation.decumulation_return_pct(float(rule), float(bridge)) == pytest.approx(
                    max(rate, 0.0), abs=1e-9), f"rule {rule} bridge {bridge}"

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
