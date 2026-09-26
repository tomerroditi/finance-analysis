"""Couples with no pension at all: how the two statutory waits combine.

With nothing claimed at 60 a single person waits for the statutory age. A
couple reads a horizon between the two people's waits — weight 0.5496 on the
man's when the partner (a woman) is his age or five years older, 0.4797 when
she is five years younger. These map that weight.
"""
from experiments.couple import couple
from scenario import form, pension, portfolio, flow

SCENARIOS = {f"cp3_f{dob[:4]}": couple(partner_dob=dob)
             for dob in ("1980-01-01", "1988-01-01", "1992-01-01", "2000-01-01")}
SCENARIOS.update({f"cp3_m{dob[:4]}": couple(partner_dob=dob, partner_gender="male")
                  for dob in ("1985-01-01", "1995-01-01")})
SCENARIOS["cp3_mainfemale_1990"] = form(
    base_problem_max_age=60, gender="female", expenses=[flow(5_000)],
    portfolios=[portfolio(1_200_000, description="W1")],
    pension=pension(0, tactic="60-67", frozen=True),
    partner={"dateOfBirth": "1990-01-01", "gender": "male"},
    partner_pension=pension(0, tactic="60-67", frozen=True))
