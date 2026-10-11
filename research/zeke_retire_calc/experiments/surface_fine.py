"""The decumulation surface at monthly resolution.

A pinned retirement age is always a whole year, so `surface` can only reach
whole-year bridges. Fractional ones come from the reference's post-60 rule
(bridge.py): a man retiring at 61 with the default tactic reads the surface at
`(67 - 61) years + (months from today to his 60th birthday) + 1 month`, so
moving his birth date one month moves the bridge one month — with the same
idle-portfolio design, and the same ~1e-9 precision.

The whole-year points double as a cross-check: they must agree with the
`surface` cells measured the ordinary, pre-60 way.
"""
from scenario import flow, form, pension, portfolio

TODAY_MONTHS = 2026 * 12 + 8  # September 2026, months since year 0 (Jan = 0)
RETIRE = 61


def dob_for(bridge_months: int) -> str:
    """Birth date that makes a man retiring at 61 read `bridge_months`."""
    age_now = 12 * (67 - RETIRE) + 60 * 12 + 1 - bridge_months
    born = TODAY_MONTHS - age_now
    return f"{born // 12}-{born % 12 + 1:02d}-01"


def cell(rule: int, bridge_months: int) -> dict:
    return form(retire_at=RETIRE, base_problem_max_age=70, retireRule=rule,
                dateOfBirth=dob_for(bridge_months), balance=20_000_000,
                incomes=[flow(10_000, "now", "fire")], expenses=[flow(5_000)],
                portfolios=[portfolio(1_000_000_000, interest=20.0, fee=0.0)],
                pension=pension(0))


SCENARIOS = {f"sff_r85_m{months}": cell(85, months) for months in range(84, 553)
             if months % 12 or months % 60 == 0}
"""Rule 85, the default, at every month from 7 to 46 years."""

KNEE = range(84, 277)
"""Past 23 years the surface is smooth enough that whole years reproduce every
month to 2e-5 (checked on rule 85); below it, it is not — the other levels are
measured monthly only there."""

SCENARIOS.update({f"sff_r{rule}_m{months}": cell(rule, months)
                  for rule in (80, 90, 95, 100) for months in KNEE if months % 12})
