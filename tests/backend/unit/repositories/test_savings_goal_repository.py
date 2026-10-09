"""Unit tests for SavingsGoalRepository — goals, entries, and links."""

import pytest

from backend.errors import EntityNotFoundException
from backend.models.savings_goal import (
    ENTRY_CLOSE,
    ENTRY_COVER,
    ENTRY_MANUAL,
    LINK_CONTRIBUTION,
    LINK_UTILIZATION,
)
from backend.repositories.savings_goal_repository import SavingsGoalRepository


@pytest.fixture
def repo(db_session):
    """A repository bound to the in-memory test database."""
    return SavingsGoalRepository(db_session)


class TestSavingsGoalCrud:
    """Tests for goal row CRUD."""

    def test_get_all_empty_returns_dataframe_with_columns(self, repo):
        """An empty table still yields the expected column layout."""
        df = repo.get_all()
        assert df.empty
        assert "target_amount" in df.columns
        assert "priority" in df.columns
        assert "monthly_amount" in df.columns

    def test_add_persists_goal(self, repo):
        """A created goal round-trips with its plan fields."""
        goal = repo.add(
            name="Vacation", target_amount=5000, priority=2, monthly_amount=400
        )
        assert goal.id is not None
        assert goal.name == "Vacation"
        assert goal.priority == 2
        assert goal.monthly_amount == 400

    def test_next_priority_appends_to_the_bottom(self, repo):
        """A new goal is ranked after every existing one."""
        assert repo.next_priority() == 0
        repo.add(name="A", target_amount=100, priority=0)
        repo.add(name="B", target_amount=100, priority=3)
        assert repo.next_priority() == 4

    def test_get_returns_goal_or_none(self, repo):
        """Fetching a missing id returns None rather than raising."""
        goal = repo.add(name="Car", target_amount=1000)
        assert repo.get(goal.id).name == "Car"
        assert repo.get(9999) is None

    def test_update_applies_none_to_clear_a_field(self, repo):
        """Passing None clears an optional field instead of being skipped."""
        goal = repo.add(name="Car", target_amount=1000, monthly_amount=250)
        updated = repo.update(goal.id, monthly_amount=None)
        assert updated.monthly_amount is None

    def test_update_missing_raises_not_found(self, repo):
        """Updating an unknown id raises for the service to translate."""
        with pytest.raises(EntityNotFoundException):
            repo.update(9999, name="nope")

    def test_delete_removes_goal_with_entries_and_links(self, repo):
        """Deleting a goal takes its entries and links with it."""
        goal = repo.add(name="Car", target_amount=1000)
        other = repo.add(name="Bike", target_amount=500)
        repo.add_entry(goal.id, "2026-03-01", 200.0, ENTRY_MANUAL)
        repo.add_entry(other.id, "2026-03-01", 50.0, ENTRY_MANUAL)
        repo.upsert_link(
            goal.id, "transaction", 7, "bank_transactions", LINK_CONTRIBUTION
        )

        repo.delete(goal.id)

        assert repo.get(goal.id) is None
        assert repo.get_entries(goal.id).empty
        assert repo.get_entries()["goal_id"].tolist() == [other.id]
        assert repo.get_links().empty

    def test_delete_missing_raises_not_found(self, repo):
        """Deleting an unknown id raises for the service to translate."""
        with pytest.raises(EntityNotFoundException):
            repo.delete(9999)

    def test_set_priorities_rewrites_the_order(self, repo):
        """Reordering assigns positions in the order the ids arrive."""
        first = repo.add(name="A", target_amount=100, priority=0)
        second = repo.add(name="B", target_amount=100, priority=1)

        repo.set_priorities([second.id, first.id])

        assert repo.get(second.id).priority == 0
        assert repo.get(first.id).priority == 1


