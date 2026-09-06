#!/usr/bin/env python3
"""Map the reference's decumulation-return table.

Design: a large cash pile funds all living costs, so the withdrawal portfolio is
never drawn and its post-retirement growth *is* the confidence-derived return.
Retirement age is pinned, so confidence and horizon are the only free variables.
"""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import probe, zeke

RULES = [80, 85, 90, 95, 100]
AGES = [40, 45, 50, 55, 58, 62]
FEE = 0.1


def scenario(rule, age):
    return probe.scenario(
        base_problem="retire_at_age", wanted_retire_age=age, base_problem_max_age=70,
        retireRule=rule, balance=20_000_000, cashBuffer=0,
        portfolioBalance1=100_000, portfolio_goal1=0,
        portfolioDesignation1="withdraw", portfolio_type1="portfolio",
        portfolioInterest1=5.0, portfolioFee1=FEE, portfolioProfitFraction1=0,
        incomeSum1=10_000, expenseSum1=5_000,
    )


def decumulation_return(rec):
    charts = rec["charts"]
    if not charts.get("asset_plot"):
        return None, None
    ages = charts["asset_plot"]["labels"][1:-1]
    series = next((d["data"][1:-1] for d in charts["asset_plot"]["datasets"]
                   if "עובר" not in d["label"]), None)
    work = next((d["data"][1:-1] for d in charts["income_plot"]["datasets"]
                 if d["label"] == "עבודה"), None)
    if series is None or work is None:
        return None, None
    retire = next((i for i in range(1, len(work)) if work[i] == 0 and work[i - 1] > 0), None)
    if retire is None or retire + 30 >= len(series) or series[retire + 5] <= 0:
        return None, None
    ratios = [series[i] / series[i - 1] for i in range(retire + 6, retire + 26)]
    factor = sum(ratios) / len(ratios)
    return 100 * ((factor ** 12) / (1 - FEE / 100) - 1), ages[retire]


if __name__ == "__main__":
    session = zeke.Session().load()
    table = {}
    for rule in RULES:
        for age in AGES:
            rec, session = probe.run(f"tri_r{rule}_a{age}", scenario(rule, age),
                                     session=session, sleep=8)
            rate, fire_age = decumulation_return(rec)
            if rate is None:
                print(f"  rule {rule} age {age}: no usable series", flush=True)
                continue
            bridge = round(67 - fire_age, 2)
            table.setdefault(str(rule), {})[str(bridge)] = round(rate, 4)
            print(f"  rule {rule:3} FIRE {fire_age:5.2f} bridge {bridge:5.2f}y -> {rate:7.4f}%",
                  flush=True)
    (Path(__file__).parent / "trinity_table.json").write_text(
        json.dumps(table, indent=1, sort_keys=True))
    print("\nwrote trinity_table.json")
