"""One-off rows and loans in a couple's bridge.

`couple9` showed rows enter the bridge as they stand at its horizon — a row
that has ended by then is ignored, one that has started counts throughout —
but a one-off 100,000 reads as ~25,800 a month, whatever its date. This sweeps
the one-off's size and sign, and adds loans that end before and after the
horizon, on the same two-men household.
"""
from experiments.couple9 import household, month
from scenario import flow, loan

SCENARIOS = {}
for amount in (10_000, 30_000, 300_000):
    SCENARIOS[f"cp10_oneoff_{amount // 1000}k"] = household(
        [flow(amount, start="one_time", start_date=month(100))])
for amount in (1_000, 3_000):
    SCENARIOS[f"cp10_oneinc_{amount // 1000}k"] = household(
        [flow(3_000)], [flow(amount, start="one_time", start_date=month(100))])
SCENARIOS["cp10_oneoff_to320"] = household(
    [flow(100_000, start="one_time", start_date=month(100), end="to_date", end_date=month(320))])

for kind in ("spitzer", "baloon", "grace"):
    for years in (20, 50):
        SCENARIOS[f"cp10_loan_{kind}_{years}"] = household(
            [], loans=[loan(500_000, years, interest=4.0, kind=kind, start_date=month(0))])
