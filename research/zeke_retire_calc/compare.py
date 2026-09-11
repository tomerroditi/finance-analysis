"""Compare our engine against a recorded reference fixture, month by month."""
import json, re, sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from backend.services.fire.engine import Simulator  # noqa: E402
from backend.services.fire.reference_form import plan_from_reference  # noqa: E402

TODAY = date(2026, 9, 1)   # month the fixtures were recorded in


def reference_series(fix):
    """Strip the area-chart padding point at each end."""
    ch = fix["charts"]["asset_plot"]
    lab = ch["labels"][1:-1]
    out = {"age": lab}
    for d in ch["datasets"]:
        out[d["label"]] = d["data"][1:-1]
    return out


def retire_index(fix, ref):
    """Month index at which the reference retired.

    Taken from the reported retirement age in the prose summary, which is the
    authoritative value; the age axis of the charts gives the mapping.
    """
    m = re.search(r"גיל פרישה: ([\d.]+)", fix["summary"])
    if not m:
        return None
    target = float(m.group(1))
    ages = ref["age"]
    return min(range(len(ages)), key=lambda i: abs(ages[i] - target))


def compare(name, upto_retirement=True):
    fix = json.loads((Path(__file__).parent / "fixtures" / f"{name}.json").read_text(encoding="utf-8"))
    ref = reference_series(fix)
    ri = retire_index(fix, ref)
    plan = plan_from_reference(fix["overrides"])
    res = Simulator(plan).run(retire_index=ri if ri is not None else 10**9, today=TODAY)

    n = min(len(ref["age"]), len(res.months))
    limit = ri if (upto_retirement and ri) else n
    rows = []
    for label, ours_key in [(k, v) for k in ref if k != "age"
                            for v in [("cash" if "עובר" in k else "portfolio0")]]:
        ours = [res.months[i].assets[ours_key] for i in range(n)]
        theirs = ref[label][:n]
        worst = max(range(min(limit, n)), key=lambda i: abs(ours[i] - theirs[i]))
        rows.append((label, ours_key, abs(ours[worst] - theirs[worst]), worst,
                     theirs[worst], ours[worst]))
    print(f"=== {name}  (months={n}, retire_index={ri}, comparing first {limit})")
    for label, key, err, i, t, o in rows:
        flag = "OK  " if err < 1.0 else "FAIL"
        print(f"  {flag} {label[:28]:28} vs {key:11} max|Δ|={err:12,.2f} "
              f"at m{i} (ref {t:,.1f} / ours {o:,.1f})")
    return rows


if __name__ == "__main__":
    names = sys.argv[1:] or ["baseline", "goal_big", "goal_big_cap", "buffer_20k",
                             "tax_profit_0", "compound_precise", "zero_return"]
    for n in names:
        compare(n)
