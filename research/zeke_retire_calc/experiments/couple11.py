"""A severance redemption in a couple's bridge.

`cx1_005` redeems 139,943 of severance at retirement and reads its bridge as if
the main person's statutory-age claim were ~1,217 — between the 1,768 the fund
pays with no redemption and the 1,061 left once the redeemed amount leaves the
entitling side. This isolates it: two men born January 1990, 7,000 of
spending, the main person's 600k pension frozen, redeemed or not, per tactic.
"""
from experiments.couple4 import EMPTY
from scenario import flow, form, pension, portfolio

SCENARIOS = {}
for tactic in ("60-67", "60", "67"):
    for redeem in (False, True):
        SCENARIOS[f"cp11_{tactic.replace('-', '')}_{'sev' if redeem else 'keep'}"] = form(
            base_problem_max_age=60, expenses=[flow(7_000)],
            portfolios=[portfolio(3_000_000, description="W1")],
            pension=pension(600_000, tactic=tactic, mukeret_pct=40, frozen=True,
                            withdraw_severance=redeem, work_start_year=2013),
            partner={"dateOfBirth": "1990-01-01", "gender": "male"}, partner_pension=EMPTY)

for tactic in ("60-67", "67"):
    for redeem in (False, True):
        SCENARIOS[f"cp11_{tactic.replace('-', '')}_{'sev' if redeem else 'keep'}_e12"] = form(
            base_problem_max_age=60, expenses=[flow(12_000)],
            portfolios=[portfolio(3_000_000, description="W1")],
            pension=pension(600_000, tactic=tactic, mukeret_pct=40, frozen=True,
                            withdraw_severance=redeem, work_start_year=2013),
            partner={"dateOfBirth": "1990-01-01", "gender": "male"}, partner_pension=EMPTY)
