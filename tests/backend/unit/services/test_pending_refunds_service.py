"""Tests for PendingRefundsService."""

import pytest

from backend.errors import EntityNotFoundException, ValidationException
from backend.models.transaction import (
    BankTransaction,
    CreditCardTransaction,
    SplitTransaction,
)
from backend.repositories.pending_refunds_repository import PendingRefundsRepository
from backend.services.pending_refunds_service import PendingRefundsService


@pytest.fixture
def seed_refund_sources(db_session) -> dict:
    """Insert the expense rows and slices these tests mark as awaiting a refund.

    A refund may only be expected on money that was actually spent, so
    ``mark_as_pending_refund`` resolves and caps against a real source row.
    The rows below give every test in this module a source to point at:
    bank ``unique_id`` 1/2, credit-card ``unique_id`` 1/2 and split ids 1/2,
    each comfortably larger than the amounts the tests expect back.

    Returns
    -------
    dict
        ``{"bank": [...], "cc": [...], "cc_parent": ..., "splits": [...]}``
        of committed ORM rows.
    """
    def _cc(tx_id: str, amount: float, tx_type: str = "normal"):
        return CreditCardTransaction(
            id=tx_id, date="2024-01-05", provider="isracard",
            account_name="Main Card", description=tx_id, amount=amount,
            category="Food", tag="Groceries",
            source="credit_card_transactions", type=tx_type, status="completed",
        )

    def _bank(tx_id: str, amount: float):
        return BankTransaction(
            id=tx_id, date="2024-01-05", provider="hapoalim",
            account_name="Checking", description=tx_id, amount=amount,
            category="Home", tag="Rent", source="bank_transactions",
            type="normal", status="completed",
        )

    bank_rows = [_bank("refund-bank-1", -600.0), _bank("refund-bank-2", -400.0)]
    cc_rows = [_cc("refund-cc-1", -300.0), _cc("refund-cc-2", -200.0)]
    cc_parent = _cc("refund-cc-parent", -500.0, tx_type="split_parent")
    db_session.add_all([*bank_rows, *cc_rows, cc_parent])
    db_session.flush()

    splits = [
        SplitTransaction(
            transaction_id=cc_parent.unique_id,
            source="credit_card_transactions",
            amount=-300.0, category="Food", tag="Groceries",
        ),
        SplitTransaction(
            transaction_id=cc_parent.unique_id,
            source="credit_card_transactions",
            amount=-200.0, category="Home", tag="Cleaning",
        ),
    ]
    db_session.add_all(splits)
    db_session.commit()
    for row in [*bank_rows, *cc_rows, cc_parent, *splits]:
        db_session.refresh(row)

    # The literal ids the tests below use are the per-table auto-increments
    # of a fresh database; pin them here so a seeding change cannot make the
    # tests quietly point at nothing.
    assert [r.unique_id for r in bank_rows] == [1, 2]
    assert [r.unique_id for r in cc_rows] == [1, 2]
    assert [s.id for s in splits] == [1, 2]

    return {
        "bank": bank_rows,
        "cc": cc_rows,
        "cc_parent": cc_parent,
        "splits": splits,
    }


