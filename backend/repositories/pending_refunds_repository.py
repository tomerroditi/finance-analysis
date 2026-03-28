"""Pending refunds repository with SQLAlchemy ORM."""

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.pending_refund import PendingRefund, RefundLink


class PendingRefundsRepository:
    """
    Repository for managing pending refund records using ORM.

    Handles CRUD operations for pending refunds and refund links.
    """

    def __init__(self, db: Session):
        self.db = db

    def create_pending_refund(
        self,
        source_type: str,
        source_id: int,
        source_table: str,
        expected_amount: float,
        notes: str = None,
    ) -> PendingRefund:
        """
        Create a new pending refund record.

        Parameters
        ----------
        source_type : str
            Type of source: 'transaction' or 'split'.
        source_id : int
            ID of the source transaction/split.
        source_table : str
            Table where source lives: 'banks', 'credit_cards', 'cash'.
        expected_amount : float
            Amount expected to be refunded.
        notes : str, optional
            User notes about this pending refund.

        Returns
        -------
        PendingRefund
            The newly created pending refund record.
        """
        pending = PendingRefund(
            source_type=source_type,
            source_id=source_id,
            source_table=source_table,
            expected_amount=expected_amount,
            notes=notes,
        )
        self.db.add(pending)
        self.db.commit()
        self.db.refresh(pending)
        return pending

    def get_all_pending_refunds(self, status: str = None) -> pd.DataFrame:
        """
        Get all pending refunds, optionally filtered by status.

        Parameters
        ----------
        status : str, optional
            Filter by status ('pending', 'resolved', 'partial').

        Returns
        -------
        pd.DataFrame
            DataFrame of pending refund records.
        """
        stmt = select(PendingRefund)
        if status:
            stmt = stmt.where(PendingRefund.status == status)
        return pd.read_sql(stmt, self.db.bind)

    def get_by_id(self, pending_id: int) -> PendingRefund | None:
        """
        Get a pending refund by ID.

        Parameters
        ----------
        pending_id : int
            ID of the pending refund.

        Returns
        -------
        PendingRefund or None
            The pending refund record, or None if not found.
        """
        return self.db.get(PendingRefund, pending_id)

    def get_pending_for_source(
        self,
        source_type: str,
        source_id: int,
        source_table: str,
    ) -> PendingRefund | None:
        """
        Get pending refund for a specific source.

        Parameters
        ----------
        source_type : str
            Type of source: 'transaction' or 'split'.
        source_id : int
            ID of the source.
        source_table : str
            Table where source lives.

        Returns
        -------
        PendingRefund or None
            The pending refund if exists, None otherwise.
        """
        stmt = (
            select(PendingRefund)
            .where(PendingRefund.source_type == source_type)
            .where(PendingRefund.source_id == source_id)
            .where(PendingRefund.source_table == source_table)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def add_refund_link(
        self,
        pending_refund_id: int,
        refund_transaction_id: int,
        refund_source: str,
        amount: float,
    ) -> RefundLink:
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
        RefundLink
            The newly created link.
        """
        link = RefundLink(
            pending_refund_id=pending_refund_id,
            refund_transaction_id=refund_transaction_id,
            refund_source=refund_source,
            amount=amount,
        )
        self.db.add(link)
        self.db.commit()
        self.db.refresh(link)
        return link

    def get_links_for_pending(self, pending_id: int) -> pd.DataFrame:
        """
        Get all refund links for a pending refund.

        Parameters
        ----------
        pending_id : int
            ID of the pending refund.

        Returns
        -------
        pd.DataFrame
            DataFrame of refund links.
        """
        stmt = select(RefundLink).where(RefundLink.pending_refund_id == pending_id)
        return pd.read_sql(stmt, self.db.bind)

    def update_status(self, pending_id: int, status: str) -> None:
        """
        Update the status of a pending refund.

        Parameters
        ----------
        pending_id : int
            ID of the pending refund.
        status : str
            New status ('pending', 'partial', 'resolved', or 'closed').
        """
        pending = self.db.get(PendingRefund, pending_id)
        if pending:
            pending.status = status
            self.db.commit()

    def delete_pending_refund(self, pending_id: int) -> None:
        """
        Delete a pending refund and all its links.

        Parameters
        ----------
        pending_id : int
            ID of the pending refund to delete.
        """
        # Delete links first
        links = (
            self.db.execute(
                select(RefundLink).where(RefundLink.pending_refund_id == pending_id)
            )
            .scalars()
            .all()
        )
        for link in links:
            self.db.delete(link)

        # Delete pending refund
        pending = self.db.get(PendingRefund, pending_id)
        if pending:
            self.db.delete(pending)
        self.db.commit()

    def delete_refund_link(self, link_id: int) -> RefundLink | None:
        """
        Delete a specific refund link.

        Parameters
        ----------
        link_id : int
            ID of the link to delete.

        Returns
        -------
        RefundLink or None
            The deleted link if found, None otherwise.
        """
        link = self.db.get(RefundLink, link_id)
        if link:
            self.db.delete(link)
            self.db.commit()
        return link

    def get_link_by_id(self, link_id: int) -> RefundLink | None:
        """
        Get a refund link by ID.

        Parameters
        ----------
        link_id : int
            ID of the link.

        Returns
        -------
        RefundLink or None
            The link if found, None otherwise.
        """
        return self.db.get(RefundLink, link_id)
