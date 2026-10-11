"""Loans that did not start this month.

The recorded loan runs all start now or later, and they match. `cx1_020`'s
balloon loan started in 2019 and our liability is three times what the
reference's net worth implies. Each type, started in the past, now and in the
future, in a plan with nothing else moving (no pension, a big idle cash pile
so nothing is ever drawn, pinned retirement).
"""
from scenario import flow, form, loan, pension, portfolio

STARTS = {"past": "2019-10-01", "now": "2026-09-01", "future": "2030-01-01"}

SCENARIOS = {
    f"ln_{kind}_{when}": form(retire_at=50, balance=5_000_000,
                              expenses=[flow(5_000)], portfolios=[portfolio(100_000)],
                              pension=pension(0),
                              loans=[loan(400_000, 20, 5.5, kind, start)])
    for kind in ("baloon", "grace", "spitzer") for when, start in STARTS.items()
}
