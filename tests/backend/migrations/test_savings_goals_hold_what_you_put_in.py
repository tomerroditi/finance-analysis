"""Tests for the migration that turns the allocation ledger into goal entries.

Every goal keeps what it held: each allocation row (a clawback included)
becomes a ``migrated`` entry dated the first of its month, an opening balance
becomes an entry at the goal's start, ``monthly_cap`` carries into
``monthly_amount``, and contribution links on money going out are dropped.

``backend.database.get_database_url`` is monkeypatched so Alembic's online
``env.py`` targets the throwaway file instead of the user's real data DB.
"""

import os

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from backend.models.base import Base
from backend.models.savings_goal import SavingsGoalEntry

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
ALEMBIC_DIR = os.path.join(PROJECT_ROOT, "backend", "alembic")

PREV_REVISION = "f54bd91edd97"
REVISION = "31ce8f3f673d"

_SCHEMA = (
    "CREATE TABLE savings_goals (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
    "target_amount REAL NOT NULL, opening_balance REAL NOT NULL DEFAULT 0, "
    "priority INTEGER NOT NULL DEFAULT 0, monthly_cap REAL, start_month TEXT, "
    "target_date TEXT, contribution_category TEXT, contribution_tags TEXT, "
    "utilization_category TEXT, utilization_tags TEXT, "
    "status TEXT NOT NULL DEFAULT 'active', closed_month TEXT, notes TEXT, "
    "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)",
    "CREATE TABLE savings_goal_allocations (id INTEGER PRIMARY KEY, "
    "goal_id INTEGER NOT NULL, year INTEGER NOT NULL, month INTEGER NOT NULL, "
    "amount REAL NOT NULL, source TEXT NOT NULL, "
    "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)",
    "CREATE TABLE savings_goal_links (id INTEGER PRIMARY KEY, "
    "goal_id INTEGER NOT NULL, source_type TEXT NOT NULL, "
    "source_id INTEGER NOT NULL, source_table TEXT NOT NULL, "
    "link_type TEXT NOT NULL, created_at DATETIME, updated_at DATETIME)",
    "CREATE TABLE bank_transactions (unique_id INTEGER PRIMARY KEY, amount REAL)",
    "CREATE TABLE credit_card_transactions (unique_id INTEGER PRIMARY KEY, amount REAL)",
    "CREATE TABLE split_transactions (id INTEGER PRIMARY KEY, amount REAL)",
)

_NOW = "'2026-01-05 10:00:00'"

_ROWS = (
    # Trip: opening balance at its start month, and a monthly cap.
    # Car: no opening balance, no cap.
    # Loose: an opening balance but no start month — dated by when it was made.
    "INSERT INTO savings_goals (id, name, target_amount, opening_balance, priority, "
    "monthly_cap, start_month, contribution_category, utilization_category, status, "
    "created_at, updated_at) VALUES "
    f"(1, 'Trip', 5000, 1000, 0, 500, '2026-01', 'Other Income', 'Travel', "
    f"'active', {_NOW}, {_NOW}), "
    f"(2, 'Car', 9000, 0, 1, NULL, '2025-12', NULL, NULL, 'closed', {_NOW}, {_NOW}), "
    "(3, 'Loose', 700, 200, 2, NULL, NULL, NULL, NULL, 'active', "
    "'2025-11-20 09:00:00', '2025-11-20 09:00:00')",
    "INSERT INTO savings_goal_allocations (goal_id, year, month, amount, source, "
    "created_at, updated_at) VALUES "
    f"(1, 2026, 1, 300, 'auto', {_NOW}, {_NOW}), "
    f"(1, 2026, 2, -120.5, 'auto', {_NOW}, {_NOW}), "
    f"(2, 2025, 12, 400, 'auto', {_NOW}, {_NOW}), "
    f"(2, 2026, 1, 0.001, 'auto', {_NOW}, {_NOW}), "
    f"(99, 2026, 1, 50, 'auto', {_NOW}, {_NOW})",
    # bank #1 goes out, bank #2 comes in; #3 goes out at the bank but comes in
    # on the card, so a link must be judged by its own table.
    "INSERT INTO bank_transactions VALUES (1, -50), (2, 80), (3, -70)",
    "INSERT INTO credit_card_transactions VALUES (3, 70), (4, -20)",
    "INSERT INTO split_transactions VALUES (5, -30), (6, 30)",
    "INSERT INTO savings_goal_links (id, goal_id, source_type, source_id, "
    "source_table, link_type) VALUES "
    "(1, 1, 'transaction', 1, 'bank_transactions', 'contribution'), "
    "(2, 1, 'transaction', 2, 'bank_transactions', 'contribution'), "
    "(3, 1, 'transaction', 3, 'credit_card_transactions', 'contribution'), "
    "(4, 1, 'transaction', 4, 'credit_card_transactions', 'utilization'), "
    "(5, 1, 'split', 5, 'bank_transactions', 'contribution'), "
    "(6, 1, 'split', 6, 'bank_transactions', 'contribution'), "
    "(7, 1, 'transaction', 3, 'bank_transactions', 'utilization')",
)


