"""
Investments service — public API and lifecycle operations.

Defines ``InvestmentsService``, assembling the snapshot
(``snapshots.py``), valuation (``valuation.py``), and insurance-sync
(``insurance_sync.py``) mixins around the investment lifecycle
(create/update/close/reopen/delete) and prior-wealth recalculation.
"""

from datetime import date
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.constants.providers import Services
from backend.errors import EntityAlreadyExistsException, ValidationException
from backend.models.transaction import InsuranceTransaction
from backend.repositories.insurance_account_repository import InsuranceAccountRepository
from backend.repositories.investments_repository import InvestmentsRepository
from backend.repositories.investment_snapshots_repository import InvestmentSnapshotsRepository
from backend.repositories.savings_goal_repository import SavingsGoalRepository
from backend.repositories.transactions_repository import TransactionsRepository
from backend.services.investments.insurance_sync import InsuranceSyncMixin
from backend.services.investments.snapshots import SnapshotsMixin
from backend.services.investments.valuation import ValuationMixin

# TransactionsService is imported lazily inside __init__ to avoid a
# module-level circular dependency (TransactionsService also lazy-imports
# InvestmentsService inside its create/delete methods).

CLOSED_SOURCE = "closed"
"""Snapshot ``source`` of the zero balance written when an investment closes."""