class TestPendingRefundsService:
    """Test suite for PendingRefundsService."""

    def test_mark_as_pending_refund_transaction(self, db_session, seed_refund_sources):
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

    def test_mark_as_pending_refund_split(self, db_session, seed_refund_sources):
        """Mark a split as pending refund."""
        service = PendingRefundsService(db_session)
        result = service.mark_as_pending_refund(
            source_type="split",
            source_id=seed_refund_sources["splits"][0].id,
            source_table="credit_card_transactions",
            expected_amount=50.0,
        )
        assert result["source_type"] == "split"

    def test_mark_as_pending_refund_missing_transaction_rejected(self, db_session):
        """A refund cannot be expected on a transaction that does not exist."""
        service = PendingRefundsService(db_session)
        with pytest.raises(ValidationException, match="does not exist"):
            service.mark_as_pending_refund("transaction", 99999, "banks", 10.0)

    def test_mark_as_pending_refund_missing_split_rejected(self, db_session):
        """A refund cannot be expected on a split slice that does not exist."""
        service = PendingRefundsService(db_session)
        with pytest.raises(ValidationException, match="Split 4242 does not exist"):
            service.mark_as_pending_refund("split", 4242, "banks", 10.0)

    def test_mark_as_pending_refund_above_source_amount_rejected(
        self, db_session, seed_refund_sources
    ):
        """The expectation is capped at the amount actually spent."""
        service = PendingRefundsService(db_session)
        with pytest.raises(ValidationException, match="cannot exceed"):
            service.mark_as_pending_refund("transaction", 2, "credit_cards", 200.01)

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

    def test_mark_as_pending_refund_already_exists(self, db_session, seed_refund_sources):
        """Reject marking same source twice."""
        service = PendingRefundsService(db_session)
        service.mark_as_pending_refund("transaction", 1, "banks", 100.0)

        with pytest.raises(ValidationException):
            service.mark_as_pending_refund("transaction", 1, "banks", 50.0)

    def test_link_refund_full(self, db_session, seed_refund_sources):
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

    def test_link_refund_partial(self, db_session, seed_refund_sources):
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

    def test_link_refund_multiple_partials(self, db_session, seed_refund_sources):
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

    def test_link_refund_to_closed_rejected(self, db_session, seed_refund_sources):
        """Cannot link a refund to a closed record."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        service.close_pending_refund(pending["id"])
        with pytest.raises(ValidationException):
            service.link_refund(pending["id"], 99, "banks", 50.0)

    def test_link_refund_to_resolved_rejected(self, db_session, seed_refund_sources):
        """Cannot link a refund to a resolved record."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        service.link_refund(pending["id"], 99, "banks", 100.0)
        with pytest.raises(ValidationException):
            service.link_refund(pending["id"], 100, "banks", 50.0)

    def test_link_same_transaction_to_multiple_refunds_allowed(self, db_session, seed_refund_sources):
        """The same transaction can fund multiple refund requests."""
        service = PendingRefundsService(db_session)
        pending1 = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        pending2 = service.mark_as_pending_refund("transaction", 2, "banks", 200.0)
        service.link_refund(pending1["id"], 99, "banks", 50.0)
        result = service.link_refund(pending2["id"], 99, "banks", 50.0)
        assert result["status"] == "partial"
        assert result["total_refunded"] == 50.0

    def test_link_same_transaction_twice_to_same_pending_rejected(self, db_session, seed_refund_sources):
        """Cannot link the same transaction twice to one refund request."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        service.link_refund(pending["id"], 99, "banks", 30.0)
        with pytest.raises(ValidationException):
            service.link_refund(pending["id"], 99, "banks", 20.0)

    def test_link_refund_non_positive_amount_rejected(self, db_session, seed_refund_sources):
        """Reject linking a non-positive amount."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        with pytest.raises(ValidationException):
            service.link_refund(pending["id"], 99, "banks", 0.0)

    def test_cancel_pending_refund(self, db_session, seed_refund_sources):
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

    def test_get_all_pending(self, db_session, seed_refund_sources):
        """Get all pending refunds."""
        service = PendingRefundsService(db_session)
        service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        service.mark_as_pending_refund(
            "split", seed_refund_sources["splits"][1].id,
            "credit_card_transactions", 50.0,
        )

        result = service.get_all_pending()
        assert len(result) == 2

    def test_get_pending_by_id(self, db_session, seed_refund_sources):
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

    def test_unlink_refund_reverts_resolved_to_partial(self, db_session, seed_refund_sources):
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

    def test_unlink_refund_reverts_partial_to_pending(self, db_session, seed_refund_sources):
        """Unlinking the only link reverts partial to pending."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        service.link_refund(pending["id"], 99, "banks", 50.0)
        details = service.get_pending_by_id(pending["id"])
        link_id = details["links"][0]["id"]
        result = service.unlink_refund(link_id)
        assert result["status"] == "pending"
        assert result["total_refunded"] == 0

    def test_unlink_refund_from_closed_rejected(self, db_session, seed_refund_sources):
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

    def test_close_pending_refund(self, db_session, seed_refund_sources):
        """Close a pending refund sets status to closed."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        result = service.close_pending_refund(pending["id"])
        assert result["status"] == "closed"

    def test_close_partial_refund(self, db_session, seed_refund_sources):
        """Close a partial refund preserves links and sets status to closed."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        service.link_refund(pending["id"], 99, "banks", 50.0)
        result = service.close_pending_refund(pending["id"])
        assert result["status"] == "closed"
        assert result["total_refunded"] == 50.0

    def test_close_resolved_refund_rejected(self, db_session, seed_refund_sources):
        """Cannot close an already resolved refund."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        service.link_refund(pending["id"], 99, "banks", 100.0)
        with pytest.raises(ValidationException):
            service.close_pending_refund(pending["id"])

    def test_close_already_closed_refund_rejected(self, db_session, seed_refund_sources):
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
        """Verify the source transaction's own stored values are copied onto the item."""
        bank_txn = (
            db_session.query(BankTransaction)
            .filter(BankTransaction.id == "bank_jan_2")
            .one()
        )

        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund(
            "transaction", bank_txn.unique_id, "banks", 50.0,
        )

        result = service.get_all_pending()
        item = next(p for p in result if p["id"] == pending["id"])

        assert item["date"] == "2024-01-03"
        assert item["description"] == "Rent Payment"
        assert item["account_name"] == "Checking"
        assert item["provider"] == "hapoalim"
        assert (item["category"], item["tag"]) == ("Home", "Rent")
        assert item["original_currency"] == "ILS"

    def test_enriches_link_details(self, db_session, seed_base_transactions):
        """Verify get_all_pending enriches linked refund transactions with details."""
        expense_txn = db_session.query(BankTransaction).filter(
            BankTransaction.amount < 0
        ).first()
        income_txn = db_session.query(BankTransaction).filter(
            BankTransaction.amount > 0
        ).first()
        assert expense_txn is not None and income_txn is not None

        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund(
            "transaction", expense_txn.unique_id, "banks", 100.0,
        )
        service.link_refund(
            pending["id"],
            income_txn.unique_id,
            "banks",
            min(50.0, income_txn.amount),
        )

        result = service.get_all_pending()
        item = next(p for p in result if p["id"] == pending["id"])

        assert len(item["links"]) == 1
        link = item["links"][0]
        assert link["date"] == income_txn.date
        assert link["description"] == income_txn.description
        assert link["transaction_amount"] == income_txn.amount
        assert link["amount"] == 50.0

    def test_enriches_split_source_details(
        self, db_session, seed_base_transactions, seed_split_transactions
    ):
        """A slice is described by its parent, prefixed ``Split: ``, with its own tagging."""
        parent = seed_split_transactions["cc_parent"]
        split = seed_split_transactions["splits"][0]

        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund(
            "split", split.id, split.source, 25.0,
        )

        result = service.get_all_pending()
        item = next(p for p in result if p["id"] == pending["id"])

        assert item["description"] == f"Split: {parent.description}"
        assert item["description"] == "Split: Mega Complex Purchase"
        assert item["date"] == parent.date
        assert item["account_name"] == parent.account_name
        # The slice's own category/tag win over the (empty) parent's.
        assert (item["category"], item["tag"]) == ("Food", "Groceries")

    def test_graceful_on_missing_source_transaction(self, db_session):
        """Verify enrichment gracefully handles nonexistent source transaction IDs.

        The service now refuses to mark a source that does not exist, but a
        row written before that guard (or one whose transaction was purged by
        a re-scrape) must still render instead of failing the whole list.
        """
        PendingRefundsRepository(db_session).create_pending_refund(
            "transaction", 99999, "bank_transactions", 100.0,
        )

        result = PendingRefundsService(db_session).get_all_pending()
        assert len(result) == 1
        assert "description" not in result[0]
        assert result[0]["links"] == []

    def test_graceful_on_missing_link_transaction(self, db_session, seed_refund_sources):
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

    def test_budget_adjustment_with_pending_refunds(self, db_session, seed_refund_sources):
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

    def test_budget_adjustment_includes_partial_remaining(self, db_session, seed_refund_sources):
        """Verify budget adjustment includes remaining amount of partial refunds."""
        service = PendingRefundsService(db_session)
        service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        partial = service.mark_as_pending_refund("transaction", 2, "banks", 200.0)
        service.link_refund(partial["id"], 99, "banks", 80.0)
        result = service.get_budget_adjustment(2024, 1)
        assert result == 220.0  # 100 + 120

    def test_budget_adjustment_excludes_closed(self, db_session, seed_refund_sources):
        """Verify budget adjustment excludes closed refunds."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        service.link_refund(pending["id"], 99, "banks", 50.0)
        service.close_pending_refund(pending["id"])
        result = service.get_budget_adjustment(2024, 1)
        assert result == 0.0

    def test_budget_adjustment_excludes_resolved(self, db_session, seed_refund_sources):
        """Verify budget adjustment excludes resolved refunds."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        service.mark_as_pending_refund("transaction", 2, "banks", 50.0)

        # Resolve the first one
        service.link_refund(pending["id"], 99, "banks", 100.0)

        result = service.get_budget_adjustment(2024, 1)
        assert result == 50.0


