"""
Budget rule model.
"""

from sqlalchemy import Column, Integer, String, Float
from backend.models.base import Base, TimestampMixin
from backend.naming_conventions import Tables


class BudgetRule(Base, TimestampMixin):
    """
    Model for budget rules (monthly and project-based).
    """

    __tablename__ = Tables.BUDGET_RULES.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)
    amount = Column(Float)
    category = Column(String, nullable=True)
    tags = Column(String, nullable=True)
    year = Column(Integer, nullable=True)
    month = Column(Integer, nullable=True)
