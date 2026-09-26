"""Tests for the migration that restates the savings-goal ledger.

Rule-funded goals changed what an allocation row means, so the open goals'
rows are cleared for the engine to recompute on the next read. Closed goals
are frozen and must keep theirs.

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

PREV_REVISION = "b9a0f25d4d28"
REVISION = "1f504bcccd13"

_SCHEMA = (
    "CREATE TABLE savings_goals (id INTEGER PRIMARY KEY, name TEXT, status TEXT)",
    "CREATE TABLE savings_goal_allocations ("
    "id INTEGER PRIMARY KEY, goal_id INTEGER, year INTEGER, month INTEGER, "
    "amount REAL, source TEXT)",
)


def _alembic_config(url: str) -> Config:
    """Build an Alembic Config pointed at the project's migration env."""
    cfg = Config()
    cfg.set_main_option("script_location", ALEMBIC_DIR)
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture
def ledger_db(tmp_path, monkeypatch):
    """A database holding one open and one closed goal, each with ledger rows."""
    url = f"sqlite:///{tmp_path / 'ledger.db'}"
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        for statement in _SCHEMA:
            conn.exec_driver_sql(statement)
        conn.exec_driver_sql(
            "INSERT INTO savings_goals VALUES (1, 'Open', 'active'), (2, 'Done', 'closed')"
        )
        conn.exec_driver_sql(
            "INSERT INTO savings_goal_allocations (goal_id, year, month, amount, source) "
            "VALUES (1, 2026, 1, 500, 'auto'), (1, 2026, 2, 700, 'auto'), "
            "(2, 2025, 6, 300, 'auto')"
        )
    engine.dispose()
    monkeypatch.setattr("backend.database.get_database_url", lambda *a, **k: url)
    return url


def _goal_ids_with_rows(url: str) -> list[int]:
    """Return the goals that still hold ledger rows."""
    engine = sa.create_engine(url)
    try:
        with engine.connect() as conn:
            rows = conn.exec_driver_sql(
                "SELECT DISTINCT goal_id FROM savings_goal_allocations ORDER BY goal_id"
            ).fetchall()
        return [row[0] for row in rows]
    finally:
        engine.dispose()


class TestRestateSavingsGoalLedger:
    """The open goals' ledger is cleared; a closed goal's frozen rows stay."""

    def test_open_goals_lose_their_rows_and_closed_goals_keep_theirs(self, ledger_db):
        """Only the closed goal's rows survive the upgrade."""
        cfg = _alembic_config(ledger_db)
        command.stamp(cfg, PREV_REVISION)
        command.upgrade(cfg, REVISION)

        assert _goal_ids_with_rows(ledger_db) == [2]

    def test_a_database_without_the_tables_is_left_alone(self, tmp_path, monkeypatch):
        """A database that never had savings goals upgrades without error."""
        url = f"sqlite:///{tmp_path / 'empty.db'}"
        sa.create_engine(url).dispose()
        monkeypatch.setattr("backend.database.get_database_url", lambda *a, **k: url)
        cfg = _alembic_config(url)
        command.stamp(cfg, PREV_REVISION)
        command.upgrade(cfg, REVISION)
