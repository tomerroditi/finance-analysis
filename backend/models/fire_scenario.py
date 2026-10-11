"""FireScenario database model: the user's saved early-retirement plan."""

from sqlalchemy import Column, Integer, Text

from backend.constants.tables import Tables
from backend.models.base import Base, TimestampMixin


class FireScenario(Base, TimestampMixin):
    """ORM model for the single-row early-retirement plan.

    The plan is stored as the calculator's own flat form, so it can be posted
    to the engine unchanged and replayed against the reference.

    Attributes
    ----------
    fields : str
        JSON object of the form's fields (``{"dateOfBirth": "1990-01-01", ...}``),
        including the hidden ``*Source`` field of each row that follows a
        tracked account.
    linked : str
        JSON list of the single-value fields that follow tracked data (the
        cash balance, the pension balance...). They are refreshed from the
        user's data whenever the plan is read.
    """

    __tablename__ = Tables.FIRE_SCENARIOS.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    fields = Column(Text, nullable=False)
    linked = Column(Text, nullable=False, default="[]")

    def __repr__(self) -> str:
        return f"<FireScenario(id={self.id})>"
