#!/usr/bin/env python3
"""Probe the reference for the three things the recorded corpus cannot settle.

Run this anywhere with a route to zekestories.com. It records each scenario as
an ordinary fixture (so the parity suites pick it up on the next run) and then
immediately replays it through our engine, printing two numbers per probe:

* **derived** — the worst gap over every asset series with *nothing* supplied;
  what a user would actually see.
* **fitted** — the same gap once the run's own decumulation rate is solved for.

The pair is the diagnostic. A tiny `fitted` beside a large `derived` means the
model is right and only the rate it read is wrong — one scalar, a surface
question. Both large means something in the model itself is off.

    python research/zeke_retire_calc/probe_open_questions.py            # all
    python research/zeke_retire_calc/probe_open_questions.py gb_        # one family
    python research/zeke_retire_calc/probe_open_questions.py --report   # no network

Already-recorded fixtures are skipped unless --force, so an interrupted run
resumes where it stopped.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import probe                                                          # noqa: E402
from backend.services.fire import decumulation as D                    # noqa: E402
from backend.services.fire.engine import Simulator                     # noqa: E402
from backend.services.fire.reference_form import plan_from_reference    # noqa: E402
from backend.services.fire.solver import solve                          # noqa: E402
from validate import our_key, retire_index                             # noqa: E402

TODAY = date(2026, 9, 1)
FIXTURES = HERE / "fixtures"

PENSION_FROZEN = dict(pensionDeposit=0, pensionInterest="0.0",
                      pensionFee1="0.0", pensionFee2="0.0", percentage_mukeret=30)
"""A pension that neither grows nor receives — so the balance at annuitisation
is exactly what was typed, and the annuity it buys is exactly balance/factor.
That takes the accumulation model out of every measurement below."""


def gemel_bridge() -> dict[str, dict]:
    """Family A — does a converting gemel change the weights, or the wait?

    `pf_mukeret3_t60` needs a bridge of 25.7 years while every annuity it holds
    starts at 60, which is a bridge of 22.7 (notes/15). Two readings survive the
    recorded corpus: the gemel money is weighted differently from a pension
    annuity, or it is waited for beyond the age it is paid from. Nothing in the
    corpus separates them, because its three gemel runs each move the retirement
    age *and* the claim structure at once.

    So: pin the retirement age with `retire_at_age`, hold everything else
    fixed, and sweep the gemel balance alone. Under "weighted differently" the
    surface value the gemel money carries is a constant and only its weight
    moves; under "waited for" that value moves with the claim structure. The
    ladder runs at all three `pension_tactics` for exactly that reason, and the
    no-gemel rung is the control that must reproduce the plain blend.
    """
    out = {}
    for tactic in ("60", "60-67", "67"):
        for balance in (0, 200_000, 400_000, 800_000, 1_600_000):
            fields = dict(
                base_problem="retire_at_age", wanted_retire_age=45,
                base_problem_max_age=60, retireRule=85,
                portfolioBalance1=1_200_000, portfolioProfitFraction1="0.0",
                pensionBalance=1_200_000, pension_tactics=tactic, **PENSION_FROZEN)
            if balance:
                fields.update({
                    "num_portfolio_fields": 2,
                    "portfolioDesignation2": "mukeret_main",
                    "portfolio_type2": "gemel", "portfolioBalance2": balance,
                    "portfolioInterest2": "5.0", "portfolioFee2": "0.1",
                    "portfolioProfitFraction2": "0.0", "portfolio_goal2": "0",
                    "portfolioDescription2": "M2"})
            out[f"gb_t{tactic.replace('-', '')}_{balance // 1000}k"] = probe.scenario(**fields)
    return out


def bridge_cells() -> dict[str, dict]:
    """Family B — sample the surface where it has no cells.

    Rule 85 is measured at a bridge of 17.25 and again at 18.33 with nothing
    between, over a stretch where the curve climbs 26%. `pn_annuity_6067` reads
    it at 18.0 and pays 260 shekels for the interpolation (notes/15).

    Nothing is claimed early here, so the bridge is the plain statutory wait,
    `67 - age at the last working month` — and a retirement pinned to an integer
    age lands that one month short of the integer. Ages 50, 49.5, 49 and 48 give
    bridges of 17.083, 17.583, 18.083 and 19.083.

    18.083 is the one that matters: it sits inside the 17.25-18.33 gap, close to
    the 18.0 that `pn_annuity_6067` reads and cannot get right. 17.083 is the
    consistency check — a measured cell sits a month away at 17.0, so a reading
    far from 1.0968 would mean the surface is wrong in this whole stretch rather
    than merely sparse.
    """
    out = {}
    for age in (48, 49, 50, 49.5):
        name = f"br_age{str(age).replace('.', '_')}"
        out[name] = probe.scenario(
            base_problem="retire_at_age", wanted_retire_age=age,
            base_problem_max_age=60, retireRule=85, pension_tactics="67",
            portfolioBalance1=1_200_000, portfolioProfitFraction1="0.0",
            pensionBalance=1_200_000, **PENSION_FROZEN)
    return out


def annuity_factors() -> dict[str, dict]:
    """Family C — tighten the four factors, the female ones most of all.

    A factor is bracketed by the annuity the reference prints, and that print
    carries one decimal — so the bracket narrows as the annuity grows. The
    female-65 factor rests on a single run paying 5,721.9, which is why its
    interval is five times wider than the other three. With the pension frozen,
    the balance at annuitisation is exactly what was typed and the printed
    annuity is exactly balance/factor: no accumulation model in between.
    """
    out = {}
    for gender, tactic, balance in (("female", "67", 6_000_000),
                                    ("female", "67", 20_000_000),
                                    ("female", "60", 20_000_000),
                                    ("male", "67", 20_000_000),
                                    ("male", "60", 20_000_000)):
        name = f"fx_{gender[0]}{tactic.replace('-', '')}_{balance // 1_000_000}m"
        out[name] = probe.scenario(gender=gender, pension_tactics=tactic,
                                   pensionBalance=balance, **PENSION_FROZEN)
    return out


SCENARIOS = {**gemel_bridge(), **bridge_cells(), **annuity_factors()}


def _worst(fixture: dict, plan, result) -> float:
    """Largest gap between our asset series and the reference's, any month."""
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


