"""
Transaction models for different financial services.
"""

from sqlalchemy import Column, Float, Integer, String

from backend.models.base import Base, TimestampMixin
from backend.constants.tables import Tables


class TransactionBase(TimestampMixin):
    """Shared column definitions for all transaction ORM models.

    Attributes
    ----------
    unique_id : int
        Auto-incremented primary key used internally across the app.
    id : str
        Original transaction ID from the financial institution.
    date : str
        Transaction date stored as ``YYYY-MM-DD`` string.
    provider : str
        Financial institution identifier (e.g. ``hapoalim``, ``isracard``).
    account_name : str
        User-assigned account label.
    account_number : str, optional
        Account number from the provider, if available.
    description : str
        Transaction description as provided by the institution.
    amount : float
        Transaction amount. Negative = expense, positive = income/refund.
    category : str, optional
        User-assigned category (``NULL`` before tagging).
    tag : str, optional
        User-assigned tag within the category (``NULL`` before tagging).
    source : str
        Service source identifier (``bank``, ``credit_card``, ``cash``, etc.).
    type : str
        Transaction type: ``normal`` or ``split_parent``.
    status : str
        Transaction status (default ``completed``).
    """

    unique_id = Column(Integer, primary_key=True, autoincrement=True)
    id = Column(String)  # Original ID from source
    date = Column(String)  # Stored as string YYYY-MM-DD
    provider = Column(String)
    account_name = Column(String)
    account_number = Column(String, nullable=True)
    description = Column(String)
    amount = Column(Float)
    category = Column(String, nullable=True)
    tag = Column(String, nullable=True)
    source = Column(String)  # 'bank', 'credit_card', etc.
    type = Column(String, default="normal")  # 'normal', 'split_parent'
    status = Column(String, default="completed")


class BankTransaction(Base, TransactionBase):
    """ORM model for bank account transactions (``bank_transactions`` table)."""

    __tablename__ = Tables.BANK.value


class CreditCardTransaction(Base, TransactionBase):
    """ORM model for credit card transactions (``credit_card_transactions`` table)."""

    __tablename__ = Tables.CREDIT_CARD.value


class CashTransaction(Base, TransactionBase):
    """ORM model for manually entered cash transactions (``cash_transactions`` table)."""

    __tablename__ = Tables.CASH.value


class ManualInvestmentTransaction(Base, TransactionBase):
    """ORM model for manually entered investment transactions (``manual_investment_transactions`` table)."""

    __tablename__ = Tables.MANUAL_INVESTMENT_TRANSACTIONS.value


class SplitTransaction(Base, TimestampMixin):
    """ORM model for a single portion of a split transaction.

    When a transaction is split, the original row in its source table is marked
    as ``type='split_parent'`` and remains unchanged. Each portion of the split
    is stored as a separate ``SplitTransaction`` row referencing the parent's
    ``unique_id``. Services merge splits with their parents for analysis.

    Attributes
    ----------
    transaction_id : int
        ``unique_id`` of the parent transaction being split.
    source : str
        Source table of the parent (``bank_transactions``, ``credit_card_transactions``, etc.).
    amount : float
        Amount allocated to this split portion (negative = expense).
    category : str, optional
        Category assigned to this portion.
    tag : str, optional
        Tag assigned to this portion.
    """

    __tablename__ = Tables.SPLIT_TRANSACTIONS.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(Integer)  # References unique_id of parent
    source = Column(String)  # Source table of parent
    amount = Column(Float)
    category = Column(String, nullable=True)
    tag = Column(String, nullable=True)
