"""Bituach Leumi old-age pension, as the reference models it.

The reference does **not** derive this from contributions, salary or work
history — it is a flat constant. Probed against gender, date of birth, income
up to 40k, `work_start_year` and partner presence: nothing moves it
(notes/05). Each person in the plan receives the full amount.
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


def monthly_amount(person: Person, age: float) -> float:
    """Old-age pension at `age`. Paid from the month *after* the birthday."""
    if age <= STATUTORY_AGE[person.gender]:
        return 0.0
    return AGE_80_MONTHLY if age > STEP_UP_AGE else BASE_MONTHLY
