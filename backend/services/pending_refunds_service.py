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
        Get all pending refunds.

        Parameters
        ----------
        status : str, optional
            Filter by status.

        Returns
        -------
        list[dict]
            List of pending refund records.
        """
        df = self.repo.get_all_pending_refunds(status=status)
        return df.to_dict(orient="records") if not df.empty else []

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
