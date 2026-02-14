"""Tests for PendingRefundsService."""

import pytest

from backend.errors import EntityNotFoundException, ValidationException
from backend.repositories.pending_refunds_repository import PendingRefundsRepository
from backend.services.pending_refunds_service import PendingRefundsService


class TestPendingRefundsService:
    """Test suite for PendingRefundsService."""

    def test_mark_as_pending_refund_transaction(self, db_session):
        """Mark a transaction as pending refund."""
        service = PendingRefundsService(db_session)
        result = service.mark_as_pending_refund(
            source_type="transaction",
            source_id=1,
            source_table="credit_cards",
            expected_amount=100.0,
            notes="Friend owes me",
        )
        assert result["id"] is not None
        assert result["status"] == "pending"
        assert result["expected_amount"] == 100.0

    def test_mark_as_pending_refund_split(self, db_session):
        """Mark a split as pending refund."""
        service = PendingRefundsService(db_session)
        result = service.mark_as_pending_refund(
            source_type="split",
            source_id=5,
            source_table="banks",
            expected_amount=50.0,
        )
        assert result["source_type"] == "split"

    def test_mark_as_pending_refund_invalid_amount(self, db_session):
        """Reject non-positive expected amounts."""
        service = PendingRefundsService(db_session)
        with pytest.raises(ValidationException):
            service.mark_as_pending_refund(
                source_type="transaction",
                source_id=1,
                source_table="banks",
                expected_amount=0,
            )

    def test_mark_as_pending_refund_already_exists(self, db_session):
        """Reject marking same source twice."""
        service = PendingRefundsService(db_session)
        service.mark_as_pending_refund("transaction", 1, "banks", 100.0)

        with pytest.raises(ValidationException):
            service.mark_as_pending_refund("transaction", 1, "banks", 50.0)

    def test_link_refund_full(self, db_session):
        """Link a full refund to pending."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)

        result = service.link_refund(
            pending_refund_id=pending["id"],
            refund_transaction_id=99,
            refund_source="banks",
            amount=100.0,
        )

        assert result["status"] == "resolved"
        assert result["total_refunded"] == 100.0

    def test_link_refund_partial(self, db_session):
        """Link a partial refund updates status to partial."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)

        result = service.link_refund(
            pending_refund_id=pending["id"],
            refund_transaction_id=99,
            refund_source="banks",
            amount=50.0,
        )

        assert result["status"] == "partial"
        assert result["total_refunded"] == 50.0
        assert result["remaining"] == 50.0

    def test_link_refund_multiple_partials(self, db_session):
        """Multiple partial refunds sum to full resolution."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)

        service.link_refund(pending["id"], 99, "banks", 50.0)
        result = service.link_refund(pending["id"], 100, "banks", 50.0)

        assert result["status"] == "resolved"
        assert result["total_refunded"] == 100.0

    def test_link_refund_not_found(self, db_session):
        """Error when pending refund not found."""
        service = PendingRefundsService(db_session)
        with pytest.raises(EntityNotFoundException):
            service.link_refund(9999, 99, "banks", 100.0)

    def test_cancel_pending_refund(self, db_session):
        """Cancel a pending refund."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)

        service.cancel_pending_refund(pending["id"])

        repo = PendingRefundsRepository(db_session)
        assert repo.get_by_id(pending["id"]) is None

    def test_cancel_pending_refund_not_found(self, db_session):
        """Error when canceling non-existent pending refund."""
        service = PendingRefundsService(db_session)
        with pytest.raises(EntityNotFoundException):
            service.cancel_pending_refund(9999)

    def test_get_all_pending(self, db_session):
        """Get all pending refunds."""
        service = PendingRefundsService(db_session)
        service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        service.mark_as_pending_refund("split", 2, "credit_cards", 50.0)

        result = service.get_all_pending()
        assert len(result) == 2

    def test_get_pending_by_id(self, db_session):
        """Get a single pending refund with its links."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        service.link_refund(pending["id"], 99, "banks", 50.0)

        result = service.get_pending_by_id(pending["id"])
        assert result["expected_amount"] == 100.0
        assert result["total_refunded"] == 50.0
        assert len(result["links"]) == 1
