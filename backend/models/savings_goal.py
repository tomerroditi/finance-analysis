"""SavingsGoal database model.

Stores user-defined savings goals — a target amount, an optional target date,
and the amount saved so far — for progress tracking on the dashboard.
"""

from sqlalchemy import Column, Integer, Float, String

from backend.models.base import Base, TimestampMixin
from backend.constants.tables import Tables


class SavingsGoal(Base, TimestampMixin):
    """ORM model for a single savings goal.

    Attributes
    ----------
    name : str
        User-facing goal name (e.g. "Vacation", "Emergency fund").
    target_amount : float
        Amount the user wants to reach (NIS).
    current_amount : float
        Amount saved so far toward the goal (NIS).
    target_date : str or None
        Optional target date in ``YYYY-MM-DD`` format.
    notes : str or None
        Optional free-text note.
    """

    __tablename__ = Tables.SAVINGS_GOALS.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    target_amount = Column(Float, nullable=False)
    current_amount = Column(Float, nullable=False, default=0.0)
    target_date = Column(String, nullable=True)
    notes = Column(String, nullable=True)

    def __repr__(self):
        return f"<SavingsGoal(id={self.id}, name={self.name!r}, target={self.target_amount})>"
