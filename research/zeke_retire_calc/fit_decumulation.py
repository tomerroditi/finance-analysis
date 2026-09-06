"""Harvest the reference's decumulation-return table from recorded fixtures.

For each pension-free fixture, solve for the single scalar `decumulation_return`
that makes our simulation match the reference. Two things fall out:

* a residual near zero proves the *rest* of the model is exact for that
  scenario, and
* the fitted value is a data point of the reference's Trinity-style lookup on
  (confidence, horizon).
"""
import json, re, sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from backend.services.fire.engine import Simulator                    # noqa: E402
from backend.services.fire.reference_form import plan_from_reference   # noqa: E402
from validate import retire_index, our_key                             # noqa: E402

TODAY = date(2026, 9, 1)
STATUTORY = {"male": 67, "female": 65}


def residual(plan, fix, ri, rate):
    plan.decumulation_return_pct = rate
    res = Simulator(plan).run(retire_index=ri, today=TODAY)
    worst = 0.0
    for d in fix["charts"]["asset_plot"]["datasets"]:
        key = our_key(d["label"], plan)
        if key is None:
            continue
        ref = d["data"][1:-1]
        n = min(len(ref), len(res.months))
        for i in range(n):
            worst = max(worst, abs(res.months[i].assets.get(key, 0.0) - ref[i]))
    return worst


def fit(name):
    fix = json.loads((HERE / "fixtures" / f"{name}.json").read_text(encoding="utf-8"))
    ov = fix["overrides"]
    if not fix.get("charts", {}).get("asset_plot"):
        return None
    plan = plan_from_reference(ov)
    ri = retire_index(fix)
    if ri is None or ri >= len(fix["charts"]["asset_plot"]["labels"]) - 3:
        return None

    # The residual is a max over months, so different months dominate at
    # different rates and it is only piecewise smooth — a bare ternary search
    # can settle in a local minimum. Bracket with a coarse grid first.
    grid = [-1.0 + i * 0.05 for i in range(141)]
    seed = min(grid, key=lambda r: residual(plan, fix, ri, r))
    lo, hi = seed - 0.05, seed + 0.05
    for _ in range(40):
        a = lo + (hi - lo) / 3
        b = hi - (hi - lo) / 3
        if residual(plan, fix, ri, a) < residual(plan, fix, ri, b):
            hi = b
        else:
            lo = a
    best = (lo + hi) / 2
    ages = fix["charts"]["asset_plot"]["labels"][1:-1]
    fire = ages[min(ri, len(ages) - 1)]
    return dict(name=name,
                rule=float(ov.get("retireRule", 85)),
                fire=round(fire, 2),
                bridge=round(STATUTORY[ov.get("gender", "male")] - fire, 2),
                rate=round(best, 8),
                residual=round(residual(plan, fix, ri, best), 2))


def write_table(rows, path):
    """Freeze the fitted rates so the parity tests can assert against them.

    Every fitted row is kept, whatever its residual: a scenario whose replay is
    a hundred shekels short over 533 months still pins its rate to one part in
    ten thousand, and `build_decumulation_table.py` re-checks that pinning
    itself rather than trusting a residual threshold here. Each row carries its
    own residual so the consumers that do want a clean subset — the
    full-horizon parity class, say — can pick one.
    """
    json.dump({r["name"]: {"rule": r["rule"], "fire_age": r["fire"],
                           "bridge_years": r["bridge"], "decumulation_return_pct": r["rate"],
                           "residual": r["residual"]}
               for r in rows},
              open(path, "w"), indent=1, sort_keys=True)


if __name__ == "__main__":
    names = sys.argv[1:] or sorted(p.stem for p in (HERE / "fixtures").glob("*.json"))
    rows = []
    for n in names:
        try:
            row = fit(n)
        except Exception:
            row = None
        if row:
            rows.append(row)
    rows.sort(key=lambda r: (r["rule"], r["bridge"]))
    write_table(rows, HERE / "decumulation_rates.json")
    print(f"{'fixture':24}{'rule':>6}{'FIRE':>7}{'bridge':>8}{'fitted r%':>11}{'residual':>10}")
    for r in rows:
        flag = "" if r["residual"] < 1.0 else "   <-- model gap"
        print(f"{r['name']:24}{r['rule']:6.0f}{r['fire']:7.2f}{r['bridge']:8.2f}"
              f"{r['rate']:11.4f}{r['residual']:10.2f}{flag}")
