"""Pending refund and refund link models."""

from sqlalchemy import Column, Float, Integer, String

from backend.models.base import Base, TimestampMixin
from backend.naming_conventions import Tables


class PendingRefund(Base, TimestampMixin):
    """
    Tracks transactions/splits marked as expecting a refund or payback.

    Attributes
    ----------
    source_type : str
        Type of source: 'transaction' or 'split'.
    source_id : int
        ID of the source (unique_id for transactions, id for splits).
    source_table : str
        Table where the source lives: 'banks', 'credit_cards', 'cash'.
    expected_amount : float
        Positive amount expected to be refunded.
    status : str
        Current status: 'pending', 'resolved', or 'partial'.
    notes : str, optional
        User notes about this pending refund.
    """

    __tablename__ = Tables.PENDING_REFUNDS.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_type = Column(String, nullable=False)  # 'transaction' or 'split'
    source_id = Column(Integer, nullable=False)
    source_table = Column(String, nullable=False)
    expected_amount = Column(Float, nullable=False)
    status = Column(String, default="pending")
    notes = Column(String, nullable=True)


class RefundLink(Base, TimestampMixin):
    """
    Links pending refunds to actual refund transactions.

    Supports multiple partial refunds linking to a single pending refund.

    Attributes
    ----------
    pending_refund_id : int
        ID of the PendingRefund this link belongs to.
    refund_transaction_id : int
        unique_id of the refund transaction.
    refund_source : str
        Table where refund lives: 'banks', 'credit_cards', 'cash'.
    amount : float
        Amount this refund covers (may be partial).
    """

    __tablename__ = Tables.REFUND_LINKS.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    pending_refund_id = Column(Integer, nullable=False)
    refund_transaction_id = Column(Integer, nullable=False)
    refund_source = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
