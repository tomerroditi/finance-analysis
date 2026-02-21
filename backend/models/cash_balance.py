"""
Cash balance snapshot model.
"""

from sqlalchemy import Column, Float, Integer, String

from backend.constants.tables import Tables
from backend.models.base import Base, TimestampMixin


class CashBalance(Base, TimestampMixin):
    """ORM model for cash envelope balances and prior wealth."""

    __tablename__ = Tables.CASH_BALANCES.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_name = Column(String, nullable=False, unique=True)
    balance = Column(Float, nullable=False)
    prior_wealth_amount = Column(Float, nullable=False, default=0.0)
    last_manual_update = Column(String, nullable=True)
