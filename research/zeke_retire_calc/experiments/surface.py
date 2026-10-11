"""The decumulation surface, measured directly and densely.

An idle withdrawal portfolio of 1e9 with no fee and a 20% return (so the
`min(table, user return)` cap never binds), a 20M cash pile that funds every
month of spending, no pension, and a pinned retirement age. The portfolio is
never touched, so its post-retirement growth *is* the surface value, and at
1e9 printed to one decimal the whole decumulation span pins it to ~1e-9.

With no pension the bridge is the plain wait to the statutory age, so a man
retiring at `67 - N` reads the surface at N. `wanted_retire_age` must be a
whole number (the reference refuses `45.5` outright) and the last working month
is the one at exactly that age, so a pinned retirement only ever reads whole
bridges. Those are exactly the cells a pinned plan needs; fractional bridges
come only from `retire_asap` runs. Three birth years cover the range: the
search cannot start before next month.
"""
from datetime import date

from scenario import flow, form, pension, portfolio

TODAY = date(2026, 9, 1)


def age_now(dob: date) -> float:
    return ((TODAY.year - dob.year) * 12 + TODAY.month - dob.month) / 12


def cell(rule: int, bridge: float, gender: str = "male", statutory: int = 67) -> dict:
    retire = statutory - bridge
    dob = next(d for d in (date(1990, 1, 1), date(2000, 1, 1), date(2005, 1, 1))
               if retire >= age_now(d) + 1 / 12)
    return form(retire_at=round(retire, 6), base_problem_max_age=70, retireRule=rule,
                dateOfBirth=dob.isoformat(), gender=gender, balance=20_000_000,
                incomes=[flow(10_000, "now", "fire")], expenses=[flow(5_000)],
                portfolios=[portfolio(1_000_000_000, interest=20.0, fee=0.0)],
                pension=pension(0))


SCENARIOS = {f"sf_r{rule}_n{bridge * 12}": cell(rule, bridge)
             for rule in (80, 85, 90, 95, 100) for bridge in range(7, 46)}
SCENARIOS.update({f"sf_r{rule}_n{bridge * 12}": cell(rule, bridge)
                  for rule in (82, 87) for bridge in (15, 22, 30)})
