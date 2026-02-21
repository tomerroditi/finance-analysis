"""
Investment balance snapshot model.
"""

from sqlalchemy import Column, Integer, Float, String, ForeignKey, UniqueConstraint
from backend.models.base import Base, TimestampMixin
from backend.constants.tables import Tables


class InvestmentBalanceSnapshot(Base, TimestampMixin):
    """ORM model for an investment balance snapshot.

    Records the market value of an investment on a specific date.
    One snapshot per investment per date (upsert semantics).

    Attributes
    ----------
    investment_id : int
        Foreign key referencing the investment record.
    date : str
        Snapshot date in ``YYYY-MM-DD`` format.
    balance : float
        Market value of the investment on this date.
    source : str
        How the snapshot was created: ``"manual"``, ``"scraped"``, or ``"calculated"``.
    """

    __tablename__ = Tables.INVESTMENT_BALANCE_SNAPSHOTS.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    investment_id = Column(
        Integer,
        ForeignKey(f"{Tables.INVESTMENTS.value}.id", ondelete="CASCADE"),
        nullable=False,
    )
    date = Column(String, nullable=False)
    balance = Column(Float, nullable=False)
    source = Column(String, nullable=False, default="manual")

    __table_args__ = (
        UniqueConstraint("investment_id", "date", name="uq_snapshot_investment_date"),
    )
