"""Monthly cash-flow parity: every shekel in and out, against the reference.

The reference publishes two more charts alongside the balances — `income_plot`
and `expense_plot` — and they are a *closed* decomposition: in all 134 recorded
runs the two sides balance to the agora, every month. That makes them a far
sharper instrument than the asset series, which only show the net effect: they
pin the withdrawal order, the deposit routing, the tax on each individual sale,
the split of each pension into its recognised and entitling halves, and the
national-insurance base — each as its own row.

Two modelling errors surfaced the first time these were compared, neither
visible in any balance (notes/16): a severance redemption re-split the pension
the wrong way, and national insurance was charged on the pension annuity alone
when the reference charges it on everything a person draws, an annuitised gemel
included.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from backend.services.fire.engine import Simulator
from backend.services.fire.models import PortfolioDesignation, PortfolioType
from backend.services.fire.reference_form import plan_from_reference

FIXTURES = Path(__file__).resolve().parents[4] / "research" / "zeke_retire_calc" / "fixtures"
RECORDED_IN = date(2026, 9, 1)

TOLERANCE = 0.5
"""Shekels, over 533 months. The reference prints every row to one decimal, and
a row that is a residual of several others — `unplanned` most of all — carries a
rounding step from each. 123 of the 134 runs match every row inside 0.15."""

KNOWN_GAPS = {
    "pf_mukeret2": (6_200, "gemel-conversion bridge (notes/15)"),
    "pf_mukeret3_t60": (6_200, "gemel-conversion bridge (notes/15)"),
    "pf_mukeret4_order": (6_200, "gemel-conversion bridge (notes/15)"),
    "lot_lifo_nodep": (5, "synthetic lot history (notes/13)"),
    "pf_lifo": (4, "synthetic lot history (notes/13)"),
    "pf_fifo_nodep": (3, "synthetic lot history (notes/13)"),
    "pf_fifo": (3, "synthetic lot history (notes/13)"),
    "cf_rise": (3, "which bucket funds the month the plan runs dry"),
}
"""Runs with a row outside `TOLERANCE`, bounded and named.

The three `pf_mukeret*` are the unsolved decumulation bridge, so their
withdrawal is genuinely different. The rest is the synthetic lot history
deciding a tax to the agora, and one run where rounding decides which bucket
funds the month the plan runs dry."""

TYPE_LABELS = {
    PortfolioType.BROKER_IL: "תיק בברוקר בארץ",
    PortfolioType.IBKR: 'תיק בברוקר בחו"ל',
    PortfolioType.GEMEL: "קופת גמל להשקעה",
    PortfolioType.POLISA: "פוליסת חיסכון",
    PortfolioType.KASPIT: "קרן כספית",
    PortfolioType.PIKADON: "פיקדון",
}
"""What the reference calls a portfolio the user did not name."""


def _fixtures() -> list[str]:
    return sorted(
        path.stem for path in FIXTURES.glob("*.json")
        if json.loads(path.read_text(encoding="utf-8")).get("charts", {}).get("income_plot"))


def _portfolio_index(plan, text: str) -> int | None:
    """Which portfolio a chart label names."""
    for match in (lambda p: p.description and p.description == text.strip(),
                  lambda p: p.description and p.description in text,
                  lambda p: TYPE_LABELS.get(p.kind, "\0") in text):
        hits = [i for i, p in enumerate(plan.portfolios) if match(p)]
        if len(hits) == 1:
            return hits[0]
    return 0 if len(plan.portfolios) == 1 else None


def _whose(plan, label: str) -> str:
    """Suffix identifying the partner's copy of a per-person row."""
    if plan.partner is not None and plan.partner.name:
        if label.rstrip().endswith(plan.partner.name):
            return "_partner"
    return ""


def _gemel_keys(plan, suffix: str) -> list[str]:
    wanted = (PortfolioDesignation.MUKERET_PARTNER if suffix
              else PortfolioDesignation.MUKERET_MAIN)
    return [f"gemel{i}" for i, p in enumerate(plan.portfolios)
            if p.kind is PortfolioType.GEMEL and p.designation is wanted]


def _income_keys(label: str, plan) -> list[str] | None:
    if label.startswith("עבודה"):
        return ["work"]
    if label.startswith("הכנסות חד פעמיות"):
        return ["one_time"]
    if label.startswith("משיכה מעובר ושב"):
        return ["cash"]
    if label.startswith("משיכה מתיק"):
        index = _portfolio_index(plan, label[len("משיכה מתיק"):])
        return None if index is None else [f"portfolio{index}"]
    if label.startswith("משיכה מקרן השתלמות"):
        return [f"keren{i}" for i in range(len(plan.kranot_hishtalmut))]
    if label.startswith("קיצבת זיקנה"):
        return ["state_pension" + _whose(plan, label)]
    if label.startswith("מוכרת גמל להשקעה"):
        return _gemel_keys(plan, _whose(plan, label))
    if label.startswith("מוכרת"):
        return ["recognised" + _whose(plan, label)]
    if label.startswith("מזכה"):
        return ["entitling" + _whose(plan, label)]
    if label.startswith("החתיכה החסרה"):
        return ["shortfall"]
    return None


