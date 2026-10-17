"""Category and tag names with special meaning to the app."""

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
    """Categories that count as income."""

    SALARY = "Salary"
    OTHER_INCOME = "Other Income"


#: A category is considered unused when it has had no transactions for this
#: many months AND was itself created longer ago than this. One constant
#: governs both windows so the rule reads as a single sentence.
UNUSED_CATEGORY_MONTHS = 6
