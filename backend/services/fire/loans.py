"""Loan amortization.

The reference uses a **nominal** monthly rate (`annual / 12`) for loans, unlike
portfolios, which compound geometrically. Payments run in months
`start + 1 … start + 12 * years` — there is no payment in the start month.
Verified against `fixtures/cf_loan_*`.
"""

from __future__ import annotations

from backend.services.fire.models import Loan, LoanType


def monthly_rate(loan: Loan) -> float:
    return loan.annual_interest_pct / 100 / 12


def term_months(loan: Loan) -> int:
    return int(round(loan.term_years * 12))


def spitzer_payment(loan: Loan) -> float:
    """Level payment for an equal-instalment (Spitzer) loan."""
    r, n = monthly_rate(loan), term_months(loan)
    if n <= 0:
        return 0.0
    if r == 0:
        return loan.initial_sum / n
    return loan.initial_sum * r / (1 - (1 + r) ** -n)


def payment_at(loan: Loan, elapsed: int) -> float:
    """Payment due `elapsed` months after the loan's start month.

    `elapsed` is 1-based: the first payment falls one month after the start.
    """
    n = term_months(loan)
    if elapsed < 1 or elapsed > n:
        return 0.0
    r = monthly_rate(loan)
    if loan.kind == LoanType.SPITZER:
        return spitzer_payment(loan)
    if loan.kind == LoanType.GRACE:
        interest = loan.initial_sum * r
        return interest + loan.initial_sum if elapsed == n else interest
    return loan.initial_sum * (1 + r) ** n if elapsed == n else 0.0


def balance_at(loan: Loan, elapsed: int) -> float:
    """Outstanding principal `elapsed` months after the start month."""
    n, r = term_months(loan), monthly_rate(loan)
    if elapsed < 0:
        return 0.0
    if elapsed >= n:
        return 0.0
    if loan.kind == LoanType.BALOON:
        return loan.initial_sum * (1 + r) ** elapsed
    if loan.kind == LoanType.GRACE:
        return loan.initial_sum
    payment = spitzer_payment(loan)
    if r == 0:
        return max(loan.initial_sum - payment * elapsed, 0.0)
    growth = (1 + r) ** elapsed
    return loan.initial_sum * growth - payment * (growth - 1) / r
