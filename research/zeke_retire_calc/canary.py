#!/usr/bin/env python3
"""Re-ask the live reference a fixed set of questions and check we still agree.

Parity was proven against answers recorded in 2026. The author can change a
formula, a statutory constant or a default at any time, and nothing on our side
would notice. This sends ~20 recorded scenarios again — one per rule the corpus
pinned down — and replays each fresh answer through our engine at *today's*
month, exactly as `lab.py` judges a new probe:

* **drift** — the reference still answers, but we no longer agree within 0.1%
  of peak net worth, or the two solvers pick different retirement months;
* **refused** — a scenario it used to answer is now rejected;
* **answers now** — a mode that crashed on its side (`improve_cash`) now
  returns charts: our inferred implementation can finally be checked.
* **site error** — the reference answered with an error banner instead of a
  result. That says nothing about parity; the run stops after three in a row
  rather than keep loading a server that is failing.

Fresh answers are compared with our engine, not with the old fixture: the
scenarios carry fixed birth dates, so every month they age by one and the old
answer is no longer the right one. Nothing under `fixtures/` is touched; pass
`--out` to keep the fresh answers for a look at what moved.

    python research/zeke_retire_calc/canary.py                 # all canaries
    python research/zeke_retire_calc/canary.py --out answers/  # keep the answers
    python research/zeke_retire_calc/canary.py --only cx2_     # by prefix
    python research/zeke_retire_calc/canary.py --dry           # no network

Exits non-zero when anything drifted, so a scheduled run fails loudly. The
reference is a shared job queue: probes go one at a time with a pause between.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))

import lab  # noqa: E402
import parity  # noqa: E402
import zeke  # noqa: E402

THRESHOLD = 0.001
"""Relative gap counted as agreement — the corpus' own bar."""

CANARIES: dict[str, str] = {
    "baseline": "the reference's own default form, end to end",
    "fx_m67_20m": "male annuity factor at 67, national insurance on the annuity",
    "fx_f60_20m": "female annuity factor at 60, insurance ceiling",
    "pn_pizuim_2010": "severance redemption and its exemption offset",
    "pn_keren_maslulit": "keren hishtalmut growth, fee and draw",
    "pn_bl_partner": "Bituach Leumi rate and the spouse increment",
    "pn_rule90_pf": "decumulation return at a 90% confidence",
    "pf_mukeret2": "gemel converted to a recognised annuity at 60",
    "pf_american": "US-person portfolio tax",
    "pf_fifo": "FIFO lot history",
    "lt2_lifo_p70": "LIFO lot ladder rounding and scaling",
    "ln_spitzer_now": "Spitzer loan amortisation",
    "cf_realestate": "real estate appreciation and the credit line",
    "tx2_couple_stack": "capital-gains exemption stacked on a spouse's pension",
    "cp9_xend_320": "couple bridge: spending read at the horizon",
    "cp11_6067_sev": "couple bridge with a split tactic and severance",
    "cx2_016": "retirement pinned to an age already behind today",
    "cx2_018": "goal portfolio reached while still working",
    "desig_goal": "bequest fails on an earmarked portfolio short of its goal",
    "sol_at_age_58": "retire-at-age check-up",
    "sol_improve_cash": "improve-cash mode — crashed on the reference when recorded",
}
"""Fixture name -> the rule it guards. Each is a recorded run whose payload is
re-sent unchanged."""


@dataclass
class Verdict:
    """What one canary found."""

    name: str
    status: str
    detail: str

    @property
    def ok(self) -> bool:
        """Whether this canary still agrees with what was recorded."""
        return self.status in ("ok", "still refused")


def charted(fixture: dict) -> bool:
    """Whether the reference answered with charts."""
    return bool((fixture.get("charts") or {}).get("asset_plot"))


def judge(name: str, recorded: dict, fresh: dict) -> Verdict:
    """Compare a fresh answer with our engine, in light of what was recorded."""
    if fresh.get("meta", {}).get("errors"):
        # An error banner instead of an answer is the site failing, not a
        # verdict on the scenario: on 2026-10-10 every request, the default
        # form included, came back as `E_SIMSTATE_DESYNC` in 0.2 seconds.
        return Verdict(name, "site error", fresh["meta"]["errors"][:160])
    if not charted(fresh):
        if charted(recorded):
            return Verdict(name, "refused", fresh.get("meta", {}).get("messages", "")[:120])
        return Verdict(name, "still refused", "")
    if not charted(recorded):
        return Verdict(name, "answers now", "a mode it used to refuse returns charts")
    report = parity.diff_fixture(name, fresh)
    if report.error:
        return Verdict(name, "drift", report.error)
    ours, theirs = parity.solver_check_fixture(fresh)
    detail = f"rel {report.relative:.4%} worst {report.worst:,.0f} first@m{report.first_month}"
    if ours != theirs:
        return Verdict(name, "drift", f"{detail}; solver ours m{ours} reference m{theirs}")
    if report.relative >= THRESHOLD:
        return Verdict(name, "drift", detail)
    return Verdict(name, "ok", detail)


def main() -> int:
    """Run the canaries and return the process exit code."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="", help="only canaries starting with this prefix")
    parser.add_argument("--out", type=Path, help="directory to keep the fresh answers in")
    parser.add_argument("--sleep", type=float, default=3.0, help="seconds between probes")
    parser.add_argument("--dry", action="store_true",
                        help="no network: judge each recorded answer as if it were fresh")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    names = [n for n in CANARIES if n.startswith(args.only)]
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
    session = None if args.dry else zeke.Session().load()
    verdicts = []
    for name in names:
        recorded = parity.load(name)
        try:
            if session is None:
                fresh = recorded
            else:
                time.sleep(args.sleep)
                fresh = lab.probe(session, name, recorded["overrides"], "canary")
        except Exception as exc:  # noqa: BLE001 — one failed probe must not hide the rest
            verdicts.append(Verdict(name, "failed", f"{type(exc).__name__}: {exc}"))
            print(f"{name:20s} failed  {exc}", flush=True)
            continue
        if args.out:
            body = json.dumps(fresh, ensure_ascii=False, separators=(",", ":"))
            (args.out / f"{name}.json.gz").write_bytes(gzip.compress(body.encode("utf-8")))
        verdict = judge(name, recorded, fresh)
        verdicts.append(verdict)
        print(f"{name:20s} {verdict.status:13s} {verdict.detail}  ({CANARIES[name]})",
              flush=True)
        if len(verdicts) >= 3 and all(v.status == "site error" for v in verdicts[-3:]):
            print("three site errors in a row — the reference is failing; stopping", flush=True)
            break

    broken = [v for v in verdicts if not v.ok]
    print(f"\n{len(verdicts) - len(broken)}/{len(verdicts)} canaries agree")
    for verdict in broken:
        print(f"  {verdict.status}: {verdict.name} — {CANARIES[verdict.name]}")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
