"""
Bank balance snapshot model.
"""

from sqlalchemy import Column, Float, Integer, String

from backend.constants.tables import Tables
from backend.models.base import Base, TimestampMixin


class BankBalance(Base, TimestampMixin):
    """ORM model for bank account balance snapshots."""

    __tablename__ = Tables.BANK_BALANCES.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(String, nullable=False)
    account_name = Column(String, nullable=False)
    balance = Column(Float, nullable=False)
    prior_wealth_amount = Column(Float, nullable=False, default=0.0)
    last_manual_update = Column(String, nullable=True)
    last_scrape_update = Column(String, nullable=True)
