"""
Unit tests for BudgetRepository CRUD operations.
"""

from contextlib import contextmanager
from sqlalchemy import event
import pytest
from sqlalchemy.orm import Session

from backend.repositories.budget_repository import BudgetRepository


def _rule(repo: BudgetRepository, rule_id: int):
    """Return the single-row frame for ``rule_id`` out of ``read_all``."""
    rules = repo.read_all()
    return rules[rules["id"] == rule_id].reset_index(drop=True)


class TestBudgetRepository:
    """Tests for BudgetRepository CRUD operations."""

    def test_add_monthly_rule(self, db_session: Session):
        """Verify adding a monthly budget rule persists every column, with the
        tags kept verbatim as one semicolon-separated string."""
        repo = BudgetRepository(db_session)
        repo.add(
            name="Food",
            amount=2000.0,
            category="Food",
            tags="Groceries;Restaurants;Coffee",
            month=1,
            year=2024,
        )

        result = repo.read_all()
        assert len(result) == 1
        row = result.iloc[0]
        assert row["name"] == "Food"
        assert row["amount"] == 2000.0
        assert row["category"] == "Food"
        assert row["tags"] == "Groceries;Restaurants;Coffee"
        assert row["tags"].split(";") == ["Groceries", "Restaurants", "Coffee"]
        assert row["month"] == 1
        assert row["year"] == 2024

    def test_add_project_rule(self, db_session: Session):
        """Verify adding a project rule (month=None, year=None) persists correctly."""
        repo = BudgetRepository(db_session)
        repo.add(
            name="Wedding Budget",
            amount=50000.0,
            category="Wedding",
            tags="Venue;Catering",
            month=None,
            year=None,
        )

        result = repo.read_all()
        assert len(result) == 1
        row = result.iloc[0]
        assert row["name"] == "Wedding Budget"
        assert row["amount"] == 50000.0
        assert row["category"] == "Wedding"
        assert row["tags"] == "Venue;Catering"
        assert row["month"] is None
        assert row["year"] is None

    def test_read_all(self, db_session: Session):
        """Verify read_all returns all rules as DataFrame."""
        repo = BudgetRepository(db_session)
        repo.add("Food", 2000.0, "Food", "Groceries", month=1, year=2024)
        repo.add("Transport", 500.0, "Transport", "Gas", month=1, year=2024)
        repo.add("Wedding", 50000.0, "Wedding", "Venue;Catering", month=None, year=None)

        result = repo.read_all()
        assert len(result) == 3
        assert set(result["name"].tolist()) == {"Food", "Transport", "Wedding"}

    def test_update_rule(self, db_session: Session):
        """Verify update changes the specified fields."""
        repo = BudgetRepository(db_session)
        repo.add("Food", 2000.0, "Food", "Groceries", month=1, year=2024)

        all_rules = repo.read_all()
        rule_id = int(all_rules.iloc[0]["id"])

        repo.update(rule_id, amount=3000.0, name="Food Updated")

        updated = _rule(repo, rule_id)
        assert updated.iloc[0]["amount"] == 3000.0
        assert updated.iloc[0]["name"] == "Food Updated"
        # Unchanged fields remain the same
        assert updated.iloc[0]["category"] == "Food"

    def test_update_nonexistent_rule_raises(self, db_session: Session):
        """Verify update raises EntityNotFoundException for nonexistent rule ID."""
        from backend.errors import EntityNotFoundException

        repo = BudgetRepository(db_session)
        with pytest.raises(EntityNotFoundException, match="No rule found with ID 999"):
            repo.update(999, amount=5000.0)

    def test_delete_rule(self, db_session: Session):
        """Verify delete removes the rule."""
        repo = BudgetRepository(db_session)
        repo.add("Food", 2000.0, "Food", "Groceries", month=1, year=2024)

        all_rules = repo.read_all()
        rule_id = int(all_rules.iloc[0]["id"])

        repo.delete(rule_id)

        result = repo.read_all()
        assert result.empty

    def test_delete_by_month(self, db_session: Session):
        """Verify delete_by_month removes all rules for that month."""
        repo = BudgetRepository(db_session)
        repo.add("Food Jan", 2000.0, "Food", "Groceries", month=1, year=2024)
        repo.add("Transport Jan", 500.0, "Transport", "Gas", month=1, year=2024)
        repo.add("Food Feb", 2500.0, "Food", "Groceries", month=2, year=2024)

        repo.delete_by_month(year=2024, month=1)

        result = repo.read_all()
        assert len(result) == 1
        assert result.iloc[0]["name"] == "Food Feb"

    def test_delete_by_category(self, db_session: Session):
        """Verify delete_by_category removes only project rules for that category."""
        repo = BudgetRepository(db_session)
        # Project rule
        repo.add("Wedding Budget", 50000.0, "Wedding", "Venue;Catering", month=None, year=None)
        # Monthly rule with same category -- should NOT be deleted
        repo.add("Wedding Jan", 5000.0, "Wedding", "Venue", month=1, year=2024)
        # Another project rule
        repo.add("Renovation", 25000.0, "Renovation", "Materials", month=None, year=None)

        repo.delete_by_category("Wedding")

        result = repo.read_all()
        assert len(result) == 2
        names = set(result["name"].tolist())
        assert "Wedding Budget" not in names
        assert "Wedding Jan" in names
        assert "Renovation" in names


    def test_delete_by_category_spares_yearly_rule(self, db_session: Session):
        """Verify delete_by_category keys on period_type, not null year/month.

        A yearly rule also has a null month; it must survive a project delete
        on the same category.
        """
        repo = BudgetRepository(db_session)
        repo.add("Wedding Project", 50000.0, "Wedding", "all_tags", month=None, year=None)
        repo.add("Wedding Y", 5000.0, "Wedding", "Venue", month=None, year=2024)

        repo.delete_by_category("Wedding")

        result = repo.read_all()
        assert list(result["name"]) == ["Wedding Y"]
        assert list(result["period_type"]) == ["yearly"]


