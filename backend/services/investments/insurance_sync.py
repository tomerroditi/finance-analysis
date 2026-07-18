"""
Insurance-account synchronization for the investments service.

Provides the ``InsuranceSyncMixin`` that creates/updates Keren Hishtalmut
investments from scraped insurance account metadata and backfills them
from persisted insurance accounts. Mixed into ``InvestmentsService``
(see ``core.py``).
"""

import pandas as pd

from backend.constants.categories import INVESTMENTS_CATEGORY
from backend.repositories.insurance_account_repository import InsuranceAccountRepository


class InsuranceSyncMixin:
    """Insurance-sync methods for ``InvestmentsService``."""

    def sync_from_insurance(self, insurance_meta: dict) -> None:
        """Create or update an Investment from scraped insurance account metadata.

        Only processes hishtalmut policies. Creates the Investment if not found
        by ``insurance_policy_id``, otherwise updates metadata fields. Upserts
        a ``"scraped"`` balance snapshot if balance data is present, without
        overwriting existing ``"manual"`` snapshots.

        Parameters
        ----------
        insurance_meta : dict
            Insurance account metadata with keys: ``policy_id``, ``policy_type``,
            ``provider``, ``account_name``, ``balance``, ``balance_date``,
            ``commission_deposits_pct``, ``commission_savings_pct``,
            ``liquidity_date``.
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
        tag = f"Keren Hishtalmut - {provider} ({policy_id})"
        metadata_fields = {
            "tag": tag,
            "name": display_name,
            "commission_deposit": insurance_meta.get("commission_deposits_pct"),
            "commission_management": insurance_meta.get("commission_savings_pct"),
            "liquidity_date": insurance_meta.get("liquidity_date"),
        }

        existing = self.investments_repo.get_by_insurance_policy_id(policy_id)
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
                    inv_id, insurance_policy_id=policy_id, **metadata_fields
                )
            else:
                inv_id = self.investments_repo.create_investment(
                    category=INVESTMENTS_CATEGORY,
                    tag=tag,
                    type_="hishtalmut",
                    name=display_name,
                    interest_rate_type="variable",
                    commission_deposit=insurance_meta.get("commission_deposits_pct"),
                    commission_management=insurance_meta.get("commission_savings_pct"),
                    liquidity_date=insurance_meta.get("liquidity_date"),
                    insurance_policy_id=policy_id,
                )

        balance = insurance_meta.get("balance")
        balance_date = insurance_meta.get("balance_date")
        if balance is None or balance_date is None:
            return

        existing_snapshots = self.snapshots_repo.get_snapshots_for_investment(inv_id)
        if not existing_snapshots.empty:
            date_match = existing_snapshots[existing_snapshots["date"] == balance_date]
            if not date_match.empty and date_match.iloc[0]["source"] == "manual":
                return

        self.snapshots_repo.upsert_snapshot(inv_id, balance_date, balance, source="scraped")

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
            self.sync_from_insurance({
                "policy_type": row.policy_type,
                "policy_id": row.policy_id,
                "provider": row.provider,
                "account_name": row.account_name,
                "custom_name": row.custom_name,
                "balance": row.balance,
                "balance_date": row.balance_date,
                "commission_deposits_pct": row.commission_deposits_pct,
                "commission_savings_pct": row.commission_savings_pct,
                "liquidity_date": row.liquidity_date,
            })
        return len(rows)
