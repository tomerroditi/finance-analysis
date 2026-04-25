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

from backend.constants.tables import (
    Tables,
    TransactionsTableFields,
    CreditCardTableFields,
    BankTableFields,
    SplitTransactionsTableFields,
    InvestmentsTableFields,
    InvestmentBalanceSnapshotsTableFields,
    LiabilitiesTableFields,
    LiabilityTransactionsTableFields,
)
from backend.constants.providers import (
    cc_providers,
    bank_providers,
    insurance_providers,
    Services,
    CreditCards,
    Banks,
    Fields,
    LoginFields,
)
from backend.constants.categories import (
    PRIOR_WEALTH_TAG,
    CREDIT_CARDS,
    IGNORE_CATEGORY,
    INVESTMENTS_CATEGORY,
    LIABILITIES_CATEGORY,
    PROTECTED_TAGS,
    PROTECTED_CATEGORIES,
    IncomeCategories,
)
from backend.constants.budget import (
    ID,
    CATEGORY,
    TAGS,
    NAME,
    AMOUNT,
    MONTH,
    YEAR,
    ALL_TAGS,
    TOTAL_BUDGET,
)

__all__ = [
    # tables
    "Tables",
    "TransactionsTableFields",
    "CreditCardTableFields",
    "BankTableFields",
    "SplitTransactionsTableFields",
    "InvestmentsTableFields",
    "InvestmentBalanceSnapshotsTableFields",
    "LiabilitiesTableFields",
    "LiabilityTransactionsTableFields",
    # providers
    "cc_providers",
    "bank_providers",
    "insurance_providers",
    "Services",
    "CreditCards",
    "Banks",
    "Fields",
    "LoginFields",
    # categories
    "PRIOR_WEALTH_TAG",
    "CREDIT_CARDS",
    "IGNORE_CATEGORY",
    "INVESTMENTS_CATEGORY",
    "LIABILITIES_CATEGORY",
    "PROTECTED_TAGS",
    "PROTECTED_CATEGORIES",
    "IncomeCategories",
    # budget
    "ID",
    "CATEGORY",
    "TAGS",
    "NAME",
    "AMOUNT",
    "MONTH",
    "YEAR",
    "ALL_TAGS",
    "TOTAL_BUDGET",
]
