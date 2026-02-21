from enum import Enum


PRIOR_WEALTH_TAG = "Prior Wealth"
CREDIT_CARDS = "Credit Cards"
IGNORE_CATEGORY = "Ignore"
IVESTMENTS_CATEGORY = "Investments"
LIABILITIES_CATEGORY = "Liabilities"

PROTECTED_TAGS = [PRIOR_WEALTH_TAG]
PROTECTED_CATEGORIES = [
    CREDIT_CARDS,
    "Salary",
    "Other Income",
    "Investments",
    "Ignore",
    "Liabilities",
]


class IncomeCategories(Enum):
    """
    Enum defining categories that are considered income.
    """

    SALARY = "Salary"
    OTHER_INCOME = "Other Income"