def _expense_keys(label: str, plan) -> list[str] | None:
    if label.startswith("הוצאות שוטפות"):
        return ["living"]
    if label.startswith("יעדים"):
        return ["one_time"]
    if label.startswith("הוצאה לא מתוכננת"):
        return ["unplanned"]
    if label.startswith("הפרשה לעובר ושב"):
        return ["buffer"]
    if label.startswith("הלוואות"):
        return ["loans"]
    if label.startswith("הפקדה ל"):
        index = _portfolio_index(plan, label[len("הפקדה ל"):])
        return None if index is None else [f"deposit_portfolio{index}"]
    if label.startswith("מס על רווחי"):
        index = _portfolio_index(plan, label[len("מס על רווחי"):])
        return None if index is None else [f"capital_gains_tax{index}"]
    if label.startswith("מס הכנסה"):
        return ["income_tax" + _whose(plan, label)]
    if label.startswith("ביטוח לאומי"):
        return ["national_insurance" + _whose(plan, label)]
    return None


def _retire_index(fixture: dict) -> int:
    """First fully retired month, read from the reference's own output.

    The printed date is the last *working* month. A plan that never reaches its
    goals prints no date at all, so fall back to the month pay stops — those
    runs still retire, they just fail afterwards.
    """
    import re

    match = re.search(r"ב-(\d{2})/(\d{4})", fixture.get("summary", ""))
    if match:
        month, year = int(match.group(1)), int(match.group(2))
        return ((year - RECORDED_IN.year) * 12 + (month - RECORDED_IN.month)) + 1
    work = next(d["data"][1:-1] for d in fixture["charts"]["income_plot"]["datasets"]
                if d["label"] == "עבודה")
    return next((i for i in range(1, len(work)) if work[i] == 0 and work[i - 1] > 0),
                10 ** 9)


class TestCashFlowParity:
    """Every income and expense row, month by month, for every recorded run."""

    @pytest.mark.parametrize("name", _fixtures())
    def test_every_row_matches(self, name):
        """Each charted row equals the sum of the keys our engine files under it."""
        fixture = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
        plan = plan_from_reference(fixture["overrides"])
        result = Simulator(plan).run(
            retire_index=_retire_index(fixture), today=RECORDED_IN)
        bound, why = KNOWN_GAPS.get(name, (TOLERANCE, ""))

        for chart, mapper, attribute in (
                ("income_plot", _income_keys, "incomes"),
                ("expense_plot", _expense_keys, "expenses")):
            for dataset in fixture["charts"][chart]["datasets"]:
                keys = mapper(dataset["label"], plan)
                assert keys is not None, f"{name}: unmapped row {dataset['label']!r}"
                expected = dataset["data"][1:-1]
                for month in range(min(len(expected), len(result.months))):
                    ours = sum(getattr(result.months[month], attribute).get(k, 0.0)
                               for k in keys)
                    assert abs(ours - expected[month]) < bound, (
                        f"{name}: {dataset['label']} diverges at month {month}: "
                        f"reference {expected[month]:,.2f} vs ours {ours:,.2f}"
                        + (f" (known gap: {why})" if why else ""))

    @pytest.mark.parametrize("name", sorted(KNOWN_GAPS))
    def test_every_known_gap_is_still_needed(self, name):
        """A gap that has closed must leave the list, or it hides a regression."""
        fixture = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
        plan = plan_from_reference(fixture["overrides"])
        result = Simulator(plan).run(
            retire_index=_retire_index(fixture), today=RECORDED_IN)
        worst = 0.0
        for chart, mapper, attribute in (
                ("income_plot", _income_keys, "incomes"),
                ("expense_plot", _expense_keys, "expenses")):
            for dataset in fixture["charts"][chart]["datasets"]:
                expected = dataset["data"][1:-1]
                keys = mapper(dataset["label"], plan)
                for month in range(min(len(expected), len(result.months))):
                    ours = sum(getattr(result.months[month], attribute).get(k, 0.0)
                               for k in keys)
                    worst = max(worst, abs(ours - expected[month]))
        assert worst >= TOLERANCE, (
            f"{name} now matches to {worst:.2f} — remove it from KNOWN_GAPS")

    def test_the_two_sides_balance(self):
        """Our decomposition closes, exactly as the reference's does.

        Not a comparison — an internal identity. Every shekel recorded as coming
        in is recorded going somewhere, which is what makes a missing row show up
        as a mismatch rather than quietly vanishing.
        """
        for name in _fixtures():
            fixture = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
            plan = plan_from_reference(fixture["overrides"])
            result = Simulator(plan).run(
                retire_index=_retire_index(fixture), today=RECORDED_IN)
            for record in result.months:
                assert sum(record.incomes.values()) == pytest.approx(
                    sum(record.expenses.values()), abs=1e-6), (
                    f"{name}: month {record.index} does not balance")
