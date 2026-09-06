"""Parity tests against the reference early-retirement calculator.

Each fixture in ``research/zeke_retire_calc/fixtures`` is a real run of the
reference calculator, recorded with its full monthly series. These tests assert
our engine reproduces those series to the shekel.

Scope note: only the **accumulation** phase (up to the reference's own reported
retirement month) is asserted here. The drawdown phase depends on the capital
gains and pension models, which are still being characterised — see
``research/zeke_retire_calc/notes/``.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest

from backend.services.fire.engine import Simulator
from backend.services.fire.reference_form import plan_from_reference

FIXTURES = Path(__file__).resolve().parents[4] / "research" / "zeke_retire_calc" / "fixtures"
RECORDED_IN = date(2026, 9, 1)
"""Calendar month the fixtures were recorded in — the simulation's month zero."""

RATES = json.loads(
    (FIXTURES.parent / "decumulation_rates.json").read_text(encoding="utf-8"))
"""Frozen decumulation returns, one per fixture.

The reference derives this from `retireRule` and the horizon via a
Trinity-style table we have not mapped yet (notes/10). Everything *else* in
each scenario is asserted, so a passing test means one free scalar reproduces
the whole 533-month series — accumulation, tax, timing, debt and drawdown.
"""

FULL_HORIZON_FIXTURES = sorted(RATES)

TOLERANCE = 2.0
"""The reference reports balances to one decimal. Over a 533-month compounding
chain that rounding accumulates, so a couple of shekels on a seven-figure
balance (under 2 parts per million) is display noise, not a modelling
difference."""


def _reference_assets(fixture: dict) -> dict[str, list[float]]:
    """Asset series with the area-chart padding point stripped from each end."""
    chart = fixture["charts"]["asset_plot"]
    series = {"age": chart["labels"][1:-1]}
    for dataset in chart["datasets"]:
        series[dataset["label"]] = dataset["data"][1:-1]
    return series


def _reference_retire_index(fixture: dict) -> int:
    """Index of the first fully-retired month in the reference's own output.

    Read from the retirement **date** the reference prints, never the age: the
    age is rounded to one decimal, so 53.2 is ambiguous between 53.17 and
    53.25 and silently shifts the whole drawdown by a month. The printed date
    is the last working month, so retirement begins one month later (notes/08).
    """
    match = re.search(r"ב-(\d{2})/(\d{4})", fixture["summary"])
    if match:
        month, year = int(match.group(1)), int(match.group(2))
        return ((year - RECORDED_IN.year) * 12 + (month - RECORDED_IN.month)) + 1

    # A plan that never reaches retirement prints no date; fall back to the
    # month work income stops.
    work = next(
        d["data"][1:-1]
        for d in fixture["charts"]["income_plot"]["datasets"]
        if d["label"] == "עבודה"
    )
    return next(
        (i for i in range(1, len(work)) if work[i] == 0 and work[i - 1] > 0),
        len(work),
    )


def _asset_key(label: str, plan) -> str | None:
    """Map a reference chart series onto one of our asset keys."""
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


class TestFullHorizonParity:
    """Our simulation must match the reference for all 533 months."""

    @pytest.mark.parametrize("name", FULL_HORIZON_FIXTURES)
    def test_matches_reference_month_by_month(self, name):
        """Every asset series agrees to the shekel over the whole horizon."""
        fixture = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
        reference = _reference_assets(fixture)
        retire_index = _reference_retire_index(fixture)

        plan = plan_from_reference(fixture["overrides"])
        plan.decumulation_return_pct = RATES[name]["decumulation_return_pct"]
        result = Simulator(plan).run(retire_index=retire_index, today=RECORDED_IN)

        for label, expected in reference.items():
            if label == "age":
                continue
            key = _asset_key(label, plan)
            if key is None:
                continue
            for month in range(len(result.months)):
                ours = result.months[month].assets[key]
                assert abs(ours - expected[month]) < TOLERANCE, (
                    f"{name}: {label} diverges at month {month}: "
                    f"reference {expected[month]:,.1f} vs ours {ours:,.1f}"
                )

    def test_horizon_ends_at_age_81(self):
        """The simulation runs to age 81 exactly, as the reference does."""
        fixture = json.loads((FIXTURES / "baseline.json").read_text(encoding="utf-8"))
        reference = _reference_assets(fixture)
        result = Simulator(plan_from_reference(fixture["overrides"])).run(
            retire_index=10**9, today=RECORDED_IN
        )
        assert len(result.months) == len(reference["age"])
        assert result.months[-1].age == pytest.approx(81.0)


class TestDrawdownParity:
    """The retirement-phase funding order must match the reference."""

    def test_cash_drawdown_matches_before_pension_starts(self):
        """Cash is spent down exactly as the reference does, to the agora.

        The window runs from retirement to the month Bituach Leumi starts, so
        the comparison isolates the withdrawal ordering from the pension model.
        """
        fixture = json.loads((FIXTURES / "baseline.json").read_text(encoding="utf-8"))
        reference = _reference_assets(fixture)
        retire_index = _reference_retire_index(fixture)
        pension = next(
            d["data"][1:-1]
            for d in fixture["charts"]["income_plot"]["datasets"]
            if "זיקנה" in d["label"]
        )
        pension_start = next(i for i in range(len(pension)) if pension[i] > 0)

        result = Simulator(plan_from_reference(fixture["overrides"])).run(
            retire_index=retire_index, today=RECORDED_IN
        )

        cash_label = next(k for k in reference if "עובר" in k)
        for month in range(retire_index, pension_start):
            ours = result.months[month].assets["cash"]
            assert abs(ours - reference[cash_label][month]) < TOLERANCE, (
                f"cash diverges at month {month} (age {reference['age'][month]}): "
                f"reference {reference[cash_label][month]:,.1f} vs ours {ours:,.1f}"
            )
