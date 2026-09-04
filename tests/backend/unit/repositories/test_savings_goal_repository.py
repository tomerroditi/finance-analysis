"""Unit tests for SavingsGoalRepository — goals, allocations, and links."""

import pytest

from backend.models.savings_goal import (
    GOAL_STATUS_CLOSED,
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

    def test_add_persists_goal(self, repo):
        """A created goal round-trips with its waterfall fields."""
        goal = repo.add(name="Vacation", target_amount=5000, priority=2, monthly_cap=400)
        assert goal.id is not None
        assert goal.name == "Vacation"
        assert goal.priority == 2
        assert goal.monthly_cap == 400

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
        """Passing None clears an optional field instead of being skipped.

        The old repository skipped None, which made a monthly cap or target
        date impossible to remove once set.
        """
        goal = repo.add(name="Car", target_amount=1000, monthly_cap=250)
        updated = repo.update(goal.id, monthly_cap=None)
        assert updated.monthly_cap is None

    def test_update_missing_raises_value_error(self, repo):
        """Updating an unknown id raises for the service to translate."""
        with pytest.raises(ValueError):
            repo.update(9999, name="nope")

    def test_delete_removes_goal_with_allocations_and_links(self, repo):
        """Deleting a goal takes its ledger rows and links with it."""
        goal = repo.add(name="Car", target_amount=1000)
        repo.upsert_allocation(goal.id, 2026, 3, 200.0, "auto")
        repo.upsert_link(goal.id, "transaction", 7, "bank_transactions", LINK_CONTRIBUTION)

        repo.delete(goal.id)

        assert repo.get(goal.id) is None
        assert repo.get_allocations().empty
        assert repo.get_links().empty

    def test_delete_missing_raises_value_error(self, repo):
        """Deleting an unknown id raises for the service to translate."""
        with pytest.raises(ValueError):
            repo.delete(9999)

    def test_set_priorities_rewrites_the_order(self, repo):
        """Reordering assigns positions in the order the ids arrive."""
        first = repo.add(name="A", target_amount=100, priority=0)
        second = repo.add(name="B", target_amount=100, priority=1)

        repo.set_priorities([second.id, first.id])

        assert repo.get(second.id).priority == 0
        assert repo.get(first.id).priority == 1

    def test_active_goals_excludes_closed_and_sorts_by_priority(self, repo):
        """The waterfall only sees active goals, in priority order."""
        repo.add(name="Low", target_amount=100, priority=5)
        repo.add(name="High", target_amount=100, priority=1)
        repo.add(name="Gone", target_amount=100, priority=0, status=GOAL_STATUS_CLOSED)

        assert [g.name for g in repo.active_goals()] == ["High", "Low"]


class TestAllocations:
    """Tests for the per-month allocation ledger."""

    def test_upsert_allocation_inserts_then_updates(self, repo):
        """A second write to the same (goal, month) replaces the first."""
        goal = repo.add(name="Car", target_amount=1000)
        repo.upsert_allocation(goal.id, 2026, 3, 200.0, "auto")
        repo.upsert_allocation(goal.id, 2026, 3, 350.0, "auto")

        rows = repo.get_allocations(goal.id)
        assert len(rows) == 1
        assert rows.iloc[0]["amount"] == 350.0

    def test_get_month_allocations_scopes_to_one_month(self, repo):
        """Only rows for the requested calendar month come back."""
        goal = repo.add(name="Car", target_amount=1000)
        repo.upsert_allocation(goal.id, 2026, 3, 200.0, "auto")
        repo.upsert_allocation(goal.id, 2026, 4, 300.0, "auto")

        rows = repo.get_month_allocations(2026, 4)
        assert len(rows) == 1
        assert rows.iloc[0]["amount"] == 300.0

    def test_delete_allocations_only_clears_from_the_given_month(self, repo):
        """A rebuild range leaves earlier months untouched."""
        goal = repo.add(name="Car", target_amount=1000)
        repo.upsert_allocation(goal.id, 2026, 2, 100.0, "auto")
        repo.upsert_allocation(goal.id, 2026, 3, 200.0, "auto")
        repo.upsert_allocation(goal.id, 2026, 4, 300.0, "auto")

        repo.delete_allocations([goal.id], 2026, 3)

        months = sorted(repo.get_allocations(goal.id)["month"].tolist())
        assert months == [2]

    def test_delete_allocations_with_no_goals_is_a_noop(self, repo):
        """An empty goal list (everything frozen) deletes nothing."""
        goal = repo.add(name="Car", target_amount=1000)
        repo.upsert_allocation(goal.id, 2026, 3, 200.0, "auto")

        repo.delete_allocations([], 2026, 1)

        assert len(repo.get_allocations()) == 1


class TestLinks:
    """Tests for transaction-to-goal links."""

    def test_upsert_link_moves_an_already_linked_transaction(self, repo):
        """Re-linking a transaction reassigns it rather than raising."""
        first = repo.add(name="A", target_amount=100)
        second = repo.add(name="B", target_amount=100)
        repo.upsert_link(first.id, "transaction", 7, "bank_transactions", LINK_CONTRIBUTION)

        repo.upsert_link(second.id, "transaction", 7, "bank_transactions", LINK_UTILIZATION)

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
        repo.upsert_link(goal.id, "transaction", 7, "bank_transactions", LINK_CONTRIBUTION)

        assert repo.get_link_by_source("transaction", 7, "bank_transactions") is not None
        assert repo.get_link_by_source("transaction", 7, "credit_card_transactions") is None

    def test_delete_link_missing_raises_value_error(self, repo):
        """Deleting an unknown link id raises for the service to translate."""
        with pytest.raises(ValueError):
            repo.delete_link(9999)
