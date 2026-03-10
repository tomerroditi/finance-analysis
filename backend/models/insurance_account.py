"""Insurance account metadata model."""

from sqlalchemy import Column, Float, Integer, String, Text

from backend.constants.tables import Tables
from backend.models.base import Base, TimestampMixin


class InsuranceAccount(Base, TimestampMixin):
    """ORM model for insurance account metadata (``insurance_accounts`` table).

    Stores per-policy metadata scraped from insurance providers: investment
    tracks, commission rates, insurance covers, and liquidity dates.
    One row per policy, upserted on each scrape.

    Attributes
    ----------
    provider : str
        Insurance provider identifier (e.g. ``hafenix``).
    policy_id : str
        Unique policy ID from the provider.
    policy_type : str
        Account type: ``pension`` or ``hishtalmut``.
    pension_type : str, optional
        Pension sub-type: ``makifa`` or ``mashlima`` (pension only).
    account_name : str
        Human-readable policy/product name.
    balance : float, optional
        Current account balance.
    balance_date : str, optional
        Date of the balance value (YYYY-MM-DD).
    investment_tracks : str, optional
        JSON string: ``[{name, yield_pct, allocation_pct, sum}]``.
    commission_deposits_pct : float, optional
        Commission rate on deposits (percentage).
    commission_savings_pct : float, optional
        Commission rate on savings/profits (percentage).
    insurance_covers : str, optional
        JSON string: ``[{title, desc, sum}]`` (pension only).
    insurance_costs : str, optional
        JSON string: ``[{title, amount}]`` — annual internal deductions (pension only).
    liquidity_date : str, optional
        Earliest withdrawal date (hishtalmut only, YYYY-MM-DD).
    """

    __tablename__ = Tables.INSURANCE_ACCOUNTS.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(String, nullable=False)
    policy_id = Column(String, nullable=False, unique=True)
    policy_type = Column(String, nullable=False)
    pension_type = Column(String, nullable=True)
    account_name = Column(String, nullable=False)
    balance = Column(Float, nullable=True)
    balance_date = Column(String, nullable=True)
    investment_tracks = Column(Text, nullable=True)
    commission_deposits_pct = Column(Float, nullable=True)
    commission_savings_pct = Column(Float, nullable=True)
    insurance_covers = Column(Text, nullable=True)
    insurance_costs = Column(Text, nullable=True)
    liquidity_date = Column(String, nullable=True)
