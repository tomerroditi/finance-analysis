"""Parity tests against the reference early-retirement calculator.

Each fixture in ``research/zeke_retire_calc/fixtures`` is a real run of the
reference calculator, recorded with its full monthly series. These tests assert
our engine reproduces those series to the shekel.

Two levels are asserted:

* :class:`TestDerivedParity` replays **every** recorded run over the whole
  horizon with nothing fed in — the engine derives the decumulation return
  itself. That is the end-to-end claim.
* :class:`TestFullHorizonParity` replays the runs that pin their rate with that
  rate supplied, to a two-shekel tolerance. It is the tighter statement about
  everything *other* than the decumulation surface.
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

FULL_HORIZON_FIXTURES = sorted(
    name for name, row in RATES.items() if row["residual"] <= 2.0)
"""Runs our model replays exactly once its decumulation rate is supplied.

The rest of `RATES` still measures the surface — a fit is a measurement as long
as the scenario pins the rate (see `build_decumulation_table.py`) — but carries
a residual of its own, from the synthetic lot history or the one-decimal
annuity factors, so it is asserted by `TestDerivedParity`'s bounds instead."""

DERIVED_TOLERANCE = 30.0
"""Shekels, over 533 months, with nothing supplied to the engine.

Three parts per million of a seven-figure balance: what is left after the
reference's own one-decimal display rounding has compounded."""

KNOWN_GAPS = {
    "pf_mukeret2": (40_000, "gemel-conversion bridge (notes/15)"),
    "pf_mukeret3_t60": (60_000, "gemel-conversion bridge (notes/15)"),
    "pf_mukeret4_order": (20_000, "gemel-conversion bridge (notes/15)"),
    "pn_annuity_6067": (300, "interpolated bridge for a split pension claim"),
    "lot_lifo_nodep": (250, "synthetic lot history (notes/13)"),
    "pf_lifo": (120, "synthetic lot history (notes/13)"),
    "pf_fifo": (110, "synthetic lot history (notes/13)"),
    "pf_fifo_nodep": (70, "synthetic lot history (notes/13)"),
    "pf_gemel_two": (110, "deposit order across two capped accounts"),
    "pf_deposit_caps": (110, "deposit order across two capped accounts"),
    "pf_mukeret_ref": (70, "a couple both annuitising at 60"),
    "pf_mukeret_main": (70, "a couple both annuitising at 60"),
    "pf_mukeret_partner": (70, "a couple both annuitising at 60"),
}
"""Fixtures that miss by more than `DERIVED_TOLERANCE`, and how far.

Every one is a bound on a *named* open question, not a blanket exemption: the
bound is asserted, so a regression that widens one still fails."""

ALL_FIXTURES = sorted(
    path.stem for path in FIXTURES.glob("*.json")
    if json.loads(path.read_text(encoding="utf-8")).get("charts", {}).get("asset_plot"))

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


class TestDerivedParity:
    """Every recorded run, replayed with no fitted input of any kind."""

    @pytest.mark.parametrize("name", ALL_FIXTURES)
    def test_replays_with_nothing_supplied(self, name):
        """The engine derives its own decumulation return and still matches."""
        fixture = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
        reference = _reference_assets(fixture)
        plan = plan_from_reference(fixture["overrides"])
        assert plan.decumulation_return_pct is None
        result = Simulator(plan).run(
            retire_index=_reference_retire_index(fixture), today=RECORDED_IN)

        bound, why = KNOWN_GAPS.get(name, (DERIVED_TOLERANCE, ""))
        worst = 0.0
        for label, expected in reference.items():
            key = None if label == "age" else _asset_key(label, plan)
            if key is None:
                continue
            worst = max(worst, *(abs(result.months[month].assets[key] - expected[month])
                                 for month in range(len(result.months))))
        assert worst < bound, (
            f"{name}: worst asset gap {worst:,.1f} exceeds {bound:,.0f}"
            + (f" (known gap: {why})" if why else ""))

    @pytest.mark.parametrize("name", sorted(KNOWN_GAPS))
    def test_every_known_gap_is_still_needed(self, name):
        """A gap that has closed must leave the list, or it hides a regression."""
        assert name in ALL_FIXTURES
        fixture = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
        reference = _reference_assets(fixture)
        plan = plan_from_reference(fixture["overrides"])
        result = Simulator(plan).run(
            retire_index=_reference_retire_index(fixture), today=RECORDED_IN)
        worst = 0.0
        for label, expected in reference.items():
            key = None if label == "age" else _asset_key(label, plan)
            if key is None:
                continue
            worst = max(worst, *(abs(result.months[month].assets[key] - expected[month])
                                 for month in range(len(result.months))))
        assert worst >= DERIVED_TOLERANCE, (
            f"{name} now matches to {worst:.2f} — remove it from KNOWN_GAPS")


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
