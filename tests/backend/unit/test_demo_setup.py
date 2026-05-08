"""Unit tests for backend.demo_setup.prepare_empty_database.

The demo-DB preparation path already has implicit coverage via the demo route
tests; these tests focus on the empty-DB path that the Vercel demo-off
toggle relies on.
"""

import os
import sqlite3

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from backend import database
from backend.config import AppConfig
from backend.demo_setup import prepare_empty_database
from backend.models import Base, BankTransaction


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

    def test_does_not_overwrite_existing_production_db(self, isolated_config):
        """A real production DB with user transactions must survive a toggle-off.

        This is the load-bearing safety guard. On a laptop, ``data.db`` always
        exists (created by ``lifespan``) and contains the user's actual
        finances. ``toggle_demo_mode(enabled=False)`` calls
        ``prepare_empty_database`` — if that ever copied the bundled empty DB
        over the existing file, the user would lose months of scraped
        transactions, budgets, and investments.
        """
        config = AppConfig()
        target = config.get_db_path()

        # Stand up a realistic production DB: full ORM schema + a real
        # transaction record the way the app would store one.
        os.makedirs(os.path.dirname(target), exist_ok=True)
        engine = create_engine(f"sqlite:///{target}", poolclass=NullPool)
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine)
        with SessionLocal() as session:
            session.add(
                BankTransaction(
                    id="prod-tx-1",
                    account_name="Hapoalim",
                    date="2026-04-01",
                    amount=-1234.56,
                    description="Rent payment",
                    category="Household",
                    tag="Mortgage",
                )
            )
            session.commit()
        engine.dispose()

        prepare_empty_database()

        # The user's transaction must still be there, untouched.
        with sqlite3.connect(target) as conn:
            row = conn.execute(
                "SELECT id, amount, description FROM bank_transactions"
            ).fetchone()
            assert row == ("prod-tx-1", -1234.56, "Rent payment")
            # And the bundled empty DB's seeded categories must NOT have been
            # copied in — proves no copy happened, not just that this row
            # survived merging.
            category_count = conn.execute(
                "SELECT COUNT(*) FROM categories"
            ).fetchone()[0]
            assert category_count == 0
