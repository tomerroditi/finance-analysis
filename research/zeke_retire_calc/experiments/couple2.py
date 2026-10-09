"""Couples, second pass: the main person's pension beside a woman partner.

`couple` showed a partner's own pension reads exactly like a single person's,
on her window, and two pensions add up. What does not fit is the main person's
pension when the partner is a woman: `cp_main_only` ends its bridge at month
334.7, on neither person's window. These sweep that pension's share, and the
partner's age with no pension of her own.
"""
from experiments.couple import EMPTY, couple
from scenario import pension

SCENARIOS = {f"cp2_main_s{share}": couple(main=pension(1_200_000, tactic="60-67",
                                                       mukeret_pct=share, frozen=True))
             for share in (10, 50, 90)}
SCENARIOS.update({f"cp2_empty_{dob[:4]}": couple(partner_dob=dob)
                  for dob in ("1985-01-01", "1990-01-01", "1995-01-01")})
SCENARIOS.update({f"cp2_main_s30_{dob[:4]}": couple(main=pension(1_200_000, tactic="60-67",
                                                                 frozen=True), partner_dob=dob)
                  for dob in ("1985-01-01", "1995-01-01")})
SCENARIOS["cp2_main_s30_male"] = couple(main=pension(1_200_000, tactic="60-67", frozen=True),
                                        partner_pension=EMPTY, partner_gender="male")
