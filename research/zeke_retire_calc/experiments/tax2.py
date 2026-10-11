"""The statutory-age exemption against capital gains, with and without a pension.

`cx2_035` (single, entitling annuity 1,621.5) has the exemption left over after
its own annuity shield its gains; `cx2_010` (a couple, the main person's
annuity 1,816, the wife's taxable annuity stacked under the gain) has the
exemption cover the annuity and nothing more. This separates "single or
couple" from "stacked income or none": a man turning 67 in 2030 with a pension
that pays an entitling annuity from 67, alone, beside a wife whose own taxable
pension starts at 65 in 2027, beside a wife with none, and with his own pension
emptied instead. One flat-basis portfolio carries the spending throughout.
"""
from scenario import flow, form, pension, portfolio

MAN = {"dateOfBirth": "1963-01-01", "gender": "male"}
WIFE = {"dateOfBirth": "1962-01-01", "gender": "female"}


def plan(main_pension: int, wife: bool, wife_pension: int = 0) -> dict:
    extra = ({"partner": WIFE, "partner_pension": pension(wife_pension, tactic="67",
                                                          mukeret_pct=20, frozen=True)}
             if wife else {})
    return form(base_problem_max_age=66, incomes=[flow(10_000, "now", "fire")],
                expenses=[flow(25_000)],
                portfolios=[portfolio(9_000_000, interest=5.0, fee=0.0, profit_pct=60,
                                      description="W1")],
                pension=pension(main_pension, tactic="67", mukeret_pct=20, frozen=True),
                **MAN, **extra)


SCENARIOS = {
    "tx2_single": plan(1_500_000, wife=False),
    "tx2_couple_stack": plan(1_500_000, wife=True, wife_pension=2_000_000),
    "tx2_couple_nostack": plan(1_500_000, wife=True),
    "tx2_couple_mainnone": plan(0, wife=True, wife_pension=2_000_000),
}