def replay(name: str) -> tuple[float, float, float] | None:
    """`(derived gap, fitted gap, fitted rate)` for one recorded fixture."""
    path = FIXTURES / f"{name}.json"
    if not path.exists():
        return None
    fixture = json.loads(path.read_text(encoding="utf-8"))
    if not fixture.get("charts", {}).get("asset_plot"):
        return None
    index = retire_index(fixture)

    plan = plan_from_reference(fixture["overrides"])
    derived = _worst(fixture, plan, Simulator(plan).run(retire_index=index, today=TODAY))

    def at(rate: float) -> float:
        pinned = plan_from_reference(fixture["overrides"])
        pinned.decumulation_return_pct = rate
        return _worst(fixture, pinned,
                      Simulator(pinned).run(retire_index=index, today=TODAY))

    low, high = -1.0, 4.0
    for _ in range(50):
        a, b = low + (high - low) * 0.382, low + (high - low) * 0.618
        if at(a) < at(b):
            high = b
        else:
            low = a
    rate = (low + high) / 2
    return derived, at(rate), rate


def implied_gemel_surface(name: str, rate: float) -> str:
    """What surface value the gemel money must carry, given the fitted rate.

    Solves the weighting rule for the one unknown: with the pension streams at
    their own bridges, the gemel's annuity has to sit at whatever value makes
    the blend come out at `rate`. If that value is constant across the balance
    ladder, the gemel is one more stream and only its weight moved.
    """
    fixture = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    plan = plan_from_reference(fixture["overrides"])
    index = retire_index(fixture)
    simulator = Simulator(plan)
    result = simulator.run(retire_index=index, today=TODAY)

    annuities = [a for a in result.annuities if a.source in ("pension", "gemel")]
    gemel = [a for a in annuities if a.source == "gemel"]
    if not gemel:
        return ""

    # Bridges come from the engine's own stream months, never re-derived. An
    # annuity starts the month *after* the claim birthday, so reading "the
    # first month at that age" off the series lands one month early — 1/12 of
    # a year, and enough to move the solved value in the third decimal.
    # Distinct claim ages and distinct stream months are both ascending, so
    # zipping them pairs each age with the month the engine actually used.
    ages = sorted({a.claim_age for a in annuities})
    months = sorted({month for _, month in simulator._streams})
    if len(ages) != len(months):
        return "  (streams and claim ages do not line up)"
    bridge = {age: (month - index) / 12 for age, month in zip(ages, months)}

    rule = plan.retire_rule_confidence
    locked = sum(a.monthly for a in gemel)
    pension = [a for a in annuities if a.source == "pension"]
    paid = sum(a.monthly for a in pension)
    weighted = sum(a.monthly * D._for_rule(rule, bridge[a.claim_age]) for a in pension)
    value = (rate * (paid + locked) - weighted) / locked
    inside = D._for_rule(rule, 7.0) <= value <= D._for_rule(rule, 30.333333)
    return (f"  gemel carries {value:.4f}"
            + ("" if inside else "  <- off the curve entirely"))


