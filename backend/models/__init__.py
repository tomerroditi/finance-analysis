"""
SQLAlchemy ORM Models

This package contains SQLAlchemy ORM models for database tables.
"""

from backend.models.bank_balance import BankBalance
from backend.models.base import Base, TimestampMixin
from backend.models.budget import BudgetRule
from backend.models.budget_month_override import BudgetMonthOverride
from backend.models.cash_balance import CashBalance
from backend.models.category import Category
from backend.models.credential import Credential
from backend.models.insight_dismissal import InsightDismissal
from backend.models.insurance_account import InsuranceAccount
from backend.models.interest_rate import InterestRate
from backend.models.investment import Investment
from backend.models.investment_balance_snapshot import InvestmentBalanceSnapshot
from backend.models.liability import Liability, LiabilityTransaction
from backend.models.pending_refund import PendingRefund, RefundLink
from backend.models.recurring_decision import RecurringDecision
from backend.models.retirement_goal import RetirementGoal
from backend.models.savings_goal import (
    SavingsGoal,
    SavingsGoalAllocation,
    SavingsGoalInvestment,
    SavingsGoalLink,
)
from backend.models.scraping import ScrapingHistory
from backend.models.tagging_rules import TaggingRule
from backend.models.transaction import (
    BankTransaction,
    CashTransaction,
    CreditCardTransaction,
    InsuranceTransaction,
    ManualInvestmentTransaction,
    SplitTransaction,
)

__all__ = [
    # Other models
    "BankBalance",
    # Transactions
    "BankTransaction",
    # Base
    "Base",
    # Budget month override
    "BudgetMonthOverride",
    "BudgetRule",
    "CashBalance",
    "CashTransaction",
    "Category",
    "Credential",
    "CreditCardTransaction",
    # Dashboard insights
    "InsightDismissal",
    "InsuranceAccount",
    "InsuranceTransaction",
    "Investment",
    "InvestmentBalanceSnapshot",
    "Liability",
    "LiabilityTransaction",
    "ManualInvestmentTransaction",
    # Refund linking
    "PendingRefund",
    # Recurring charges
    "RecurringDecision",
    "RefundLink",
    "RetirementGoal",
    # Savings goals
    "SavingsGoal",
    "SavingsGoalAllocation",
    "SavingsGoalInvestment",
    "SavingsGoalLink",
    "ScrapingHistory",
    "SplitTransaction",
    "TaggingRule",
    "TimestampMixin",
]
