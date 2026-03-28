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

    def test_link_refund_to_closed_rejected(self, db_session):
        """Cannot link a refund to a closed record."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        service.close_pending_refund(pending["id"])
        with pytest.raises(ValidationException):
            service.link_refund(pending["id"], 99, "banks", 50.0)

    def test_link_refund_to_resolved_rejected(self, db_session):
        """Cannot link a refund to a resolved record."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        service.link_refund(pending["id"], 99, "banks", 100.0)
        with pytest.raises(ValidationException):
            service.link_refund(pending["id"], 100, "banks", 50.0)

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


class TestUnlinkRefund:
    """Tests for unlink_refund with status recalculation."""

    def test_unlink_refund_reverts_resolved_to_partial(self, db_session):
        """Unlinking one of multiple links reverts resolved to partial."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        service.link_refund(pending["id"], 99, "banks", 60.0)
        result = service.link_refund(pending["id"], 100, "banks", 40.0)
        assert result["status"] == "resolved"
        details = service.get_pending_by_id(pending["id"])
        link_id = details["links"][1]["id"]
        result = service.unlink_refund(link_id)
        assert result["status"] == "partial"
        assert result["total_refunded"] == 60.0

    def test_unlink_refund_reverts_partial_to_pending(self, db_session):
        """Unlinking the only link reverts partial to pending."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        service.link_refund(pending["id"], 99, "banks", 50.0)
        details = service.get_pending_by_id(pending["id"])
        link_id = details["links"][0]["id"]
        result = service.unlink_refund(link_id)
        assert result["status"] == "pending"
        assert result["total_refunded"] == 0

    def test_unlink_refund_from_closed_rejected(self, db_session):
        """Cannot unlink a refund from a closed record."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        service.link_refund(pending["id"], 99, "banks", 50.0)
        service.close_pending_refund(pending["id"])
        details = service.get_pending_by_id(pending["id"])
        link_id = details["links"][0]["id"]
        with pytest.raises(ValidationException):
            service.unlink_refund(link_id)

    def test_unlink_refund_not_found(self, db_session):
        """Error when link not found."""
        service = PendingRefundsService(db_session)
        with pytest.raises(EntityNotFoundException):
            service.unlink_refund(9999)


class TestClosePendingRefund:
    """Tests for closing a pending refund as accepted partial."""

    def test_close_pending_refund(self, db_session):
        """Close a pending refund sets status to closed."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        result = service.close_pending_refund(pending["id"])
        assert result["status"] == "closed"

    def test_close_partial_refund(self, db_session):
        """Close a partial refund preserves links and sets status to closed."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        service.link_refund(pending["id"], 99, "banks", 50.0)
        result = service.close_pending_refund(pending["id"])
        assert result["status"] == "closed"
        assert result["total_refunded"] == 50.0

    def test_close_resolved_refund_rejected(self, db_session):
        """Cannot close an already resolved refund."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        service.link_refund(pending["id"], 99, "banks", 100.0)
        with pytest.raises(ValidationException):
            service.close_pending_refund(pending["id"])

    def test_close_already_closed_refund_rejected(self, db_session):
        """Cannot close a refund that is already closed."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        service.close_pending_refund(pending["id"])
        with pytest.raises(ValidationException):
            service.close_pending_refund(pending["id"])

    def test_close_not_found(self, db_session):
        """Error when pending refund not found."""
        service = PendingRefundsService(db_session)
        with pytest.raises(EntityNotFoundException):
            service.close_pending_refund(9999)


class TestGetAllPendingEnrichment:
    """Tests for get_all_pending enrichment with real transaction data."""

    def test_enriches_transaction_source_details(self, db_session, seed_base_transactions):
        """Verify get_all_pending enriches transaction-sourced pending refunds with details."""
        from backend.models.transaction import BankTransaction

        # Find a real bank transaction to reference
        bank_txn = db_session.query(BankTransaction).first()
        assert bank_txn is not None

        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund(
            "transaction", bank_txn.unique_id, "banks", 50.0,
        )

        result = service.get_all_pending()
        item = next(p for p in result if p["id"] == pending["id"])

        # Should be enriched with transaction details
        assert "date" in item
        assert "description" in item

    def test_enriches_link_details(self, db_session, seed_base_transactions):
        """Verify get_all_pending enriches linked refund transactions with details."""
        from backend.models.transaction import BankTransaction

        bank_txns = db_session.query(BankTransaction).limit(2).all()
        assert len(bank_txns) >= 2

        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund(
            "transaction", bank_txns[0].unique_id, "banks", 100.0,
        )
        service.link_refund(
            pending["id"], bank_txns[1].unique_id, "banks", 50.0,
        )

        result = service.get_all_pending()
        item = next(p for p in result if p["id"] == pending["id"])

        # Links should be enriched with transaction details
        assert len(item["links"]) == 1
        link = item["links"][0]
        assert "date" in link
        assert "description" in link

    def test_enriches_split_source_details(self, db_session, seed_base_transactions, seed_split_transactions):
        """Verify get_all_pending enriches split-sourced pending refunds with parent details."""
        from backend.models.transaction import SplitTransaction

        split = db_session.query(SplitTransaction).first()
        if split is None:
            pytest.skip("No split transactions in seed data")

        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund(
            "split", split.id, split.source, 25.0,
        )

        result = service.get_all_pending()
        item = next(p for p in result if p["id"] == pending["id"])

        # Should be enriched from parent transaction
        assert "description" in item

    def test_graceful_on_missing_source_transaction(self, db_session):
        """Verify enrichment gracefully handles nonexistent source transaction IDs."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund(
            "transaction", 99999, "banks", 100.0,
        )

        # Should not raise even though transaction ID doesn't exist
        result = service.get_all_pending()
        assert len(result) == 1

    def test_graceful_on_missing_link_transaction(self, db_session):
        """Verify link enrichment gracefully handles nonexistent refund transaction IDs."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund(
            "transaction", 1, "banks", 100.0,
        )
        service.link_refund(pending["id"], 99999, "banks", 50.0)

        # Should not raise even though link transaction ID doesn't exist
        result = service.get_all_pending()
        item = next(p for p in result if p["id"] == pending["id"])
        assert len(item["links"]) == 1


class TestGetBudgetAdjustment:
    """Tests for get_budget_adjustment calculation."""

    def test_budget_adjustment_with_pending_refunds(self, db_session):
        """Verify budget adjustment sums all pending refund expected amounts."""
        service = PendingRefundsService(db_session)
        service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        service.mark_as_pending_refund("transaction", 2, "credit_cards", 50.0)

        result = service.get_budget_adjustment(2024, 1)
        assert result == 150.0

    def test_budget_adjustment_empty(self, db_session):
        """Verify budget adjustment returns 0 when no pending refunds exist."""
        service = PendingRefundsService(db_session)
        result = service.get_budget_adjustment(2024, 1)
        assert result == 0.0

    def test_budget_adjustment_includes_partial_remaining(self, db_session):
        """Verify budget adjustment includes remaining amount of partial refunds."""
        service = PendingRefundsService(db_session)
        service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        partial = service.mark_as_pending_refund("transaction", 2, "banks", 200.0)
        service.link_refund(partial["id"], 99, "banks", 80.0)
        result = service.get_budget_adjustment(2024, 1)
        assert result == 220.0  # 100 + 120

    def test_budget_adjustment_excludes_closed(self, db_session):
        """Verify budget adjustment excludes closed refunds."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        service.link_refund(pending["id"], 99, "banks", 50.0)
        service.close_pending_refund(pending["id"])
        result = service.get_budget_adjustment(2024, 1)
        assert result == 0.0

    def test_budget_adjustment_excludes_resolved(self, db_session):
        """Verify budget adjustment excludes resolved refunds."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        service.mark_as_pending_refund("transaction", 2, "banks", 50.0)

        # Resolve the first one
        service.link_refund(pending["id"], 99, "banks", 100.0)

        result = service.get_budget_adjustment(2024, 1)
        assert result == 50.0


class TestLinkRefundAutoSplit:
    """Tests for auto-split when refund amount exceeds pending remaining."""

    def test_auto_split_when_amount_exceeds_remaining(self, db_session, seed_base_transactions):
        """Auto-split refund transaction when amount > remaining."""
        from backend.models.transaction import BankTransaction, SplitTransaction

        expense_txn = db_session.query(BankTransaction).filter(
            BankTransaction.amount < 0
        ).first()
        assert expense_txn is not None

        refund_txn = BankTransaction(
            id="test-refund-oversized",
            date="2024-01-15",
            provider="hapoalim",
            account_name="Main Account",
            description="Large refund",
            amount=150.0,
            category="Shopping",
            tag="Online",
            source="bank_transactions",
            type="normal",
            status="completed",
        )
        db_session.add(refund_txn)
        db_session.flush()

        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund(
            "transaction", expense_txn.unique_id, "banks", 100.0,
        )

        result = service.link_refund(
            pending["id"], refund_txn.unique_id, "bank_transactions", 150.0,
        )

        assert result["status"] == "resolved"
        assert result["total_refunded"] == 100.0

        db_session.refresh(refund_txn)
        assert refund_txn.type == "split_parent"

        splits = db_session.query(SplitTransaction).filter(
            SplitTransaction.transaction_id == refund_txn.unique_id,
        ).all()
        assert len(splits) == 2
        amounts = sorted([s.amount for s in splits])
        assert amounts[0] == 50.0
        assert amounts[1] == 100.0

    def test_no_split_when_amount_equals_remaining(self, db_session):
        """No split when refund amount exactly matches remaining."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        result = service.link_refund(pending["id"], 99, "banks", 100.0)
        assert result["status"] == "resolved"
        assert result["total_refunded"] == 100.0

    def test_no_split_when_amount_less_than_remaining(self, db_session):
        """No split when refund amount is less than remaining."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        result = service.link_refund(pending["id"], 99, "banks", 50.0)
        assert result["status"] == "partial"
        assert result["total_refunded"] == 50.0