def _alembic_config(url: str) -> Config:
    """Build an Alembic Config pointed at the project's migration env."""
    cfg = Config()
    cfg.set_main_option("script_location", ALEMBIC_DIR)
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _build(url: str, *, entries_table: bool) -> None:
    """Create the pre-migration schema and rows.

    With ``entries_table`` the database also holds an empty
    ``savings_goal_entries`` table, as startup's ``create_all`` makes it
    before Alembic runs.
    """
    engine = sa.create_engine(url)
    try:
        with engine.begin() as conn:
            for statement in (*_SCHEMA, *_ROWS):
                conn.exec_driver_sql(statement)
        if entries_table:
            SavingsGoalEntry.__table__.create(engine)
    finally:
        engine.dispose()


def _query(url: str, sql: str) -> list[tuple]:
    """Run one read query against the throwaway database."""
    engine = sa.create_engine(url)
    try:
        with engine.connect() as conn:
            return [tuple(row) for row in conn.exec_driver_sql(sql).fetchall()]
    finally:
        engine.dispose()


def _upgrade(url: str) -> None:
    """Stamp the previous head and upgrade to this revision."""
    cfg = _alembic_config(url)
    command.stamp(cfg, PREV_REVISION)
    command.upgrade(cfg, REVISION)


_ENTRIES_SQL = (
    "SELECT goal_id, date, amount, source, note FROM savings_goal_entries "
    "ORDER BY goal_id, date, amount"
)

_EXPECTED_ENTRIES = [
    (1, "2026-01-01", 300.0, "migrated", None),
    (1, "2026-01-01", 1000.0, "migrated", "Opening balance"),
    (1, "2026-02-01", -120.5, "migrated", None),
    (2, "2025-12-01", 400.0, "migrated", None),
    (3, "2025-11-01", 200.0, "migrated", "Opening balance"),
]


@pytest.fixture(params=[False, True], ids=["no-entries-table", "create-all-first"])
def goals_db(request, tmp_path, monkeypatch):
    """The old ledger, with or without ``create_all`` having made the entries table."""
    url = f"sqlite:///{tmp_path / 'goals.db'}"
    _build(url, entries_table=request.param)
    monkeypatch.setattr("backend.database.get_database_url", lambda *a, **k: url)
    return url