class TestEntries:
    """Tests for money put into and taken out of goals."""

    def test_add_entry_persists_every_field(self, repo):
        """An entry round-trips its date, signed amount, source and note."""
        goal = repo.add(name="Car", target_amount=1000)

        entry = repo.add_entry(goal.id, "2026-03-05", -75.5, ENTRY_COVER, note="cover")

        assert entry.id is not None
        row = repo.get_entries(goal.id).iloc[0]
        assert row["date"] == "2026-03-05"
        assert row["amount"] == -75.5
        assert row["source"] == ENTRY_COVER
        assert row["note"] == "cover"

    def test_get_entries_orders_by_date_then_id(self, repo):
        """Entries come back oldest first; same-day entries in insertion order."""
        goal = repo.add(name="Car", target_amount=1000)
        repo.add_entry(goal.id, "2026-04-01", 3.0, ENTRY_MANUAL)
        repo.add_entry(goal.id, "2026-03-01", 1.0, ENTRY_MANUAL)
        repo.add_entry(goal.id, "2026-04-01", 4.0, ENTRY_MANUAL)
        repo.add_entry(goal.id, "2026-03-15", 2.0, ENTRY_MANUAL)

        assert repo.get_entries(goal.id)["amount"].tolist() == [1.0, 2.0, 3.0, 4.0]

    def test_get_entries_scopes_to_one_goal(self, repo):
        """A goal id filters out every other goal's entries."""
        goal = repo.add(name="Car", target_amount=1000)
        other = repo.add(name="Bike", target_amount=500)
        repo.add_entry(goal.id, "2026-03-01", 100.0, ENTRY_MANUAL)
        repo.add_entry(other.id, "2026-03-01", 50.0, ENTRY_MANUAL)

        assert repo.get_entries(goal.id)["amount"].tolist() == [100.0]
        assert len(repo.get_entries()) == 2

    def test_get_entries_empty_keeps_columns(self, repo):
        """No entries still yields the expected column layout."""
        df = repo.get_entries()
        assert df.empty
        assert {"goal_id", "date", "amount", "source", "note"} <= set(df.columns)

    def test_get_entry_returns_entry_or_none(self, repo):
        """Fetching a missing entry returns None rather than raising."""
        goal = repo.add(name="Car", target_amount=1000)
        entry = repo.add_entry(goal.id, "2026-03-01", 100.0, ENTRY_MANUAL)

        assert repo.get_entry(entry.id).amount == 100.0
        assert repo.get_entry(9999) is None

    def test_delete_entry_removes_only_that_entry(self, repo):
        """Deleting one entry leaves the goal's others."""
        goal = repo.add(name="Car", target_amount=1000)
        first = repo.add_entry(goal.id, "2026-03-01", 100.0, ENTRY_MANUAL)
        repo.add_entry(goal.id, "2026-03-02", 200.0, ENTRY_MANUAL)

        repo.delete_entry(first.id)

        assert repo.get_entries(goal.id)["amount"].tolist() == [200.0]

    def test_delete_entry_missing_raises_not_found(self, repo):
        """Deleting an unknown entry raises for the service to translate."""
        with pytest.raises(EntityNotFoundException):
            repo.delete_entry(9999)

    def test_delete_entries_clears_one_source_of_one_goal(self, repo):
        """Only the named source on the named goal is removed."""
        goal = repo.add(name="Car", target_amount=1000)
        other = repo.add(name="Bike", target_amount=500)
        repo.add_entry(goal.id, "2026-03-01", 100.0, ENTRY_MANUAL)
        repo.add_entry(goal.id, "2026-04-01", -100.0, ENTRY_CLOSE)
        repo.add_entry(other.id, "2026-04-01", -50.0, ENTRY_CLOSE)

        repo.delete_entries(goal.id, ENTRY_CLOSE)

        assert repo.get_entries(goal.id)["source"].tolist() == [ENTRY_MANUAL]
        assert repo.get_entries(other.id)["source"].tolist() == [ENTRY_CLOSE]


class TestAtomic:
    """Writes inside ``atomic`` land together or not at all."""

    def test_atomic_rolls_back_every_write_on_error(self, repo):
        """A failure halfway leaves none of the block's entries behind."""
        goal = repo.add(name="Car", target_amount=1000)

        with pytest.raises(RuntimeError), repo.atomic():
            repo.add_entry(goal.id, "2026-03-01", 100.0, ENTRY_MANUAL)
            raise RuntimeError("boom")

        assert repo.get_entries().empty

    def test_atomic_commits_once_at_the_end(self, repo):
        """A completed block keeps every write."""
        goal = repo.add(name="Car", target_amount=1000)

        with repo.atomic():
            repo.add_entry(goal.id, "2026-03-01", 100.0, ENTRY_MANUAL)
            repo.add_entry(goal.id, "2026-03-02", 200.0, ENTRY_MANUAL)

        assert repo.get_entries()["amount"].tolist() == [100.0, 200.0]


class TestLinks:
    """Tests for transaction-to-goal links."""

    def test_upsert_link_moves_an_already_linked_transaction(self, repo):
        """Re-linking a transaction reassigns it rather than raising."""
        first = repo.add(name="A", target_amount=100)
        second = repo.add(name="B", target_amount=100)
        repo.upsert_link(
            first.id, "transaction", 7, "bank_transactions", LINK_CONTRIBUTION
        )

        repo.upsert_link(
            second.id, "transaction", 7, "bank_transactions", LINK_UTILIZATION
        )

        links = repo.get_links()
        assert len(links) == 1
        assert links.iloc[0]["goal_id"] == second.id
        assert links.iloc[0]["link_type"] == LINK_UTILIZATION

    def test_get_link_by_source_pairs_id_with_table(self, repo):
        """A bare unique_id from another table must not match.

        `unique_id` is a per-table auto-increment, so bank #7 and credit-card
        #7 are different transactions.
        """
        goal = repo.add(name="A", target_amount=100)
        repo.upsert_link(
            goal.id, "transaction", 7, "bank_transactions", LINK_CONTRIBUTION
        )

        assert (
            repo.get_link_by_source("transaction", 7, "bank_transactions") is not None
        )
        assert (
            repo.get_link_by_source("transaction", 7, "credit_card_transactions")
            is None
        )

    def test_delete_link_missing_raises_not_found(self, repo):
        """Deleting an unknown link id raises for the service to translate."""
        with pytest.raises(EntityNotFoundException):
            repo.delete_link(9999)