class TestLinkRefundAllocation:
    """Tests for multi-refund allocation of a single refund transaction."""

    def _add_refund_txn(self, db_session, amount: float = 150.0):
        """Insert a real bank refund transaction and return it."""
        refund_txn = BankTransaction(
            id="test-refund-shared",
            date="2024-01-15",
            provider="hapoalim",
            account_name="Main Account",
            description="Shared refund",
            amount=amount,
            category="Shopping",
            tag="Online",
            source="bank_transactions",
            type="normal",
            status="completed",
        )
        db_session.add(refund_txn)
        db_session.flush()
        return refund_txn

    def test_leftover_stays_available_no_split(self, db_session, seed_base_transactions):
        """Linking more than remaining clamps the link and leaves the rest available — no split."""
        expense_txn = db_session.query(BankTransaction).filter(
            BankTransaction.amount < 0
        ).first()
        assert expense_txn is not None

        refund_txn = self._add_refund_txn(db_session, 150.0)

        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund(
            "transaction", expense_txn.unique_id, "banks", 100.0,
        )

        result = service.link_refund(
            pending["id"], refund_txn.unique_id, "bank_transactions", 150.0,
        )

        assert result["status"] == "resolved"
        assert result["total_refunded"] == 100.0

        # The refund transaction is untouched — no auto-split
        db_session.refresh(refund_txn)
        assert refund_txn.type == "normal"
        splits = db_session.query(SplitTransaction).filter(
            SplitTransaction.transaction_id == refund_txn.unique_id,
        ).all()
        assert len(splits) == 0

        # The unallocated remainder is reported as available
        allocated = service.get_allocated_for_transaction(
            refund_txn.unique_id, "bank_transactions"
        )
        assert allocated == 100.0

    def test_shared_transaction_funds_two_refunds(self, db_session, seed_base_transactions):
        """One refund transaction can settle two pending refunds up to its amount."""
        expenses = (
            db_session.query(BankTransaction)
            .filter(BankTransaction.amount < 0)
            .limit(2)
            .all()
        )
        assert len(expenses) >= 2

        refund_txn = self._add_refund_txn(db_session, 150.0)

        service = PendingRefundsService(db_session)
        p1 = service.mark_as_pending_refund(
            "transaction", expenses[0].unique_id, "banks", 100.0,
        )
        p2 = service.mark_as_pending_refund(
            "transaction", expenses[1].unique_id, "banks", 80.0,
        )

        r1 = service.link_refund(p1["id"], refund_txn.unique_id, "bank_transactions", 100.0)
        assert r1["status"] == "resolved"

        r2 = service.link_refund(p2["id"], refund_txn.unique_id, "bank_transactions", 50.0)
        assert r2["status"] == "partial"
        assert r2["total_refunded"] == 50.0

    def test_over_allocation_rejected(self, db_session, seed_base_transactions):
        """Cannot allocate more than the transaction's amount across refunds."""
        expenses = (
            db_session.query(BankTransaction)
            .filter(BankTransaction.amount < 0)
            .limit(2)
            .all()
        )
        refund_txn = self._add_refund_txn(db_session, 150.0)

        service = PendingRefundsService(db_session)
        p1 = service.mark_as_pending_refund(
            "transaction", expenses[0].unique_id, "banks", 100.0,
        )
        p2 = service.mark_as_pending_refund(
            "transaction", expenses[1].unique_id, "banks", 80.0,
        )
        service.link_refund(p1["id"], refund_txn.unique_id, "bank_transactions", 100.0)

        with pytest.raises(ValidationException):
            service.link_refund(p2["id"], refund_txn.unique_id, "bank_transactions", 80.0)

    def test_source_name_variants_count_as_same_transaction(self, db_session, seed_base_transactions):
        """Allocation tracking normalizes 'banks' vs 'bank_transactions' source names."""
        expenses = (
            db_session.query(BankTransaction)
            .filter(BankTransaction.amount < 0)
            .limit(2)
            .all()
        )
        refund_txn = self._add_refund_txn(db_session, 150.0)

        service = PendingRefundsService(db_session)
        p1 = service.mark_as_pending_refund(
            "transaction", expenses[0].unique_id, "banks", 100.0,
        )
        p2 = service.mark_as_pending_refund(
            "transaction", expenses[1].unique_id, "banks", 80.0,
        )
        # Link with the table-name variant, then try to over-allocate with
        # the service-name variant — must be recognized as the same money.
        service.link_refund(p1["id"], refund_txn.unique_id, "bank_transactions", 100.0)
        with pytest.raises(ValidationException):
            service.link_refund(p2["id"], refund_txn.unique_id, "banks", 80.0)
        # Within the remaining 50 it's fine
        result = service.link_refund(p2["id"], refund_txn.unique_id, "banks", 50.0)
        assert result["total_refunded"] == 50.0


