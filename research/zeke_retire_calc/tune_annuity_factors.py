#!/usr/bin/env python3
"""Pick each annuity factor inside its measured bracket by replay error.

`measure_annuity_factors.py` brackets every factor from the reference's own
printed annuity; the bracket is the hard constraint, but it is a thousandth
wide and the replay can still see across it. This walks each factor over its
bracket, refits the decumulation rate for every run that annuitises on it, and
reports the value that replays the corpus best — a second measurement of the
same number, against a different observable.

Run:  python research/zeke_retire_calc/tune_annuity_factors.py [passes]
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

from backend.services.fire import pension                              # noqa: E402
from backend.services.fire.engine import Simulator                     # noqa: E402
from backend.services.fire.models import Gender                        # noqa: E402
from backend.services.fire.reference_form import plan_from_reference    # noqa: E402
import parity                                                          # noqa: E402

GRID = 9
"""Points sampled across a bracket in one pass; each pass narrows to a step."""

UNRELATED_GAP = {"pf_mukeret4_order"}
"""Runs whose residual floor is an unsolved bridge (a couple's, notes/18).

Their refit absorbs that gap into the decumulation rate, so what is left is
insensitive to the annuity factor and would only add noise to the score."""

BRACKETS = {
    (Gender.MALE, 60): (224.417054, 224.417342),
    (Gender.MALE, 67): (197.823056, 197.823655),
    (Gender.FEMALE, 60): (227.343006, 227.343772),
    (Gender.FEMALE, 65): (209.718715, 209.722380),
}


def users() -> dict[tuple[Gender, int], list[str]]:
    """Which recorded runs read which factor."""
    out: dict[tuple[Gender, int], list[str]] = defaultdict(list)
    for name in parity.corpus(charted=True):
        if name in UNRELATED_GAP:
            continue
        fixture = parity.load(name)
        plan = plan_from_reference(fixture["overrides"])
        for annuity in Simulator(plan).run(retire_index=parity.retire_index(fixture),
                                           today=parity.recorded_in(fixture)).annuities:
            if annuity.factor is None:
                continue
            gender = (plan.person.gender if annuity.owner == plan.person.name
                      else plan.partner.gender)
            key = (gender, int(annuity.claim_age))
            if name not in out[key]:
                out[key].append(name)
    return out


def best_residual(name: str) -> float:
    """Replay error of a run once its own decumulation rate is refitted."""
    fixture = parity.load(name)
    index = parity.retire_index(fixture)

    def error(rate: float) -> float:
        plan = plan_from_reference(fixture["overrides"])
        plan.decumulation_return_pct = rate
        result = Simulator(plan).run(retire_index=index, today=parity.recorded_in(fixture))
        return parity.worst_asset_gap(fixture, plan, result)

    low, high = -1.0, 4.0
    for _ in range(50):
        a, b = low + (high - low) * 0.382, low + (high - low) * 0.618
        if error(a) < error(b):
            high = b
        else:
            low = a
    return error((low + high) / 2)


def main() -> None:
    passes = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    by_factor = users()
    span = {key: BRACKETS[key] for key in BRACKETS}
    for round_number in range(passes):
        for key, (low, high) in list(span.items()):
            names = by_factor.get(key, [])
            if not names:
                continue
            original = pension.ANNUITY_FACTORS[key[0]][key[1]]
            scored = []
            for step in range(GRID):
                value = low + (high - low) * step / (GRID - 1)
                pension.ANNUITY_FACTORS[key[0]][key[1]] = value
                scored.append((sum(best_residual(n) for n in names), value))
            scored.sort()
            best = scored[0][1]
            pension.ANNUITY_FACTORS[key[0]][key[1]] = best
            width = (high - low) / (GRID - 1)
            span[key] = (max(low, best - width), min(high, best + width))
            print(f"pass {round_number} {key[0].value:6s} {key[1]}: "
                  f"{original:.6f} -> {best:.6f}  total residual {scored[0][0]:.2f} "
                  f"over {len(names)} runs", flush=True)
    print("\nfinal:")
    for gender, ages in pension.ANNUITY_FACTORS.items():
        for age, value in ages.items():
            print(f"  {gender.value:6s} {age}: {value:.6f}")


if __name__ == "__main__":
    main()
