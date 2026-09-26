"""Two men, no pensions: how a couple combines two statutory waits.

Everything else about a couple builds on this base case, so it is isolated:
same gender (one window length), no pension at 60 on either side, and only the
partner's birth date moving. A same-date pair must read like a single person.
"""
from scenario import flow, form, pension, portfolio

EMPTY = pension(0, tactic="60-67", frozen=True)


def pair(partner_dob: str) -> dict:
    return form(base_problem_max_age=60, expenses=[flow(5_000)],
                portfolios=[portfolio(1_200_000, description="W1")], pension=EMPTY,
                partner={"dateOfBirth": partner_dob, "gender": "male"},
                partner_pension=EMPTY)


SCENARIOS = {f"cp4_{dob[:7].replace('-', '_')}": pair(dob) for dob in (
    "1990-01-01", "1989-07-01", "1988-01-01", "1987-01-01", "1983-01-01", "1978-01-01",
    "1990-07-01", "1992-01-01", "1995-01-01", "2000-01-01")}
