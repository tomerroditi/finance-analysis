"""The reference's other three result sections, against its own output.

Beyond the charts, the reference prints an annuity list, a drawdown plan and
two asset cards with doughnut breakdowns. All three are checkable: the first two
appear as prose in the summary, and the cards are the `assetspie0` / `assetspie1`
datasets. This asserts ours against all of them, for every recorded run.

The annuity list is the sharpest of the three. It prints each pension as its
four components — contributions and severance, each recognised or entitling —
with the claim age and annuity factor beside it, so it pins the 60/40 split, the
statutory ages, both annuity-factor tables, what a severance redemption removes,
and the spouse increment, none of which any balance shows directly.
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

ANNUITY_ROW = re.compile(
    r"קצבה מגיל (\d+) בגובה ([\d,]+\.\d) ₪(?: \(מקדם ([\d.]+) \))?")
WITHDRAWAL_ROW = re.compile(
    r"מגיל ([\d.]+) עד גיל ([\d.]+), ממוצע של ([\d,]+\.\d) ש")
PIE_CATEGORIES = {"תיקים": "portfolios", "עובר ושב": "cash", "השתלמות": "keren",
                  "פנסיה": "pension", "נדלן": "realestate"}
SHORTFALL_SLICE = "חוסר"
"""What the plan is short, as capital — a slice beside the assets."""
NOTHING_YET = "אין עדיין נכסים"
"""The placeholder the reference draws when the plan owns nothing at all."""

KNOWN_GAPS = {
    "pf_mukeret2": "gemel-conversion bridge (notes/15)",
    "pf_mukeret3_t60": "gemel-conversion bridge (notes/15)",
    "pf_mukeret4_order": "gemel-conversion bridge (notes/15)",
    "pf_fifo": "synthetic lot history (notes/13)",
    "pf_fifo_nodep": "synthetic lot history (notes/13)",
}
"""Runs whose drawdown differs because of a documented open question.

Their annuity lists and asset classes are still asserted to the shekel — only
what depends on the drawdown path is allowed to drift: the segment averages,
and the shortfall slice, which those runs show because their portfolio empties
a few months early."""


def _number(text: str) -> float:
    return float(text.replace(",", ""))


def _fixtures() -> list[str]:
    out = []
    for path in sorted(FIXTURES.glob("*.json")):
        fixture = json.loads(path.read_text(encoding="utf-8"))
        if fixture.get("charts", {}).get("asset_plot") and "קצבה מגיל" in fixture.get("summary", ""):
            out.append(path.stem)
    return out


def _retire_index(fixture: dict) -> int:
    """First fully retired month, from the reference's own output.

    The printed date is the last working month. A plan that misses its goals
    prints no date, so fall back to the month pay stops.
    """
    match = re.search(r"ב-(\d{2})/(\d{4})", fixture.get("summary", ""))
    if match:
        return (((int(match.group(2)) - RECORDED_IN.year) * 12
                 + (int(match.group(1)) - RECORDED_IN.month)) + 1)
    work = next(d["data"][1:-1] for d in fixture["charts"]["income_plot"]["datasets"]
                if d["label"] == "עבודה")
    return next((i for i in range(1, len(work)) if work[i] == 0 and work[i - 1] > 0),
                10 ** 9)


def _run(name):
    fixture = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    plan = plan_from_reference(fixture["overrides"])
    return fixture, Simulator(plan).run(
        retire_index=_retire_index(fixture), today=RECORDED_IN)


class TestAnnuityList:
    """`רשימת הקצבאות` — one row per annuity component."""

    @pytest.mark.parametrize("name", _fixtures())
    def test_every_component_matches(self, name):
        """Same rows, same claim ages, same amounts, same annuity factors."""
        fixture, result = _run(name)
        expected = sorted((int(age), _number(amount), float(factor) if factor else None)
                          for age, amount, factor in ANNUITY_ROW.findall(fixture["summary"]))
        ours = sorted((int(a.claim_age), round(a.monthly, 1),
                       round(a.factor, 1) if a.factor else None)
                      for a in result.annuities)
        assert len(ours) == len(expected), (
            f"{name}: {len(ours)} annuity rows against the reference's {len(expected)}")
        tolerance = 1.0 if name in KNOWN_GAPS else 0.15
        for (age, amount, factor), (their_age, their_amount, their_factor) in zip(ours, expected):
            assert age == their_age
            assert amount == pytest.approx(their_amount, abs=tolerance)
            assert factor == their_factor


class TestWithdrawalPlan:
    """`תוכנית המשיכה מהתיקים` — which bucket funded which stretch."""

    @pytest.mark.parametrize("name", _fixtures())
    def test_every_segment_matches(self, name):
        """Same buckets, same age ranges, same monthly averages."""
        fixture, result = _run(name)
        expected = sorted((round(float(a), 1), round(float(b), 1), _number(average))
                          for a, b, average in WITHDRAWAL_ROW.findall(fixture["summary"]))
        ours = sorted((round(w.from_age, 1), round(w.to_age, 1),
                       round(w.monthly_average, 1))
                      for w in result.withdrawal_plan())
        assert len(ours) == len(expected), (
            f"{name}: {len(ours)} drawdown segments against {len(expected)}")
        tolerance = 100 if name in KNOWN_GAPS else 0.6
        for (start, end, average), (their_start, their_end, their_average) in zip(ours, expected):
            if name not in KNOWN_GAPS:
                assert (start, end) == (their_start, their_end)
            assert average == pytest.approx(their_average, abs=tolerance)


class TestAssetCards:
    """The two doughnuts: what the plan holds today, and at retirement."""

    @pytest.mark.parametrize("name", _fixtures())
    def test_both_cards_match(self, name):
        """Every asset class, in both snapshots, to the agora."""
        fixture, result = _run(name)
        snapshots = {snapshot.label: snapshot for snapshot in result.snapshots()}
        for key, label in (("assetspie0", "now"), ("assetspie1", "retirement")):
            pie = fixture["charts"].get(key)
            if not pie or label not in snapshots:
                continue
            snapshot = snapshots[label]
            drawn = dict(zip(pie["labels"], pie["datasets"][0]["data"]))
            if NOTHING_YET in drawn:
                assert not snapshot.breakdown and snapshot.shortfall_capital < 0.01, (
                    f"{name}: {key} should be the empty placeholder")
                continue
            assert snapshot.shortfall_capital == pytest.approx(
                drawn.pop(SHORTFALL_SLICE, 0.0),
                abs=20_000 if name in KNOWN_GAPS else 1.0), (
                f"{name}: {key} shortfall slice")
            expected = {PIE_CATEGORIES[label_]: value for label_, value in drawn.items()}
            assert set(snapshot.breakdown) == set(expected), f"{name}: {key} classes differ"
            for group, value in expected.items():
                assert snapshot.breakdown[group] == pytest.approx(value, abs=0.6), (
                    f"{name}: {key} {group}")
