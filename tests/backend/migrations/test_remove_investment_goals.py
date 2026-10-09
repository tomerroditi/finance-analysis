"""Tests for the migration that removes investment goals.

Savings goals became cash only. Investment goals are deleted with their links
and allocations, the ``kind`` / ``funding_*`` columns are dropped, cash goals
survive untouched, and the open goals' ledger is cleared to be recomputed.

``backend.database.get_database_url`` is monkeypatched so Alembic's online
``env.py`` targets the throwaway file instead of the user's real data DB.
"""

import os

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
ALEMBIC_DIR = os.path.join(PROJECT_ROOT, "backend", "alembic")

PREV_REVISION = "ee9bb63e5eaf"
REVISION = "2a03db5febd7"

_SCHEMA = (
    "CREATE TABLE savings_goals (id INTEGER PRIMARY KEY, name TEXT, status TEXT, "
    "contribution_category TEXT, contribution_tags TEXT, kind TEXT, "
    "funding_category TEXT, funding_tags TEXT)",
    "CREATE TABLE savings_goal_allocations ("
    "id INTEGER PRIMARY KEY, goal_id INTEGER, year INTEGER, month INTEGER, "
    "amount REAL, source TEXT)",
    "CREATE TABLE savings_goal_links (id INTEGER PRIMARY KEY, goal_id INTEGER, "
    "source_type TEXT, source_id TEXT, source_table TEXT, link_type TEXT)",
)


def _alembic_config(url: str) -> Config:
    """Build an Alembic Config pointed at the project's migration env."""
    cfg = Config()
    cfg.set_main_option("script_location", ALEMBIC_DIR)
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture
def goals_db(tmp_path, monkeypatch):
    """Two cash goals (one closed) and two investment goals, one with funding."""
    url = f"sqlite:///{tmp_path / 'goals.db'}"
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        for statement in _SCHEMA:
            conn.exec_driver_sql(statement)
        conn.exec_driver_sql(
            "INSERT INTO savings_goals VALUES "
            "(1, 'Trip', 'active', NULL, NULL, 'cash', NULL, NULL), "
            "(2, 'Done', 'closed', NULL, NULL, NULL, NULL, NULL), "
            "(3, 'Yearly', 'active', 'Investments', NULL, 'investment', NULL, NULL), "
            "(4, 'Kickstart', 'active', 'Investments', NULL, 'investment', "
            "'Other Income', 'Kickstart')"
        )
        conn.exec_driver_sql(
            "INSERT INTO savings_goal_allocations (goal_id, year, month, amount, source) "
            "VALUES (1, 2026, 1, 500, 'auto'), (2, 2025, 6, 300, 'auto'), "
            "(3, 2026, 1, 900, 'auto')"
        )
        conn.exec_driver_sql(
            "INSERT INTO savings_goal_links (goal_id, source_type, source_id, "
            "source_table, link_type) VALUES "
            "(1, 'transaction', '7', 'bank_transactions', 'utilization'), "
            "(4, 'transaction', '8', 'bank_transactions', 'contribution')"
        )
    engine.dispose()
    monkeypatch.setattr("backend.database.get_database_url", lambda *a, **k: url)
    return url


def _query(url: str, sql: str) -> list[tuple]:
    """Run one read query against the throwaway database."""
    engine = sa.create_engine(url)
    try:
        with engine.connect() as conn:
            return [tuple(row) for row in conn.exec_driver_sql(sql).fetchall()]
    finally:
        engine.dispose()


class TestRemoveInvestmentGoals:
    """Investment goals go, cash goals stay, and the columns are dropped."""

    def _upgrade(self, url: str) -> None:
        """Stamp the previous head and upgrade to this revision."""
        cfg = _alembic_config(url)
        command.stamp(cfg, PREV_REVISION)
        command.upgrade(cfg, REVISION)

    def test_investment_goals_are_deleted_with_their_rows(self, goals_db):
        """Both investment goals, funded or not, leave with links and allocations."""
        self._upgrade(goals_db)

        assert _query(goals_db, "SELECT id FROM savings_goals ORDER BY id") == [(1,), (2,)]
        assert _query(goals_db, "SELECT goal_id FROM savings_goal_links") == [(1,)]
        # Open goals' rows are cleared for the engine; the closed goal's stay.
        assert _query(goals_db, "SELECT goal_id FROM savings_goal_allocations") == [(2,)]

    def test_the_investment_columns_are_dropped(self, goals_db):
        """``kind`` and the funding rule columns no longer exist."""
        self._upgrade(goals_db)

        columns = {row[1] for row in _query(goals_db, "PRAGMA table_info(savings_goals)")}
        assert not columns & {"kind", "funding_category", "funding_tags"}
        assert {"name", "contribution_category", "contribution_tags"} <= columns

    def test_a_database_without_the_tables_is_left_alone(self, tmp_path, monkeypatch):
        """A database that never had savings goals upgrades without error."""
        url = f"sqlite:///{tmp_path / 'empty.db'}"
        sa.create_engine(url).dispose()
        monkeypatch.setattr("backend.database.get_database_url", lambda *a, **k: url)
        self._upgrade(url)
