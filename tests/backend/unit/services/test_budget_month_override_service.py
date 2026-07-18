"""Unit tests for BudgetMonthOverrideService and BudgetMonthOverrideRepository.

Covers override set/clear/precedence rules (one-month movement cap, revert on
real-month target) and the merge/lookup-map logic used by budget filtering.
"""

import pytest

from backend.errors import EntityNotFoundException, ValidationException
from backend.models.budget_month_override import BudgetMonthOverride
from backend.repositories.budget_month_override_repository import (
    BudgetMonthOverrideRepository,
)
from backend.services.budget_month_override_service import (
    BudgetMonthOverrideService,
)


def _record_by_id(records: list, record_id: str):
    """Return the seeded transaction whose source id matches ``record_id``."""
    return next(r for r in records if r.id == record_id)


class TestSetOverride:
    """Tests for BudgetMonthOverrideService.set_override."""

    def test_set_override_forward_one_month_creates_record(
        self, db_session, seed_base_transactions
    ):
        """Moving a transaction one month forward persists an override row."""
        tx = _record_by_id(seed_base_transactions, "cc_jan_1")  # 2024-01-05
        service = BudgetMonthOverrideService(db_session)

        result = service.set_override(
            "transaction", tx.unique_id, tx.source, 2024, 2
        )

        assert result["override_year"] == 2024
        assert result["override_month"] == 2
        assert result["source_id"] == tx.unique_id
        assert result["source_table"] == tx.source
        stored = db_session.get(BudgetMonthOverride, result["id"])
        assert stored is not None
        assert stored.override_month == 2

    def test_set_override_backward_across_year_boundary_allowed(
        self, db_session, seed_base_transactions
    ):
        """A January transaction can move back to December of the prior year."""
        tx = _record_by_id(seed_base_transactions, "bank_jan_1")  # 2024-01-01
        service = BudgetMonthOverrideService(db_session)

        result = service.set_override(
            "transaction", tx.unique_id, tx.source, 2023, 12
        )

        assert result["override_year"] == 2023
        assert result["override_month"] == 12

    def test_set_override_two_months_away_raises_validation(
        self, db_session, seed_base_transactions
    ):
        """Movement beyond one month before/after the real month is rejected."""
        tx = _record_by_id(seed_base_transactions, "cc_jan_1")  # 2024-01-05
        service = BudgetMonthOverrideService(db_session)

        with pytest.raises(ValidationException, match="one month"):
            service.set_override("transaction", tx.unique_id, tx.source, 2024, 3)
        assert service.get_all() == []

    def test_set_override_month_out_of_range_raises_validation(
        self, db_session, seed_base_transactions
    ):
        """An override_month outside 1-12 is rejected before any lookup."""
        tx = _record_by_id(seed_base_transactions, "cc_jan_1")
        service = BudgetMonthOverrideService(db_session)

        with pytest.raises(ValidationException, match="between 1 and 12"):
            service.set_override("transaction", tx.unique_id, tx.source, 2024, 13)

    def test_set_override_missing_transaction_raises_not_found(self, db_session):
        """An unknown transaction id cannot be overridden."""
        service = BudgetMonthOverrideService(db_session)

        with pytest.raises(EntityNotFoundException):
            service.set_override(
                "transaction", 99999, "bank_transactions", 2024, 2
            )

    def test_set_override_unknown_source_table_raises_not_found(
        self, db_session, seed_base_transactions
    ):
        """A source table missing from the repo map resolves to not-found."""
        tx = _record_by_id(seed_base_transactions, "cc_jan_1")
        service = BudgetMonthOverrideService(db_session)

        with pytest.raises(EntityNotFoundException):
            service.set_override(
                "transaction", tx.unique_id, "nonexistent_table", 2024, 2
            )

    def test_set_override_real_month_removes_existing_override(
        self, db_session, seed_base_transactions
    ):
        """Targeting the transaction's real month clears its existing override."""
        tx = _record_by_id(seed_base_transactions, "cc_jan_1")  # 2024-01-05
        service = BudgetMonthOverrideService(db_session)
        service.set_override("transaction", tx.unique_id, tx.source, 2024, 2)

        result = service.set_override(
            "transaction", tx.unique_id, tx.source, 2024, 1
        )

        assert result == {"removed": True}
        assert service.get_all() == []

    def test_set_override_real_month_without_existing_is_noop_removed(
        self, db_session, seed_base_transactions
    ):
        """Targeting the real month with no prior override reports removal."""
        tx = _record_by_id(seed_base_transactions, "cc_jan_1")
        service = BudgetMonthOverrideService(db_session)

        result = service.set_override(
            "transaction", tx.unique_id, tx.source, 2024, 1
        )

        assert result == {"removed": True}
        assert service.get_all() == []

    def test_set_override_twice_upserts_single_record(
        self, db_session, seed_base_transactions
    ):
        """Re-overriding the same source updates the row instead of duplicating."""
        tx = _record_by_id(seed_base_transactions, "cc_feb_1")  # 2024-02-03
        service = BudgetMonthOverrideService(db_session)

        first = service.set_override("transaction", tx.unique_id, tx.source, 2024, 3)
        second = service.set_override("transaction", tx.unique_id, tx.source, 2024, 1)

        assert second["id"] == first["id"]
        overrides = service.get_all()
        assert len(overrides) == 1
        assert overrides[0]["override_month"] == 1

    def test_set_override_split_uses_parent_transaction_date(
        self, db_session, seed_split_transactions
    ):
        """A split override resolves the parent transaction's real month."""
        split = seed_split_transactions["splits"][0]  # parent dated 2024-02-08
        service = BudgetMonthOverrideService(db_session)

        result = service.set_override("split", split.id, split.source, 2024, 3)

        assert result["source_type"] == "split"
        assert result["override_month"] == 3

        # Two months from the parent's real month (Feb) is rejected.
        with pytest.raises(ValidationException, match="one month"):
            service.set_override("split", split.id, split.source, 2024, 4)

    def test_set_override_missing_split_raises_not_found(self, db_session):
        """An unknown split id cannot be overridden."""
        service = BudgetMonthOverrideService(db_session)

        with pytest.raises(EntityNotFoundException):
            service.set_override("split", 424242, "split_transactions", 2024, 2)


