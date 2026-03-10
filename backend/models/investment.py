"""
Investment tracking model.
"""

from sqlalchemy import Column, Integer, String, Float, Text

from backend.models.base import Base, TimestampMixin
from backend.constants.tables import Tables


class Investment(Base, TimestampMixin):
    """ORM model for a tracked investment instrument.

    Each investment is identified by its ``category`` + ``tag`` pair, which
    corresponds to the category/tag used on manual investment transactions.
    ``prior_wealth_amount`` captures the total invested before the app started
    tracking, computed from the sum of manual investment transactions at startup.

    Attributes
    ----------
    category : str
        Category grouping this investment (e.g. ``Investments``).
    tag : str
        Tag identifying this specific instrument (e.g. ``Pension``).
    type : str
        Instrument type (e.g. ``pension``, ``stocks``, ``savings``).
    name : str
        Human-readable name of the investment.
    interest_rate : float, optional
        Annual interest/return rate as a decimal (e.g. ``0.05`` for 5 %).
    interest_rate_type : str
        Rate type: ``fixed`` or ``variable``.
    commission_deposit : float, optional
        Commission charged on deposits (percentage).
    commission_management : float, optional
        Ongoing management fee (percentage per year).
    commission_withdrawal : float, optional
        Commission charged on withdrawals (percentage).
    liquidity_date : str, optional
        Earliest date funds can be withdrawn (``YYYY-MM-DD``).
    maturity_date : str, optional
        Date the investment matures (``YYYY-MM-DD``).
    is_closed : int
        ``1`` if the investment has been closed, ``0`` otherwise.
    created_date : str
        Date the investment was first recorded (``YYYY-MM-DD``).
    closed_date : str, optional
        Date the investment was closed (``YYYY-MM-DD``).
    notes : str, optional
        Free-text notes.
    prior_wealth_amount : float
        Total amount invested before the app started tracking (non-negative).
    """

    __tablename__ = Tables.INVESTMENTS.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String, nullable=False)
    tag = Column(String, nullable=False)
    type = Column(String, nullable=False)
    name = Column(String, nullable=False)

    # Financial details
    interest_rate = Column(Float, nullable=True)
    interest_rate_type = Column(String, default="fixed")
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
    prior_wealth_amount = Column(Float, nullable=False, default=0.0)
