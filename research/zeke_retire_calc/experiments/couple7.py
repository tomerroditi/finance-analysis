"""Same-age couples, pension-free, spending swept — and singles beside them.

`couple6` showed a pension-free couple's bridge moves with spending and can
run past both statutory ages. Two men born the same month reach 67 together:
if the bridge still extends past 67 once their two Bituach Leumi allowances
(2 x 2,757) fall short of the spending, the couple bridge is a coverage test
on the household's income. The singles are the control: their bridge has so
far always ended at the statutory age.
"""
from experiments.couple4 import EMPTY
from scenario import flow, form, portfolio


def household(spend: int, couple: bool) -> dict:
    extra = ({"partner": {"dateOfBirth": "1990-01-01", "gender": "male"},
              "partner_pension": EMPTY} if couple else {})
    return form(base_problem_max_age=60, expenses=[flow(spend)],
                portfolios=[portfolio(3_000_000, description="W1")], pension=EMPTY, **extra)


SCENARIOS = {f"cp7_{'pair' if couple else 'single'}_e{spend // 100}": household(spend, couple)
             for couple in (True, False) for spend in (4_000, 5_500, 6_000, 8_000, 12_000)}