class TestRemoveOverride:
    """Tests for BudgetMonthOverrideService.remove_override."""

    def test_remove_override_deletes_record(
        self, db_session, seed_base_transactions
    ):
        """Removing an existing override deletes its row."""
        tx = _record_by_id(seed_base_transactions, "cc_jan_1")
        service = BudgetMonthOverrideService(db_session)
        created = service.set_override(
            "transaction", tx.unique_id, tx.source, 2024, 2
        )

        service.remove_override(created["id"])

        assert service.get_all() == []
        assert db_session.get(BudgetMonthOverride, created["id"]) is None

    def test_remove_override_missing_raises_not_found(self, db_session):
        """Removing a nonexistent override id raises EntityNotFoundException."""
        service = BudgetMonthOverrideService(db_session)

        with pytest.raises(EntityNotFoundException, match="not found"):
            service.remove_override(9999)


class TestGetAllAndOverrideMap:
    """Tests for get_all and the get_override_map lookup structure."""

    def test_get_all_empty_returns_empty_list(self, db_session):
        """With no overrides, get_all returns an empty list, not a DataFrame."""
        service = BudgetMonthOverrideService(db_session)
        assert service.get_all() == []

    def test_get_all_returns_serialized_records(
        self, db_session, seed_base_transactions
    ):
        """get_all returns plain dicts with the override fields."""
        tx = _record_by_id(seed_base_transactions, "cc_jan_1")
        service = BudgetMonthOverrideService(db_session)
        service.set_override("transaction", tx.unique_id, tx.source, 2024, 2)

        records = service.get_all()

        assert len(records) == 1
        rec = records[0]
        assert rec["source_type"] == "transaction"
        assert rec["source_id"] == tx.unique_id
        assert rec["source_table"] == tx.source
        assert (rec["override_year"], rec["override_month"]) == (2024, 2)

    def test_get_override_map_empty_returns_empty_buckets(self, db_session):
        """With no overrides, both lookup buckets exist and are empty."""
        service = BudgetMonthOverrideService(db_session)
        assert service.get_override_map() == {"transaction": {}, "split": {}}

    def test_get_override_map_keys_transaction_by_table_and_id(
        self, db_session, seed_base_transactions
    ):
        """Transaction overrides are keyed by (source_table, source_id).

        unique_id is a per-table auto-increment, so the bare integer is
        ambiguous across tables — the map must carry the table.
        """
        cc_tx = _record_by_id(seed_base_transactions, "cc_jan_1")  # 2024-01-05
        bank_tx = _record_by_id(seed_base_transactions, "bank_jan_2")  # 2024-01-03
        service = BudgetMonthOverrideService(db_session)
        service.set_override("transaction", cc_tx.unique_id, cc_tx.source, 2024, 2)
        service.set_override(
            "transaction", bank_tx.unique_id, bank_tx.source, 2023, 12
        )

        override_map = service.get_override_map()

        assert override_map["transaction"][
            ("credit_card_transactions", cc_tx.unique_id)
        ] == (2024, 2)
        assert override_map["transaction"][
            ("bank_transactions", bank_tx.unique_id)
        ] == (2023, 12)
        assert override_map["split"] == {}

    def test_get_override_map_keys_split_by_id_alone(
        self, db_session, seed_split_transactions
    ):
        """Split overrides are keyed by the split id alone (single table)."""
        split = seed_split_transactions["splits"][0]
        service = BudgetMonthOverrideService(db_session)
        service.set_override("split", split.id, split.source, 2024, 3)

        override_map = service.get_override_map()

        assert override_map["split"][split.id] == (2024, 3)
        assert override_map["transaction"] == {}