class TestLinkRefundAvailabilityTolerance:
    """The availability check allows a float epsilon, not a real overdraw.

    Money is stored as a float, so an amount that should exactly exhaust a
    refund transaction can arrive a hair over it. ``link_refund`` forgives
    ``1e-6`` and rejects anything beyond.
    """

    @staticmethod
    def _pending_and_refund(db_session) -> tuple[dict, int]:
        """Mark a 100 expense and add an unallocated 100 refund transaction."""
        expense = BankTransaction(
            id="tol-expense", date="2024-04-01", provider="hapoalim",
            account_name="Checking", description="purchase", amount=-100.0,
            category="Food", tag="Groceries", source="bank_transactions",
            type="normal", status="completed",
        )
        refund = BankTransaction(
            id="tol-refund", date="2024-04-05", provider="hapoalim",
            account_name="Checking", description="refund", amount=100.0,
            category="Other Income", tag=None, source="bank_transactions",
            type="normal", status="completed",
        )
        db_session.add_all([expense, refund])
        db_session.commit()
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund(
            "transaction", expense.unique_id, "bank_transactions", 100.0
        )
        return pending, refund.unique_id

    def test_one_epsilon_over_available_is_accepted(self, db_session):
        """``available + 1e-6`` is rounding noise and links successfully."""
        pending, refund_id = self._pending_and_refund(db_session)
        service = PendingRefundsService(db_session)

        result = service.link_refund(
            pending["id"], refund_id, "bank_transactions", 100.0 + 1e-6
        )

        assert result["status"] == "resolved"
        assert result["total_refunded"] == pytest.approx(100.0)

    def test_two_epsilons_over_available_is_rejected(self, db_session):
        """``available + 2e-6`` is past the tolerance and is refused."""
        pending, refund_id = self._pending_and_refund(db_session)
        service = PendingRefundsService(db_session)

        with pytest.raises(ValidationException, match="still available"):
            service.link_refund(
                pending["id"], refund_id, "bank_transactions", 100.0 + 2e-6
            )

        assert service.get_pending_by_id(pending["id"])["links"] == []


