#!/usr/bin/env python3
"""Measure the reference's annuity factors (מקדם קצבה) from the recorded runs.

The factor is the one number in the pension model we cannot derive: the
reference divides an accrued balance by it to get a monthly annuity, and it
never prints the factor to more than one decimal ("מקדם 224.4").

It does, however, print the resulting annuity to one decimal in its closing
line — "הקצבה שלך מכל המקורות הפנסיוניים תעמוד בגיל 60.0 על 24,055.5 ₪" — and
our engine computes the balance at annuitisation *without* using the factor at
all (contributions, growth, and the two management fees). So each such run
brackets its factor:

    balance / (printed + 0.05)  <=  factor  <=  balance / (printed - 0.05)

Intersecting those brackets across every run that annuitises at the same
(gender, claim age) is the measurement. A run whose printed total also covers
an annuitised gemel, or splits its claim across two ages, describes a different
quantity and is dropped.

Run:  python research/zeke_retire_calc/measure_annuity_factors.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

from backend.services.fire.engine import Simulator                    # noqa: E402
from backend.services.fire.models import Gender                       # noqa: E402
from backend.services.fire.pension import ANNUITY_FACTORS             # noqa: E402
from backend.services.fire.reference_form import plan_from_reference   # noqa: E402
from validate import retire_index                                      # noqa: E402

TODAY = date(2026, 9, 1)
PRINTED_HALF_STEP = 0.05
"""The closing line carries one decimal, so a printed total is that ±0.05."""

MIXED_TOTAL = 2e-4
"""Relative gap above which the printed total is not the pension fund alone.

An annuitised gemel adds a stream the closing line counts and this measurement
does not, and a split claim pays two different factors. Both land orders of
magnitude outside the display rounding, so one threshold separates them."""

SELF = re.compile(
    r"הקצבה שלך מכל המקורות הפנסיוניים תעמוד בגיל ([\d.]+) על ([\d,.]+) ₪")
PARTNER = re.compile(
    r"הקצבה של \S+ מכל המקורות הפנסיוניים תעמוד בגיל ([\d.]+) על ([\d,.]+) ₪")


def _our_annuity(result, partner: bool) -> float:
    """The pension annuity our engine pays, from the first month it pays one."""
    suffix = "_partner" if partner else ""
    for record in result.months:
        total = sum(value for key, value in record.incomes.items()
                    if key in (f"recognised{suffix}", f"entitling{suffix}"))
        if total > 0:
            return total
    return 0.0


def brackets() -> dict[tuple[str, int], list[tuple[str, float, float, float]]]:
    """Every (fixture, printed total, lower, upper) bracket, by gender and age."""
    rates = json.loads((HERE / "decumulation_rates.json").read_text(encoding="utf-8"))
    found: dict[tuple[str, int], list] = defaultdict(list)
    for path in sorted((HERE / "fixtures").glob("*.json")):
        fixture = json.loads(path.read_text(encoding="utf-8"))
        if not fixture.get("charts", {}).get("asset_plot"):
            continue
        plan = plan_from_reference(fixture["overrides"])
        if path.stem in rates:
            plan.decumulation_return_pct = rates[path.stem]["decumulation_return_pct"]
        result = Simulator(plan).run(retire_index=retire_index(fixture), today=TODAY)

        for pattern, partner in ((SELF, False), (PARTNER, True)):
            match = pattern.search(fixture["summary"])
            person = plan.partner if partner else plan.person
            pension = plan.partner_pension if partner else plan.pension
            if not match or person is None or pension is None:
                continue
            printed = float(match.group(2).replace(",", ""))
            ours = _our_annuity(result, partner)
            if ours <= 0 or abs(ours - printed) / printed > MIXED_TOTAL:
                continue
            claim_age = int(round(float(match.group(1))))
            factor = ANNUITY_FACTORS[person.gender].get(claim_age)
            if factor is None:
                continue
            balance = ours * factor      # independent of the factor used
            found[(person.gender.value, claim_age)].append((
                path.stem, printed,
                balance / (printed + PRINTED_HALF_STEP),
                balance / (printed - PRINTED_HALF_STEP)))
    return found


def main() -> None:
    for key, rows in sorted(brackets().items()):
        low = max(row[2] for row in rows)
        high = min(row[3] for row in rows)
        shipped = ANNUITY_FACTORS[Gender(key[0])][key[1]]
        verdict = "ships the midpoint" if low <= shipped <= high else "SHIPPED VALUE OUTSIDE"
        print(f"{key[0]:6s} at {key[1]}: {len(rows)} runs -> "
              f"[{low:.6f}, {high:.6f}] mid {(low + high) / 2:.6f} "
              f"(shipped {shipped}, {verdict})")
        for name, printed, lo, hi in sorted(rows, key=lambda row: row[3] - row[2]):
            print(f"    {name:24s} printed {printed:>10,.1f}  [{lo:.6f}, {hi:.6f}]")


if __name__ == "__main__":
    main()
