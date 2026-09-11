"""Tests for the migration that labels legacy closing snapshots as ``closed``.

Closing an investment has always written a zero snapshot, but before the
``closed`` source existed it was stored as ``manual``. Only ``closed``
snapshots follow an investment's transactions when a later one lands, so the
legacy zeros have to be recognised first.

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

PREV_REVISION = "c1a3e5b7d9f2"
REVISION = "d4e6f8a0b2c4"

_SCHEMA = """
CREATE TABLE investments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    tag TEXT NOT NULL,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    is_closed INTEGER DEFAULT 0,
    closed_date TEXT,
    created_date TEXT NOT NULL,
    UNIQUE(category, tag)
);
CREATE TABLE investment_balance_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    investment_id INTEGER,
    date TEXT,
    balance REAL,
    source TEXT,
    UNIQUE(investment_id, date)
);
"""

# (investment id, tag, is_closed, [(date, balance, source), ...])
_INVESTMENTS = (
    (1, "Legacy Close", 1, [("2024-06-01", 5000.0, "manual"), ("2024-12-08", 0.0, "manual")]),
    (2, "Open Fund", 0, [("2024-12-08", 0.0, "manual")]),
    (3, "Valued Last", 1, [("2024-01-01", 0.0, "manual"), ("2024-06-01", 800.0, "manual")]),
    (4, "Already Closed", 1, [("2025-03-01", 0.0, "closed")]),
)


def _alembic_config(url: str) -> Config:
    """Build an Alembic Config pointed at the project's migration env."""
    cfg = Config()
    cfg.set_main_option("script_location", ALEMBIC_DIR)
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture
def legacy_db(tmp_path, monkeypatch):
    """Create a temp DB holding closed and open investments with zero snapshots."""
    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        for statement in filter(None, (s.strip() for s in _SCHEMA.split(";"))):
            conn.exec_driver_sql(statement)
        for inv_id, tag, is_closed, snapshots in _INVESTMENTS:
            conn.exec_driver_sql(
                "INSERT INTO investments (id, category, tag, type, name, is_closed, created_date) "
                "VALUES (?, 'Investments', ?, 'etf', ?, ?, '2024-01-01')",
                (inv_id, tag, tag, is_closed),
            )
            for snap_date, balance, source in snapshots:
                conn.exec_driver_sql(
                    "INSERT INTO investment_balance_snapshots "
                    "(investment_id, date, balance, source) VALUES (?, ?, ?, ?)",
                    (inv_id, snap_date, balance, source),
                )
    engine.dispose()

    monkeypatch.setattr("backend.database.get_database_url", lambda *a, **k: url)
    return url


def _sources(url):
    """Return ``{(investment_id, date): source}`` for every snapshot."""
    engine = sa.create_engine(url)
    try:
        with engine.connect() as conn:
            rows = conn.exec_driver_sql(
                "SELECT investment_id, date, source FROM investment_balance_snapshots"
            ).fetchall()
    finally:
        engine.dispose()
    return {(inv_id, snap_date): source for inv_id, snap_date, source in rows}


def _upgrade(url):
    """Stamp the DB one revision below the migration and upgrade to it."""
    cfg = _alembic_config(url)
    command.stamp(cfg, PREV_REVISION)
    command.upgrade(cfg, REVISION)


class TestAdoptLegacyClosingSnapshots:
    """Tests for relabelling a closed investment's final zero as ``closed``."""

    def test_final_zero_of_a_closed_investment_becomes_closed(self, legacy_db):
        """Verify the legacy close zero is relabelled and earlier snapshots are not."""
        _upgrade(legacy_db)

        sources = _sources(legacy_db)
        assert sources[(1, "2024-12-08")] == "closed"
        assert sources[(1, "2024-06-01")] == "manual"

    def test_open_investment_zero_is_left_alone(self, legacy_db):
        """Verify a zero snapshot on an open investment is a real valuation, not a close."""
        _upgrade(legacy_db)

        assert _sources(legacy_db)[(2, "2024-12-08")] == "manual"

    def test_zero_that_is_not_the_final_snapshot_is_left_alone(self, legacy_db):
        """Verify a closed investment whose newest snapshot is non-zero keeps every label."""
        _upgrade(legacy_db)

        sources = _sources(legacy_db)
        assert sources[(3, "2024-01-01")] == "manual"
        assert sources[(3, "2024-06-01")] == "manual"

    def test_upgrade_is_idempotent(self, legacy_db):
        """Verify running the relabel twice changes nothing further."""
        _upgrade(legacy_db)
        first = _sources(legacy_db)
        cfg = _alembic_config(legacy_db)
        command.downgrade(cfg, PREV_REVISION)
        command.upgrade(cfg, REVISION)

        assert _sources(legacy_db) == first
        assert first[(4, "2025-03-01")] == "closed"
