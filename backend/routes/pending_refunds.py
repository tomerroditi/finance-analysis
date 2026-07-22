"""
Pending Refunds API routes.

Provides endpoints for managing pending refunds and linking refund transactions.
"""

from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.routes.schemas import ApiRequestModel
from backend.services.pending_refunds_service import PendingRefundsService

router = APIRouter(tags=["pending-refunds"])


class CreatePendingRefundRequest(ApiRequestModel):
    """Request to mark a transaction/split as pending refund."""

    source_type: Literal["transaction", "split"]
    source_id: int
    source_table: str
    expected_amount: float
    notes: Optional[str] = None


class LinkRefundRequest(ApiRequestModel):
    """Request to link a refund transaction to a pending refund."""

    refund_transaction_id: int
    refund_source: str
    amount: float


class UpdatePendingRefundRequest(ApiRequestModel):
    """Request to update a pending refund's note."""

    notes: Optional[str] = None


class SourceNoteRequest(ApiRequestModel):
    """Request to set or clear the note on a refund source transaction."""

    refund_source: str
    refund_transaction_id: int
    note: Optional[str] = None


@router.post("/")
def create_pending_refund(
    request: CreatePendingRefundRequest,
    db: Session = Depends(get_database),
):
    """Mark a transaction or split as expecting a refund."""
    service = PendingRefundsService(db)
    return service.mark_as_pending_refund(
        source_type=request.source_type,
        source_id=request.source_id,
        source_table=request.source_table,
        expected_amount=request.expected_amount,
        notes=request.notes,
    )


@router.get("/")
def get_all_pending_refunds(
    status: Optional[str] = None,
    db: Session = Depends(get_database),
):
    """Get all pending refunds, optionally filtered by status."""
    service = PendingRefundsService(db)
    return service.get_all_pending(status=status)


@router.get("/budget-adjustment")
def get_budget_adjustment(
    year: int,
    month: int,
    db: Session = Depends(get_database),
):
    """Return the total amount to exclude from budget expenses for pending refunds.

    Sums the ``expected_amount`` of all currently pending (unresolved) refunds.
    This value can be subtracted from reported expenses in the monthly budget
    view to account for money the user expects to recover. The ``year``/``month``
    parameters are accepted for future filtering but are not yet applied.

    Parameters
    ----------
    year : int
        Budget year (reserved for future month-level filtering).
    month : int
        Budget month 1–12 (reserved for future month-level filtering).

    Returns
    -------
    dict
        ``{"adjustment": float}`` — a positive number representing the sum
        of expected refund amounts outstanding.
    """
    service = PendingRefundsService(db)
    adjustment = service.get_budget_adjustment(year, month)
    return {"adjustment": adjustment}


@router.get("/refund-sources")
def get_refund_sources(
    db: Session = Depends(get_database),
):
    """Summarize refund transactions used as refund sources.

    Returns one entry per refund transaction with its total amount, the
    portion already allocated to pending refunds (and to which ones), and
    the amount still available for further matching.
    """
    service = PendingRefundsService(db)
    return service.get_refund_sources()


@router.put("/refund-sources/note")
def set_refund_source_note(
    request: SourceNoteRequest,
    db: Session = Depends(get_database),
):
    """Set or clear the user note on a refund source transaction."""
    service = PendingRefundsService(db)
    return service.set_source_note(
        refund_source=request.refund_source,
        refund_transaction_id=request.refund_transaction_id,
        note=request.note,
    )


@router.patch("/{pending_id}")
def update_pending_refund(
    pending_id: int,
    request: UpdatePendingRefundRequest,
    db: Session = Depends(get_database),
):
    """Update the note on a pending refund."""
    service = PendingRefundsService(db)
    return service.update_notes(pending_id, request.notes)


@router.get("/{pending_id}")
def get_pending_refund(
    pending_id: int,
    db: Session = Depends(get_database),
):
    """Get a pending refund with its links."""
    service = PendingRefundsService(db)
    return service.get_pending_by_id(pending_id)


@router.delete("/{pending_id}")
def cancel_pending_refund(
    pending_id: int,
    db: Session = Depends(get_database),
):
    """Cancel a pending refund (remove pending status)."""
    service = PendingRefundsService(db)
    service.cancel_pending_refund(pending_id)
    return {"status": "success"}


@router.post("/{pending_id}/link")
def link_refund(
    pending_id: int,
    request: LinkRefundRequest,
    db: Session = Depends(get_database),
):
    """Link a refund transaction to a pending refund."""
    service = PendingRefundsService(db)
    return service.link_refund(
        pending_refund_id=pending_id,
        refund_transaction_id=request.refund_transaction_id,
        refund_source=request.refund_source,
        amount=request.amount,
    )


@router.post("/{pending_id}/close")
def close_pending_refund(
    pending_id: int,
    db: Session = Depends(get_database),
):
    """Close a pending refund, accepting the current partial refund amount."""
    service = PendingRefundsService(db)
    return service.close_pending_refund(pending_id)


@router.delete("/links/{link_id}")
def unlink_refund(
    link_id: int,
    db: Session = Depends(get_database),
):
    """Remove a refund link (unlink transaction)."""
    service = PendingRefundsService(db)
    return service.unlink_refund(link_id)