class TestBudgetRepositoryEmptyUpdate:
    """Tests for update with empty fields."""

    def test_update_empty_fields_is_noop_for_existing_rule(self, db_session: Session):
        """Verify update leaves an existing rule untouched when no fields are given."""
        repo = BudgetRepository(db_session)
        repo.add("Food", 2000.0, "Food", "Groceries", month=1, year=2024)

        all_rules = repo.read_all()
        rule_id = int(all_rules.iloc[0]["id"])

        repo.update(rule_id)

        result = _rule(repo, rule_id)
        assert result.iloc[0]["amount"] == 2000.0
        assert result.iloc[0]["name"] == "Food"

    def test_update_empty_fields_unknown_id_raises(self, db_session: Session):
        """Verify an empty update on a missing id still raises EntityNotFoundException.

        The early return used to skip the existence check entirely.
        """
        from backend.errors import EntityNotFoundException

        repo = BudgetRepository(db_session)
        with pytest.raises(EntityNotFoundException, match="No rule found with ID 999"):
            repo.update(999)


class TestBudgetRepositoryPeriodType:
    """period_type is derived on write."""

    def test_add_derives_period_type(self, db_session):
        """add() sets monthly/yearly/project from year/month when not passed."""
        from backend.repositories.budget_repository import BudgetRepository
        repo = BudgetRepository(db_session)
        repo.add("M", 10.0, "Food", "Groceries", month=5, year=2026)
        repo.add("Y", 20.0, "Travel", "Hotels", month=None, year=2026)
        repo.add("P", 30.0, "Reno", "all_tags", month=None, year=None)

        by_name = {r["name"]: r["period_type"] for r in repo.read_all().to_dict("records")}
        assert by_name == {"M": "monthly", "Y": "yearly", "P": "project"}


@contextmanager
def _query_counter(db_session):
    """Yield a list that gains an entry for every SQL statement executed."""
    queries: list[str] = []

    def record(conn, cursor, statement, params, context, executemany):
        queries.append(statement)

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        yield queries
    finally:
        event.remove(engine, "before_cursor_execute", record)


class TestReadAllIsRequestCached:
    """Assembling one budget month asks for the rule set a dozen times over.

    Every ask re-read the whole table. The cache is the request-scoped one,
    so it dies with the session and is dropped on any commit.
    """

    def test_repeat_reads_hit_the_database_once(self, db_session, seed_budget_rules):
        """A second identical read is served from the session cache."""
        repo = BudgetRepository(db_session)
        with _query_counter(db_session) as queries:
            repo.read_all()
            repo.read_all()
            repo.read_all()

        assert len(queries) == 1

    def test_a_write_invalidates_the_cache(self, db_session, seed_budget_rules):
        """A newly added rule shows up in the next read."""
        repo = BudgetRepository(db_session)
        before = len(repo.read_all())

        repo.add(
            name="Fresh", amount=100.0, category="Food", tags="Groceries",
            month=1, year=2024,
        )

        assert len(repo.read_all()) == before + 1

    def test_callers_cannot_corrupt_the_cached_frame(self, db_session, seed_budget_rules):
        """The service layer rewrites ``tags`` in place on what it gets back."""
        repo = BudgetRepository(db_session)
        first = repo.read_all()
        first.loc[:, "name"] = "clobbered"

        assert "clobbered" not in set(repo.read_all()["name"])


class TestReadProjectCategoryNames:
    """BudgetRepository.read_project_category_names."""

    def test_distinct_project_categories_in_table_order(self, db_session: Session):
        """Only project rules count, closed ones included, each category once."""
        repo = BudgetRepository(db_session)
        assert repo.read_project_category_names() == []

        repo.add("Total Budget", 100.0, "Wedding", "", None, None, "project")
        repo.add("Food", 50.0, "Food", "", 1, 2024, "monthly")
        repo.add("Venue", 60.0, "Wedding", "Venue", None, None, "project")
        repo.add("Total Budget", 70.0, "Renovation", "", None, None, "project")
        db_session.expire_all()
        rules = repo.read_all()
        renovation = rules[rules["period_type"] == "project"]
        repo.update(
            int(renovation.loc[renovation["category"] == "Renovation", "id"].iloc[0]),
            is_closed=True,
        )

        assert repo.read_project_category_names() == ["Wedding", "Renovation"]
