"""Tests for the migration that adds a billing date to card transactions.

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
CREATE TABLE credit_card_transactions (
    unique_id INTEGER PRIMARY KEY,
    id VARCHAR,
    date VARCHAR,
    provider VARCHAR,
    account_name VARCHAR,
    account_number VARCHAR,
    description VARCHAR,
    amount FLOAT,
    category VARCHAR,
    tag VARCHAR,
    source VARCHAR,
    type VARCHAR,
    status VARCHAR,
    created_at DATETIME,
    updated_at DATETIME
)
"""


class TestAddCardBillingDate:
    """The column is added once and existing rows are kept as they were."""

    def test_existing_rows_have_no_billing_date_yet(self, tmp_path, monkeypatch):
        """A stored purchase keeps every value and starts without a billing date."""
        url = f"sqlite:///{tmp_path / 'cards.db'}"
        engine = sa.create_engine(url)
        with engine.begin() as conn:
            conn.exec_driver_sql(_LEGACY_TABLE)
            conn.exec_driver_sql(
                "INSERT INTO credit_card_transactions (id, date, provider, amount) "
                "VALUES ('p-1', '2026-08-20', 'isracard', -100.0)"
            )
        monkeypatch.setattr("backend.database.get_database_url", lambda *a, **k: url)
        cfg = Config()
        cfg.set_main_option("script_location", ALEMBIC_DIR)
        cfg.set_main_option("sqlalchemy.url", url)
        command.stamp(cfg, "b7d9f1a3c5e2")
        command.upgrade(cfg, "9d3f5b7a1c42")
        command.upgrade(cfg, "9d3f5b7a1c42")
        try:
            with engine.begin() as conn:
                rows = conn.exec_driver_sql(
                    "SELECT id, date, amount, billing_date FROM credit_card_transactions"
                ).fetchall()
        finally:
            engine.dispose()

        assert [tuple(r) for r in rows] == [("p-1", "2026-08-20", -100.0, None)]
