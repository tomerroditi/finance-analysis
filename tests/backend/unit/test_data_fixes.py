"""Tests for the one-time data repairs run at startup."""

import pytest

import backend.data_fixes as data_fixes
from backend.models.transaction import BankTransaction
from backend.repositories.applied_data_fixes_repository import (
    AppliedDataFixesRepository,
)
from backend.services.pending_refunds_service import PendingRefundsService
from backend.services.refund_tag_alignment import RefundTagAlignmentService

BANK = "bank_transactions"


def _bank(db_session, tx_id: str, amount: float, category: str, tag: str) -> BankTransaction:
    """Insert one bank row and return it."""
    row = BankTransaction(
        id=tx_id, date="2024-01-05", provider="hapoalim",
        account_name="Checking", description=tx_id, amount=amount,
        category=category, tag=tag, source=BANK,
        type="normal", status="completed",
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


class TestRunPendingDataFixes:
    """The runner applies each registered fix once per database."""

    def test_runs_each_fix_once_and_records_it(self, db_session, monkeypatch):
        """A fix runs on the first call and is skipped once recorded."""
        calls = []
        monkeypatch.setattr(data_fixes, "DATA_FIXES", {"one": lambda db: calls.append("one")})

        assert data_fixes.run_pending_data_fixes(db_session) == ["one"]
        assert data_fixes.run_pending_data_fixes(db_session) == []
        assert calls == ["one"]
        assert AppliedDataFixesRepository(db_session).get_names() == {"one"}

    def test_failing_fix_is_retried_and_does_not_block_others(self, db_session, monkeypatch):
        """A raising fix stays unrecorded, the next one still runs, and it reruns later."""
        attempts = []

        def flaky(db) -> None:
            """Fail on the first attempt only."""
            attempts.append(1)
            if len(attempts) == 1:
                raise RuntimeError("boom")

        monkeypatch.setattr(
            data_fixes, "DATA_FIXES", {"flaky": flaky, "after": lambda db: None}
        )

        assert data_fixes.run_pending_data_fixes(db_session) == ["after"]
        assert AppliedDataFixesRepository(db_session).get_names() == {"after"}
        assert data_fixes.run_pending_data_fixes(db_session) == ["flaky"]
        assert len(attempts) == 2


class TestAlignLinkedRefundTags:
    """The registered fix moves legacy linked refunds under their purchase's tag."""

    @pytest.fixture
    def mismatched(self, db_session) -> BankTransaction:
        """A refund linked to a grocery purchase but tagged elsewhere, as legacy links were."""
        service = PendingRefundsService(db_session)
        purchase = _bank(db_session, "purchase", -300.0, "Food", "Groceries")
        refund = _bank(db_session, "refund", 300.0, "Food", "Groceries")
        pending_id = service.mark_as_pending_refund(
            "transaction", purchase.unique_id, "banks", 300.0
        )["id"]
        service.link_refund(pending_id, refund.unique_id, BANK, 300.0)
        refund.category, refund.tag = "Other Income", "Bit"
        db_session.commit()
        return refund

    def test_aligns_once_and_leaves_later_retags_alone(self, db_session, mismatched):
        """The first start aligns the refund; a retag after that survives the next start."""
        assert RefundTagAlignmentService(db_session).get_mismatches()

        assert data_fixes.run_pending_data_fixes(db_session) == ["align_linked_refund_tags"]
        db_session.refresh(mismatched)
        assert (mismatched.category, mismatched.tag) == ("Food", "Groceries")

        mismatched.category, mismatched.tag = "Other Income", "Bit"
        db_session.commit()
        assert data_fixes.run_pending_data_fixes(db_session) == []
        db_session.refresh(mismatched)
        assert (mismatched.category, mismatched.tag) == ("Other Income", "Bit")
