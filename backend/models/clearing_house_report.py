"""Monthly household summaries from the pension clearing house."""

from sqlalchemy import Column, Float, Integer, String, UniqueConstraint

from backend.constants.tables import Tables
from backend.models.base import Base, TimestampMixin


class ClearingHouseReport(Base, TimestampMixin):
    """One monthly clearing-house report's household-wide summary.

    The clearing house reports across every fund the saver holds, so these
    figures belong to no single insurance account. Its portal deletes a report
    about two months after issuing it; storing one row per report month keeps
    the history of the forecasts.

    Attributes
    ----------
    provider : str
        Scraping provider (``mislaka``).
    account_name : str
        Credential label the report was scraped under.
    calc_date : str
        The report's as-of month end (``YYYY-MM-DD``).
    total_savings : float
        Savings across all products at ``calc_date``.
    forecast_total_balance : float
        Projected savings at retirement age if deposits continue.
    forecast_monthly_pension : float
        Projected monthly pension at retirement age if deposits continue.
    forecast_lump_sum : float
        Projected lump sum at retirement (Keren Hishtalmut and provident
        funds) if deposits continue.
    disability_monthly : float
        Monthly benefit on full loss of working capacity.
    survivor_spouse_monthly : float
        Monthly survivor pension to a spouse.
    survivor_child_monthly : float
        Monthly survivor pension to children.
    death_lump_sum : float
        One-time life-insurance payout.
    report_number, report_count : int, optional
        Position of the report in the subscription ("1 of 7").
    subscription_expires : str, optional
        When the monthly subscription ends (newest report only).
    subscription_months_left : int, optional
        Reports still due on the subscription (newest report only).
    license_holder : str, optional
        Licensee authorized to receive the data (newest report only).
    """

    __tablename__ = Tables.CLEARING_HOUSE_REPORTS.value
    __table_args__ = (
        UniqueConstraint(
            "provider", "account_name", "calc_date", name="uq_clearing_house_report"
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(String, nullable=False)
    account_name = Column(String, nullable=False)
    calc_date = Column(String, nullable=False)
    total_savings = Column(Float, nullable=True)
    forecast_total_balance = Column(Float, nullable=True)
    forecast_monthly_pension = Column(Float, nullable=True)
    forecast_lump_sum = Column(Float, nullable=True)
    disability_monthly = Column(Float, nullable=True)
    survivor_spouse_monthly = Column(Float, nullable=True)
    survivor_child_monthly = Column(Float, nullable=True)
    death_lump_sum = Column(Float, nullable=True)
    report_number = Column(Integer, nullable=True)
    report_count = Column(Integer, nullable=True)
    subscription_expires = Column(String, nullable=True)
    subscription_months_left = Column(Integer, nullable=True)
    license_holder = Column(String, nullable=True)