class TestGetRefundSources:
    """Tests for the refund-sources allocation summary."""

    def test_empty_when_no_links(self, db_session, seed_refund_sources):
        """No links yields an empty summary."""
        service = PendingRefundsService(db_session)
        service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        assert service.get_refund_sources() == []

    def test_groups_links_by_transaction(self, db_session, seed_base_transactions):
        """Links of the same transaction group into one source entry."""
        expenses = (
            db_session.query(BankTransaction)
            .filter(BankTransaction.amount < 0)
            .limit(2)
            .all()
        )
        refund_txn = BankTransaction(
            id="test-refund-sources",
            date="2024-02-10",
            provider="hapoalim",
            account_name="Main Account",
            description="Insurance payout",
            amount=200.0,
            category="Other Income",
            tag="",
            source="bank_transactions",
            type="normal",
            status="completed",
        )
        db_session.add(refund_txn)
        db_session.flush()

        service = PendingRefundsService(db_session)
        p1 = service.mark_as_pending_refund(
            "transaction", expenses[0].unique_id, "banks", 120.0,
        )
        p2 = service.mark_as_pending_refund(
            "transaction", expenses[1].unique_id, "banks", 90.0,
        )
        service.link_refund(p1["id"], refund_txn.unique_id, "bank_transactions", 120.0)
        service.link_refund(p2["id"], refund_txn.unique_id, "bank_transactions", 60.0)

        sources = service.get_refund_sources()
        assert len(sources) == 1
        src = sources[0]
        assert src["refund_transaction_id"] == refund_txn.unique_id
        assert src["transaction_amount"] == 200.0
        assert src["total_allocated"] == 180.0
        assert src["available"] == 20.0
        assert len(src["allocations"]) == 2
        pending_ids = {a["pending_refund_id"] for a in src["allocations"]}
        assert pending_ids == {p1["id"], p2["id"]}

    def test_unresolvable_transaction_has_null_available(self, db_session, seed_refund_sources):
        """Links to unknown transactions report null amounts, not crashes."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        service.link_refund(pending["id"], 99999, "banks", 50.0)

        sources = service.get_refund_sources()
        assert len(sources) == 1
        assert sources[0]["transaction_amount"] is None
        assert sources[0]["available"] is None
        assert sources[0]["total_allocated"] == 50.0


class TestLinkEnrichmentAmounts:
    """Regression tests for link enrichment preserving allocated amounts."""

    def test_link_amount_not_overwritten_by_transaction_amount(
        self, db_session, seed_base_transactions
    ):
        """The link's allocated amount survives enrichment; the txn amount is separate."""
        expense_txn = db_session.query(BankTransaction).filter(
            BankTransaction.amount < 0
        ).first()
        refund_txn = BankTransaction(
            id="test-refund-enrich",
            date="2024-01-20",
            provider="hapoalim",
            account_name="Main Account",
            description="Big refund",
            amount=500.0,
            category="Other Income",
            tag="",
            source="bank_transactions",
            type="normal",
            status="completed",
        )
        db_session.add(refund_txn)
        db_session.flush()

        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund(
            "transaction", expense_txn.unique_id, "banks", 80.0,
        )
        service.link_refund(pending["id"], refund_txn.unique_id, "bank_transactions", 80.0)

        result = service.get_all_pending()
        item = next(p for p in result if p["id"] == pending["id"])
        link = item["links"][0]
        assert link["amount"] == 80.0
        assert link["transaction_amount"] == 500.0


