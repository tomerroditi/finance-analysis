"""Tests for the migration repairing ``retirement_goals``' missing columns.

Two earlier revisions guarded on ``retirement_goal`` (singular) while the
table is ``retirement_goals``, so both silently took their "table absent"
branch and were stamped as applied without adding anything. Every database
created before them is missing four columns the ORM maps, which makes
``GET /api/retirement/goal`` and ``/api/retirement/projections`` 500 with
``no such column: retirement_goals.monthly_income``.

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

PREV_REVISION = "c5b7e9d1f3a8"
REVISION = "e7a9c1b3d5f8"

REPAIRED_COLUMNS = (
    "monthly_income",
    "net_worth_override",
    "monthly_expenses_override",
    "total_investments_override",
)

# The table exactly as an affected database holds it: every column the model
# declared before the two mistyped revisions, and none of the four they were
# supposed to add.
_SCHEMA = """
CREATE TABLE retirement_goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    current_age INTEGER NOT NULL,
    gender TEXT NOT NULL DEFAULT 'male',
    target_retirement_age INTEGER NOT NULL DEFAULT 50,
    life_expectancy INTEGER NOT NULL DEFAULT 90,
    monthly_expenses_in_retirement REAL NOT NULL,
    inflation_rate REAL NOT NULL DEFAULT 0.025,
    expected_return_rate REAL NOT NULL DEFAULT 0.04,
    withdrawal_rate REAL NOT NULL DEFAULT 0.035,
    pension_monthly_payout_estimate REAL NOT NULL DEFAULT 0.0,
    keren_hishtalmut_balance REAL NOT NULL DEFAULT 0.0,
    keren_hishtalmut_monthly_contribution REAL NOT NULL DEFAULT 0.0,
    bituach_leumi_eligible INTEGER NOT NULL DEFAULT 1,
    bituach_leumi_monthly_estimate REAL NOT NULL DEFAULT 2800.0,
    other_passive_income REAL NOT NULL DEFAULT 0.0,
    created_at TEXT,
    updated_at TEXT
);
"""


def _alembic_config(url: str) -> Config:
    """Build an Alembic Config pointed at the project's migration env."""
    cfg = Config()
    cfg.set_main_option("script_location", ALEMBIC_DIR)
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _columns(url: str) -> set[str]:
    """Return the column names currently on ``retirement_goals``."""
    engine = sa.create_engine(url)
    try:
        return {c["name"] for c in sa.inspect(engine).get_columns("retirement_goals")}
    finally:
        engine.dispose()


def _goal_row(url: str) -> tuple:
    """Return the single seeded goal row."""
    engine = sa.create_engine(url)
    try:
        with engine.connect() as conn:
            return conn.exec_driver_sql(
                "SELECT current_age, monthly_expenses_in_retirement FROM retirement_goals"
            ).fetchone()
    finally:
        engine.dispose()


@pytest.fixture
def affected_db(tmp_path, monkeypatch):
    """A database shaped like one the mistyped revisions skipped over."""
    url = f"sqlite:///{tmp_path / 'affected.db'}"
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        conn.exec_driver_sql(_SCHEMA.strip().rstrip(";"))
        conn.exec_driver_sql(
            "INSERT INTO retirement_goals "
            "(current_age, monthly_expenses_in_retirement) VALUES (35, 18000.0)"
        )
    engine.dispose()

    monkeypatch.setattr("backend.database.get_database_url", lambda *a, **k: url)
    return url


class TestRepairRetirementGoalsColumns:
    """Tests for restoring the four columns the mistyped revisions never added."""

    def test_affected_database_gains_every_missing_column(self, affected_db):
        """All four columns land on a database the earlier revisions skipped."""
        cfg = _alembic_config(affected_db)
        command.stamp(cfg, PREV_REVISION)
        command.upgrade(cfg, REVISION)

        columns = _columns(affected_db)
        for name in REPAIRED_COLUMNS:
            assert name in columns

    def test_existing_goal_survives_the_repair(self, affected_db):
        """The table is altered, not rebuilt from scratch — the row stays."""
        cfg = _alembic_config(affected_db)
        command.stamp(cfg, PREV_REVISION)
        command.upgrade(cfg, REVISION)

        assert _goal_row(affected_db) == (35, 18000.0)

    def test_repaired_columns_are_nullable(self, affected_db):
        """Existing rows have no value for them, so they must accept NULL."""
        cfg = _alembic_config(affected_db)
        command.stamp(cfg, PREV_REVISION)
        command.upgrade(cfg, REVISION)

        engine = sa.create_engine(affected_db)
        try:
            columns = {
                c["name"]: c for c in sa.inspect(engine).get_columns("retirement_goals")
            }
        finally:
            engine.dispose()

        for name in REPAIRED_COLUMNS:
            assert columns[name]["nullable"] is True

    def test_rerunning_on_a_healthy_database_is_a_no_op(self, affected_db):
        """A fresh install already has the columns; the repair must not fail."""
        cfg = _alembic_config(affected_db)
        command.stamp(cfg, PREV_REVISION)
        command.upgrade(cfg, REVISION)

        command.downgrade(cfg, PREV_REVISION)
        command.upgrade(cfg, REVISION)
        command.upgrade(cfg, REVISION)

        columns = _columns(affected_db)
        for name in REPAIRED_COLUMNS:
            assert name in columns

    def test_missing_table_is_not_an_error(self, tmp_path, monkeypatch):
        """A partial database with no such table has nothing to repair."""
        url = f"sqlite:///{tmp_path / 'empty.db'}"
        sa.create_engine(url).dispose()
        monkeypatch.setattr("backend.database.get_database_url", lambda *a, **k: url)

        cfg = _alembic_config(url)
        command.stamp(cfg, PREV_REVISION)
        command.upgrade(cfg, REVISION)

        engine = sa.create_engine(url)
        try:
            assert "retirement_goals" not in sa.inspect(engine).get_table_names()
        finally:
            engine.dispose()
