"""
Transactions repository package.

Decomposed from the former single-module ``backend/repositories/
transactions_repository.py``:

- ``service_repositories`` — ``ServiceRepository`` base + the five
  per-table repositories + ``ManualTransactionDTO``.
- ``ingestion`` — scraped-transaction insert + pending-row reconciliation.
- ``splits`` — batched split-children builder + split/revert operations.
- ``core`` — the aggregating ``TransactionsRepository``.

The old module path remains as a compatibility shim re-exporting the
public names from here.
"""

from backend.repositories.transactions.core import TransactionsRepository
from backend.repositories.transactions.ingestion import IngestionMixin
from backend.repositories.transactions.service_repositories import (
    DEPOSIT_TYPE,
    WITHDRAWAL_TYPE,
    BankRepository,
    CashRepository,
    CreditCardRepository,
    InsuranceRepository,
    ManualInvestmentTransactionsRepository,
    ManualTransactionDTO,
    ServiceRepository,
    T_service,
)
from backend.repositories.transactions.splits import SplitsMixin

__all__ = [
    "DEPOSIT_TYPE",
    "WITHDRAWAL_TYPE",
    "BankRepository",
    "CashRepository",
    "CreditCardRepository",
    "IngestionMixin",
    "InsuranceRepository",
    "ManualInvestmentTransactionsRepository",
    "ManualTransactionDTO",
    "ServiceRepository",
    "SplitsMixin",
    "T_service",
    "TransactionsRepository",
]
