"""
Constants package for the finance-analysis backend.

Domain modules:
- tables: Database table names and field enums
- providers: Financial service providers and credentials
- categories: Transaction classification and protected categories
- budget: Budget-specific field name constants

Constants are re-exported from this package so callers can simply do
``from backend.constants import <name>`` instead of importing from each
sub-module. New names must be added explicitly to ``__all__`` below — wildcard
re-exports were intentionally removed so the public surface is discoverable
from one place.
"""

from backend.constants.budget import (
    ALL_TAGS,
    AMOUNT,
    CATEGORY,
    ID,
    MONTH,
    NAME,
    TAGS,
    TOTAL_BUDGET,
    YEAR,
)
from backend.constants.categories import (
    CREDIT_CARDS,
    IGNORE_CATEGORY,
    INVESTMENTS_CATEGORY,
    LIABILITIES_CATEGORY,
    PRIOR_WEALTH_TAG,
    PROTECTED_CATEGORIES,
    PROTECTED_TAGS,
    IncomeCategories,
)
from backend.constants.providers import (
    Banks,
    CreditCards,
    Fields,
    LoginFields,
    Services,
    bank_providers,
    cc_providers,
    insurance_providers,
)
from backend.constants.tables import (
    BankTableFields,
    CreditCardTableFields,
    InvestmentBalanceSnapshotsTableFields,
    InvestmentsTableFields,
    LiabilitiesTableFields,
    LiabilityTransactionsTableFields,
    SplitTransactionsTableFields,
    Tables,
    TransactionsTableFields,
)

__all__ = [
    "ALL_TAGS",
    "AMOUNT",
    "CATEGORY",
    "CREDIT_CARDS",
    # budget
    "ID",
    "IGNORE_CATEGORY",
    "INVESTMENTS_CATEGORY",
    "LIABILITIES_CATEGORY",
    "MONTH",
    "NAME",
    # categories
    "PRIOR_WEALTH_TAG",
    "PROTECTED_CATEGORIES",
    "PROTECTED_TAGS",
    "TAGS",
    "TOTAL_BUDGET",
    "YEAR",
    "BankTableFields",
    "Banks",
    "CreditCardTableFields",
    "CreditCards",
    "Fields",
    "IncomeCategories",
    "InvestmentBalanceSnapshotsTableFields",
    "InvestmentsTableFields",
    "LiabilitiesTableFields",
    "LiabilityTransactionsTableFields",
    "LoginFields",
    "Services",
    "SplitTransactionsTableFields",
    # tables
    "Tables",
    "TransactionsTableFields",
    "bank_providers",
    # providers
    "cc_providers",
    "insurance_providers",
]
