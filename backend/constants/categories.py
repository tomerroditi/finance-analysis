from enum import Enum


PRIOR_WEALTH_TAG = "Prior Wealth"
CREDIT_CARDS = "Credit Cards"
IGNORE_CATEGORY = "Ignore"
INVESTMENTS_CATEGORY = "Investments"
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


# Categories excluded from expense breakdowns / analytics. Combines the
# non-expense base set (Investments, Liabilities, the Credit Cards bank
# bill-payment category, Ignore) with the income categories.
NON_EXPENSE_CATEGORIES = [
    INVESTMENTS_CATEGORY,
    LIABILITIES_CATEGORY,
    CREDIT_CARDS,
    IGNORE_CATEGORY,
    *(c.value for c in IncomeCategories),
]
