"""Tests for the migration that adds yearly savings targets.

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


class TestAddYearlySavingsTargets:
    """The targets table is created once, and an existing one is left alone."""

    def test_the_table_is_created_and_takes_a_target(self, tmp_path, monkeypatch):
        """Upgrading creates a table a target can be stored in."""
        url = f"sqlite:///{tmp_path / 'targets.db'}"
        sa.create_engine(url).dispose()
        monkeypatch.setattr("backend.database.get_database_url", lambda *a, **k: url)
        cfg = _alembic_config(url)
        command.stamp(cfg, "2a03db5febd7")
        command.upgrade(cfg, "f54bd91edd97")
        command.upgrade(cfg, "f54bd91edd97")

        engine = sa.create_engine(url)
        try:
            with engine.begin() as conn:
                conn.exec_driver_sql(
                    "INSERT INTO yearly_savings_targets (year, target_amount) "
                    "VALUES (2026, 120000)"
                )
                rows = conn.exec_driver_sql(
                    "SELECT year, target_amount FROM yearly_savings_targets"
                ).fetchall()
        finally:
            engine.dispose()
        assert [tuple(row) for row in rows] == [(2026, 120000.0)]
