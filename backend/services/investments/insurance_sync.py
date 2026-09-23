"""
Insurance-account synchronization for the investments service.

Provides the ``InsuranceSyncMixin`` that creates/updates Keren Hishtalmut
investments from scraped insurance account metadata and backfills them
from persisted insurance accounts. Mixed into ``InvestmentsService``
(see ``core.py``).
"""

from collections.abc import Iterable
from typing import Any

import pandas as pd

from backend.constants.categories import INVESTMENTS_CATEGORY
from backend.models.insurance_account import InsuranceAccount
from backend.repositories.insurance_account_repository import InsuranceAccountRepository
from backend.services.investments.valuation import HISHTALMUT_TYPE


class InsuranceSyncMixin:
    """Insurance-sync methods for ``InvestmentsService``."""

    def sync_from_insurance(self, insurance_meta: dict[str, Any]) -> None:
        """Create or update an Investment from scraped insurance account metadata.

        Only processes hishtalmut policies. Creates the Investment if not found
        by ``insurance_policy_id``, otherwise updates metadata fields — but
        never its tag, which is the investment's identity: a policy taken
        over by another provider stays the same investment. Upserts a
        ``"scraped"`` balance snapshot for the current balance and for every
        ``balance_history`` point, without overwriting ``"manual"`` snapshots.

        Parameters
        ----------
        insurance_meta : dict
            Insurance account metadata with keys: ``policy_id``, ``policy_type``,
            ``provider``, ``account_name``, ``balance``, ``balance_date``,
            ``commission_deposits_pct``, ``commission_savings_pct``,
            ``liquidity_date``, and optionally ``balance_history``
            (``[{date, balance}]`` of earlier month-end balances).
        """
        if insurance_meta.get("policy_type") != "hishtalmut":
            return

        policy_id = insurance_meta["policy_id"]
        provider = insurance_meta.get("provider", "unknown")
        account_name = insurance_meta["account_name"]
        custom_name = insurance_meta.get("custom_name")
        if custom_name is None:
            persisted = InsuranceAccountRepository(self.db).get_by_policy_id(policy_id)
            if persisted is not None:
                custom_name = persisted.custom_name
        display_name = custom_name or account_name

        existing = self.investments_repo.get_by_insurance_policy_id(policy_id)
        tag = f"Keren Hishtalmut - {provider} ({policy_id})"
        metadata_fields = {
            "name": display_name,
            "commission_deposit": insurance_meta.get("commission_deposits_pct"),
            "commission_management": insurance_meta.get("commission_savings_pct"),
            "liquidity_date": insurance_meta.get("liquidity_date"),
        }

        if not existing.empty:
            inv_id = int(existing.iloc[0]["id"])
            self.investments_repo.update_investment(inv_id, **metadata_fields)
        else:
            legacy_tag = f"Keren Hishtalmut - {provider}"
            by_tag = self.investments_repo.get_by_category_tag(
                INVESTMENTS_CATEGORY, legacy_tag
            )
            if not by_tag.empty and pd.isna(by_tag.iloc[0].get("insurance_policy_id")):
                inv_id = int(by_tag.iloc[0]["id"])
                self.investments_repo.update_investment(
                    inv_id, insurance_policy_id=policy_id, tag=tag, **metadata_fields
                )
            else:
                inv_id = self.investments_repo.create_investment(
                    category=INVESTMENTS_CATEGORY,
                    tag=tag,
                    type_=HISHTALMUT_TYPE,
                    name=display_name,
                    interest_rate_type="variable",
                    commission_deposit=insurance_meta.get("commission_deposits_pct"),
                    commission_management=insurance_meta.get("commission_savings_pct"),
                    liquidity_date=insurance_meta.get("liquidity_date"),
                    insurance_policy_id=policy_id,
                )

        points = [
            (point.get("date"), point.get("balance"))
            for point in insurance_meta.get("balance_history") or []
        ]
        points.append(
            (insurance_meta.get("balance_date"), insurance_meta.get("balance"))
        )
        self._upsert_scraped_snapshots(inv_id, points)

    def _upsert_scraped_snapshots(
        self, inv_id: int, points: Iterable[tuple[str | None, float | None]]
    ) -> None:
        """Write ``"scraped"`` snapshots, leaving dates with a manual one alone.

        Parameters
        ----------
        inv_id : int
            Investment the snapshots belong to.
        points : iterable of (date, balance)
            Snapshot candidates; incomplete points are skipped.
        """
        existing_snapshots = self.snapshots_repo.get_snapshots_for_investment(inv_id)
        manual_dates = (
            set(
                existing_snapshots.loc[existing_snapshots["source"] == "manual", "date"]
            )
            if not existing_snapshots.empty
            else set()
        )
        for balance_date, balance in points:
            if balance is None or balance_date is None or balance_date in manual_dates:
                continue
            self.snapshots_repo.upsert_snapshot(
                inv_id, balance_date, balance, source="scraped"
            )

    def sync_from_insurance_account(
        self,
        account: InsuranceAccount,
        balance_history: list[dict[str, Any]] | None = None,
    ) -> None:
        """Sync a hishtalmut investment from a persisted insurance account.

        Reading the stored row rather than a scrape's raw metadata means the
        investment follows what the account upsert actually kept — the owning
        provider, and the newest balance of any source.

        Parameters
        ----------
        account : InsuranceAccount
            The stored insurance account.
        balance_history : list[dict], optional
            Earlier ``[{date, balance}]`` points to snapshot as well.
        """
        self.sync_from_insurance(
            {
                "policy_type": account.policy_type,
                "policy_id": account.policy_id,
                "provider": account.provider,
                "account_name": account.account_name,
                "custom_name": account.custom_name,
                "balance": account.balance,
                "balance_date": account.balance_date,
                "commission_deposits_pct": account.commission_deposits_pct,
                "commission_savings_pct": account.commission_savings_pct,
                "liquidity_date": account.liquidity_date,
                "balance_history": balance_history,
            }
        )

    def backfill_from_insurance_accounts(self) -> int:
        """Sync investments for all existing hishtalmut insurance accounts.

        Idempotent: re-running does not create duplicates because
        ``sync_from_insurance`` matches by ``insurance_policy_id``.

        Returns
        -------
        int
            Number of hishtalmut policies processed.
        """
        rows = InsuranceAccountRepository(self.db).get_by_policy_type("hishtalmut")
        for row in rows:
            self.sync_from_insurance_account(row)
        return len(rows)
