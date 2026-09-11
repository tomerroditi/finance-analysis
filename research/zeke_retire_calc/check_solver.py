"""Does our solver reach the same retirement date the reference published?"""
import json, re, sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

from backend.services.fire.models import BaseProblem            # noqa: E402
from backend.services.fire.reference_form import plan_from_reference  # noqa: E402
from backend.services.fire.solver import solve_retire_asap      # noqa: E402
from validate import retire_index                               # noqa: E402

TODAY = date(2026, 9, 1)
RATES = json.loads((HERE / "decumulation_rates.json").read_text(encoding="utf-8"))

agree = disagree = skipped = 0
rows = []
for name, meta in sorted(RATES.items()):
    fx = json.loads((HERE / "fixtures" / f"{name}.json").read_text(encoding="utf-8"))
    plan = plan_from_reference(fx["overrides"])
    if plan.base_problem is not BaseProblem.RETIRE_ASAP:
        skipped += 1
        continue
    if not re.search(r"ב-(\d{2})/(\d{4})", fx.get("summary", "")):
        skipped += 1
        continue
    plan.decumulation_return_pct = meta["decumulation_return_pct"]
    ours = solve_retire_asap(plan, TODAY).retire_index
    theirs = retire_index(fx)
    if ours == theirs:
        agree += 1
    else:
        disagree += 1
        rows.append((name, theirs, ours))

print(f"{agree} agree, {disagree} disagree, {skipped} skipped (not retire_asap)")
for name, theirs, ours in rows[:15]:
    print(f"   {name:24} reference m{theirs}  ours m{ours}  (Δ {ours - theirs:+d} months)")
