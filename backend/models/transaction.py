"""
Transaction models for different financial services.
"""

from sqlalchemy import Column, Float, Integer, String

from backend.models.base import Base, TimestampMixin
from backend.constants.tables import Tables


class TransactionBase(TimestampMixin):
    """
    Base class for all transaction types with common columns.
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
    __tablename__ = Tables.BANK.value


class CreditCardTransaction(Base, TransactionBase):
    __tablename__ = Tables.CREDIT_CARD.value


class CashTransaction(Base, TransactionBase):
    __tablename__ = Tables.CASH.value


class ManualInvestmentTransaction(Base, TransactionBase):
    __tablename__ = Tables.MANUAL_INVESTMENT_TRANSACTIONS.value


class SplitTransaction(Base, TimestampMixin):
    """
    Model for split transactions.
    """

    __tablename__ = Tables.SPLIT_TRANSACTIONS.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(Integer)  # References unique_id of parent
    source = Column(String)  # Source table of parent
    amount = Column(Float)
    category = Column(String, nullable=True)
    tag = Column(String, nullable=True)
