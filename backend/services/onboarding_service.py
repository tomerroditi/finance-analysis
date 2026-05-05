"""
Onboarding service.

Reports whether the database has been populated by the user yet, so the
frontend can route fresh installs to the onboarding flow instead of
empty-but-functional dashboards.

The shape is deliberately coarse — boolean flags per concern, no counts,
no PII — so the response is safe to runtime-cache and to surface in
log lines.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.budget import BudgetRule
from backend.models.credential import Credential
from backend.models.investment import Investment
from backend.models.transaction import (
    BankTransaction,
    CashTransaction,
    CreditCardTransaction,
    ManualInvestmentTransaction,
)


class OnboardingService:
    """Compute first-run / onboarding status flags from the live DB."""

    def __init__(self, db: Session):
        self.db = db

    def _has_any(self, model) -> bool:
        """Return True if at least one row exists for the given ORM model."""
        return self.db.execute(select(model).limit(1)).first() is not None

    def get_status(self) -> dict[str, bool]:
        """Return the onboarding status flags for the current database.

        Returns
        -------
        dict[str, bool]
            ``has_credentials``: any provider credential is stored.
            ``has_transactions``: any row exists in any transactions table
                (bank, credit card, cash, or manual investment).
            ``has_budgets``: any budget rule exists.
            ``has_investments``: any investment record exists.
            ``is_first_run``: none of the above are true. The frontend
                uses this as the single signal for "show the wizard."
        """
        has_credentials = self._has_any(Credential)
        has_transactions = (
            self._has_any(BankTransaction)
            or self._has_any(CreditCardTransaction)
            or self._has_any(CashTransaction)
            or self._has_any(ManualInvestmentTransaction)
        )
        has_budgets = self._has_any(BudgetRule)
        has_investments = self._has_any(Investment)

        return {
            "has_credentials": has_credentials,
            "has_transactions": has_transactions,
            "has_budgets": has_budgets,
            "has_investments": has_investments,
            "is_first_run": not (
                has_credentials or has_transactions or has_budgets or has_investments
            ),
        }
