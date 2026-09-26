"""Random plans that use many features at once — the acceptance test.

Every other family isolates one rule. This one does the opposite: each plan
draws a realistic household from a seeded generator — a couple half the time,
several portfolios of mixed types and designations, study funds, a mortgage,
real estate, one-off income and spending, rising costs, a pension with any
claim tactic — and asks whether the rules still compose. A plan is judged by
the corpus differ like any other fixture; the bar is 0.1% of peak net worth.

The generator is deterministic per seed, so `cx_<seed>` always names the same
plan. Add seeds; never change what an existing seed draws (bump `VERSION` and
the name prefix instead).
"""
from __future__ import annotations

import random

from scenario import flow, form, keren, loan, pension, portfolio, realestate

VERSION = 1


def _date(rng: random.Random, year_low: int, year_high: int) -> str:
    return f"{rng.randint(year_low, year_high)}-{rng.randint(1, 12):02d}-01"


def plan(seed: int) -> dict:
    """One random household."""
    rng = random.Random(f"combos-v{VERSION}-{seed}")
    born = rng.randint(1968, 1998)
    couple = rng.random() < 0.5
    gender = rng.choice(["male", "female"])

    salary = rng.randrange(8_000, 45_000, 500)
    incomes = [flow(salary, "now", "fire", rise=rng.choice([0.0, 0.0, 1.0, 2.0]),
                    description="Salary")]
    if rng.random() < 0.4:
        incomes.append(flow(rng.randrange(1_000, 8_000, 250), "now", "to_date",
                            end_date=_date(rng, 2030, 2045), description="Side"))
    if rng.random() < 0.3:
        incomes.append(flow(rng.randrange(50_000, 600_000, 10_000), "one_time",
                            start_date=_date(rng, 2027, 2040), description="Windfall"))
    if rng.random() < 0.25:
        incomes.append(flow(rng.randrange(1_500, 6_000, 250), "now", "forever",
                            description="Rent"))

    living = rng.randrange(6_000, min(salary, 30_000) + 1_000, 500)
    expenses = [flow(living, "now", "forever", rise=rng.choice([0.0, 0.0, 0.5, 1.0]),
                     description="Living")]
    if rng.random() < 0.4:
        expenses.append(flow(rng.randrange(1_000, 5_000, 250), "now", "to_date",
                             end_date=_date(rng, 2030, 2045), description="Kids"))
    if rng.random() < 0.3:
        expenses.append(flow(rng.randrange(40_000, 300_000, 10_000), "one_time",
                             start_date=_date(rng, 2027, 2045), description="Car"))
    if rng.random() < 0.3:
        expenses.append(flow(rng.randrange(500, 4_000, 250), "fire", "forever",
                             description="Travel"))

    portfolios = [portfolio(rng.randrange(0, 2_000_000, 10_000), "withdraw",
                            rng.choice(["portfolio", "ibkr", "kaspit"]),
                            interest=rng.choice([4.0, 5.0, 6.0, 7.0]),
                            fee=rng.choice([0.05, 0.1, 0.25, 0.5]),
                            profit_pct=rng.randrange(0, 80, 5),
                            lots=rng.choice(["flat", "flat", "fifo", "lifo"]),
                            description="Main")]
    for index in range(rng.randint(0, 3)):
        kind = rng.choice(["portfolio", "ibkr", "gemel", "polisa", "kaspit", "pikadon"])
        designation = rng.choice(["withdraw", "goal"]
                                 + (["mukeret_main"] if kind in ("gemel", "polisa") else []))
        portfolios.append(portfolio(
            rng.randrange(0, 1_000_000, 10_000), designation, kind,
            deposit_cap=rng.choice(["", "", 1_000, 3_000]),
            goal=rng.choice([0, 0, 200_000, 500_000]) if designation == "goal" else 0,
            interest=rng.choice([3.0, 4.0, 5.0, 6.0]), fee=rng.choice([0.1, 0.3, 0.7]),
            profit_pct=rng.randrange(0, 60, 5), description=f"P{index + 2}"))

    kranot = [keren(rng.randrange(0, 400_000, 10_000), rng.choice([0, 1_000, 1_500, 2_000]),
                    fee=rng.choice([0.6, 0.8]), kind=rng.choice(["maslulit", "ira"]))
              for _ in range(rng.randint(0, 2))]
    loans = []
    if rng.random() < 0.4:
        loans.append(loan(rng.randrange(200_000, 1_500_000, 50_000), rng.choice([15, 20, 25, 30]),
                          interest=rng.choice([3.0, 4.5, 5.5]),
                          kind=rng.choice(["spitzer", "spitzer", "baloon", "grace"]),
                          start_date=_date(rng, 2018, 2026)))
    realestates = ([realestate(rng.randrange(1_000_000, 4_000_000, 100_000),
                               rng.choice([0.0, 1.0, 2.0]))]
                   if rng.random() < 0.3 else [])

    def a_pension() -> dict:
        severance = rng.random() < 0.2
        return pension(rng.randrange(0, 2_000_000, 10_000), rng.randrange(0, 6_000, 100),
                       interest=rng.choice([4.0, 5.0, 6.0, 7.0]),
                       tactic=rng.choice(["60", "67", "60-67"]),
                       mukeret_pct=rng.choice([20, 30, 40, 50]),
                       withdraw_severance=severance,
                       work_start_year=rng.randint(2000, 2020) if severance else "")

    retire_at = None
    fields: dict = {}
    if rng.random() < 0.4:
        age_now = 2026 - born
        retire_at = rng.randint(min(age_now + 1, 60), 60)
    fields.update(dateOfBirth=f"{born}-{rng.randint(1, 12):02d}-01", gender=gender,
                  retireRule=rng.choice([80, 85, 90, 95, 100]),
                  balance=rng.randrange(0, 400_000, 5_000),
                  cashBuffer=rng.choice([0, 0, 20_000, 50_000]),
                  creditLimit=rng.choice([0, 0, 20_000]),
                  prati_hishtalmut_order=rng.choice(["prati", "hishtalmut"]))
    partner = None
    if couple:
        partner = {"dateOfBirth": f"{born + rng.randint(-4, 4)}-{rng.randint(1, 12):02d}-01",
                   "gender": "female" if gender == "male" else "male"}
    return form(incomes=incomes, expenses=expenses, portfolios=portfolios, kranot=kranot,
                loans=loans, realestates=realestates, pension=a_pension(),
                partner=partner, partner_pension=a_pension() if couple else None,
                retire_at=retire_at, **fields)


SCENARIOS = {f"cx{VERSION}_{seed:03d}": plan(seed) for seed in range(40)}
