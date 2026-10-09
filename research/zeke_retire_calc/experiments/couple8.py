"""The same-age couple's bridge past 67, finely: how far it runs by coverage.

`couple7`: two men who turn 67 together end their bridge at 67 while their two
allowances (5,514) cover the spending, and past it otherwise (6,000 -> 7.3
months, 8,000 -> 60 months). A 10M portfolio makes every run retire at once,
so only the spending moves.
"""
from experiments.couple4 import EMPTY
from scenario import flow, form, portfolio

SCENARIOS = {f"cp8_e{spend}": form(
    base_problem_max_age=60, expenses=[flow(spend)],
    portfolios=[portfolio(10_000_000, description="W1")], pension=EMPTY,
    partner={"dateOfBirth": "1990-01-01", "gender": "male"}, partner_pension=EMPTY)
    for spend in (5_520, 5_600, 5_800, 6_500, 7_000, 9_000, 10_000, 12_000, 16_000, 25_000)}
