from enum import Enum


PRIOR_WEALTH_TAG = "Prior Wealth"
CREDIT_CARDS = "Credit Cards"
IGNORE_CATEGORY = "Ignore"

PROTECTED_TAGS = [PRIOR_WEALTH_TAG]
PROTECTED_CATEGORIES = [
    CREDIT_CARDS,
    "Salary",
    "Other Income",
    "Investments",
    "Ignore",
    "Liabilities",
]


class InvestmentCategories(Enum):
    """
    Enum defining categories that are considered savings and investments.
    """

    INVESTMENTS = "Investments"


class IncomeCategories(Enum):
    """
    Enum defining categories that are considered income.
    """

    SALARY = "Salary"
    OTHER_INCOME = "Other Income"


class LiabilitiesCategories(Enum):
    """Enum defining categories that represent liabilities or debt payments."""

    LIABILITIES = "Liabilities"


class NonExpensesCategories(Enum):
    """
    Enum defining categories that are not considered expenses.

    These categories are used to classify transactions that should not be counted
    as expenses in financial analysis.

    Attributes
    ----------
    SALARY : str
        Income from employment.
    INVESTMENTS : str
        Money allocated to investments.
    OTHER_INCOME : str
        Income from sources other than salary.
    LIABILITIES : str
        Payments related to liabilities.
    """

    INVESTMENTS = InvestmentCategories.INVESTMENTS.value
    SALARY = IncomeCategories.SALARY.value
    OTHER_INCOME = IncomeCategories.OTHER_INCOME.value
    LIABILITIES = LiabilitiesCategories.LIABILITIES.value
