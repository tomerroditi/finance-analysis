"""Existence checks behind the onboarding status flags."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.base import Base
from backend.models.budget import BudgetRule
from backend.models.credential import Credential
from backend.models.investment import Investment
from backend.models.transaction import (
    BankTransaction,
    CashTransaction,
    CreditCardTransaction,
    ManualInvestmentTransaction,
)


class OnboardingRepository:
    """Answers "does the user have any X yet?" without loading any rows.

    Parameters
    ----------
    db : Session
        SQLAlchemy database session.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def _has_any(self, model: type[Base]) -> bool:
        """Return True if at least one row exists for the given ORM model."""
        return self.db.execute(select(model).limit(1)).first() is not None

    def has_credentials(self) -> bool:
        """Return True if any provider credential is stored."""
        return self._has_any(Credential)

    def has_transactions(self) -> bool:
        """Return True if any bank, card, cash or manual investment row exists."""
        return (
            self._has_any(BankTransaction)
            or self._has_any(CreditCardTransaction)
            or self._has_any(CashTransaction)
            or self._has_any(ManualInvestmentTransaction)
        )

    def has_budgets(self) -> bool:
        """Return True if any budget rule exists."""
        return self._has_any(BudgetRule)

    def has_investments(self) -> bool:
        """Return True if any investment record exists."""
        return self._has_any(Investment)
