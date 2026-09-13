"""Validate our engine against every recorded reference fixture.

Reports the worst per-series deviation over the accumulation phase (always) and
over the full horizon (where the drawdown model is complete enough).
"""
import json, re, sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from backend.services.fire.engine import Simulator          # noqa: E402
from backend.services.fire.reference_form import plan_from_reference  # noqa: E402

TODAY = date(2026, 9, 1)


def load(name):
    return json.loads((HERE / "fixtures" / f"{name}.json").read_text(encoding="utf-8"))


def retire_index(fix, start=(2026, 9)):
    """First fully retired month.

    Read from the retirement **date** the reference prints, not the age: the
    age is rounded to one decimal and 53.2 is ambiguous between 53.17 and
    53.25, which silently shifts the whole drawdown by a month. The printed
    date is the LAST WORKING month, so the first retired month is one later
    (notes/08).
    """
    m = re.search(r"ב-(\d{2})/(\d{4})", fix.get("summary", ""))
    if m:
        month, year = int(m.group(1)), int(m.group(2))
        return (year - start[0]) * 12 + (month - start[1]) + 1
    try:
        work = next(d["data"][1:-1] for d in fix["charts"]["income_plot"]["datasets"]
                    if d["label"] == "עבודה")
    except (KeyError, StopIteration):
        return None
    for i in range(1, len(work)):
        if work[i] == 0 and work[i - 1] > 0:
            return i
    return None


def measure_decumulation_return(fix, ri, plan):
    """Recover the reference's post-FIRE return from an untouched portfolio.

    Isolates the one quantity we cannot yet derive (the Trinity haircut) so the
    rest of the model can be checked exactly. Only valid where a portfolio is
    growing without being withdrawn from; returns None otherwise.
    """
    ap = fix["charts"]["asset_plot"]
    for d in ap["datasets"]:
        if "עובר" in d["label"] or not any(
                k in d["label"] for k in ("תיק", "שווי")):
            continue
        series = d["data"][1:-1]
        a, b = ri + 1, ri + 25
        if b >= len(series) or series[a] <= 0 or series[b] <= 0:
            continue
        # Only usable if the balance moves smoothly (no withdrawals/deposits).
        ratios = [series[i] / series[i - 1] for i in range(a + 1, b + 1)]
        if max(ratios) - min(ratios) > 1e-6:
            continue
        fee = plan.portfolios[0].annual_fee_pct / 100
        return 100 * ((sum(ratios) / len(ratios)) ** 12 / (1 - fee) - 1)
    return None


def our_key(label, plan):
    if "עובר" in label:
        return "cash"
    for i, p in enumerate(plan.portfolios):
        if p.description and p.description in label:
            return f"portfolio{i}"
    if "תיק" in label or "קרן כספית" in label or "פיקדון" in label:
        return "portfolio0"
    if "השתלמות" in label:
        return "keren0"
    if "נדל" in label or "דירה" in label:
        return "realestate0"
    return None


def check(name, upto=None):
    fix = load(name)
    if not fix.get("charts", {}).get("asset_plot"):
        return f"{name}: no asset chart (calc failed)"
    plan = plan_from_reference(fix["overrides"])
    ri = retire_index(fix)
    if ri is not None:
        measured = measure_decumulation_return(fix, ri, plan)
        if measured is not None:
            plan.decumulation_return_pct = measured
    res = Simulator(plan).run(retire_index=ri if ri is not None else 10 ** 9, today=TODAY)
    ap = fix["charts"]["asset_plot"]
    limit = upto or len(res.months)   # full horizon: decumulation is now modelled
    lines = []
    for d in ap["datasets"]:
        key = our_key(d["label"], plan)
        if key is None:
            lines.append(f"    ?    {d['label'][:30]:30} (unmapped)")
            continue
        ref = d["data"][1:-1]
        n = min(limit, len(ref), len(res.months))
        worst = max(range(n), key=lambda i: abs(res.months[i].assets.get(key, 0.0) - ref[i]))
        err = abs(res.months[worst].assets.get(key, 0.0) - ref[worst])
        lines.append(f"    {'OK ' if err < 0.5 else 'BAD'}  {d['label'][:30]:30} "
                     f"max|Δ|={err:12,.2f} at m{worst}")
    nv = fix["charts"].get("netval_plot")
    if nv and nv["datasets"]:
        ref = nv["datasets"][0]["data"][1:-1]
        n = min(limit, len(ref), len(res.months))
        worst = max(range(n), key=lambda i: abs(res.months[i].net_worth - ref[i]))
        err = abs(res.months[worst].net_worth - ref[worst])
        lines.append(f"    {'OK ' if err < 0.5 else 'BAD'}  {'NET WORTH':30} "
                     f"max|Δ|={err:12,.2f} at m{worst} (ref {ref[worst]:,.1f})")
    return f"{name} (retire m{ri}, checked {limit} months)\n" + "\n".join(lines)


if __name__ == "__main__":
    names = sys.argv[1:] or sorted(p.stem for p in (HERE / "fixtures").glob("*.json"))
    for n in names:
        try:
            print(check(n))
        except Exception as exc:  # noqa: BLE001
            print(f"{n}: ERROR {type(exc).__name__}: {exc}")
