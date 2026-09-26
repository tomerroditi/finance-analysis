"""Does the post-60 horizon's "months until 60" term come from the claim?

`post60_dob` found N = (statutory - L) + (I60 + 1) for a retirement in
(60, statutory], and N = Is + 1 past the statutory age — every probe with the
default `pension_tactics=60` and an empty pension. If the I60 term is really
the claim month, tactic 67 moves it; if it is a fixed 60, nothing moves.
"""
from scenario import flow, form, pension, portfolio


def cell(age: int, tactic: str, balance: float) -> dict:
    return form(retire_at=age, base_problem_max_age=70, retireRule=90,
                dateOfBirth="1990-01-01", balance=20_000_000,
                incomes=[flow(10_000, "now", "fire")], expenses=[flow(5_000)],
                portfolios=[portfolio(1_000_000_000, interest=20.0, fee=0.0)],
                pension=pension(balance, tactic=tactic, frozen=True))


SCENARIOS = {f"spt_a{age}_t{tactic.replace('-', '')}_{balance // 1000}k": cell(age, tactic, balance)
             for age in (63, 66, 68) for tactic in ("60", "67", "60-67")
             for balance in (0, 600_000)}
