"""
Loan type constants for liability tracking.

Israeli loans vary along two orthogonal dimensions:

- **Rate behavior** (:class:`LoanType`): how the annual interest rate
  evolves over the life of the loan.
- **Amortization method** (:class:`AmortizationMethod`): how each payment
  splits between principal and interest.
"""

from enum import Enum


class LoanType(Enum):
    """Rate behavior of a loan.

    Attributes
    ----------
    FIXED_UNLINKED : str
        Fixed annual rate for the whole term (קבוע לא צמוד).
    PRIME_LINKED : str
        Rate tracks the Israeli prime rate (Bank of Israel key rate
        + 1.5%) plus a per-loan spread (צמוד פריים). The spread is
        stored in ``liabilities.rate_spread`` and may be negative
        (e.g. "prime − 0.5").
    VARIABLE_UNLINKED : str
        Rate resets every ``rate_reset_months`` months to the prime
        rate at the reset date plus ``rate_spread``; constant between
        resets (משתנה לא צמודה).
    """

    FIXED_UNLINKED = "fixed_unlinked"
    PRIME_LINKED = "prime_linked"
    VARIABLE_UNLINKED = "variable_unlinked"


class AmortizationMethod(Enum):
    """Payment structure of a loan.

    Attributes
    ----------
    SHPITZER : str
        Standard annuity — constant payment per rate period (שפיצר).
    EQUAL_PRINCIPAL : str
        Constant principal portion, declining interest (קרן שווה).
    BALLOON : str
        Interest-only payments; the full principal is repaid together
        with the final payment (בלון).
    """

    SHPITZER = "shpitzer"
    EQUAL_PRINCIPAL = "equal_principal"
    BALLOON = "balloon"


# Everyday Israeli "prime" is the BoI key rate plus a constant 1.5%.
PRIME_SPREAD_PCT = 1.5

BOI_RATE_SERIES = "boi_rate"
PRIME_SERIES = "prime"

# Loan types whose effective rate derives from the prime rate series.
PRIME_BASED_LOAN_TYPES = {LoanType.PRIME_LINKED.value, LoanType.VARIABLE_UNLINKED.value}