class TestSavingsGoalsHoldWhatYouPutIn:
    """Allocations and opening balances become entries; the old ledger goes."""

    def test_allocations_and_opening_balances_become_entries(self, goals_db):
        """Same amounts, dated the first of their month; dust and orphans are skipped."""
        _upgrade(goals_db)

        assert _query(goals_db, _ENTRIES_SQL) == _EXPECTED_ENTRIES

    def test_entries_carry_timestamps(self, goals_db):
        """Every migrated row is stamped, so the ORM can read it back."""
        _upgrade(goals_db)

        assert _query(
            goals_db,
            "SELECT COUNT(*) FROM savings_goal_entries "
            "WHERE created_at IS NULL OR updated_at IS NULL",
        ) == [(0,)]

    def test_monthly_cap_becomes_monthly_amount(self, goals_db):
        """The cap carries over as the monthly amount; a missing cap stays missing."""
        _upgrade(goals_db)

        assert _query(
            goals_db, "SELECT id, name, monthly_amount FROM savings_goals ORDER BY id"
        ) == [(1, "Trip", 500.0), (2, "Car", None), (3, "Loose", None)]

    def test_old_columns_and_the_allocations_table_are_gone(self, goals_db):
        """``monthly_cap``, ``opening_balance`` and the ledger table are dropped."""
        _upgrade(goals_db)

        columns = {
            row[1] for row in _query(goals_db, "PRAGMA table_info(savings_goals)")
        }
        assert not columns & {"monthly_cap", "opening_balance"}
        assert {"monthly_amount", "contribution_category", "status"} <= columns
        tables = {
            row[0]
            for row in _query(
                goals_db, "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert "savings_goal_allocations" not in tables

    def test_goal_rows_survive_the_table_rebuild(self, goals_db):
        """Rules, status and timestamps come through the column drop untouched."""
        _upgrade(goals_db)

        assert _query(
            goals_db,
            "SELECT id, contribution_category, utilization_category, status, "
            "created_at IS NOT NULL FROM savings_goals ORDER BY id",
        ) == [
            (1, "Other Income", "Travel", "active", 1),
            (2, None, None, "closed", 1),
            (3, None, None, "active", 1),
        ]

    def test_only_outgoing_contribution_links_are_removed(self, goals_db):
        """Income links and every spending link stay; a link is judged by its own table."""
        _upgrade(goals_db)

        assert _query(goals_db, "SELECT id FROM savings_goal_links ORDER BY id") == [
            (2,),
            (3,),
            (4,),
            (6,),
            (7,),
        ]

    def test_running_it_again_changes_nothing(self, goals_db):
        """A second pass over an upgraded database adds no entries and drops nothing."""
        _upgrade(goals_db)
        _upgrade(goals_db)

        assert _query(goals_db, _ENTRIES_SQL) == _EXPECTED_ENTRIES
        assert _query(
            goals_db, "SELECT monthly_amount FROM savings_goals WHERE id = 1"
        ) == [(500.0,)]


class TestFreshDatabases:
    """Databases that never had the old ledger."""

    def test_a_database_without_the_tables_is_left_alone(self, tmp_path, monkeypatch):
        """A database that never had savings goals only gains the entries table."""
        url = f"sqlite:///{tmp_path / 'empty.db'}"
        sa.create_engine(url).dispose()
        monkeypatch.setattr("backend.database.get_database_url", lambda *a, **k: url)

        _upgrade(url)

        tables = {
            row[0]
            for row in _query(
                url, "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert "savings_goal_entries" in tables
        assert "savings_goals" not in tables

    def test_a_fresh_install_upgrades_to_head(self, tmp_path, monkeypatch):
        """``create_all`` then ``upgrade head`` — what startup does — leaves the new schema."""
        url = f"sqlite:///{tmp_path / 'fresh.db'}"
        engine = sa.create_engine(url)
        Base.metadata.create_all(engine)
        engine.dispose()
        monkeypatch.setattr("backend.database.get_database_url", lambda *a, **k: url)

        cfg = _alembic_config(url)
        command.upgrade(cfg, "head")

        columns = {row[1] for row in _query(url, "PRAGMA table_info(savings_goals)")}
        assert "monthly_amount" in columns
        assert not columns & {"monthly_cap", "opening_balance"}
        head = ScriptDirectory.from_config(cfg).get_current_head()
        assert _query(url, "SELECT version_num FROM alembic_version") == [(head,)]
