"""
Budget rule model.
"""

from sqlalchemy import Column, Integer, String, Float
from backend.models.base import Base, TimestampMixin
from backend.constants.tables import Tables


class BudgetRule(Base, TimestampMixin):
    """ORM model for budget rules covering both monthly limits and project budgets.

    Monthly rules have ``year`` and ``month`` set; project budget rules leave both
    ``NULL``. The ``tags`` field stores a semicolon-separated list of tag names
    (e.g. ``"Groceries;Restaurants"``). The special category ``"Total Budget"``
    represents an overall monthly spending cap.

    Attributes
    ----------
    name : str
        Human-readable rule name.
    amount : float
        Budget limit in currency units.
    category : str, optional
        Category this rule applies to.
    tags : str, optional
        Semicolon-separated tag names within the category.
    year : int, optional
        Year of the monthly budget rule; ``NULL`` for project budgets.
    month : int, optional
        Month (1–12) of the monthly budget rule; ``NULL`` for project budgets.
    """

    __tablename__ = Tables.BUDGET_RULES.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)
    amount = Column(Float)
    category = Column(String, nullable=True)
    tags = Column(String, nullable=True)
    year = Column(Integer, nullable=True)
    month = Column(Integer, nullable=True)
