"""
Investment tracking model.
"""
from sqlalchemy import Column, Integer, String, Float, Text

from backend.models.base import Base, TimestampMixin
from backend.naming_conventions import Tables


class Investment(Base, TimestampMixin):
    """
    Model for tracked investments.
    """
    __tablename__ = Tables.INVESTMENTS.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String, nullable=False)
    tag = Column(String, nullable=False)
    type = Column(String, nullable=False)
    name = Column(String, nullable=False)
    
    # Financial details
    interest_rate = Column(Float, nullable=True)
    interest_rate_type = Column(String, default='fixed')
    commission_deposit = Column(Float, nullable=True)
    commission_management = Column(Float, nullable=True)
    commission_withdrawal = Column(Float, nullable=True)
    
    # Dates stored as text YYYY-MM-DD
    liquidity_date = Column(String, nullable=True)
    maturity_date = Column(String, nullable=True)
    
    is_closed = Column(Integer, default=0)
    created_date = Column(String, nullable=False)  # Original creation date
    closed_date = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
