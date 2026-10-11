"""Does a pension-free couple's bridge depend on the spending?

`couple5` found the bridge a fixed blend of the two statutory months (weight
0.5203 on the later for gaps under 84 months, another line beyond) — all at
5,000 a month of spending. If what the older spouse's Bituach Leumi (with the
dependent-spouse increment) covers is what shortens the bridge, the blend
moves with the spending; if it is a fixed rule of ages, it does not.
"""
from experiments.couple4 import EMPTY
from scenario import flow, form, portfolio


def pair(partner_dob: str, spend: int) -> dict:
    return form(base_problem_max_age=60, expenses=[flow(spend)],
                portfolios=[portfolio(3_000_000, description="W1")], pension=EMPTY,
                partner={"dateOfBirth": partner_dob, "gender": "male"},
                partner_pension=EMPTY)


SCENARIOS = {f"cp6_g{gap}_e{spend // 1000}k": pair(dob, spend)
             for gap, dob in ((36, "1987-01-01"), (108, "1981-01-01"))
             for spend in (3_000, 5_000, 10_000, 20_000)}
