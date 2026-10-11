"""How a row that starts or ends mid-bridge moves a couple's bridge.

The couple bridge weighs phases cut at each spouse's 60 and statutory age by
the running mean of their needs (notes/18 §6). The random households showed
the need also follows the rows: a side income ending, a one-off counted to its
end type. This isolates it on the simplest couple — two men born January
1990, no pensions, 5,000 of spending that their two allowances cover from 67 —
with one extra row whose date is moved before 60 (month 100), inside the
60-67 window (320) and after 67 (420).
"""
from experiments.couple4 import EMPTY
from scenario import flow, form, portfolio

TODAY = (2026, 9)


def month(index: int) -> str:
    total = TODAY[0] * 12 + TODAY[1] - 1 + index
    return f"{total // 12}-{total % 12 + 1:02d}-01"


def household(expenses: list, incomes: list | None = None, base: dict | None = None,
              loans: list | None = None) -> dict:
    return form(loans=loans, base_problem_max_age=60, expenses=[base or flow(5_000), *expenses],
                incomes=[flow(10_000, "now", "fire"), *(incomes or [])], portfolios=[portfolio(3_000_000, description="W1")],
                pension=EMPTY, partner={"dateOfBirth": "1990-01-01", "gender": "male"},
                partner_pension=EMPTY)


SCENARIOS = {}
for at in (100, 320, 420):
    SCENARIOS[f"cp9_xend_{at}"] = household([flow(3_000, end="to_date", end_date=month(at))])
    SCENARIOS[f"cp9_xstart_{at}"] = household([flow(3_000, start="from_date", start_date=month(at))])
    SCENARIOS[f"cp9_iend_{at}"] = household([flow(3_000)], [flow(1_500, end="to_date", end_date=month(at))])
    SCENARIOS[f"cp9_oneoff_{at}"] = household([flow(100_000, start="one_time", start_date=month(at))])
SCENARIOS["cp9_rise_1"] = household([], base=flow(5_000, rise=1.0))