class TestRefundNotes:
    """Tests for editable notes on pending refunds and refund sources."""

    def test_update_notes_sets_and_clears(self, db_session, seed_refund_sources):
        """Notes can be set, replaced, and cleared on a pending refund."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)

        result = service.update_notes(pending["id"], "Waiting for store credit")
        assert result["notes"] == "Waiting for store credit"
        assert service.get_pending_by_id(pending["id"])["notes"] == "Waiting for store credit"

        result = service.update_notes(pending["id"], "  ")
        assert result["notes"] is None
        assert service.get_pending_by_id(pending["id"])["notes"] is None

    def test_update_notes_not_found(self, db_session):
        """Error when updating notes of a missing pending refund."""
        service = PendingRefundsService(db_session)
        with pytest.raises(EntityNotFoundException):
            service.update_notes(9999, "note")

    def test_source_note_upsert_and_clear(self, db_session):
        """Source notes upsert on the canonical source and clear on empty."""
        service = PendingRefundsService(db_session)

        result = service.set_source_note("banks", 42, "Gett support credit")
        assert result["note"] == "Gett support credit"
        assert result["refund_source"] == "bank_transactions"

        # Update through the table-name variant hits the same record
        service.set_source_note("bank_transactions", 42, "Updated note")
        notes = service.repo.get_all_source_notes()
        assert len(notes) == 1
        assert notes.iloc[0]["note"] == "Updated note"

        # Empty note deletes the record
        result = service.set_source_note("banks", 42, "")
        assert result["note"] is None
        assert service.repo.get_all_source_notes().empty

    def test_refund_sources_include_note(self, db_session, seed_base_transactions):
        """get_refund_sources surfaces the stored note per source."""
        expense = db_session.query(BankTransaction).filter(
            BankTransaction.amount < 0
        ).first()
        refund_txn = BankTransaction(
            id="test-refund-note",
            date="2024-01-22",
            provider="hapoalim",
            account_name="Main Account",
            description="Refund with note",
            amount=90.0,
            category="Other Income",
            tag="",
            source="bank_transactions",
            type="normal",
            status="completed",
        )
        db_session.add(refund_txn)
        db_session.flush()

        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund(
            "transaction", expense.unique_id, "banks", 60.0,
        )
        service.link_refund(pending["id"], refund_txn.unique_id, "bank_transactions", 60.0)
        service.set_source_note("bank_transactions", refund_txn.unique_id, "Insurance claim payout")

        sources = service.get_refund_sources()
        assert len(sources) == 1
        assert sources[0]["note"] == "Insurance claim payout"


class TestActivePendingIdentifiers:
    """Tests for get_active_pending_identifiers source-table pairing."""

    def test_transaction_keys_pair_id_with_source_table(self, db_session, seed_refund_sources):
        """Transaction ids are returned paired with their canonical table."""
        service = PendingRefundsService(db_session)
        service.mark_as_pending_refund("transaction", 1, "banks", 100.0)

        ids = service.get_active_pending_identifiers()
        assert ids["transaction_keys"] == {("bank_transactions", 1)}
        assert ids["split_ids"] == set()

    def test_split_ids_stay_bare(self, db_session, seed_refund_sources):
        """Split ids remain bare — split_transactions is a single table."""
        service = PendingRefundsService(db_session)
        service.mark_as_pending_refund(
            "split", 1, "credit_card_transactions", 100.0
        )

        ids = service.get_active_pending_identifiers()
        assert ids["split_ids"] == {1}
        assert ids["transaction_keys"] == set()

    def test_resolved_refunds_are_not_active(self, db_session, seed_refund_sources):
        """Resolved pending refunds drop out of the active identifier sets."""
        refund = BankTransaction(
            id="ident-refund", date="2026-03-12", provider="p",
            account_name="a", description="refund", amount=100.0,
            category="Other Income", tag=None, source="bank_transactions",
            type="normal", status="completed",
        )
        db_session.add(refund)
        db_session.flush()

        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        service.link_refund(pending["id"], refund.unique_id, "banks", 100.0)

        assert service.get_active_pending_identifiers()["transaction_keys"] == set()

    def test_partial_refunds_stay_active(self, db_session, seed_refund_sources):
        """A partially refunded expense is still owed money, so it stays listed."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        assert service.link_refund(pending["id"], 99, "banks", 40.0)[
            "status"
        ] == "partial"

        assert service.get_active_pending_identifiers()["transaction_keys"] == {
            ("bank_transactions", 1)
        }

    def test_closed_refunds_are_not_active(self, db_session, seed_refund_sources):
        """Closing a refund accepts the shortfall, so it stops being active."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund(
            "split", 1, "credit_card_transactions", 100.0
        )
        service.close_pending_refund(pending["id"])

        ids = service.get_active_pending_identifiers()
        assert ids["split_ids"] == set()
        assert ids["transaction_keys"] == set()

    def test_marked_bank_txn_does_not_mask_same_id_in_other_table(self, db_session):
        """A pending refund on bank #N leaves credit-card #N in the budget.

        ``unique_id`` is a per-table auto-increment, so bank #1 and
        credit-card #1 are unrelated transactions.
        """
        from backend.services.budget_service import BudgetService

        db_session.add(
            BankTransaction(
                id="collide-bank", date="2026-03-10", provider="p",
                account_name="a", description="bank purchase", amount=-100.0,
                category="Food", tag="Groceries", source="bank_transactions",
                type="normal", status="completed",
            )
        )
        db_session.add(
            CreditCardTransaction(
                id="collide-cc", date="2026-03-11", provider="p",
                account_name="a", description="cc purchase", amount=-250.0,
                category="Food", tag="Groceries",
                source="credit_card_transactions", type="normal",
                status="completed",
            )
        )
        db_session.commit()

        bank_uid = db_session.query(BankTransaction).one().unique_id
        cc_uid = db_session.query(CreditCardTransaction).one().unique_id
        assert bank_uid == cc_uid, "precondition: per-table ids collide"

        PendingRefundsService(db_session).mark_as_pending_refund(
            "transaction", bank_uid, "banks", 100.0
        )

        descriptions = set(
            BudgetService(db_session).get_filtered_expenses()["description"]
        )
        assert "bank purchase" not in descriptions
        assert "cc purchase" in descriptions


class TestSourceTableNormalization:
    """source_table is stored canonically so downstream guards match it."""

    def test_service_name_is_stored_as_table_name(self, db_session, seed_refund_sources):
        """Marking with 'banks' stores 'bank_transactions'.

        The re-scrape purge guard matches on the table name, so a row saved
        under the service name left its transaction unprotected — the row was
        purged on the next overlapping scrape and the refund orphaned.
        """
        service = PendingRefundsService(db_session)
        service.mark_as_pending_refund("transaction", 1, "banks", 100.0)

        stored = service.repo.get_all_pending_refunds()
        assert stored.iloc[0]["source_table"] == "bank_transactions"

    def test_duplicate_detected_across_source_spellings(self, db_session, seed_refund_sources):
        """The same source marked as 'banks' then 'bank_transactions' clashes."""
        service = PendingRefundsService(db_session)
        service.mark_as_pending_refund("transaction", 1, "banks", 100.0)

        with pytest.raises(ValidationException):
            service.mark_as_pending_refund(
                "transaction", 1, "bank_transactions", 50.0
            )
