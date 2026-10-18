"""Tests for the migration that lets a refund link cover one split part.

``backend.database.get_database_url`` is monkeypatched so Alembic's online
``env.py`` targets the throwaway file instead of the user's real data DB.
"""

import os

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
ALEMBIC_DIR = os.path.join(PROJECT_ROOT, "backend", "alembic")


def _alembic_config(url: str) -> Config:
    """Build an Alembic Config pointed at the project's migration env."""
    cfg = Config()
    cfg.set_main_option("script_location", ALEMBIC_DIR)
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _columns(url: str) -> list[str]:
    """Return the ``refund_links`` column names."""
    engine = sa.create_engine(url)
    try:
        return [c["name"] for c in sa.inspect(engine).get_columns("refund_links")]
    finally:
        engine.dispose()


class TestAddRefundSplitId:
    """The column is added once, keeps existing links, and downgrades cleanly."""

    def test_upgrade_adds_column_and_keeps_links(self, tmp_path, monkeypatch):
        """An existing link survives with no split part; a second upgrade is a no-op."""
        url = f"sqlite:///{tmp_path / 'links.db'}"
        engine = sa.create_engine(url)
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "CREATE TABLE refund_links (id INTEGER PRIMARY KEY, pending_refund_id INTEGER, "
                "refund_transaction_id INTEGER, refund_source VARCHAR, amount FLOAT, "
                "created_at VARCHAR)"
            )
            conn.exec_driver_sql(
                "INSERT INTO refund_links VALUES (1, 1, 7, 'bank_transactions', 50.0, NULL)"
            )
        engine.dispose()
        monkeypatch.setattr("backend.database.get_database_url", lambda *a, **k: url)
        cfg = _alembic_config(url)
        command.stamp(cfg, "b7d9f1a3c5e2")

        command.upgrade(cfg, "e3c5a7b9d1f2")
        command.stamp(cfg, "b7d9f1a3c5e2")
        command.upgrade(cfg, "e3c5a7b9d1f2")

        assert "refund_split_id" in _columns(url)
        engine = sa.create_engine(url)
        try:
            with engine.begin() as conn:
                rows = conn.exec_driver_sql(
                    "SELECT id, amount, refund_split_id FROM refund_links"
                ).fetchall()
        finally:
            engine.dispose()
        assert [tuple(r) for r in rows] == [(1, 50.0, None)]

        command.downgrade(cfg, "b7d9f1a3c5e2")
        assert "refund_split_id" not in _columns(url)
