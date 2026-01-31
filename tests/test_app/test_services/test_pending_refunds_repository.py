"""Tests for PendingRefundsRepository."""

import pytest

from backend.repositories.pending_refunds_repository import PendingRefundsRepository


class TestPendingRefundsRepository:
    """Test suite for PendingRefundsRepository."""

    def test_create_pending_refund(self, db_session):
        """Create a pending refund record."""
        repo = PendingRefundsRepository(db_session)
        pending = repo.create_pending_refund(
            source_type="transaction",
            source_id=1,
            source_table="credit_cards",
            expected_amount=100.0,
            notes="Friend owes me",
        )
        assert pending.id is not None
        assert pending.status == "pending"
        assert pending.expected_amount == 100.0

    def test_create_pending_refund_minimal(self, db_session):
        """Create a pending refund without optional notes."""
        repo = PendingRefundsRepository(db_session)
        pending = repo.create_pending_refund(
            source_type="split",
            source_id=5,
            source_table="banks",
            expected_amount=50.0,
        )
        assert pending.id is not None
        assert pending.notes is None

    def test_get_all_pending_refunds(self, db_session):
        """Get all pending refunds."""
        repo = PendingRefundsRepository(db_session)
        repo.create_pending_refund("transaction", 1, "banks", 50.0)
        repo.create_pending_refund("split", 2, "credit_cards", 30.0)

        result = repo.get_all_pending_refunds()
        assert len(result) == 2

    def test_get_pending_refunds_filtered_by_status(self, db_session):
        """Filter pending refunds by status."""
        repo = PendingRefundsRepository(db_session)
        pending1 = repo.create_pending_refund("transaction", 1, "banks", 50.0)
        repo.create_pending_refund("transaction", 2, "banks", 30.0)
        repo.update_status(pending1.id, "resolved")

        pending_only = repo.get_all_pending_refunds(status="pending")
        assert len(pending_only) == 1

        resolved_only = repo.get_all_pending_refunds(status="resolved")
        assert len(resolved_only) == 1

    def test_get_by_id(self, db_session):
        """Get a pending refund by ID."""
        repo = PendingRefundsRepository(db_session)
        created = repo.create_pending_refund("transaction", 1, "banks", 100.0)

        fetched = repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.expected_amount == 100.0

    def test_get_by_id_not_found(self, db_session):
        """Return None for non-existent ID."""
        repo = PendingRefundsRepository(db_session)
        result = repo.get_by_id(9999)
        assert result is None

    def test_add_refund_link(self, db_session):
        """Link a refund transaction to a pending refund."""
        repo = PendingRefundsRepository(db_session)
        pending = repo.create_pending_refund("transaction", 1, "banks", 100.0)

        link = repo.add_refund_link(
            pending_refund_id=pending.id,
            refund_transaction_id=99,
            refund_source="banks",
            amount=100.0,
        )
        assert link.id is not None
        assert link.amount == 100.0

    def test_get_links_for_pending(self, db_session):
        """Get all links for a pending refund."""
        repo = PendingRefundsRepository(db_session)
        pending = repo.create_pending_refund("transaction", 1, "banks", 100.0)

        repo.add_refund_link(pending.id, 10, "banks", 50.0)
        repo.add_refund_link(pending.id, 11, "banks", 50.0)

        links = repo.get_links_for_pending(pending.id)
        assert len(links) == 2
        assert links["amount"].sum() == 100.0

    def test_update_status(self, db_session):
        """Update pending refund status."""
        repo = PendingRefundsRepository(db_session)
        pending = repo.create_pending_refund("transaction", 1, "banks", 100.0)

        repo.update_status(pending.id, "resolved")

        updated = repo.get_by_id(pending.id)
        assert updated.status == "resolved"

    def test_delete_pending_refund(self, db_session):
        """Delete a pending refund and its links."""
        repo = PendingRefundsRepository(db_session)
        pending = repo.create_pending_refund("transaction", 1, "banks", 100.0)
        repo.add_refund_link(pending.id, 10, "banks", 100.0)

        repo.delete_pending_refund(pending.id)

        assert repo.get_by_id(pending.id) is None
        # Links should also be deleted
        links = repo.get_links_for_pending(pending.id)
        assert len(links) == 0

    def test_get_pending_for_source(self, db_session):
        """Get pending refund for a specific source."""
        repo = PendingRefundsRepository(db_session)
        repo.create_pending_refund("transaction", 1, "banks", 100.0)
        repo.create_pending_refund("split", 5, "credit_cards", 50.0)

        result = repo.get_pending_for_source("transaction", 1, "banks")
        assert result is not None
        assert result.expected_amount == 100.0

        result2 = repo.get_pending_for_source("split", 5, "credit_cards")
        assert result2 is not None
        assert result2.expected_amount == 50.0

    def test_get_pending_for_source_not_found(self, db_session):
        """Return None when no pending refund exists for source."""
        repo = PendingRefundsRepository(db_session)
        result = repo.get_pending_for_source("transaction", 999, "banks")
        assert result is None
