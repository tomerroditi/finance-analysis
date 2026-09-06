"""The decumulation surface — the reference's Trinity-style haircut, measured.

`test_reference_parity` asserts each recorded run individually. These tests
cover the surface itself: its shape, the two keys it is read on (the bridge to
the pension, not the retirement age), and the quality of the whole corpus in
aggregate.
"""

from __future__ import annotations

import json
import statistics
from datetime import date
from pathlib import Path

import pytest

from backend.services.fire.decumulation import (
    BRANCH_AGE,
    decumulation_return_pct,
)
from backend.services.fire.engine import Simulator
from backend.services.fire.reference_form import plan_from_reference

RESEARCH = Path(__file__).resolve().parents[4] / "research" / "zeke_retire_calc"
FIXTURES = RESEARCH / "fixtures"
RECORDED_IN = date(2026, 9, 1)

RELATIVE_TOLERANCE = 0.002
"""Per-fixture bound on the worst asset deviation, as a share of the largest
balance in that scenario. The surface is measured at ~80 cells and interpolated
between them, so it carries interpolation error a fitted constant would not."""


class TestMeasuredSurface:
    """Shape checks on the table itself."""

    def test_higher_confidence_gives_a_lower_return(self):
        """Demanding more certainty must assume less growth."""
        rates = [decumulation_return_pct(c, 45.08) for c in (80, 85, 90, 95, 100)]
        assert rates == sorted(rates, reverse=True)

    def test_a_longer_bridge_supports_a_higher_return(self):
        """Retiring earlier leaves a longer bridge and a higher supported return."""
        early = decumulation_return_pct(85, 40.08)
        late = decumulation_return_pct(85, 50.08)
        assert early > late

    def test_the_rate_collapses_approaching_sixty(self):
        """From the mid-fifties to 60 the reference assumes essentially no growth."""
        for age in (55.08, 57.08, 59.08, 60.08):
            assert decumulation_return_pct(85, age) < 0.01

    def test_the_surface_jumps_after_sixty(self):
        """Past 60 there is no bridge left to fund, and the rate jumps back up."""
        assert decumulation_return_pct(85, 60.08) < 0.01
        assert decumulation_return_pct(85, 61.08) > 2.5

    def test_interpolation_never_crosses_the_discontinuity(self):
        """A value just above the branch age must not be dragged down by the
        near-zero rates just below it."""
        assert decumulation_return_pct(85, BRANCH_AGE + 0.6) > 2.5

    def test_confidence_below_the_table_is_clamped(self):
        """The reference rejects confidence under 80; we clamp rather than crash."""
        assert decumulation_return_pct(50, 45.08) == decumulation_return_pct(80, 45.08)

    def test_the_key_is_the_bridge_not_the_age(self):
        """A woman's bridge ends at 65, so she reads the surface two years early.

        `female` — the one recorded run with a woman retiring mid-curve — is
        only reproduced under this reading (notes/15).
        """
        assert decumulation_return_pct(85, 52.75, 65) == pytest.approx(
            decumulation_return_pct(85, 54.75, 67))

    def test_the_shape_transfer_predicts_a_held_out_cell(self, monkeypatch):
        """Drop a sparse level's measurement and rebuild it from the 85 shape.

        Only confidence 85 is densely sampled; the other four are interpolated
        in its coordinate rather than in years. Away from the knee that is
        near-exact — every held-out cell comes back within 0.03 of what was
        measured.
        """
        for rule, bridge, measured, predicted in self._hold_out_each_cell(monkeypatch):
            if 16.0 < bridge < 19.0:
                continue   # the knee — see the next test
            assert predicted == pytest.approx(measured, abs=0.03), (
                f"rule {rule:g} at bridge {bridge:.2f} is not recovered")

    def test_the_measurements_at_the_knee_are_load_bearing(self, monkeypatch):
        """Each confidence level collapses at its own bridge, so the knee is
        the one place the shared shape does not transfer.

        Rule 100 gives up about five years earlier than rule 85 does. Predicting
        its knee from the 85 curve is off by more than a tenth of a point, which
        is why those cells are measured rather than interpolated — delete one
        and the surface really does lose information.
        """
        worst = max((abs(predicted - measured), rule, bridge)
                    for rule, bridge, measured, predicted
                    in self._hold_out_each_cell(monkeypatch)
                    if 16.0 < bridge < 19.0)
        assert worst[0] > 0.1

    @staticmethod
    def _hold_out_each_cell(monkeypatch):
        """Yield `(rule, bridge, measured, predicted)` with each cell removed."""
        from backend.services.fire import decumulation

        cells, reference, shift = decumulation._surface()
        for rule in (80.0, 90.0, 95.0, 100.0):
            points = cells[rule]
            for index in range(1, len(points) - 1):
                bridge, measured = points[index]
                thinned = dict(cells)
                thinned[rule] = points[:index] + points[index + 1:]
                monkeypatch.setattr(decumulation, "_surface",
                                    lambda thinned=thinned: (thinned, reference, shift))
                yield rule, bridge, measured, decumulation._for_rule(rule, bridge)
                monkeypatch.undo()

    def test_a_pension_claimed_early_shortens_the_bridge(self):
        """Claiming at 60 instead of 67 lands seven years earlier on the curve."""
        assert (decumulation_return_pct(85, 45.0, 60)
                < decumulation_return_pct(85, 45.0, 67))


