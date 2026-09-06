#!/usr/bin/env python3
"""Build the decumulation surface the engine ships, from the recorded fixtures.

Every cell is a *measurement*, not a fit of a shape: the rate that makes our
simulation replay one recorded reference run. A cell is emitted only when that
run **pins** the rate — moving it by 0.05 points has to wreck the replay — so a
scenario that is merely insensitive to the rate can never vote. That check is
run here rather than trusted from the fit, and it is why fixtures whose replay
is a few tenths of a shekel short (the couple-and-annuity ones, where the
reference prints annuity factors to one decimal) still count: their residual
floor comes from somewhere else entirely, and they pin the rate to 1 part in
10,000.

Two structural facts turn 100-odd scattered fits into one curve per confidence
level (notes/15):

* the surface is keyed on the **bridge** to the statutory pension age
  (67 male / 65 female), not on the retirement age itself, and
* retiring past 60 lands on the *same* curve, shifted by a constant
  `POST_60_SHIFT` years.

Run:  python research/zeke_retire_calc/build_decumulation_table.py
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

from backend.services.fire.engine import Simulator                   # noqa: E402
from backend.services.fire.reference_form import plan_from_reference  # noqa: E402
from validate import our_key, retire_index                            # noqa: E402

OUT = HERE.parents[1] / "backend" / "services" / "fire" / "decumulation_table.json"
TODAY = date(2026, 9, 1)

STATUTORY = {"male": 67, "female": 65}
BRANCH_AGE = 60.5
POST_60_SHIFT = 23.45

PROBE = 0.05
"""How far to move a fitted rate when testing whether the fixture pins it."""
PIN_RATIO = 100.0
"""Required blow-up in the replay error at ``rate +- PROBE``.

This also bounds how far a fixture's own residual can drag the cell: a fit that
misses by `e` while `PROBE` of rate costs `PIN_RATIO * e` can be pulled at most
`PROBE / PIN_RATIO` = 0.0005 points off. That is why a scenario whose replay is
a hundred shekels short — the synthetic-lot fixtures — can still vote.
"""


def replay_error(plan, fixture, index, rate) -> float:
    plan.decumulation_return_pct = rate
    result = Simulator(plan).run(retire_index=index, today=TODAY)
    worst = 0.0
    for dataset in fixture["charts"]["asset_plot"]["datasets"]:
        key = our_key(dataset["label"], plan)
        if key is None:
            continue
        reference = dataset["data"][1:-1]
        for month in range(min(len(reference), len(result.months))):
            worst = max(worst, abs(result.months[month].assets.get(key, 0.0)
                                   - reference[month]))
    return worst


def pins_the_rate(name: str, rate: float) -> bool:
    fixture = json.loads((HERE / "fixtures" / f"{name}.json").read_text(encoding="utf-8"))
    plan = plan_from_reference(fixture["overrides"])
    index = retire_index(fixture)
    best = replay_error(plan, fixture, index, rate)
    off = min(replay_error(plan, fixture, index, rate + PROBE),
              replay_error(plan, fixture, index, rate - PROBE))
    return off >= PIN_RATIO * max(best, 0.05)


def usable(name: str, row: dict, overrides: dict) -> str | None:
    """Why this fixture cannot vote on the surface, or None if it can."""
    if row["decumulation_return_pct"] < -0.5:
        return "no rate fitted"
    if float(overrides.get("portfolioInterest1", 0) or 0) <= 0:
        return "portfolio earns nothing, so min(table, return) hides the rate"
    if "60" in str(overrides.get("pension_tactics", "")) or any(
            value.startswith("mukeret") for key, value in overrides.items()
            if key.startswith("portfolioDesignation")):
        # An annuity claimed before the statutory age splits the bridge across
        # several waits, so this fixture measures a blend rather than one cell
        # (notes/15).
        return "annuity claimed before the statutory age"
    if not pins_the_rate(name, row["decumulation_return_pct"]):
        return "rate not pinned by this scenario"
    return None


def cells() -> dict[float, dict[float, float]]:
    rates = json.loads((HERE / "decumulation_rates.json").read_text(encoding="utf-8"))
    grouped: dict[float, dict[float, list[float]]] = defaultdict(lambda: defaultdict(list))
    for name, row in sorted(rates.items()):
        overrides = json.loads(
            (HERE / "fixtures" / f"{name}.json").read_text(encoding="utf-8"))["overrides"]
        skip = usable(name, row, overrides)
        if skip:
            print(f"  skip {name}: {skip}")
            continue
        # Take the age from the simulator rather than the chart label: the
        # engine looks the rate up on the age in the last *working* month, in
        # whole months since birth, and the label is that rounded to two
        # decimals. Three thousandths of a year is a couple of hundred shekels
        # over the horizon, so the two conventions have to agree exactly.
        fixture = json.loads(
            (HERE / "fixtures" / f"{name}.json").read_text(encoding="utf-8"))
        plan = plan_from_reference(overrides)
        age = Simulator(plan).age_at(max(retire_index(fixture) - 1, 0), TODAY)
        bridge = STATUTORY[overrides.get("gender", "male")] - age
        if age > BRANCH_AGE:
            bridge += POST_60_SHIFT
        grouped[row["rule"]][round(bridge, 6)].append(row["decumulation_return_pct"])
    return {rule: {bridge: round(sum(v) / len(v), 4) for bridge, v in sorted(cell.items())}
            for rule, cell in sorted(grouped.items())}


def main() -> None:
    table = cells()
    payload = {
        "post_60_shift": POST_60_SHIFT,
        "bridge_years": {str(int(rule)): {f"{b:.6f}": r for b, r in cell.items()}
                         for rule, cell in table.items()},
    }
    OUT.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    for rule, cell in table.items():
        print(f"rule {rule:g}: {len(cell)} cells, bridge "
              f"{min(cell):.2f}-{max(cell):.2f}")


if __name__ == "__main__":
    main()
