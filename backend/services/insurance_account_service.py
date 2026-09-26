"""
Insurance account business logic.

Provides access to insurance account metadata (pension, keren hishtalmut)
and derived calculations such as monthly contribution estimates. Keren
Hishtalmut *balances* are not aggregated here: scraped policies are synced
into ``type='hishtalmut'`` investments, and
``InvestmentsService.get_hishtalmut_total_balance`` is the single source.
"""

import json
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from backend.constants.providers import SUPERSEDED_INSURANCE_PROVIDERS
from backend.errors import EntityNotFoundException
from backend.models.clearing_house_report import ClearingHouseReport
from backend.models.insurance_account import InsuranceAccount
from backend.repositories.clearing_house_report_repository import (
    ClearingHouseReportRepository,
)
from backend.repositories.insurance_account_repository import (
    InsuranceAccountRepository,
)
from backend.repositories.investments_repository import InvestmentsRepository
from backend.repositories.transactions import InsuranceRepository


class InsuranceAccountService:
    """Insurance account queries and balance aggregations."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = InsuranceAccountRepository(db)
        self.insurance_transactions_repo = InsuranceRepository(db)
        self.reports_repo = ClearingHouseReportRepository(db)

    def get_all(self) -> list[InsuranceAccount]:
        """Get all insurance account records."""
        return self.repo.get_all()

    def upsert(self, **fields: Any) -> InsuranceAccount:
        """Create or update an insurance account by policy_id.

        Two guards apply to an existing account:

        - A scrape by a provider that has been replaced (see
          ``SUPERSEDED_INSURANCE_PROVIDERS``) only refreshes the balance; the
          replacement keeps ownership and the rest of the metadata.
        - A balance dated before the stored one is ignored. The pension
          clearing house reports month-end figures, so its balance can be
          weeks older than one HaPhoenix already stored.

        Parameters
        ----------
        **fields
            Column values; must include ``policy_id``.

        Returns
        -------
        InsuranceAccount
            The created or updated record.
        """
        existing = (
            self.repo.get_by_policy_id(fields["policy_id"])
            if fields.get("policy_id")
            else None
        )
        if existing is not None:
            if (
                SUPERSEDED_INSURANCE_PROVIDERS.get(fields.get("provider"))
                == existing.provider
            ):
                fields = {
                    key: value
                    for key, value in fields.items()
                    if key in ("policy_id", "balance", "balance_date")
                }
            incoming_date = fields.get("balance_date")
            if (
                incoming_date
                and existing.balance_date
                and incoming_date < existing.balance_date
            ):
                fields.pop("balance", None)
                fields.pop("balance_date", None)
        return self.repo.upsert(**fields)

    def claim_policies(
        self, provider: str, account_name: str, policy_ids: list[str]
    ) -> dict[str, str]:
        """Resolve scraped policy IDs to stored ones and adopt predecessors' rows.

        A provider can print a policy differently from the one that first
        stored it (the clearing house's ``7-925-053655-0`` is HaPhoenix's
        ``007-925-053655``). The stored string is what every table joins on,
        so the scrape is re-keyed onto it. When the scraping provider replaced
        the one whose credential owns the policy's deposits, those deposits
        move to the scraping credential — history the new provider cannot
        report itself survives, and the dedup then drops re-reported overlap.

        Parameters
        ----------
        provider : str
            The scraping provider.
        account_name : str
            The scraping credential's label.
        policy_ids : list[str]
            Policy IDs as the scraper reported them.

        Returns
        -------
        dict[str, str]
            Scraped policy ID -> stored policy ID, for already-known policies.
        """
        predecessors = [
            old
            for old, new in SUPERSEDED_INSURANCE_PROVIDERS.items()
            if new == provider
        ]
        stored: dict[str, str] = {}
        for policy_id in policy_ids:
            account = self.repo.get_by_policy_id(policy_id)
            if account is None:
                continue
            stored[policy_id] = account.policy_id
            self.insurance_transactions_repo.reassign_policy(
                account.policy_id, predecessors, provider, account_name
            )
        return stored

    def rename(self, policy_id: str, custom_name: str | None) -> InsuranceAccount:
        """Set the user-defined display name for a fund.

        Persists across scrapes (the scraper never writes to ``custom_name``).
        For ``hishtalmut`` policies, the linked Investment's ``name`` is kept
        in lockstep — propagation is unconditional in both directions, so the
        two fields cannot drift apart.

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
        account = self.repo.set_custom_name(policy_id, normalized)
        if account is None:
            raise EntityNotFoundException(
                f"No insurance account found for policy_id={policy_id}"
            )

        if account.policy_type == "hishtalmut":
            investments_repo = InvestmentsRepository(self.db)
            linked = investments_repo.get_by_insurance_policy_id(policy_id)
            if not linked.empty:
                investments_repo.update_investment(
                    int(linked.iloc[0]["id"]),
                    name=normalized or account.account_name,
                )
        return account

    def save_clearing_house_reports(
        self, provider: str, account_name: str, reports: list[dict[str, Any]]
    ) -> None:
        """Store the clearing house's monthly household summaries.

        A report the portal serves again (it keeps about two) overwrites its
        stored row, so a re-scrape never duplicates a month.

        Parameters
        ----------
        provider : str
            Scraping provider.
        account_name : str
            Credential label.
        reports : list[dict]
            One summary per report, each with a ``calc_date``.
        """
        for report in reports:
            fields = dict(report)
            calc_date = fields.pop("calc_date")
            self.reports_repo.upsert(provider, account_name, calc_date, **fields)

    def get_pension_forecasts(self) -> list[dict[str, Any]]:
        """Return each pension policy's provider-published retirement forecast.

        Only policies whose ``details`` carry the clearing house's forecast
        (capital and monthly pension, with and without further deposits) are
        returned.

        Returns
        -------
        list[dict]
            ``policy_id``, ``balance``, ``as_of``, ``retirement_age``,
            ``capital_no_deposits``, ``capital_with_deposits``,
            ``pension_no_deposits`` and ``pension_with_deposits`` per policy.
        """
        forecasts = []
        for account in self.repo.get_by_policy_type("pension"):
            try:
                details = json.loads(account.details or "{}")
            except (TypeError, ValueError):
                continue
            with_deposits = details.get("monthly_pension_forecast")
            no_deposits = details.get("monthly_pension_forecast_no_deposits")
            if not with_deposits and not no_deposits:
                continue
            forecasts.append(
                {
                    "policy_id": account.policy_id,
                    "balance": account.balance or 0.0,
                    "as_of": details.get("source_date"),
                    "retirement_age": details.get("retirement_age"),
                    "capital_no_deposits": details.get("balance_forecast_no_deposits")
                    or 0.0,
                    "capital_with_deposits": details.get("balance_forecast") or 0.0,
                    "pension_no_deposits": no_deposits or 0.0,
                    "pension_with_deposits": with_deposits or 0.0,
                }
            )
        return forecasts

    def get_clearing_house_reports(self) -> list[ClearingHouseReport]:
        """Return every stored clearing-house report, oldest first."""
        return self.reports_repo.get_all()

    def get_monthly_contribution_by_type(self, policy_type: str) -> float | None:
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

        today = date.today()
        first_of_this_month = today.replace(day=1)
        first_of_prev_month = (first_of_this_month - timedelta(days=1)).replace(day=1)
        cutoff = first_of_prev_month.isoformat()

        total = 0.0
        found_active = False

        for account in accounts:
            latest_txn = self.insurance_transactions_repo.get_latest_for_policy(
                account.policy_id
            )

            if latest_txn is None:
                continue

            if latest_txn.date >= cutoff:
                found_active = True
                total += abs(latest_txn.amount)

        return total if found_active else None
