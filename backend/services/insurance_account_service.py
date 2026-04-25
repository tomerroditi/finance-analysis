"""
Insurance account business logic.

Provides access to insurance account metadata (pension, keren hishtalmut)
and derived calculations like total balances.
"""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.errors import EntityNotFoundException
from backend.models.insurance_account import InsuranceAccount
from backend.models.transaction import InsuranceTransaction
from backend.repositories.insurance_account_repository import (
    InsuranceAccountRepository,
)
from backend.repositories.investments_repository import InvestmentsRepository


class InsuranceAccountService:
    """Insurance account queries and balance aggregations."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = InsuranceAccountRepository(db)

    def get_all(self) -> list[InsuranceAccount]:
        """Get all insurance account records."""
        return self.repo.get_all()

    def upsert(self, **fields) -> InsuranceAccount:
        """Create or update an insurance account by policy_id.

        Parameters
        ----------
        **fields
            Column values; must include ``policy_id``.
        """
        return self.repo.upsert(**fields)

    def rename(self, policy_id: str, custom_name: str | None) -> InsuranceAccount:
        """Set the user-defined display name for a fund.

        Persists across scrapes (the scraper never writes to ``custom_name``).
        For ``hishtalmut`` policies, also updates the linked Investment's
        ``name`` — but only when the investment's current name still matches
        the previously-displayed fund name. If the user already gave the
        investment its own name on the Investments page, that customization is
        preserved and not overwritten by an Insurances-side rename.

        Parameters
        ----------
        policy_id : str
            Policy identifier of the insurance account to rename.
        custom_name : str or None
            New display name. ``None`` or empty string clears the override and
            falls back to the scraped ``account_name``.

        Returns
        -------
        InsuranceAccount
            The updated record.

        Raises
        ------
        EntityNotFoundException
            If no insurance account matches ``policy_id``.
        """
        normalized = (custom_name or "").strip() or None

        existing = self.repo.get_by_policy_id(policy_id)
        if existing is None:
            raise EntityNotFoundException(
                f"No insurance account found for policy_id={policy_id}"
            )
        old_display_name = existing.custom_name or existing.account_name

        account = self.repo.set_custom_name(policy_id, normalized)
        new_display_name = normalized or account.account_name

        if account.policy_type == "hishtalmut":
            investments_repo = InvestmentsRepository(self.db)
            linked = investments_repo.get_by_insurance_policy_id(policy_id)
            if not linked.empty and linked.iloc[0]["name"] == old_display_name:
                investments_repo.update_investment(
                    int(linked.iloc[0]["id"]),
                    name=new_display_name,
                )
        return account

    def get_keren_hishtalmut_balance(self) -> float | None:
        """Get total Keren Hishtalmut balance from scraped insurance data.

        Returns
        -------
        float or None
            Sum of all hishtalmut account balances, or None if no data.
        """
        accounts = self.repo.get_by_policy_type("hishtalmut")
        if not accounts:
            return None
        total = sum(a.balance for a in accounts if a.balance is not None)
        return total if total > 0 else None

    def get_monthly_contribution_by_type(
        self, policy_type: str
    ) -> float | None:
        """Get estimated monthly contribution for a policy type.

        Finds all accounts of the given type, checks which are active
        (have a transaction in the current or previous month), and sums
        the last transaction amount for each active account.

        Parameters
        ----------
        policy_type : str
            One of ``pension`` or ``hishtalmut``.

        Returns
        -------
        float or None
            Total monthly contribution across active accounts, or None
            if no active accounts exist.
        """
        accounts = self.repo.get_by_policy_type(policy_type)
        if not accounts:
            return None

        # Determine the cutoff: first day of previous month
        today = date.today()
        first_of_this_month = today.replace(day=1)
        first_of_prev_month = (first_of_this_month - timedelta(days=1)).replace(day=1)
        cutoff = first_of_prev_month.isoformat()

        total = 0.0
        found_active = False

        for account in accounts:
            # Get the latest transaction for this account (by policy_id = account_number)
            stmt = (
                select(InsuranceTransaction)
                .where(InsuranceTransaction.account_number == account.policy_id)
                .order_by(InsuranceTransaction.date.desc())
                .limit(1)
            )
            latest_txn = self.db.execute(stmt).scalars().first()

            if latest_txn is None:
                continue

            # Active = latest transaction date >= first of previous month
            if latest_txn.date >= cutoff:
                found_active = True
                total += abs(latest_txn.amount)

        return total if found_active else None