class TestBudgetMonthOverrideRepository:
    """Direct tests for the repository CRUD behaviour."""

    def test_get_for_source_returns_none_when_absent(self, db_session):
        """Looking up a source with no override returns None."""
        repo = BudgetMonthOverrideRepository(db_session)
        assert repo.get_for_source("transaction", 1, "bank_transactions") is None

    def test_upsert_creates_then_updates_in_place(self, db_session):
        """A second upsert for the same source mutates the existing row."""
        repo = BudgetMonthOverrideRepository(db_session)

        created = repo.upsert(
            source_type="transaction",
            source_id=7,
            source_table="bank_transactions",
            override_year=2024,
            override_month=5,
        )
        updated = repo.upsert(
            source_type="transaction",
            source_id=7,
            source_table="bank_transactions",
            override_year=2024,
            override_month=6,
        )

        assert updated.id == created.id
        assert updated.override_month == 6
        assert len(repo.get_all()) == 1

    def test_upsert_distinguishes_same_id_in_different_tables(self, db_session):
        """The same source_id in two tables produces two independent rows."""
        repo = BudgetMonthOverrideRepository(db_session)
        repo.upsert(
            source_type="transaction",
            source_id=7,
            source_table="bank_transactions",
            override_year=2024,
            override_month=5,
        )
        repo.upsert(
            source_type="transaction",
            source_id=7,
            source_table="credit_card_transactions",
            override_year=2024,
            override_month=6,
        )

        assert len(repo.get_all()) == 2
        bank = repo.get_for_source("transaction", 7, "bank_transactions")
        cc = repo.get_for_source("transaction", 7, "credit_card_transactions")
        assert bank.override_month == 5
        assert cc.override_month == 6

    def test_delete_for_source_removes_matching_row(self, db_session):
        """delete_for_source removes only the row for that exact source."""
        repo = BudgetMonthOverrideRepository(db_session)
        repo.upsert(
            source_type="transaction",
            source_id=7,
            source_table="bank_transactions",
            override_year=2024,
            override_month=5,
        )

        repo.delete_for_source("transaction", 7, "bank_transactions")

        assert repo.get_for_source("transaction", 7, "bank_transactions") is None
        assert repo.get_all().empty

    def test_delete_for_source_noop_when_absent(self, db_session):
        """delete_for_source does not raise when no override exists."""
        repo = BudgetMonthOverrideRepository(db_session)
        repo.delete_for_source("transaction", 7, "bank_transactions")
        assert repo.get_all().empty

    def test_delete_noop_when_id_absent(self, db_session):
        """delete by id silently ignores a missing row."""
        repo = BudgetMonthOverrideRepository(db_session)
        repo.delete(12345)
        assert repo.get_all().empty
