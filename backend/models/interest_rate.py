"""
Interest rate series model.
"""

from sqlalchemy import Column, Float, Integer, String, UniqueConstraint

from backend.constants.tables import Tables
from backend.models.base import Base, TimestampMixin


class InterestRate(Base, TimestampMixin):
    """ORM model for a point in an interest rate series.

    Each row is a step in a step function: the rate takes ``value``
    from ``date`` (inclusive) until the next point in the same series.
    The Bank of Israel key rate is stored as the ``boi_rate`` series;
    prime is derived (BoI + 1.5) and never stored.

    Attributes
    ----------
    series : str
        Series identifier (e.g. ``boi_rate``).
    date : str
        Effective date of the rate decision (YYYY-MM-DD).
    value : float
        Annual rate as a percentage (e.g. 4.5 for 4.5%).
    source : str
        Where the point came from — ``seed`` (bundled history) or
        ``fetched`` (live refresh).
    """

    __tablename__ = Tables.INTEREST_RATES.value
    __table_args__ = (
        UniqueConstraint("series", "date", name="uq_interest_rate_series_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    series = Column(String, nullable=False)
    date = Column(String, nullable=False)
    value = Column(Float, nullable=False)
    source = Column(String, nullable=False, default="seed")