UNSOLVED_BRIDGE = {"pf_mukeret2", "pf_mukeret3_t60", "pf_mukeret4_order"}
"""The three runs that annuitise a gemel, whose bridge is the one open question.

They read the surface somewhere it does not have them (notes/15), so they say
nothing about the surface's own quality; `test_reference_parity.KNOWN_GAPS`
bounds them instead."""


def _fixture_names() -> list[str]:
    rates = json.loads((RESEARCH / "decumulation_rates.json").read_text(encoding="utf-8"))
    return sorted(set(rates) - UNSOLVED_BRIDGE)


class TestSurfaceQuality:
    """The corpus as a whole, replayed from the surface alone."""

    def test_the_typical_fixture_is_reproduced_to_a_few_parts_per_million(self):
        """Median and worst-case quality over every run that pins its rate.

        Asserted in aggregate on purpose: `test_reference_parity` already bounds
        each fixture, and what this adds is that the *surface* — not a list of
        per-fixture escapes — is what makes them pass.
        """
        errors = {}
        for name in _fixture_names():
            fixture = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
            chart = fixture["charts"].get("asset_plot")
            if not chart:
                continue
            plan = plan_from_reference(fixture["overrides"])
            retire_index = _reference_retire_index(fixture)
            if retire_index is None:
                continue
            result = Simulator(plan).run(retire_index=retire_index, today=RECORDED_IN)

            worst = peak = 0.0
            for dataset in chart["datasets"]:
                reference = dataset["data"][1:-1]
                peak = max(peak, max(abs(v) for v in reference))
                key = _asset_key(dataset["label"], plan)
                if key is None:
                    continue
                for month in range(min(len(reference), len(result.months))):
                    worst = max(worst,
                                abs(result.months[month].assets.get(key, 0.0)
                                    - reference[month]))
            if peak:
                errors[name] = worst / peak

        assert errors, "no fixtures were replayed"
        breaches = {n: e for n, e in errors.items() if e > RELATIVE_TOLERANCE}
        assert not breaches, (
            f"{len(breaches)} fixture(s) exceed {RELATIVE_TOLERANCE:.1%}: "
            + ", ".join(f"{n} {e:.3%}" for n, e in sorted(breaches.items()))
        )
        assert statistics.median(errors.values()) < 2e-6, (
            "the typical fixture should be reproduced to display precision, "
            "not merely inside the bound"
        )


def _reference_retire_index(fixture: dict) -> int | None:
    import re

    match = re.search(r"ב-(\d{2})/(\d{4})", fixture.get("summary", ""))
    if not match:
        return None
    month, year = int(match.group(1)), int(match.group(2))
    return ((year - RECORDED_IN.year) * 12 + (month - RECORDED_IN.month)) + 1


def _asset_key(label: str, plan) -> str | None:
    if "עובר" in label:
        return "cash"
    if "השתלמות" in label:
        return "keren0"
    if "נדל" in label or "דירה" in label:
        return "realestate0"
    for index, portfolio in enumerate(plan.portfolios):
        if portfolio.description and portfolio.description in label:
            return f"portfolio{index}"
    return "portfolio0" if len(plan.portfolios) == 1 else None
