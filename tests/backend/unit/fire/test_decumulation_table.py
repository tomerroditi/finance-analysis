"""The decumulation table — the reference's Trinity-style haircut, measured.

`test_reference_parity` supplies each scenario's decumulation return as a known
constant, which proves everything *except* that return. These tests prove the
remaining piece: that the measured table reproduces the reference on its own,
with no fitted input at all.
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

RELATIVE_TOLERANCE = 0.025
"""Per-fixture bound on the worst asset deviation, as a share of the largest
balance in that scenario. The table is measured on a grid and interpolated, so
it carries interpolation error the fitted constant does not."""


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


def _fixture_names() -> list[str]:
    rates = json.loads((RESEARCH / "decumulation_rates.json").read_text(encoding="utf-8"))
    return sorted(rates)


class TestDerivedParity:
    """With no fitted input, the table alone must reproduce the reference."""

    def test_every_fixture_is_close_without_a_fitted_rate(self):
        """Replay every recorded run using only the measured table."""
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
            + ", ".join(f"{n} {e:.2%}" for n, e in sorted(breaches.items()))
        )
        assert statistics.median(errors.values()) < 0.005, (
            "the typical fixture should be far inside the bound, not merely under it"
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
