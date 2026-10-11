"""Tests for the migration that records where a bank balance came from.

``backend.database.get_database_url`` is monkeypatched so Alembic's online
``env.py`` targets the throwaway file instead of the user's real data DB.
"""

import os

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
ALEMBIC_DIR = os.path.join(PROJECT_ROOT, "backend", "alembic")

_LEGACY_TABLE = """
CREATE TABLE bank_balances (
    id INTEGER PRIMARY KEY,
    provider VARCHAR NOT NULL,
    account_name VARCHAR NOT NULL,
    balance FLOAT NOT NULL,
    prior_wealth_amount FLOAT NOT NULL,
    last_manual_update VARCHAR,
    last_scrape_update VARCHAR,
    created_at DATETIME,
    updated_at DATETIME
)
"""


def _upgrade(tmp_path, monkeypatch) -> sa.Engine:
    """Build the pre-migration table with two rows and upgrade it twice."""
    url = f"sqlite:///{tmp_path / 'balances.db'}"
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        conn.exec_driver_sql(_LEGACY_TABLE)
        conn.exec_driver_sql(
            "INSERT INTO bank_balances (provider, account_name, balance, "
            "prior_wealth_amount, last_manual_update) VALUES "
            "('hapoalim', 'Shir', 72604.54, 19450.86, '2026-07-10'), "
            "('leumi', 'Old', 100.0, 100.0, NULL)"
        )
    monkeypatch.setattr("backend.database.get_database_url", lambda *a, **k: url)
    cfg = Config()
    cfg.set_main_option("script_location", ALEMBIC_DIR)
    cfg.set_main_option("sqlalchemy.url", url)
    command.stamp(cfg, "31ce8f3f673d")
    command.upgrade(cfg, "7c1e9a3b5d20")
    command.upgrade(cfg, "7c1e9a3b5d20")
    return engine


class TestAddScrapedBankBalanceColumns:
    """The columns are added once, and typed balances are marked manual."""

    def test_existing_balances_keep_their_values(self, tmp_path, monkeypatch):
        """Nothing about a stored balance changes but the two new columns."""
        engine = _upgrade(tmp_path, monkeypatch)
        try:
            with engine.begin() as conn:
                rows = conn.exec_driver_sql(
                    "SELECT provider, balance, prior_wealth_amount, balance_source, "
                    "last_drift FROM bank_balances ORDER BY provider"
                ).fetchall()
        finally:
            engine.dispose()

        assert [tuple(r) for r in rows] == [
            ("hapoalim", 72604.54, 19450.86, "manual", None),
            ("leumi", 100.0, 100.0, None, None),
        ]
