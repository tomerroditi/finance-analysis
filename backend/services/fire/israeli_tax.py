"""Israeli income tax, as the reference applies it.

The reference is pinned to a 2025 bracket table and a fixed 2.25 credit points.
Both were recovered by fitting its own output and match to the agora:

* a 26,735.9/month pension is taxed 5,255.0 — exactly what these brackets minus
  the credit give (notes/05);
* a 6,072.7/month capital gain at age 60.08 is taxed 62.8 — likewise
  (notes/11).
"""

from __future__ import annotations

ANNUAL_BRACKETS: list[tuple[float, float]] = [
    (84_120, 0.10),
    (120_720, 0.14),
    (193_800, 0.20),
    (269_280, 0.31),
    (560_280, 0.35),
    (float("inf"), 0.47),
]

CREDIT_POINTS = 2.25
CREDIT_POINT_MONTHLY_VALUE = 242.0
MONTHLY_CREDIT = CREDIT_POINTS * CREDIT_POINT_MONTHLY_VALUE

CAPITAL_GAINS_FLAT_RATE = 0.25
"""Flat CGT rate, and the ceiling on the marginal-rate treatment after 60."""

MARGINAL_TREATMENT_AGE = 60.0
"""From this age the reference stops applying the flat rate and taxes gains as
ordinary income instead — usually a *reduction*, and zero for modest
withdrawals, which is why it can look like an exemption."""

STATUTORY_AGE_MONTHLY_EXEMPTION = 6_110.0
"""Additional monthly exemption from the statutory pension age (notes/05)."""


def annual_tax(annual_income: float) -> float:
    """Bracket tax on an annual income, before credit points."""
    tax = 0.0
    previous = 0.0
    for ceiling, rate in ANNUAL_BRACKETS:
        if annual_income <= previous:
            break
        tax += (min(annual_income, ceiling) - previous) * rate
        previous = ceiling
    return tax


def monthly_income_tax(monthly_income: float, exemption: float = 0.0) -> float:
    """Monthly income tax, after an exemption and the credit points."""
    taxable = max(monthly_income - exemption, 0.0)
    return max(annual_tax(taxable * 12) / 12 - MONTHLY_CREDIT, 0.0)


def capital_gains_tax(gain: float, age: float, statutory_age: int) -> float:
    """Tax on a realised monthly capital gain.

    Below 60 the flat 25% applies. From 60 the gain is taxed as ordinary
    income instead, capped at the flat rate — and from the statutory pension
    age an extra monthly exemption applies on top.
    """
    if gain <= 0:
        return 0.0
    flat = CAPITAL_GAINS_FLAT_RATE * gain
    if age <= MARGINAL_TREATMENT_AGE:
        return flat
    exemption = STATUTORY_AGE_MONTHLY_EXEMPTION if age > statutory_age else 0.0
    return min(flat, monthly_income_tax(gain, exemption))
