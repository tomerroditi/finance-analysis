"""
Compatibility shim — the transactions repositories now live in
``backend.repositories.transactions``.

Kept so existing ``from backend.repositories.transactions_repository
import X`` imports keep working. New code should import from
``backend.repositories.transactions`` (or its submodules
``service_repositories``, ``ingestion``, ``splits``, ``core``) directly.

Note: tests that monkeypatch module-level names must target the defining
submodule (e.g. ``backend.repositories.transactions.core``); patching
class attributes (e.g. ``TransactionsRepository._get_base_transactions``)
works through this shim since the class objects are shared.
"""

from backend.models.transaction import (
    BankTransaction,
    CashTransaction,
    CreditCardTransaction,
    InsuranceTransaction,
    ManualInvestmentTransaction,
    SplitTransaction,
    TransactionBase,
)
from backend.repositories.split_transactions_repository import (
    SplitTransactionsRepository,
)
from backend.repositories.transactions import (
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
    TransactionsRepository,
)

__all__ = [
    "DEPOSIT_TYPE",
    "WITHDRAWAL_TYPE",
    "BankRepository",
    "BankTransaction",
    "CashRepository",
    "CashTransaction",
    "CreditCardRepository",
    "CreditCardTransaction",
    "InsuranceRepository",
    "InsuranceTransaction",
    "ManualInvestmentTransaction",
    "ManualInvestmentTransactionsRepository",
    "ManualTransactionDTO",
    "ServiceRepository",
    "SplitTransaction",
    "SplitTransactionsRepository",
    "T_service",
    "TransactionBase",
    "TransactionsRepository",
]
