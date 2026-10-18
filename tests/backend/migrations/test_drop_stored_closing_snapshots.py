"""Tests for the migration that drops stored ``closed`` snapshots.

Valuation derives a closed investment's zero on every read, so the stored
copies the old close path wrote are removed; every other snapshot stays.

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

PREV_REVISION = "a9c1e3f5b7d9"
REVISION = "b2d4f6a8c0e1"

_SNAPSHOTS = (
    (1, "2024-06-01", 5000.0, "manual"),
    (1, "2024-12-08", 0.0, "closed"),
    (2, "2024-12-08", 0.0, "manual"),
    (2, "2025-01-01", 1200.0, "scraped"),
    (3, "2025-02-01", 900.0, "calculated"),
)


def _alembic_config(url: str) -> Config:
    """Build an Alembic Config pointed at the project's migration env."""
    cfg = Config()
    cfg.set_main_option("script_location", ALEMBIC_DIR)
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture
def snapshots_db(tmp_path, monkeypatch):
    """Create a temp DB holding snapshots of every source."""
    url = f"sqlite:///{tmp_path / 'snapshots.db'}"
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE investment_balance_snapshots ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, investment_id INTEGER, "
            "date TEXT, balance REAL, source TEXT, UNIQUE(investment_id, date))"
        )
        for row in _SNAPSHOTS:
            conn.exec_driver_sql(
                "INSERT INTO investment_balance_snapshots "
                "(investment_id, date, balance, source) VALUES (?, ?, ?, ?)",
                row,
            )
    engine.dispose()

    monkeypatch.setattr("backend.database.get_database_url", lambda *a, **k: url)
    return url


def _rows(url: str) -> set[tuple]:
    """Return every snapshot as ``(investment_id, date, balance, source)``."""
    engine = sa.create_engine(url)
    try:
        with engine.connect() as conn:
            rows = conn.exec_driver_sql(
                "SELECT investment_id, date, balance, source FROM investment_balance_snapshots"
            ).fetchall()
    finally:
        engine.dispose()
    return {tuple(r) for r in rows}


class TestDropStoredClosingSnapshots:
    """Tests for removing the stored closing zeros."""

    def test_only_closed_rows_are_dropped(self, snapshots_db):
        """Verify the ``closed`` row goes and every other source stays."""
        cfg = _alembic_config(snapshots_db)
        command.stamp(cfg, PREV_REVISION)

        command.upgrade(cfg, REVISION)

        assert _rows(snapshots_db) == {r for r in _SNAPSHOTS if r[3] != "closed"}

    def test_upgrade_is_idempotent(self, snapshots_db):
        """Verify a second pass changes nothing further."""
        cfg = _alembic_config(snapshots_db)
        command.stamp(cfg, PREV_REVISION)
        command.upgrade(cfg, REVISION)
        first = _rows(snapshots_db)

        command.downgrade(cfg, PREV_REVISION)
        command.upgrade(cfg, REVISION)

        assert _rows(snapshots_db) == first
