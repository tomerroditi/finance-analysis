"""Tests for the migration that drops legacy transaction unique constraints.

These tests exercise the *real* migration module
(``d4f6a8c0e2b5_drop_legacy_transaction_unique_constraints``) end-to-end
through Alembic's programmatic API, rather than reimplementing its drop logic.

A temporary on-disk SQLite database is seeded with raw ``CREATE TABLE``
statements that include the legacy
``CONSTRAINT <table>_unique UNIQUE (provider, date, amount, id)`` — the shape
that exists in users' real databases but not in the current ORM models. The
database is then stamped to ``c3d5e7f9a1b3`` (one revision below the new
migration) and upgraded to ``head``.

Alembic's ``env.py`` overrides ``sqlalchemy.url`` with
``backend.database.get_database_url()`` in online mode, so the test
monkeypatches that function to point at the temporary database — this is the
clean way to redirect the full env machinery at a throwaway file without
touching the user's real data DB.
"""

import os

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
ALEMBIC_DIR = os.path.join(PROJECT_ROOT, "backend", "alembic")

PREV_REVISION = "c3d5e7f9a1b3"

_RAW_CREATE = """
CREATE TABLE {table} (
    unique_id INTEGER PRIMARY KEY AUTOINCREMENT,
    id VARCHAR,
    provider VARCHAR,
    date VARCHAR,
    amount FLOAT,
    account_name VARCHAR,
    description VARCHAR,
    source VARCHAR,
    CONSTRAINT {table}_unique UNIQUE (provider, date, amount, id)
)
"""


@pytest.fixture
def legacy_db(tmp_path, monkeypatch):
    """Create a temp SQLite DB with the legacy unique constraints, env-wired.

    Yields the ``sqlalchemy.url`` for the temp DB and patches
    ``backend.database.get_database_url`` so Alembic's online ``env.py``
    targets it.
    """
    db_path = tmp_path / "legacy.db"
    url = f"sqlite:///{db_path}"

    engine = sa.create_engine(url)
    with engine.begin() as conn:
        conn.exec_driver_sql(_RAW_CREATE.format(table="bank_transactions"))
        conn.exec_driver_sql(
            _RAW_CREATE.format(table="credit_card_transactions")
        )
    engine.dispose()

    monkeypatch.setattr(
        "backend.database.get_database_url", lambda *a, **k: url
    )

    yield url


def _alembic_config(url: str) -> Config:
    """Build an Alembic Config pointed at the project's migration env."""
    cfg = Config()
    cfg.set_main_option("script_location", ALEMBIC_DIR)
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _unique_constraint_names(url: str, table: str) -> set[str]:
    """Return the named unique constraints on ``table`` in the DB at ``url``."""
    engine = sa.create_engine(url)
    try:
        inspector = sa.inspect(engine)
        return {
            uc["name"]
            for uc in inspector.get_unique_constraints(table)
            if uc.get("name")
        }
    finally:
        engine.dispose()


class TestDropLegacyUniqueConstraintsMigration:
    """Tests for the upgrade that removes legacy transaction unique constraints."""

    def test_upgrade_removes_named_constraints(self, legacy_db):
        """Verify upgrade drops both legacy ``*_unique`` constraints."""
        assert "bank_transactions_unique" in _unique_constraint_names(
            legacy_db, "bank_transactions"
        )
        assert "credit_card_transactions_unique" in _unique_constraint_names(
            legacy_db, "credit_card_transactions"
        )

        cfg = _alembic_config(legacy_db)
        command.stamp(cfg, PREV_REVISION)
        command.upgrade(cfg, "head")

        assert "bank_transactions_unique" not in _unique_constraint_names(
            legacy_db, "bank_transactions"
        )
        assert "credit_card_transactions_unique" not in _unique_constraint_names(
            legacy_db, "credit_card_transactions"
        )

    def test_duplicate_rows_insertable_after_upgrade(self, legacy_db):
        """Verify two rows sharing (provider, date, amount, id) insert post-upgrade."""
        cfg = _alembic_config(legacy_db)
        command.stamp(cfg, PREV_REVISION)
        command.upgrade(cfg, "head")

        engine = sa.create_engine(legacy_db)
        try:
            with engine.begin() as conn:
                for desc in ("ATM #1", "ATM #2"):
                    conn.exec_driver_sql(
                        "INSERT INTO bank_transactions "
                        "(id, provider, date, amount, account_name, description, source) "
                        "VALUES ('', 'hapoalim', '2024-05-01', -18000.0, 'Main', ?, "
                        "'bank_transactions')",
                        (desc,),
                    )
                count = conn.exec_driver_sql(
                    "SELECT COUNT(*) FROM bank_transactions"
                ).scalar()
            assert count == 2
        finally:
            engine.dispose()

    def test_upgrade_idempotent_when_constraint_absent(self, tmp_path, monkeypatch):
        """Verify upgrade is a no-op when tables lack the legacy constraint.

        Mirrors a fresh database created from the ORM models (no named unique
        constraint): the migration must not raise.
        """
        db_path = tmp_path / "fresh.db"
        url = f"sqlite:///{db_path}"
        engine = sa.create_engine(url)
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "CREATE TABLE bank_transactions ("
                "unique_id INTEGER PRIMARY KEY AUTOINCREMENT, id VARCHAR, "
                "provider VARCHAR, date VARCHAR, amount FLOAT)"
            )
            conn.exec_driver_sql(
                "CREATE TABLE credit_card_transactions ("
                "unique_id INTEGER PRIMARY KEY AUTOINCREMENT, id VARCHAR, "
                "provider VARCHAR, date VARCHAR, amount FLOAT)"
            )
        engine.dispose()
        monkeypatch.setattr(
            "backend.database.get_database_url", lambda *a, **k: url
        )

        cfg = _alembic_config(url)
        command.stamp(cfg, PREV_REVISION)
        command.upgrade(cfg, "head")

        assert _unique_constraint_names(url, "bank_transactions") == set()
