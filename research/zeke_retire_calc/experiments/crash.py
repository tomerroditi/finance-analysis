"""Inputs chosen to make the reference raise inside the code we cannot see.

A crash comes back with the Python traceback — every frame's source line — so
an exception inside the bridge or surface code shows how it is computed. Kept
to a handful: each one files an error on someone else's server.
"""
from scenario import flow, form, pension, portfolio

BASE = dict(retire_at=45, base_problem_max_age=60,
            portfolios=[portfolio(1_200_000, description="W1")])

SCENARIOS = {
    "crash_zero_spend": form(expenses=[flow(0)],
                             pension=pension(600_000, tactic="60", frozen=True), **BASE),
    "crash_net_zero": form(expenses=[flow(1_000)],
                           incomes=[flow(10_000, "now", "fire"), flow(1_000)],
                           pension=pension(600_000, tactic="60", frozen=True), **BASE),
    "crash_rule_1000": form(retireRule=1000, pension=pension(600_000, tactic="60", frozen=True),
                            **BASE),
    "crash_rule_frac": form(retireRule="85.5",
                            pension=pension(600_000, tactic="60", frozen=True), **BASE),
}
