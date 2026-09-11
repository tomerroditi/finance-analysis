#!/usr/bin/env python3
"""Run a named scenario against the reference calculator and record it.

Every probe is saved to fixtures/<name>.json as
{"overrides": {...}, "summary": "<plain text>", "charts": {...}, "meta": {...}}
so the recorded series double as golden fixtures for our own engine.
"""
import argparse, json, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import zeke, extract

FIXTURES = Path(__file__).parent / "fixtures"


def run(name, overrides, session=None, save_html=False, sleep=1.5):
    s = session or zeke.Session().load()
    time.sleep(sleep)
    t0 = time.time()
    res = s.calc(overrides, verbose=False)
    took = time.time() - t0
    h = res.get("results", "")
    rec = {
        "name": name,
        "overrides": overrides,
        "calc_success": res.get("calc_success"),
        "summary": zeke.text(h),
        "charts": extract.charts(h),
        "meta": {"seconds": round(took, 1), "job": res.get("_job"),
                 "messages": zeke.text(res.get("messages_html") or "")},
    }
    if save_html:
        rec["html"] = h
    FIXTURES.mkdir(exist_ok=True)
    (FIXTURES / f"{name}.json").write_text(
        json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    return rec, s


BASE = {
    "dateOfBirth": "1990-01-01", "pensionName": "T", "gender": "male",
    "base_problem": "retire_asap", "base_problem_max_age": "60", "retireRule": "85",
    "balance": "0", "cashBuffer": "0",
    "expenseSum1": "5000", "expenseStartType1": "now", "expenseEndType1": "forever",
    "expenseRise1": "0.0",
    "incomeSum1": "10000", "incomeStartType1": "now", "incomeEndType1": "fire",
    "incomeRise1": "0.0",
    "portfolioDesignation1": "withdraw", "portfolio_type1": "portfolio",
    "portfolioBalance1": "100000", "portfolioInterest1": "5.0", "portfolioFee1": "0.1",
    "portfolioProfitFraction1": "0.0", "portfolio_goal1": "0",
}


def scenario(**kw):
    d = dict(BASE)
    d.update({k: str(v) for k, v in kw.items()})
    return d


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("pairs", nargs="*", help="key=value overrides on top of BASE")
    args = ap.parse_args()
    ov = scenario(**dict(p.split("=", 1) for p in args.pairs))
    rec, _ = run(args.name, ov)
    print(rec["summary"][:1500])
