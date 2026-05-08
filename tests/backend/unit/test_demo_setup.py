"""Unit tests for backend.demo_setup.prepare_empty_database.

The demo-DB preparation path already has implicit coverage via the demo route
tests; these tests focus on the empty-DB path that the Vercel demo-off
toggle relies on.
"""

import sqlite3

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from backend import database
from backend.config import AppConfig
from backend.demo_setup import prepare_empty_database


@pytest.fixture(autouse=True)
def isolated_config(tmp_path):
    """Point AppConfig at an isolated tmp dir and restore state after."""
    config = AppConfig()
    original_demo_mode = config._demo_mode
    original_base_dir = config._base_user_dir
    original_engine = database._engine

    config._demo_mode = False
    config._base_user_dir = str(tmp_path)
    database._engine = None

    yield tmp_path

    config._demo_mode = original_demo_mode
    config._base_user_dir = original_base_dir
    database._engine = original_engine


class TestPrepareEmptyDatabase:
    """Tests for prepare_empty_database()."""

    def test_creates_db_with_schema_and_default_categories(self, isolated_config):
        """A fresh tmp dir should yield a DB with all tables and seeded categories."""
        config = AppConfig()
        target = config.get_db_path()

        prepare_empty_database()

        assert isinstance(target, str)
        with sqlite3.connect(target) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            # Spot-check a representative slice of expected tables.
            assert {
                "categories",
                "bank_transactions",
                "credit_card_transactions",
                "investments",
                "tagging_rules",
            }.issubset(tables)

            category_count = conn.execute(
                "SELECT COUNT(*) FROM categories"
            ).fetchone()[0]
            assert category_count > 0

            # Every other table must be empty.
            for table in tables - {"categories", "sqlite_sequence"}:
                count = conn.execute(f"SELECT COUNT(*) FROM \"{table}\"").fetchone()[0]
                assert count == 0, f"Expected {table} to be empty, found {count} rows"

    def test_no_op_when_target_db_exists(self, isolated_config):
        """An existing production DB must not be overwritten — safety guard."""
        config = AppConfig()
        target = config.get_db_path()

        # Stand up a "real" production DB with a single sentinel table + row.
        import os
        os.makedirs(os.path.dirname(target), exist_ok=True)
        engine = create_engine(f"sqlite:///{target}", poolclass=NullPool)
        with engine.connect() as conn:
            conn.execute(text("CREATE TABLE sentinel (id INTEGER PRIMARY KEY, marker TEXT)"))
            conn.execute(text("INSERT INTO sentinel (marker) VALUES ('keep me')"))
            conn.commit()
        engine.dispose()

        prepare_empty_database()

        with sqlite3.connect(target) as conn:
            row = conn.execute("SELECT marker FROM sentinel").fetchone()
            assert row == ("keep me",)
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            # No new tables should have been created.
            assert tables == {"sentinel"}