class InvestmentsService(SnapshotsMixin, ValuationMixin, InsuranceSyncMixin):
    """
    Service for managing investments with business logic for balance calculations,
    profit/loss tracking, and investment lifecycle management.
    """

    def __init__(self, db: Session):
        """
        Initialize the investments service.

        ``TransactionsService`` is imported lazily to avoid a circular import:
        ``TransactionsService`` also lazy-imports ``InvestmentsService`` inside
        its ``create_transaction`` and ``delete_transaction`` methods.

        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.db = db
        self.investments_repo = InvestmentsRepository(db)
        self.transactions_repo = TransactionsRepository(db)
        self.snapshots_repo = InvestmentSnapshotsRepository(db)
        from backend.services.transactions_service import TransactionsService

        self.transactions_service = TransactionsService(db)

    def get_all_investments(self, include_closed: bool = False) -> List[Dict[str, Any]]:
        """
        Get all investments as a list of JSON-safe dicts.

        Each record is enriched with ``latest_snapshot_date`` indicating the
        most recent balance snapshot, or ``None`` if no snapshots exist.

        Parameters
        ----------
        include_closed : bool, optional
            When ``True``, closed investments are included. Default is ``False``.

        Returns
        -------
        list[dict]
            Investment records with ``NaN`` values replaced by ``None``.
        """
        df = self.investments_repo.get_all_investments(include_closed=include_closed)
        df = df.replace({np.nan: None})
        records = df.to_dict(orient="records")
        if not records:
            return records

        # Batch the per-investment lookups: one snapshot GROUP BY query, one
        # merged-transactions load, and one insurance-transactions load —
        # instead of 2-3 queries per investment.
        snapshot_dates = self.snapshots_repo.get_latest_snapshot_dates(
            date.today().strftime("%Y-%m-%d")
        )

        analysis_df = self.transactions_service.get_data_for_analysis()
        manual_first_dates: dict[tuple[str, str], str] = {}
        if not analysis_df.empty:
            dated = analysis_df.assign(_date=pd.to_datetime(analysis_df["date"]))
            manual_first_dates = {
                key: first.strftime("%Y-%m-%d")
                for key, first in dated.groupby(["category", "tag"])["_date"].min().items()
            }

        policy_ids = [
            record["insurance_policy_id"]
            for record in records
            if record.get("insurance_policy_id")
        ]
        insurance_first_dates: dict[str, str] = {}
        if policy_ids:
            stmt = select(
                InsuranceTransaction.account_number,
                func.min(InsuranceTransaction.date),
            ).where(
                InsuranceTransaction.account_number.in_(policy_ids)
            ).group_by(InsuranceTransaction.account_number)
            insurance_first_dates = {
                account: first[:10]
                for account, first in self.db.execute(stmt).all()
                if first
            }

        for record in records:
            record["latest_snapshot_date"] = snapshot_dates.get(record["id"])

            candidates = []
            manual_first = manual_first_dates.get((record["category"], record["tag"]))
            if manual_first:
                candidates.append(manual_first)
            policy_id = record.get("insurance_policy_id")
            if policy_id and policy_id in insurance_first_dates:
                candidates.append(insurance_first_dates[policy_id])
            record["first_transaction_date"] = min(candidates) if candidates else None

        return records

    def get_investment(self, investment_id: int) -> Dict[str, Any]:
        """
        Get a single investment by ID as a JSON-safe dict.

        Parameters
        ----------
        investment_id : int
            ID of the investment to retrieve.

        Returns
        -------
        dict
            Investment record with ``NaN`` values replaced by ``None``.
        """
        df = self.investments_repo.get_by_id(investment_id)
        df = df.replace({np.nan: None})
        return df.iloc[0].to_dict()

    def get_investment_analysis(
        self,
        investment_id: int,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get detailed profit/loss metrics and balance history for an investment.

        Defaults ``start_date`` to the first transaction date (or one year ago)
        and ``end_date`` to today when not provided.

        Parameters
        ----------
        investment_id : int
            ID of the investment to analyse.
        start_date : str, optional
            ISO date string (``YYYY-MM-DD``) for the start of the balance history.
        end_date : str, optional
            ISO date string (``YYYY-MM-DD``) for the end of the balance history.

        Returns
        -------
        dict
            Dictionary with keys:

            - ``metrics`` – profit/loss metrics dict (from ``calculate_profit_loss``).
            - ``history`` – list of daily balance dicts (from ``calculate_balance_over_time``).
        """
        metrics = self.calculate_profit_loss(investment_id)
        if not start_date:
            start_date = metrics.get("first_transaction_date") or (
                date.today().replace(year=date.today().year - 1).strftime(r"%Y-%m-%d")
            )
        if not end_date:
            end_date = date.today().strftime(r"%Y-%m-%d")

        history = self.calculate_balance_over_time(investment_id, start_date, end_date)
        monthly_transactions = self._calculate_monthly_transactions(investment_id)
        return {
            "metrics": metrics,
            "history": history,
            "monthly_transactions": monthly_transactions,
        }

    def _calculate_monthly_transactions(
        self, investment_id: int
    ) -> List[Dict[str, Any]]:
        """Aggregate investment transactions by month.

        Returns a list of ``{month, deposits, withdrawals}`` entries sorted
        chronologically. Deposits are reported as positive numbers (the
        absolute value of negative transactions), withdrawals are positive
        amounts.
        """
        inv = self.investments_repo.get_by_id(investment_id).iloc[0]
        txns = self._get_all_transactions_for_investment(inv["category"], inv["tag"])
        if txns.empty:
            return []

        df = txns.copy()
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
        df["month"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m")
        df["deposit"] = df["amount"].where(df["amount"] < 0, 0.0).abs()
        df["withdrawal"] = df["amount"].where(df["amount"] > 0, 0.0)

        grouped = (
            df.groupby("month")[["deposit", "withdrawal"]].sum().reset_index()
        )
        grouped = grouped.sort_values("month")
        return [
            {
                "month": row["month"],
                "deposits": float(row["deposit"]),
                "withdrawals": float(row["withdrawal"]),
            }
            for _, row in grouped.iterrows()
            if row["deposit"] > 0 or row["withdrawal"] > 0
        ]

    def create_investment(self, **kwargs) -> None:
        """
        Create a new investment record.

        Parameters
        ----------
        **kwargs
            Field values forwarded to ``InvestmentsRepository.create_investment``.

        Raises
        ------
        EntityAlreadyExistsException
            If an investment with the same ``(category, tag)`` already
            exists. The pair is the investment's identity — it is how its
            transactions are matched — so a second record would read the
            same transactions and double-count them.
        """
        category, tag = kwargs.get("category"), kwargs.get("tag")
        if not self.investments_repo.get_by_category_tag(category, tag).empty:
            raise EntityAlreadyExistsException(
                f"An investment tagged '{tag}' in category '{category}' already exists"
            )
        self.investments_repo.create_investment(**kwargs)

    def update_investment(self, investment_id: int, **updates) -> None:
        """
        Update an investment record.

        For Keren Hishtalmut investments (linked via ``insurance_policy_id``),
        a ``name`` change is also persisted to ``insurance_accounts.custom_name``
        so the rename survives subsequent scrapes and stays consistent with the
        Insurances page.

        Parameters
        ----------
        investment_id : int
            ID of the investment to update.
        **updates
            Field names and new values forwarded to the repository.

        Raises
        ------
        ValidationException
            If ``type`` is among ``updates`` and the investment is
            insurance-linked (has a non-null ``insurance_policy_id``). The
            sync mixin owns the type of scraped Keren Hishtalmut policies;
            reclassifying one here would silently desync it from the
            retirement projection's KH swap.
        """
        if "type" in updates:
            row = self.investments_repo.get_by_id(investment_id)
            policy_id = row.iloc[0].get("insurance_policy_id")
            if policy_id and pd.notna(policy_id):
                raise ValidationException(
                    "Cannot change the type of an insurance-linked investment; "
                    "its type is owned by the scraped policy."
                )

        self.investments_repo.update_investment(investment_id, **updates)

        if "name" in updates:
            row = self.investments_repo.get_by_id(investment_id)
            policy_id = row.iloc[0].get("insurance_policy_id")
            if policy_id and pd.notna(policy_id):
                InsuranceAccountRepository(self.db).set_custom_name(
                    str(policy_id), updates["name"]
                )

    def close_investment(self, investment_id: int, closed_date: str) -> None:
        """
        Mark an investment as closed.

        Automatically creates a balance snapshot of 0 (``source="closed"``)
        since a closed investment has no remaining value. The snapshot is
        placed on the last transaction date (or the closure date when there
        are no transactions), pushed forward to the newest existing snapshot
        date if one is later — otherwise a later snapshot would keep
        valuing the closed holding in net worth. A snapshot already on that
        date is overwritten by the zero.

        Parameters
        ----------
        investment_id : int
            ID of the investment to close.
        closed_date : str
            Closure date in ``YYYY-MM-DD`` format.

        Raises
        ------
        EntityNotFoundException
            If no investment with ``investment_id`` exists.
        ValidationException
            If the investment is already closed.
        """
        inv = self.investments_repo.get_by_id(investment_id).iloc[0]
        if inv["is_closed"]:
            raise ValidationException(
                f"Investment {investment_id} is already closed"
            )
        self.investments_repo.close_investment(investment_id, closed_date)

        txns = self._get_all_transactions_for_investment(
            inv["category"], inv["tag"], investment_id=investment_id
        )
        if not txns.empty:
            zero_date = pd.to_datetime(txns["date"]).max().strftime("%Y-%m-%d")
        else:
            zero_date = closed_date
        snapshots = self.snapshots_repo.get_snapshots_for_investment(investment_id)
        if not snapshots.empty:
            zero_date = max(zero_date, str(snapshots["date"].max()))
        self.create_balance_snapshot(investment_id, zero_date, 0.0, source=CLOSED_SOURCE)

    def reopen_investment(self, investment_id: int) -> None:
        """
        Reopen a previously closed investment.

        Drops the zero-balance snapshot that closing wrote, so the balance
        resolves from the remaining snapshots and transactions again.

        Parameters
        ----------
        investment_id : int
            ID of the investment to reopen.

        Raises
        ------
        EntityNotFoundException
            If no investment with ``investment_id`` exists.
        """
        self.investments_repo.reopen_investment(investment_id)
        self.snapshots_repo.delete_snapshots_for_investment(
            investment_id, source=CLOSED_SOURCE
        )

    def delete_investment(self, investment_id: int) -> None:
        """
        Delete an investment record.

        Savings-goal earmarks backed by the investment are removed too:
        a dangling ``savings_goal_investments`` row would make every goal
        listing fail while valuing a holding that no longer exists.

        Parameters
        ----------
        investment_id : int
            ID of the investment to delete.

        Raises
        ------
        EntityNotFoundException
            If no investment with ``investment_id`` exists.
        """
        self.investments_repo.get_by_id(investment_id)
        SavingsGoalRepository(self.db).delete_backings_for_investment(investment_id)
        self.investments_repo.delete_investment(investment_id)

    def recalculate_prior_wealth(self, investment_id: int) -> None:
        """
        Calculate and store prior_wealth_amount for an investment.

        Reads ManualInvestmentTransactions directly (bypassing get_data_for_analysis
        to avoid depending on synthetic prior-wealth rows) and stores
        -(sum of amounts) as prior_wealth_amount. Equivalent to
        BankBalanceService.recalculate_for_account for bank accounts.

        Parameters
        ----------
        investment_id : int
            ID of the investment to recalculate.
        """
        investment = self.investments_repo.get_by_id(investment_id)
        inv = investment.iloc[0]
        all_inv_txns = self.transactions_repo.get_table(Services.MANUAL_INVESTMENTS.value)
        if all_inv_txns.empty:
            prior_wealth = 0.0
        else:
            mask = (all_inv_txns["category"] == inv["category"]) & (
                all_inv_txns["tag"] == inv["tag"]
            )
            inv_txns = all_inv_txns[mask]
            if inv_txns.empty:
                prior_wealth = 0.0
            else:
                amounts = pd.to_numeric(
                    inv_txns["amount"], errors="coerce"
                ).fillna(0.0)
                prior_wealth = -float(amounts.sum())
        self.investments_repo.update_prior_wealth(investment_id, prior_wealth)

    def recalculate_prior_wealth_by_tag(self, category: str, tag: str) -> None:
        """
        Look up investment by category and tag, then recalculate prior_wealth_amount.

        Parameters
        ----------
        category : str
            Investment category (e.g. "Investments").
        tag : str
            Investment tag identifying the specific investment.
        """
        inv_df = self.investments_repo.get_by_category_tag(category, tag)
        if inv_df.empty:
            return
        self.recalculate_prior_wealth(int(inv_df.iloc[0]["id"]))

    def get_total_prior_wealth(self, include_closed: bool = True) -> float:
        """
        Sum prior_wealth_amount across investments.

        Parameters
        ----------
        include_closed : bool, optional
            When ``True`` (default), includes closed investments.
            Use ``False`` for overview identity calculations where closed
            investment capital is already reflected in bank balances.

        Returns
        -------
        float
            Total prior wealth across selected investments.
        """
        df = self.investments_repo.get_all_investments(include_closed=include_closed)
        if df.empty:
            return 0.0
        return float(df["prior_wealth_amount"].sum())
