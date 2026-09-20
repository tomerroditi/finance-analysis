"""Pending refunds service with business logic."""

import logging
from typing import Literal, Optional

import pandas as pd
from sqlalchemy.orm import Session

from backend.constants.tables import TransactionsTableFields
from backend.errors import EntityNotFoundException, ValidationException
from backend.models.transaction import SplitTransaction
from backend.repositories.pending_refunds_repository import PendingRefundsRepository
from backend.repositories.transactions_repository import TransactionsRepository

logger = logging.getLogger(__name__)


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
        self.transactions_repo = TransactionsRepository(db)

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
            If expected_amount is not positive, exceeds the source amount,
            the source transaction/split does not exist, or the source is
            already marked.
        """
        if expected_amount <= 0:
            raise ValidationException("Expected refund amount must be positive")

        # Store the canonical table name. Callers pass service names ("banks")
        # or table names ("bank_transactions") interchangeably, and the
        # re-scrape purge guard in the ingestion repository matches on the
        # table name — a row saved as "banks" left its transaction unprotected
        # and the refund orphaned when the row was re-scraped.
        source_table = self._canonical_source(source_table)

        # A refund can only be expected on money that was actually spent: the
        # source must resolve, and the expectation is capped at its amount.
        source_amount = self._resolve_source_amount(
            source_type, source_id, source_table
        )
        if expected_amount > abs(source_amount) + 1e-6:
            raise ValidationException(
                f"Expected refund amount cannot exceed the {source_type} "
                f"amount ({abs(source_amount):.2f})"
            )

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

    def _resolve_source_amount(
        self, source_type: str, source_id: int, source_table: str
    ) -> float:
        """
        Look up the amount of the transaction or split a refund is marked on.

        Parameters
        ----------
        source_type : str
            Either 'transaction' or 'split'.
        source_id : int
            unique_id for transactions, split id for splits.
        source_table : str
            Canonical table name of the transaction (ignored for splits,
            whose ids are global).

        Returns
        -------
        float
            The signed amount of the source row.

        Raises
        ------
        ValidationException
            If the source table is unknown or the row does not exist.
        """
        if source_type == "split":
            split = self.db.get(SplitTransaction, source_id)
            if split is None:
                raise ValidationException(f"Split {source_id} does not exist")
            return float(split.amount)

        if self.transactions_repo.repo_map.get(source_table) is None:
            raise ValidationException(f"Unknown source table '{source_table}'")
        txn = self._get_refund_transaction(source_id, source_table)
        if txn is None:
            raise ValidationException(
                f"Transaction {source_id} does not exist in {source_table}"
            )
        return float(txn.amount)

    def _get_refund_transaction(self, transaction_id: int, source: str):
        """
        Resolve a refund transaction ORM row from its id and source table.

        Parameters
        ----------
        transaction_id : int
            unique_id of the transaction.
        source : str
            Table or service name where the transaction lives.

        Returns
        -------
        object or None
            The ORM transaction row, or None when the source/transaction
            can't be resolved.
        """
        from sqlalchemy import select

        repo = self.transactions_repo.repo_map.get(source)
        if not repo:
            return None
        return self.db.execute(
            select(repo.model).where(repo.model.unique_id == transaction_id)
        ).scalar_one_or_none()

    def get_allocated_for_transaction(
        self, transaction_id: int, source: str
    ) -> float:
        """
        Total amount of a refund transaction already allocated to refunds.

        Sums link amounts across ALL pending refunds this transaction funds.
        Source strings are normalized (table vs service name variants), so
        links recorded as ``"banks"`` and ``"bank_transactions"`` count as
        the same transaction.

        Parameters
        ----------
        transaction_id : int
            unique_id of the refund transaction.
        source : str
            Table or service name where the transaction lives.

        Returns
        -------
        float
            Total allocated amount (0.0 when unlinked).
        """
        links = self.repo.get_all_links()
        if links.empty:
            return 0.0
        canonical = self._canonical_source(source)
        mask = (links["refund_transaction_id"] == transaction_id) & (
            links["refund_source"].map(self._canonical_source) == canonical
        )
        return float(links.loc[mask, "amount"].sum())

    def _canonical_source(self, source: str) -> str:
        """
        Normalize a source string to its canonical table name.

        Parameters
        ----------
        source : str
            Table or service name (e.g. ``"banks"`` or ``"bank_transactions"``).

        Returns
        -------
        str
            The table name when resolvable, the input otherwise.
        """
        repo = self.transactions_repo.repo_map.get(source)
        return repo.model.__tablename__ if repo else source

    def link_refund(
        self,
        pending_refund_id: int,
        refund_transaction_id: int,
        refund_source: str,
        amount: float,
    ) -> dict:
        """
        Link a refund transaction to a pending refund.

        A single refund transaction may fund multiple pending refunds, as
        long as the total allocated across all of them does not exceed the
        transaction's amount. The linked amount is clamped to the pending
        refund's remaining expectation.

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
        ValidationException
            If the amount is not positive, ``refund_source`` is not a known
            table, the transaction is already linked to this pending refund,
            or the amount exceeds what's still available on the transaction.
        """
        pending = self.repo.get_by_id(pending_refund_id)
        if not pending:
            raise EntityNotFoundException(
                f"Pending refund {pending_refund_id} not found"
            )

        if pending.status in ("closed", "resolved"):
            raise ValidationException(
                f"Cannot link a refund to a {pending.status} record"
            )

        if amount <= 0:
            raise ValidationException("Refund amount must be positive")

        if self.transactions_repo.repo_map.get(refund_source) is None:
            raise ValidationException(f"Unknown refund source '{refund_source}'")

        # The same transaction may fund several pending refunds, but only
        # once per pending refund.
        existing_links = self.repo.get_links_for_pending(pending_refund_id)
        if not existing_links.empty:
            canonical = self._canonical_source(refund_source)
            duplicate = (
                (existing_links["refund_transaction_id"] == refund_transaction_id)
                & (
                    existing_links["refund_source"].map(self._canonical_source)
                    == canonical
                )
            ).any()
            if duplicate:
                raise ValidationException(
                    "This transaction is already linked to this refund request"
                )

        # Validate against the money still available on the transaction
        # (skipped when the transaction can't be resolved, e.g. manual data).
        txn = self._get_refund_transaction(refund_transaction_id, refund_source)
        if txn is not None:
            allocated = self.get_allocated_for_transaction(
                refund_transaction_id, refund_source
            )
            available = float(txn.amount) - allocated
            if amount > available + 1e-6:
                raise ValidationException(
                    f"Only {max(0.0, available):.2f} of this transaction is still "
                    "available for refund matching"
                )

        # Clamp to the pending refund's remaining expectation
        already_refunded = (
            existing_links["amount"].sum() if not existing_links.empty else 0
        )
        remaining = max(0, pending.expected_amount - already_refunded)
        actual_link_amount = min(amount, remaining) if remaining > 0 else amount

        # Add the link (store the canonical table name so links of the same
        # transaction always group together)
        self.repo.add_refund_link(
            pending_refund_id=pending_refund_id,
            refund_transaction_id=refund_transaction_id,
            refund_source=self._canonical_source(refund_source),
            amount=actual_link_amount,
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

    def update_notes(self, pending_refund_id: int, notes: Optional[str]) -> dict:
        """
        Update the note on a pending refund.

        Parameters
        ----------
        pending_refund_id : int
            ID of the pending refund.
        notes : str or None
            New note text; None or empty clears the note.

        Returns
        -------
        dict
            ``{"id": ..., "notes": ...}`` with the stored value.

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

        cleaned = (notes or "").strip() or None
        self.repo.update_notes(pending_refund_id, cleaned)
        return {"id": pending_refund_id, "notes": cleaned}

    def set_source_note(
        self, refund_source: str, refund_transaction_id: int, note: Optional[str]
    ) -> dict:
        """
        Create, update, or clear the note on a refund source transaction.

        Parameters
        ----------
        refund_source : str
            Table or service name where the transaction lives (normalized to
            the canonical table name before storing).
        refund_transaction_id : int
            unique_id of the refund transaction.
        note : str or None
            Note text; None or empty deletes the note.

        Returns
        -------
        dict
            ``{"refund_source", "refund_transaction_id", "note"}`` with the
            stored (canonicalized) values.
        """
        canonical = self._canonical_source(refund_source)
        cleaned = (note or "").strip()
        if cleaned:
            self.repo.upsert_source_note(
                canonical, refund_transaction_id, cleaned
            )
        else:
            self.repo.delete_source_note(canonical, refund_transaction_id)
        return {
            "refund_source": canonical,
            "refund_transaction_id": refund_transaction_id,
            "note": cleaned or None,
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

        df = self.repo.get_all_pending_refunds(status=status)
        pending_list = df.to_dict(orient="records") if not df.empty else []

        if not pending_list:
            return []

        trans_repo = self.transactions_repo

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
                    repo = trans_repo.repo_map.get(table)
                    if repo:
                        model = repo.model
                        # Fetch transactions
                        stmt = select(model).where(model.unique_id.in_(ids))
                        results = self.db.execute(stmt).scalars().all()
                        for tx in results:
                            details_map[(table, type_, tx.unique_id)] = {
                                "date": tx.date,
                                "description": tx.description,
                                "account_name": tx.account_name,
                                "provider": tx.provider,
                                "category": tx.category,
                                "tag": tx.tag,
                                "original_currency": "ILS",  # Assumption
                            }
                except Exception:
                    logger.warning(
                        "Failed to enrich pending refunds from %s", table, exc_info=True
                    )
            elif type_ == "split":
                # For splits, we need to get the split record to find the parent transaction
                # Then get details from the parent
                try:
                    # We can't batch efficiently across mixed split IDs easily without ORM for splits
                    # But we can iterate. Optimally we'd use SplitTransactionsRepository.
                    # Since split repo is SQL-based/Pandas in parts, let's use the DB directly for efficiency if possible
                    # or just use the repo.
                    for split_id in ids:
                        split = self.db.get(SplitTransaction, split_id)
                        if split:
                            # Get parent
                            repo = trans_repo.repo_map.get(split.source)
                            if repo:
                                parent = self.db.execute(
                                    select(repo.model).where(
                                        repo.model.unique_id == split.transaction_id
                                    )
                                ).scalar_one_or_none()
                                if parent:
                                    details_map[(table, type_, split_id)] = {
                                        "date": parent.date,
                                        "description": f"Split: {parent.description}",
                                        "account_name": parent.account_name,
                                        "provider": parent.provider,
                                        "category": split.category,
                                        "tag": split.tag,
                                        "original_currency": "ILS",
                                    }
                except Exception:
                    logger.warning(
                        "Failed to enrich pending refund splits from %s",
                        table,
                        exc_info=True,
                    )

        # Apply details to pending items
        for p in pending_list:
            details = details_map.get(
                (p["source_table"], p["source_type"], p["source_id"]), {}
            )
            p.update(details)

        # Fetch linked transactions details — one batched query for every
        # pending item instead of one query per item.
        missing_link_ids = [p["id"] for p in pending_list if "links" not in p]
        all_links_df = self.repo.get_links_for_pendings(missing_link_ids)
        links_by_pending: dict[int, list[dict]] = {}
        if not all_links_df.empty:
            for pending_id, group in all_links_df.groupby("pending_refund_id"):
                links_by_pending[int(pending_id)] = group.to_dict(orient="records")

        for p in pending_list:
            if "links" not in p:
                p["links"] = links_by_pending.get(int(p["id"]), [])

            # Normalize legacy source-name variants so the frontend can key
            # links of the same transaction consistently.
            for link in p["links"]:
                link["refund_source"] = self._canonical_source(
                    link["refund_source"]
                )

            # Compute totals from links
            total_refunded = sum(link["amount"] for link in p["links"])
            p["total_refunded"] = total_refunded
            p["remaining"] = max(0, p["expected_amount"] - total_refunded)

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
                    repo = trans_repo.repo_map.get(table)
                    if repo:
                        model = repo.model
                        stmt = select(model).where(model.unique_id.in_(ids))
                        results = self.db.execute(stmt).scalars().all()
                        for tx in results:
                            # NOTE: the link's own `amount` is the allocated
                            # portion — never overwrite it with the full
                            # transaction amount.
                            link_details_map[(table, tx.unique_id)] = {
                                "date": tx.date,
                                "description": tx.description,
                                "account_name": tx.account_name,
                                "provider": tx.provider,
                                "transaction_amount": tx.amount,
                                "original_currency": "ILS",
                            }
                except Exception:
                    logger.warning(
                        "Failed to enrich refund links from %s", table, exc_info=True
                    )

            # Apply details to links
            for link in p["links"]:
                details = link_details_map.get(
                    (link["refund_source"], link["refund_transaction_id"]), {}
                )
                link.update(details)

        return pending_list

    def get_refund_sources(self) -> list[dict]:
        """
        Summarize every refund transaction used as a refund source.

        Groups all refund links by the underlying transaction and reports,
        per transaction, how much of it is allocated to which pending
        refunds and how much is still available for further matching.

        Returns
        -------
        list[dict]
            One entry per refund transaction with keys:
            ``refund_source``, ``refund_transaction_id``, ``description``,
            ``date``, ``account_name``, ``provider``, ``transaction_amount``
            (None when the transaction can't be resolved),
            ``total_allocated``, ``available`` (None when unresolvable),
            ``note`` (user note on the source, None when absent) and
            ``allocations`` — a list of ``{link_id, pending_refund_id,
            amount, pending_description, pending_status, pending_date,
            expected_amount}``.
        """
        pendings = self.get_all_pending()

        notes_df = self.repo.get_all_source_notes()
        notes_map: dict[tuple[str, int], str] = {}
        if not notes_df.empty:
            for _, row in notes_df.iterrows():
                notes_map[
                    (
                        self._canonical_source(row["refund_source"]),
                        int(row["refund_transaction_id"]),
                    )
                ] = row["note"]

        sources: dict[tuple[str, int], dict] = {}
        for p in pendings:
            for link in p.get("links", []):
                key = (
                    self._canonical_source(link["refund_source"]),
                    int(link["refund_transaction_id"]),
                )
                entry = sources.setdefault(
                    key,
                    {
                        "refund_source": key[0],
                        "refund_transaction_id": key[1],
                        "description": link.get("description"),
                        "date": link.get("date"),
                        "account_name": link.get("account_name"),
                        "provider": link.get("provider"),
                        "transaction_amount": link.get("transaction_amount"),
                        "total_allocated": 0.0,
                        "note": notes_map.get(key),
                        "allocations": [],
                    },
                )
                entry["total_allocated"] += float(link["amount"])
                entry["allocations"].append(
                    {
                        "link_id": link["id"],
                        "pending_refund_id": p["id"],
                        "amount": link["amount"],
                        "pending_description": p.get("description"),
                        "pending_status": p["status"],
                        "pending_date": p.get("date"),
                        "expected_amount": p["expected_amount"],
                    }
                )

        result = []
        for entry in sources.values():
            txn_amount = entry["transaction_amount"]
            entry["available"] = (
                max(0.0, float(txn_amount) - entry["total_allocated"])
                if txn_amount is not None
                else None
            )
            result.append(entry)

        result.sort(key=lambda e: str(e["date"] or ""), reverse=True)
        return result

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

        Includes full expected_amount for pending refunds and remaining
        amount for partial refunds. Excludes resolved and closed refunds.

        Parameters
        ----------
        year : int
            Budget year (reserved for future filtering).
        month : int
            Budget month (reserved for future filtering).

        Returns
        -------
        float
            Total amount expecting refund (to exclude from budget).
        """
        pending_df = self.repo.get_all_pending_refunds(status="pending")
        pending_total = pending_df["expected_amount"].sum() if not pending_df.empty else 0.0

        partial_df = self.repo.get_all_pending_refunds(status="partial")
        partial_remaining = 0.0
        if not partial_df.empty:
            for _, row in partial_df.iterrows():
                links = self.repo.get_links_for_pending(int(row["id"]))
                total_refunded = links["amount"].sum() if not links.empty else 0
                partial_remaining += max(0, row["expected_amount"] - total_refunded)

        return pending_total + partial_remaining

    def close_pending_refund(self, pending_refund_id: int) -> dict:
        """
        Close a pending refund, accepting whatever has been refunded so far.

        Parameters
        ----------
        pending_refund_id : int
            ID of the pending refund to close.

        Returns
        -------
        dict
            Updated pending refund with closed status.

        Raises
        ------
        EntityNotFoundException
            If pending refund not found.
        ValidationException
            If refund is already resolved or closed.
        """
        pending = self.repo.get_by_id(pending_refund_id)
        if not pending:
            raise EntityNotFoundException(
                f"Pending refund {pending_refund_id} not found"
            )

        if pending.status in ("resolved", "closed"):
            raise ValidationException(
                f"Cannot close a refund that is already {pending.status}"
            )

        self.repo.update_status(pending_refund_id, "closed")

        links = self.repo.get_links_for_pending(pending_refund_id)
        total_refunded = links["amount"].sum() if not links.empty else 0

        return {
            "id": pending_refund_id,
            "status": "closed",
            "expected_amount": pending.expected_amount,
            "total_refunded": total_refunded,
            "remaining": max(0, pending.expected_amount - total_refunded),
        }

    def unlink_refund(self, link_id: int) -> dict:
        """
        Unlink a refund transaction from its pending refund and recalculate status.

        Parameters
        ----------
        link_id : int
            ID of the refund link to remove.

        Returns
        -------
        dict
            Updated pending refund status with recalculated totals.

        Raises
        ------
        EntityNotFoundException
            If link not found.
        """
        link = self.repo.get_link_by_id(link_id)
        if not link:
            raise EntityNotFoundException(f"Refund link {link_id} not found")

        pending_refund_id = link.pending_refund_id
        pending = self.repo.get_by_id(pending_refund_id)
        if not pending:
            raise EntityNotFoundException(
                f"Pending refund {pending_refund_id} not found"
            )

        if pending.status == "closed":
            raise ValidationException("Cannot unlink a refund from a closed record")

        self.repo.delete_refund_link(link_id)

        links = self.repo.get_links_for_pending(pending_refund_id)
        total_refunded = links["amount"].sum() if not links.empty else 0

        if total_refunded <= 0:
            new_status = "pending"
        elif total_refunded >= pending.expected_amount:
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

    def get_active_pending_identifiers(self) -> dict[str, set]:
        """
        Get sets of identifiers for active pending refunds.

        Transactions are keyed by ``(canonical_table, unique_id)`` rather than
        by bare ``unique_id``: ``unique_id`` is a per-table auto-increment, so
        bank #5 and credit-card #5 are different transactions. Keying on the
        bare id would make one pending refund mask up to one transaction per
        source table.

        Splits stay keyed by bare id — ``split_transactions`` is a single
        table, so its ids are globally unique.

        Returns
        -------
        dict[str, set]
            Dictionary with keys 'transaction_keys' and 'split_ids'.
            'transaction_keys' contains ``(table_name, unique_id)`` tuples.
            'split_ids' contains ids of split transactions.
        """
        pending_df = self.repo.get_all_pending_refunds()
        if pending_df.empty:
            return {"transaction_keys": set(), "split_ids": set()}

        # Filter for active pending refunds (pending or partial)
        active_pending = pending_df[~pending_df["status"].isin(["resolved", "closed"])]

        # Pair each transaction id with its canonical source table so the
        # merged (cross-table) analysis frame can be filtered unambiguously.
        transaction_pending = active_pending[
            active_pending["source_type"] == "transaction"
        ]
        transaction_keys = {
            (self._canonical_source(row["source_table"]), row["source_id"])
            for _, row in transaction_pending.iterrows()
        }

        # Get split ids
        split_pending = active_pending[active_pending["source_type"] == "split"]
        split_ids = set(split_pending["source_id"].tolist())

        return {"transaction_keys": transaction_keys, "split_ids": split_ids}

    def get_refund_amount_adjustments(
        self, exclude_open: bool = True
    ) -> dict[str, dict]:
        """
        Build per-row amount adjustments that net matched refunds against the
        purchases they pay back, whatever months the two landed in.

        A refund is not the receiving month's income, and the purchase it
        cancels is not the spending month's expense. Netting by date — what an
        unlinked positive amount in an expense category does — only works when
        both fall in the same month; a January purchase refunded in March
        otherwise overstates January and understates March. Every
        ``refund_links`` row names the purchase an incoming transaction pays
        back and how much of it, so the matched money can be taken off both
        sides wherever each one sits.

        Adjustments are signed values to **add** to a row's ``amount``: a
        -1,000 purchase refunded in full gets +1,000 and the +1,000 refund
        transaction gets -1,000, so neither month sees either.

        Parameters
        ----------
        exclude_open : bool, optional
            When ``True``, the still-outstanding part of an *open*
            (``pending`` / ``partial``) expectation is taken off the purchase
            too — the "Pending Refunds Excluded" view. A ``closed`` refund is
            money the user gave up on, so its unmatched remainder always stays
            an expense however this is set. Default is ``True``.

        Returns
        -------
        dict[str, dict]
            ``{"transactions": {(table, unique_id): adjustment},
            "splits": {split_id: adjustment}}``.
        """
        empty: dict[str, dict] = {"transactions": {}, "splits": {}}
        pending_df = self.repo.get_all_pending_refunds()
        if pending_df.empty:
            return empty

        links_df = self.repo.get_links_for_pendings(
            [int(v) for v in pending_df["id"].tolist()]
        )
        links_by_pending = (
            dict(tuple(links_df.groupby("pending_refund_id")))
            if not links_df.empty
            else {}
        )

        tx_adj: dict[tuple[str, int], float] = {}
        split_adj: dict[int, float] = {}

        for _, pending in pending_df.iterrows():
            links = links_by_pending.get(pending["id"])
            matched = float(links["amount"].sum()) if links is not None else 0.0

            # Take the matched money back off the refund transactions that
            # carried it. One incoming transaction may fund several
            # expectations, so only its linked share is removed — the rest is
            # somebody else's refund, or genuine income.
            if links is not None:
                for _, link in links.iterrows():
                    key = (
                        self._canonical_source(link["refund_source"]),
                        int(link["refund_transaction_id"]),
                    )
                    tx_adj[key] = tx_adj.get(key, 0.0) - float(link["amount"])

            credit = matched
            if exclude_open and pending["status"] in ("pending", "partial"):
                credit += max(
                    0.0, float(pending["expected_amount"]) - matched
                )
            if credit <= 0:
                continue

            if pending["source_type"] == "split":
                split_id = int(pending["source_id"])
                split_adj[split_id] = split_adj.get(split_id, 0.0) + credit
            else:
                key = (
                    self._canonical_source(pending["source_table"]),
                    int(pending["source_id"]),
                )
                tx_adj[key] = tx_adj.get(key, 0.0) + credit

        return {"transactions": tx_adj, "splits": split_adj}


#: Column holding a row's pre-netting amount when netting is asked to keep it.
#: Budget envelopes total the netted amount but list the real transactions, so
#: they need both on the same frame.
GROSS_AMOUNT_COLUMN = "_gross_amount"


def restore_gross_amounts(df: pd.DataFrame) -> pd.DataFrame:
    """
    Undo netting on a frame about to be handed to the client as transactions.

    An envelope totals what a month *cost* — net of refunds — but the rows
    underneath it are real transactions the user can select, retag, split or
    mark as awaiting a refund, and those actions validate against the amount
    actually in the database. Serving a netted amount there would show a
    ``1,000`` charge as ``700`` and let the user reason (and act) on a figure
    no table elsewhere agrees with. So the sum nets and the list does not.

    Parameters
    ----------
    df : pd.DataFrame
        Frame that may carry :data:`GROSS_AMOUNT_COLUMN`.

    Returns
    -------
    pd.DataFrame
        A copy with ``amount`` restored and the helper column dropped, or
        ``df`` unchanged when it was never netted.
    """
    if GROSS_AMOUNT_COLUMN not in df.columns:
        return df
    df = df.copy()
    df["amount"] = df[GROSS_AMOUNT_COLUMN]
    return df.drop(columns=[GROSS_AMOUNT_COLUMN])


def apply_refund_amount_adjustments(
    df: pd.DataFrame,
    adjustments: dict[str, dict],
    keep_gross_in: str | None = None,
) -> pd.DataFrame:
    """
    Net matched refunds out of a transactions frame.

    Adds each row's adjustment (see
    :meth:`PendingRefundsService.get_refund_amount_adjustments`) to its
    ``amount``, clamped so no row can cross zero: netting reduces what a
    purchase cost and what a refund returned, it never turns an expense into
    income or the reverse. The clamp is load-bearing rather than defensive —
    ``link_refund`` deliberately allows a link past the expected amount once
    the expectation is already met, so the credit on a purchase can exceed it.

    Rows netted to zero are kept, not dropped: they contribute nothing to a
    sum, and a caller that filters on sign (``amount < 0``) drops them anyway.

    Parameters
    ----------
    df : pd.DataFrame
        Transactions frame carrying ``source``, ``unique_id`` and ``amount``;
        ``split_id`` when split children are present.
    adjustments : dict[str, dict]
        ``{"transactions": ..., "splits": ...}`` as built by the service.
    keep_gross_in : str or None, optional
        When given, the pre-netting amount is preserved in this column (see
        :func:`restore_gross_amounts`). Default is ``None``.

    Returns
    -------
    pd.DataFrame
        A copy with ``amount`` netted, or ``df`` unchanged when there is
        nothing to net.
    """
    tx_adj = adjustments.get("transactions") or {}
    split_adj = adjustments.get("splits") or {}
    if df.empty or (not tx_adj and not split_adj):
        return df

    source_col = TransactionsTableFields.SOURCE.value
    unique_id_col = TransactionsTableFields.UNIQUE_ID.value
    split_id_col = TransactionsTableFields.SPLIT_ID.value

    df = df.copy()
    adj = pd.Series(0.0, index=df.index)

    if tx_adj:
        # `unique_id` is a per-table auto-increment, so it only identifies a
        # row alongside its source table.
        keys = pd.Series(
            list(zip(df[source_col], df[unique_id_col])), index=df.index
        )
        adj = adj.add(keys.map(tx_adj).fillna(0.0).astype(float))
    if split_adj and split_id_col in df.columns:
        adj = adj.add(df[split_id_col].map(split_adj).fillna(0.0).astype(float))

    original = df["amount"].astype(float)
    if keep_gross_in is not None:
        df[keep_gross_in] = original
    netted = original + adj
    df["amount"] = netted.clip(upper=0.0).where(
        original < 0, netted.clip(lower=0.0)
    )
    return df