def predicted_rate(overrides: dict) -> float:
    """The decumulation return our engine will read for a scenario.

    Computed before the reference is asked anything, which is what makes the
    sweep a test rather than a fit. The `gb_t60_*` ladder is the one to watch:
    every annuity in those runs starts in the same month, so our rule has no
    way to return five different numbers for five different gemel balances.
    """
    plan = plan_from_reference(overrides)
    outcome = solve(plan, TODAY)
    simulator = Simulator(plan)
    simulator.run(retire_index=outcome.retire_index, today=TODAY)
    return simulator._decumulation_return(outcome.retire_index)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("prefix", nargs="?", default="",
                        help="only scenarios whose name starts with this")
    parser.add_argument("--report", action="store_true",
                        help="replay what is already recorded; no network")
    parser.add_argument("--predict", action="store_true",
                        help="print what our engine expects, before asking; no network")
    parser.add_argument("--force", action="store_true", help="re-record even if present")
    parser.add_argument("--sleep", type=float, default=2.0, help="seconds between probes")
    args = parser.parse_args()

    wanted = {n: o for n, o in SCENARIOS.items() if n.startswith(args.prefix)}
    print(f"{len(wanted)} scenario(s)\n")

    if args.predict:
        for name, overrides in wanted.items():
            print(f"{name:22s} {predicted_rate(overrides):.8f}")
        return

    session = None
    if not args.report:
        import zeke
        session = zeke.Session().load()
        print("form loaded; csrf token acquired\n")

    for name, overrides in wanted.items():
        path = FIXTURES / f"{name}.json"
        if args.report or (path.exists() and not args.force):
            state = "on disk" if path.exists() else "not recorded"
        else:
            try:
                record, session = probe.run(name, overrides, session=session,
                                            sleep=args.sleep)
                state = "recorded" if record.get("calc_success") else "REFUSED"
            except Exception as exc:                       # keep the sweep going
                print(f"{name:22s} FAILED  {type(exc).__name__}: {exc}")
                continue

        outcome = replay(name)
        if outcome is None:
            print(f"{name:22s} {state}  (no chart to compare)")
            continue
        derived, fitted, rate = outcome
        print(f"{name:22s} {state}  derived {derived:12,.2f}   "
              f"fitted {fitted:8,.2f} @ {rate:.5f}"
              + (implied_gemel_surface(name, rate) if name.startswith("gb_") else ""))


if __name__ == "__main__":
    main()
