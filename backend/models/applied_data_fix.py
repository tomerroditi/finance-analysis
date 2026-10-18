"""One-time data repairs that have already run on this database."""

from sqlalchemy import Column, Integer, String

from backend.constants.tables import Tables
from backend.models.base import Base, TimestampMixin


class AppliedDataFix(Base, TimestampMixin):
    """A one-time data repair recorded as done.

    Alembic revisions repair data with raw SQL against the schema of their
    own point in history; a repair that needs the application's services runs
    after every revision instead (``backend/data_fixes.py``), and a row here
    keeps it from running twice.

    Attributes
    ----------
    name : str
        The fix's registered name. Unique — a fix runs once per database.
    """

    __tablename__ = Tables.APPLIED_DATA_FIXES.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
