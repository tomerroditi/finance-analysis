"""Pending refunds service with business logic."""

from typing import Literal, Optional

from sqlalchemy.orm import Session

from backend.errors import EntityNotFoundException, ValidationException
from backend.repositories.pending_refunds_repository import PendingRefundsRepository


class PendingRefundsService:
    """
    Service for pending refund business logic.

    Coordinates marking transactions as pending refunds,
    linking actual refunds, and calculating budget adjustments.
    """

    def __init__(self, db: Session):
        """
        Initialize the pending refunds service.

        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.db = db
        self.repo = PendingRefundsRepository(db)

    def mark_as_pending_refund(
        self,
        source_type: Literal["transaction", "split"],
        source_id: int,
        source_table: str,
        expected_amount: float,
        notes: Optional[str] = None,
    ) -> dict:
        """
        Mark a transaction or split as expecting a refund.

        Parameters
        ----------
        source_type : str
            Either 'transaction' or 'split'.
        source_id : int
            ID of the source (unique_id for transactions, id for splits).
        source_table : str
            Table name: 'banks', 'credit_cards', or 'cash'.
        expected_amount : float
            Positive amount expected to be refunded.
        notes : str, optional
            User notes about this pending refund.

        Returns
        -------
        dict
            The created pending refund record as dict.

        Raises
        ------
        ValidationException
            If expected_amount is not positive or source already marked.
        """
        if expected_amount <= 0:
            raise ValidationException("Expected refund amount must be positive")

        # Check if already marked
        existing = self.repo.get_pending_for_source(
            source_type, source_id, source_table
        )
        if existing:
            raise ValidationException(
                f"This {source_type} is already marked as pending refund"
            )

        pending = self.repo.create_pending_refund(
            source_type=source_type,
            source_id=source_id,
            source_table=source_table,
            expected_amount=expected_amount,
            notes=notes,
        )

        return {
            "id": pending.id,
            "source_type": pending.source_type,
            "source_id": pending.source_id,
            "source_table": pending.source_table,
            "expected_amount": pending.expected_amount,
            "status": pending.status,
            "notes": pending.notes,
        }

    def link_refund(
        self,
        pending_refund_id: int,
        refund_transaction_id: int,
        refund_source: str,
        amount: float,
    ) -> dict:
        """
        Link a refund transaction to a pending refund.

        Parameters
        ----------
        pending_refund_id : int
            ID of the pending refund.
        refund_transaction_id : int
            unique_id of the refund transaction.
        refund_source : str
            Table where refund lives.
        amount : float
            Amount this refund covers.

        Returns
        -------
        dict
            Updated pending refund status with total refunded.

        Raises
        ------
        EntityNotFoundException
            If pending refund not found.
        """
        pending = self.repo.get_by_id(pending_refund_id)
        if not pending:
            raise EntityNotFoundException(
                f"Pending refund {pending_refund_id} not found"
            )

        # Add the link
        self.repo.add_refund_link(
            pending_refund_id=pending_refund_id,
            refund_transaction_id=refund_transaction_id,
            refund_source=refund_source,
            amount=amount,
        )

        # Calculate total refunded
        links = self.repo.get_links_for_pending(pending_refund_id)
        total_refunded = links["amount"].sum() if not links.empty else 0

        # Determine new status
        if total_refunded >= pending.expected_amount:
            new_status = "resolved"
        else:
            new_status = "partial"

        self.repo.update_status(pending_refund_id, new_status)

        remaining = max(0, pending.expected_amount - total_refunded)

        return {
            "id": pending_refund_id,
            "status": new_status,
            "expected_amount": pending.expected_amount,
            "total_refunded": total_refunded,
            "remaining": remaining,
        }

    def cancel_pending_refund(self, pending_refund_id: int) -> None:
        """
        Cancel a pending refund (remove pending status).

        Parameters
        ----------
        pending_refund_id : int
            ID of the pending refund to cancel.

        Raises
        ------
        EntityNotFoundException
            If pending refund not found.
        """
        pending = self.repo.get_by_id(pending_refund_id)
        if not pending:
            raise EntityNotFoundException(
                f"Pending refund {pending_refund_id} not found"
            )

        self.repo.delete_pending_refund(pending_refund_id)

    def get_all_pending(self, status: Optional[str] = None) -> list[dict]:
        """
        Get all pending refunds enriched with source details.

        Parameters
        ----------
        status : str, optional
            Filter by status.

        Returns
        -------
        list[dict]
            List of pending refund records with source transaction details.
        """
        from sqlalchemy import select

        from backend.repositories.transactions_repository import TransactionsRepository

        df = self.repo.get_all_pending_refunds(status=status)
        pending_list = df.to_dict(orient="records") if not df.empty else []

        if not pending_list:
            return []

        # Initialize repos
        trans_repo = TransactionsRepository(self.db)
        # Split repo is needed if we have split sources, but we need parent transaction anyway.

        # Group by source table/type to batch fetch
        # format: { (table, type): [ids] }
        sources = {}
        for p in pending_list:
            key = (p["source_table"], p["source_type"])
            if key not in sources:
                sources[key] = []
            sources[key].append(p["source_id"])

        # Fetch details
        details_map = {}  # (table, type, id) -> details dict

        for (table, type_), ids in sources.items():
            if type_ == "transaction":
                try:
                    repo_cls = trans_repo.repo_map.get(table)
                    if repo_cls:
                        model = repo_cls.model
                        # Fetch transactions
                        stmt = select(model).where(model.unique_id.in_(ids))
                        results = self.db.execute(stmt).scalars().all()
                        for tx in results:
                            details_map[(table, type_, tx.unique_id)] = {
                                "date": tx.date,
                                "description": tx.description,
                                "account_name": tx.account_name,
                                "provider": tx.provider,
                                "original_currency": "ILS",  # Assumption
                            }
                except Exception:
                    pass  # Fail gracefully on enrichment
            elif type_ == "split":
                # For splits, we need to get the split record to find the parent transaction
                # Then get details from the parent
                try:
                    # We can't batch efficiently across mixed split IDs easily without ORM for splits
                    # But we can iterate. Optimally we'd use SplitTransactionsRepository.
                    # Since split repo is SQL-based/Pandas in parts, let's use the DB directly for efficiency if possible
                    # or just use the repo.
                    for split_id in ids:
                        split_df = (
                            trans_repo.split_repo.get_data()
                        )  # Inefficient if large
                        # Better to select specific split. split_repo doesn't have get_by_id?
                        # It has get_splits_for_transaction.
                        # Let's direct query split table
                        from backend.models.transaction import SplitTransaction

                        split = self.db.get(SplitTransaction, split_id)
                        if split:
                            # Get parent
                            repo_cls = trans_repo.repo_map.get(split.source)
                            if repo_cls:
                                parent = self.db.execute(
                                    select(repo_cls.model).where(
                                        repo_cls.model.unique_id == split.transaction_id
                                    )
                                ).scalar_one_or_none()
                                if parent:
                                    details_map[(table, type_, split_id)] = {
                                        "date": parent.date,
                                        "description": f"Split: {parent.description}",
                                        "account_name": parent.account_name,
                                        "provider": parent.provider,
                                        "original_currency": "ILS",
                                    }
                except Exception:
                    pass

        # Apply details to pending items
        for p in pending_list:
            details = details_map.get(
                (p["source_table"], p["source_type"], p["source_id"]), {}
            )
            p.update(details)

        # Fetch linked transactions details
        for p in pending_list:
            if "links" not in p:
                # Fetch links if not already present (repo might not fetch relation if I used get_all_pending_refunds which does distinct?)
                # Actually repo methods separate links. get_pending_by_id fetches links. get_all_pending_refunds returns just pending table.
                # So we need to fetch links for all these items.
                links_df = self.repo.get_links_for_pending(p["id"])
                p["links"] = (
                    links_df.to_dict(orient="records") if not links_df.empty else []
                )

            # Now enrich links
            link_sources = {}
            for link in p["links"]:
                k = (
                    link["refund_source"],
                    "transaction",
                )  # Links are always transactions? Yes, refund_transaction_id.
                if k not in link_sources:
                    link_sources[k] = []
                link_sources[k].append(link["refund_transaction_id"])

            # Fetch details for links
            link_details_map = {}
            for (table, _), ids in link_sources.items():
                try:
                    repo_cls = trans_repo.repo_map.get(table)
                    if repo_cls:
                        model = repo_cls.model
                        stmt = select(model).where(model.unique_id.in_(ids))
                        results = self.db.execute(stmt).scalars().all()
                        for tx in results:
                            link_details_map[(table, tx.unique_id)] = {
                                "date": tx.date,
                                "description": tx.description,
                                "account_name": tx.account_name,
                                "provider": tx.provider,
                                "amount": tx.amount,
                                "original_currency": "ILS",
                            }
                except Exception:
                    pass

            # Apply details to links
            for link in p["links"]:
                details = link_details_map.get(
                    (link["refund_source"], link["refund_transaction_id"]), {}
                )
                link.update(details)

        return pending_list

    def get_pending_by_id(self, pending_refund_id: int) -> dict:
        """
        Get a pending refund with its links.

        Parameters
        ----------
        pending_refund_id : int
            ID of the pending refund.

        Returns
        -------
        dict
            Pending refund with links and calculated totals.

        Raises
        ------
        EntityNotFoundException
            If pending refund not found.
        """
        pending = self.repo.get_by_id(pending_refund_id)
        if not pending:
            raise EntityNotFoundException(
                f"Pending refund {pending_refund_id} not found"
            )

        links_df = self.repo.get_links_for_pending(pending_refund_id)
        links = links_df.to_dict(orient="records") if not links_df.empty else []
        total_refunded = links_df["amount"].sum() if not links_df.empty else 0

        return {
            "id": pending.id,
            "source_type": pending.source_type,
            "source_id": pending.source_id,
            "source_table": pending.source_table,
            "expected_amount": pending.expected_amount,
            "status": pending.status,
            "notes": pending.notes,
            "links": links,
            "total_refunded": total_refunded,
            "remaining": max(0, pending.expected_amount - total_refunded),
        }

    def get_budget_adjustment(self, year: int, month: int) -> float:
        """
        Calculate total amount to exclude from budget for pending refunds.

        For now, this returns the sum of all pending (not resolved) expected amounts.
        In a full implementation, this would filter by transactions in the given month.

        Parameters
        ----------
        year : int
            Budget year.
        month : int
            Budget month.

        Returns
        -------
        float
            Total amount expecting refund (to exclude from budget).
        """
        pending_df = self.repo.get_all_pending_refunds(status="pending")
        if pending_df.empty:
            return 0.0

        # Sum expected amounts for pending refunds
        # Note: In full implementation, would filter by source transaction dates
        return pending_df["expected_amount"].sum()

    def get_active_pending_identifiers(self) -> dict[str, set]:
        """
        Get sets of identifiers for active pending refunds.

        Returns
        -------
        dict[str, set]
            Dictionary with keys 'transaction_ids' and 'split_ids'.
            'transaction_ids' contains unique_ids of transactions.
            'split_ids' contains ids of split transactions.
        """
        pending_df = self.repo.get_all_pending_refunds()
        if pending_df.empty:
            return {"transaction_ids": set(), "split_ids": set()}

        # Filter for active pending refunds (pending or partial)
        active_pending = pending_df[pending_df["status"] != "resolved"]

        # Get transaction unique_ids
        transaction_pending = active_pending[
            active_pending["source_type"] == "transaction"
        ]

        # Get transaction unique_ids (source_id corresponds to unique_id for transactions)
        transaction_ids = set(transaction_pending["source_id"].tolist())

        # Get split ids
        split_pending = active_pending[active_pending["source_type"] == "split"]
        split_ids = set(split_pending["source_id"].tolist())

        return {"transaction_ids": transaction_ids, "split_ids": split_ids}
