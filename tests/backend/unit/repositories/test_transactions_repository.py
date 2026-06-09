"""Tests for TransactionsRepository delegation to sub-repositories."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from backend.models.transaction import (
    CashTransaction,
)
from backend.repositories.transactions_repository import (
    TransactionsRepository,
    CreditCardRepository,
    BankRepository,
    CashRepository,
    ManualInvestmentTransactionsRepository,
    ManualTransactionDTO,
)


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return MagicMock(spec=Session)


@pytest.fixture
def transactions_repo(mock_db):
    """Create a TransactionsRepository with mocked sub-repositories."""
    repo = TransactionsRepository(mock_db)
    repo.cc_repo = MagicMock(spec=CreditCardRepository)
    repo.bank_repo = MagicMock(spec=BankRepository)
    repo.cash_repo = MagicMock(spec=CashRepository)
    repo.manual_investments_repo = MagicMock(
        spec=ManualInvestmentTransactionsRepository
    )
    return repo


class TestTransactionsRepositoryDelegation:
    """Tests for TransactionsRepository delegating operations to all sub-repositories."""

    def test_nullify_category(self, transactions_repo):
        """Verify nullify_category delegates to all four sub-repositories."""
        transactions_repo.nullify_category("Groceries")

        transactions_repo.cc_repo.nullify_category.assert_called_once_with("Groceries")
        transactions_repo.bank_repo.nullify_category.assert_called_once_with(
            "Groceries"
        )
        transactions_repo.cash_repo.nullify_category.assert_called_once_with(
            "Groceries"
        )
        transactions_repo.manual_investments_repo.nullify_category.assert_called_once_with(
            "Groceries"
        )

    def test_nullify_category_and_tag(self, transactions_repo):
        """Verify nullify_category_and_tag delegates to all four sub-repositories."""
        transactions_repo.nullify_category_and_tag("Entertainment", "Cinema")

        transactions_repo.cc_repo.nullify_category_and_tag.assert_called_once_with(
            "Entertainment", "Cinema"
        )
        transactions_repo.bank_repo.nullify_category_and_tag.assert_called_once_with(
            "Entertainment", "Cinema"
        )
        transactions_repo.cash_repo.nullify_category_and_tag.assert_called_once_with(
            "Entertainment", "Cinema"
        )
        transactions_repo.manual_investments_repo.nullify_category_and_tag.assert_called_once_with(
            "Entertainment", "Cinema"
        )

    def test_update_category_for_tag(self, transactions_repo):
        """Verify update_category_for_tag delegates to all four sub-repositories."""
        transactions_repo.update_category_for_tag("OldCat", "NewCat", "SomeTag")

        transactions_repo.cc_repo.update_category_for_tag.assert_called_once_with(
            "OldCat", "NewCat", "SomeTag"
        )
        transactions_repo.bank_repo.update_category_for_tag.assert_called_once_with(
            "OldCat", "NewCat", "SomeTag"
        )
        transactions_repo.cash_repo.update_category_for_tag.assert_called_once_with(
            "OldCat", "NewCat", "SomeTag"
        )
        transactions_repo.manual_investments_repo.update_category_for_tag.assert_called_once_with(
            "OldCat", "NewCat", "SomeTag"
        )


class TestAddTransactionIdGeneration:
    """Tests for ServiceRepository.add_transaction generating IDs via ORM."""

    def test_add_transaction_generates_id_from_max(self, db_session):
        """Verify new transaction gets MAX(existing_id) + 1."""
        # Seed some existing transactions with string IDs
        db_session.add_all([
            CashTransaction(
                id="5", date="2024-01-01", amount=-10.0,
                description="Existing 1", account_name="Cash",
                provider="manual", source="cash_transactions",
            ),
            CashTransaction(
                id="12", date="2024-01-02", amount=-20.0,
                description="Existing 2", account_name="Cash",
                provider="manual", source="cash_transactions",
            ),
        ])
        db_session.commit()

        repo = CashRepository(db_session)
        dto = ManualTransactionDTO(
            date=datetime(2024, 2, 1),
            account_name="Cash",
            description="New Entry",
            amount=-30.0,
            provider="manual",
        )
        result = repo.add_transaction(dto)

        assert result is True

        # New transaction should have id "13" (MAX(12) + 1)
        df = repo.get_table()
        new_row = df[df["description"] == "New Entry"]
        assert len(new_row) == 1
        assert new_row.iloc[0]["id"] == "13"

    def test_add_transaction_first_entry_gets_id_1(self, db_session):
        """Verify first transaction in empty table gets id '1'."""
        repo = CashRepository(db_session)
        dto = ManualTransactionDTO(
            date=datetime(2024, 3, 1),
            account_name="Cash",
            description="First Entry",
            amount=-5.0,
            provider="manual",
        )
        result = repo.add_transaction(dto)

        assert result is True

        df = repo.get_table()
        assert len(df) == 1
        assert df.iloc[0]["id"] == "1"


class TestDeleteTransactionExceptionHandler:
    """Tests for ServiceRepository.delete_transaction_by_unique_id exception handling."""

    def test_delete_returns_true_on_success(self, db_session):
        """Verify delete_transaction_by_unique_id returns True when transaction exists."""
        tx = CashTransaction(
            id="1", date="2024-01-01", amount=-10.0,
            description="Test", account_name="Cash",
            provider="manual", source="cash_transactions",
        )
        db_session.add(tx)
        db_session.commit()
        db_session.refresh(tx)

        repo = CashRepository(db_session)
        result = repo.delete_transaction_by_unique_id(tx.unique_id)
        assert result is True

    def test_delete_returns_false_on_not_found(self, db_session):
        """Verify delete_transaction_by_unique_id returns False for nonexistent unique_id."""
        repo = CashRepository(db_session)
        result = repo.delete_transaction_by_unique_id(99999)
        assert result is False

    def test_delete_rollback_on_error(self, db_session):
        """Verify delete_transaction_by_unique_id returns False on exception."""
        tx = CashTransaction(
            id="1", date="2024-01-01", amount=-10.0,
            description="Test", account_name="Cash",
            provider="manual", source="cash_transactions",
        )
        db_session.add(tx)
        db_session.commit()
        db_session.refresh(tx)
        uid = tx.unique_id

        repo = CashRepository(db_session)

        with patch.object(db_session, "commit", side_effect=RuntimeError("DB error")):
            result = repo.delete_transaction_by_unique_id(uid)

        assert result is False


class TestUpdateTransactionByUniqueId:
    """Tests for ServiceRepository.update_transaction_by_unique_id edge cases."""

    def test_empty_updates_returns_true(self, db_session):
        """Verify empty updates dict returns True without hitting the DB."""
        repo = CashRepository(db_session)
        result = repo.update_transaction_by_unique_id(1, {})
        assert result is True

    def test_update_returns_true_on_success(self, db_session):
        """Verify update returns True when transaction exists and is updated."""
        tx = CashTransaction(
            id="1", date="2024-01-01", amount=-10.0,
            description="Original", account_name="Cash",
            provider="manual", source="cash_transactions",
        )
        db_session.add(tx)
        db_session.commit()
        db_session.refresh(tx)

        repo = CashRepository(db_session)
        result = repo.update_transaction_by_unique_id(
            tx.unique_id, {"description": "Updated"}
        )
        assert result is True

    def test_update_rollback_on_error(self, db_session):
        """Verify update returns False on exception and rolls back."""
        tx = CashTransaction(
            id="1", date="2024-01-01", amount=-10.0,
            description="Test", account_name="Cash",
            provider="manual", source="cash_transactions",
        )
        db_session.add(tx)
        db_session.commit()
        db_session.refresh(tx)
        uid = tx.unique_id

        repo = CashRepository(db_session)

        with patch.object(db_session, "commit", side_effect=RuntimeError("DB error")):
            result = repo.update_transaction_by_unique_id(
                uid, {"description": "Fail"}
            )

        assert result is False


class TestAddTransactionExceptionHandler:
    """Tests for ServiceRepository.add_transaction exception handling."""

    def test_add_transaction_rollback_on_error(self, db_session):
        """Verify add_transaction returns False on exception."""
        repo = CashRepository(db_session)
        dto = ManualTransactionDTO(
            date=datetime(2024, 1, 1),
            account_name="Cash",
            description="Failing",
            amount=-10.0,
            provider="manual",
        )

        with patch.object(db_session, "execute", side_effect=RuntimeError("DB error")):
            result = repo.add_transaction(dto)

        assert result is False


class TestBulkUpdateTagging:
    """Tests for TransactionsRepository.bulk_update_tagging."""

    def test_bulk_update_tagging_delegates_to_sub_repos(self, db_session):
        """Verify bulk_update_tagging iterates and delegates to each sub-repo."""
        # Add a cash transaction
        tx = CashTransaction(
            id="1", date="2024-01-01", amount=-10.0,
            description="Test", account_name="Cash",
            provider="manual", source="cash_transactions",
        )
        db_session.add(tx)
        db_session.commit()
        db_session.refresh(tx)

        repo = TransactionsRepository(db_session)
        repo.bulk_update_tagging(
            [{"source": "cash_transactions", "unique_id": tx.unique_id}],
            category="Food",
            tag="Groceries",
        )

        db_session.expire_all()
        updated = db_session.query(CashTransaction).filter_by(unique_id=tx.unique_id).first()
        assert updated.category == "Food"
        assert updated.tag == "Groceries"

    def test_bulk_update_tagging_invalid_source_raises(self, db_session):
        """Verify an unrecognized source raises a clean ValueError.

        Regression: ``get_repo_by_source`` returns ``None`` for unknown
        sources, so bulk_update_tagging must guard against it instead of
        dereferencing ``None`` (which produced an opaque AttributeError/500).
        """
        repo = TransactionsRepository(db_session)
        with pytest.raises(ValueError):
            repo.bulk_update_tagging(
                [{"source": "not_a_real_source", "unique_id": 1}],
                category="Food",
                tag="Groceries",
            )


class TestGetDateFromTable:
    """Tests for get_latest_date_from_table and get_earliest_date_from_table."""

    def test_latest_date_returns_datetime(self, db_session):
        """Verify get_latest_date_from_table returns the latest date as datetime."""
        db_session.add_all([
            CashTransaction(
                id="1", date="2024-01-01", amount=-10.0,
                description="Old", account_name="Cash",
                provider="manual", source="cash_transactions",
            ),
            CashTransaction(
                id="2", date="2024-06-15", amount=-20.0,
                description="New", account_name="Cash",
                provider="manual", source="cash_transactions",
            ),
        ])
        db_session.commit()

        repo = TransactionsRepository(db_session)
        result = repo.get_latest_date_from_table("cash_transactions")
        assert result == datetime(2024, 6, 15)

    def test_earliest_date_returns_datetime(self, db_session):
        """Verify get_earliest_date_from_table returns the earliest date as datetime."""
        db_session.add_all([
            CashTransaction(
                id="1", date="2024-01-01", amount=-10.0,
                description="Old", account_name="Cash",
                provider="manual", source="cash_transactions",
            ),
            CashTransaction(
                id="2", date="2024-06-15", amount=-20.0,
                description="New", account_name="Cash",
                provider="manual", source="cash_transactions",
            ),
        ])
        db_session.commit()

        repo = TransactionsRepository(db_session)
        result = repo.get_earliest_date_from_table("cash_transactions")
        assert result == datetime(2024, 1, 1)

    def test_latest_date_empty_table_returns_none(self, db_session):
        """Verify get_latest_date_from_table returns None for empty table."""
        repo = TransactionsRepository(db_session)
        result = repo.get_latest_date_from_table("cash_transactions")
        assert result is None

    def test_earliest_date_empty_table_returns_none(self, db_session):
        """Verify get_earliest_date_from_table returns None for empty table."""
        repo = TransactionsRepository(db_session)
        result = repo.get_earliest_date_from_table("cash_transactions")
        assert result is None

    def test_latest_date_invalid_format_returns_none(self, db_session):
        """Verify get_latest_date_from_table returns None for unparseable date."""
        tx = CashTransaction(
            id="1", date="not-a-date", amount=-10.0,
            description="Bad date", account_name="Cash",
            provider="manual", source="cash_transactions",
        )
        db_session.add(tx)
        db_session.commit()

        repo = TransactionsRepository(db_session)
        result = repo.get_latest_date_from_table("cash_transactions")
        assert result is None

    def test_earliest_date_invalid_format_returns_none(self, db_session):
        """Verify get_earliest_date_from_table returns None for unparseable date."""
        tx = CashTransaction(
            id="1", date="not-a-date", amount=-10.0,
            description="Bad date", account_name="Cash",
            provider="manual", source="cash_transactions",
        )
        db_session.add(tx)
        db_session.commit()

        repo = TransactionsRepository(db_session)
        result = repo.get_earliest_date_from_table("cash_transactions")
        assert result is None


class TestGetTransactionById:
    """Tests for TransactionsRepository.get_transaction_by_id."""

    def test_get_transaction_by_id_success(self, db_session):
        """Verify get_transaction_by_id returns the matching transaction."""
        tx = CashTransaction(
            id="1", date="2024-01-01", amount=-10.0,
            description="Test", account_name="Cash",
            provider="manual", source="cash_transactions",
        )
        db_session.add(tx)
        db_session.commit()
        db_session.refresh(tx)

        repo = TransactionsRepository(db_session)
        result = repo.get_transaction_by_id(tx.unique_id)
        assert result["description"] == "Test"

    def test_get_transaction_by_id_not_found_raises(self, db_session):
        """Verify get_transaction_by_id raises ValueError when not found."""
        # Need at least one row so the merged DF has columns
        tx = CashTransaction(
            id="1", date="2024-01-01", amount=-10.0,
            description="Existing", account_name="Cash",
            provider="manual", source="cash_transactions",
        )
        db_session.add(tx)
        db_session.commit()

        repo = TransactionsRepository(db_session)
        with pytest.raises(ValueError, match="not found"):
            repo.get_transaction_by_id(99999)


class TestPendingReconciliation:
    """Tests for pending-row reconciliation in add_scraped_transactions."""

    @staticmethod
    def _scraped_df(rows):
        """Build a scraped-transactions DataFrame from partial row dicts."""
        import pandas as pd

        defaults = {
            "id": "txn-1",
            "date": "2026-06-05",
            "provider": "hapoalim",
            "account_name": "Main",
            "account_number": "123",
            "description": "Coffee",
            "amount": -100.0,
            "category": None,
            "tag": None,
            "source": "bank_transactions",
            "type": "normal",
            "status": "completed",
        }
        return pd.DataFrame([{**defaults, **row} for row in rows])

    @staticmethod
    def _add_bank_row(db_session, **overrides):
        """Insert a BankTransaction directly and return it."""
        from backend.models.transaction import BankTransaction

        fields = {
            "id": "txn-1",
            "date": "2026-06-05",
            "provider": "hapoalim",
            "account_name": "Main",
            "description": "Coffee",
            "amount": -100.0,
            "source": "bank_transactions",
            "type": "normal",
            "status": "pending",
        }
        fields.update(overrides)
        row = BankTransaction(**fields)
        db_session.add(row)
        db_session.commit()
        return row

    def test_settled_pending_row_replaced(self, db_session):
        """A pending row settling with a new amount is purged, not duplicated."""
        from backend.models.transaction import BankTransaction

        self._add_bank_row(db_session, amount=-100.0, status="pending")
        repo = TransactionsRepository(db_session)

        df = self._scraped_df([{"amount": -105.0, "status": "completed"}])
        repo.add_scraped_transactions(df, "bank_transactions", scrape_start_date="2026-06-01")

        rows = db_session.query(BankTransaction).all()
        assert len(rows) == 1
        assert rows[0].status == "completed"
        assert rows[0].amount == -105.0

    def test_still_pending_row_reinserted_with_carried_tag(self, db_session):
        """A re-reported pending row keeps the user's category and tag."""
        from backend.models.transaction import BankTransaction

        self._add_bank_row(db_session, status="pending", category="Food", tag="Coffee")
        repo = TransactionsRepository(db_session)

        df = self._scraped_df([{"status": "pending"}])
        repo.add_scraped_transactions(df, "bank_transactions", scrape_start_date="2026-06-01")

        rows = db_session.query(BankTransaction).all()
        assert len(rows) == 1
        assert rows[0].status == "pending"
        assert rows[0].category == "Food"
        assert rows[0].tag == "Coffee"

    def test_pending_outside_window_untouched(self, db_session):
        """Pending rows older than the scraped window are not purged."""
        from backend.models.transaction import BankTransaction

        self._add_bank_row(db_session, id="old", date="2026-05-01", status="pending")
        repo = TransactionsRepository(db_session)

        df = self._scraped_df([{"id": "new", "date": "2026-06-05"}])
        repo.add_scraped_transactions(df, "bank_transactions", scrape_start_date="2026-06-01")

        rows = {r.id: r for r in db_session.query(BankTransaction).all()}
        assert set(rows) == {"old", "new"}
        assert rows["old"].status == "pending"

    def test_split_parent_pending_not_purged(self, db_session):
        """A split pending row is never purged (splits reference it)."""
        from backend.models.transaction import BankTransaction

        self._add_bank_row(db_session, id="split", type="split_parent", status="pending")
        repo = TransactionsRepository(db_session)

        df = self._scraped_df([{"id": "new"}])
        repo.add_scraped_transactions(df, "bank_transactions", scrape_start_date="2026-06-01")

        ids = {r.id for r in db_session.query(BankTransaction).all()}
        assert ids == {"split", "new"}

    def test_refund_locked_pending_not_purged(self, db_session):
        """A pending row referenced by a pending refund is never purged."""
        from backend.models.pending_refund import PendingRefund
        from backend.models.transaction import BankTransaction

        row = self._add_bank_row(db_session, id="locked", status="pending")
        db_session.add(
            PendingRefund(
                source_type="transaction",
                source_id=row.unique_id,
                source_table="bank_transactions",
                expected_amount=100.0,
            )
        )
        db_session.commit()
        repo = TransactionsRepository(db_session)

        df = self._scraped_df([{"id": "new"}])
        repo.add_scraped_transactions(df, "bank_transactions", scrape_start_date="2026-06-01")

        ids = {r.id for r in db_session.query(BankTransaction).all()}
        assert ids == {"locked", "new"}

    def test_completed_rows_unaffected(self, db_session):
        """Completed rows in the window are never reconciled away."""
        from backend.models.transaction import BankTransaction

        self._add_bank_row(db_session, id="done", status="completed")
        repo = TransactionsRepository(db_session)

        df = self._scraped_df([{"id": "new"}])
        repo.add_scraped_transactions(df, "bank_transactions", scrape_start_date="2026-06-01")

        ids = {r.id for r in db_session.query(BankTransaction).all()}
        assert ids == {"done", "new"}

    def test_no_window_start_falls_back_to_df_min_date(self, db_session):
        """Without an explicit window the earliest scraped date bounds the purge."""
        from backend.models.transaction import BankTransaction

        self._add_bank_row(db_session, id="older", date="2026-06-01", status="pending")
        self._add_bank_row(db_session, id="inside", date="2026-06-04", status="pending")
        repo = TransactionsRepository(db_session)

        df = self._scraped_df([{"id": "new", "date": "2026-06-03"}])
        repo.add_scraped_transactions(df, "bank_transactions")

        ids = {r.id for r in db_session.query(BankTransaction).all()}
        assert ids == {"older", "new"}
