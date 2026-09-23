"""
RetirementGoal database model.

Stores the user's early retirement planning parameters, including
Israeli-specific savings vehicles (pension, Keren Hishtalmut, Bituach Leumi).
"""

from sqlalchemy import Boolean, Column, Float, Integer, String

from backend.constants.tables import Tables
from backend.models.base import Base, TimestampMixin


class RetirementGoal(Base, TimestampMixin):
    """ORM model for the single-row retirement goal profile.

    Attributes
    ----------
    current_age : int
        User's current age.
    gender : str
        ``male`` or ``female`` — affects pension age (67 vs 65).
    target_retirement_age : int
        Desired early retirement age.
    life_expectancy : int
        Planning horizon (age to plan funds until).
    monthly_expenses_in_retirement : float
        Expected monthly spending in retirement (NIS).
    inflation_rate : float
        Annual inflation assumption as decimal (e.g. 0.025 for 2.5%).
    expected_return_rate : float
        Annual real return on investments as decimal.
    withdrawal_rate : float
        Safe withdrawal rate as decimal (e.g. 0.035 for 3.5%).
    pension_monthly_payout_estimate : float
        Expected monthly pension at full pension age (NIS).
    keren_hishtalmut_balance : float
        Current Keren Hishtalmut balance (NIS).
    keren_hishtalmut_monthly_contribution : float
        Monthly contribution to Keren Hishtalmut (NIS).
    bituach_leumi_eligible : int
        1 if eligible for Bituach Leumi old-age pension, 0 otherwise.
    bituach_leumi_monthly_estimate : float
        Expected monthly Bituach Leumi pension (NIS).
    other_passive_income : float
        Other monthly passive income like rental (NIS).
    monthly_income : float, optional
        User-entered monthly income (NIS).
    net_worth_override : float, optional
        Manual override for the current-status net worth.
    monthly_expenses_override : float, optional
        Manual override for the current-status monthly expenses.
    total_investments_override : float, optional
        Manual override for the current-status investments total. For all
        three overrides ``NULL`` means use the value calculated from tracked
        data.
    """

    __tablename__ = Tables.RETIREMENT_GOAL.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    current_age = Column(Integer, nullable=False)
    gender = Column(String, nullable=False, default="male")
    target_retirement_age = Column(Integer, nullable=False, default=50)
    life_expectancy = Column(Integer, nullable=False, default=90)
    monthly_expenses_in_retirement = Column(Float, nullable=False)
    inflation_rate = Column(Float, nullable=False, default=0.025)
    expected_return_rate = Column(Float, nullable=False, default=0.04)
    withdrawal_rate = Column(Float, nullable=False, default=0.035)

    pension_monthly_payout_estimate = Column(Float, nullable=False, default=0.0)
    keren_hishtalmut_balance = Column(Float, nullable=False, default=0.0)
    keren_hishtalmut_monthly_contribution = Column(Float, nullable=False, default=0.0)
    bituach_leumi_eligible = Column(Boolean, nullable=False, default=1)
    bituach_leumi_monthly_estimate = Column(Float, nullable=False, default=2800.0)
    other_passive_income = Column(Float, nullable=False, default=0.0)
    monthly_income = Column(Float, nullable=True)

    net_worth_override = Column(Float, nullable=True)
    monthly_expenses_override = Column(Float, nullable=True)
    total_investments_override = Column(Float, nullable=True)

    def __repr__(self) -> str:
        return f"<RetirementGoal(id={self.id}, age={self.current_age}, target={self.target_retirement_age})>"
