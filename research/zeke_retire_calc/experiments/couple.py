"""How a couple's pensions enter the bridge.

The single-person rule (bridge.py) is `x = (pension started at 60, valued at
retirement) / spending`, on a window anchored at the main person's 60th
birthday. `pf_mukeret4_order` — a couple — reads a bridge that rule cannot
give. With frozen pensions, one thing moves at a time: whose pension exists,
the partner's age and gender, and the tactic.

These use `retire_asap`: a couple with `retire_at_age` crashes the reference
(`get_summary_text` raises `KeyError: 'age'` — it returned the traceback), so
there is no pinned couple to probe.
"""
from scenario import flow, form, pension, portfolio

EMPTY = pension(0, tactic="60-67", frozen=True)


def couple(main=EMPTY, partner_pension=EMPTY, partner_dob="1990-01-01",
           partner_gender="female") -> dict:
    return form(base_problem_max_age=60,
                expenses=[flow(5_000)], portfolios=[portfolio(1_200_000, description="W1")],
                pension=main, partner={"dateOfBirth": partner_dob, "gender": partner_gender},
                partner_pension=partner_pension)


FUND = pension(1_200_000, tactic="60-67", frozen=True)
SCENARIOS = {
    "cp_main_only": couple(main=FUND),
    "cp_partner_only": couple(partner_pension=FUND),
    "cp_both": couple(main=FUND, partner_pension=FUND),
    "cp_partner_older": couple(partner_pension=FUND, partner_dob="1985-01-01"),
    "cp_partner_younger": couple(partner_pension=FUND, partner_dob="1995-01-01"),
    "cp_partner_male": couple(partner_pension=FUND, partner_gender="male"),
    "cp_partner_t60": couple(partner_pension=pension(600_000, tactic="60", frozen=True)),
    "cp_main_t67_partner_t60": couple(main=pension(1_200_000, tactic="67", frozen=True),
                                      partner_pension=pension(600_000, tactic="60", frozen=True)),
}
