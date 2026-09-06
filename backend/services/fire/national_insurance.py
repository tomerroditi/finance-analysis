"""Bituach Leumi old-age pension, as the reference models it.

The reference does **not** derive this from contributions, salary or work
history — it is a flat constant. Probed against gender, date of birth, income
up to 40k and `work_start_year`: nothing moves it (notes/05). Each person in
the plan receives the full amount, and one thing does move it — a spouse
increment, while one partner is eligible and the other is not yet (notes/15).
"""

from __future__ import annotations

from backend.services.fire.models import Gender, Person

BASE_MONTHLY = 2757.0
"""Flat old-age pension. Hard-coded in the reference; not means- or
contribution-tested."""

AGE_80_MONTHLY = 2911.5
"""Stepped-up amount from the month after the 80th birthday."""

STATUTORY_AGE = {Gender.MALE: 67, Gender.FEMALE: 65}
"""Claim age. Note the reference uses a flat 65 for women; Israeli law is
actually phasing the female age from 62 up to 65 by cohort, so this is a
simplification of the reference's own, not of ours."""

STEP_UP_AGE = 80

SPOUSE_INCREMENT = 1386.0
"""Paid on top while the claimant's spouse has not reached their *own* claim age.

The Israeli תוספת עבור בן/בת זוג, measured as 4,143.0 - 2,757.0 in
`pf_mukeret_ref`: the wife there claims at 65 and the husband only at 67, and
she draws 4,143.0 for exactly those 24 months, then 2,757.0 from his 67th
birthday on. The reference does not means-test it — he is drawing a 24k pension
throughout that window and it is paid in full (notes/15).
"""


def monthly_amount(person: Person, age: float, spouse: Person | None = None,
                   spouse_age: float | None = None) -> float:
    """Old-age pension at `age`. Paid from the month *after* the birthday."""
    if age <= STATUTORY_AGE[person.gender]:
        return 0.0
    amount = AGE_80_MONTHLY if age > STEP_UP_AGE else BASE_MONTHLY
    if (spouse is not None and spouse_age is not None
            and spouse_age <= STATUTORY_AGE[spouse.gender]):
        amount += SPOUSE_INCREMENT
    return amount
