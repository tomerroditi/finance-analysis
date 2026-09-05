"""Tests for the migration that merges policy-ID-forked insurance duplicates.

Exercises the real migration module
(``b7d4f1a9c3e2_canonicalize_insurance_policy_ids``) end-to-end through
Alembic's programmatic API against a temporary SQLite database seeded with
the exact shape of the September 2026 HaPhoenix incident: a first scrape that
stored ``"007-916-407357 (8296857)"`` and a second that reported the same
policy as ``"007-916-407357 (08296857)"``, forking a duplicate insurance
account, a duplicate Keren Hishtalmut investment (so its balance was counted
twice in net worth) and a second copy of every deposit.

As in ``test_drop_legacy_unique_constraints``, ``backend.database.
get_database_url`` is monkeypatched so Alembic's online ``env.py`` targets the
throwaway file instead of the user's real data DB.
"""

import os

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
ALEMBIC_DIR = os.path.join(PROJECT_ROOT, "backend", "alembic")

PREV_REVISION = "a3e5c7b9d1f4"
REVISION = "b7d4f1a9c3e2"

OLD_ID = "007-916-407357 (8296857)"
NEW_ID = "007-916-407357 (08296857)"
CANONICAL = "007-916-407357"
PENSION_ID = "1215029099"

_SCHEMA = """
CREATE TABLE insurance_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_id VARCHAR,
    policy_type VARCHAR,
    provider VARCHAR,
    account_name VARCHAR,
    custom_name VARCHAR,
    balance FLOAT,
    balance_date VARCHAR
);
CREATE TABLE investments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    tag TEXT NOT NULL,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    is_closed INTEGER DEFAULT 0,
    created_date TEXT NOT NULL,
    insurance_policy_id VARCHAR,
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
CREATE TABLE manual_investment_transactions (
    unique_id INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT, date TEXT, provider TEXT, account_name TEXT, account_number TEXT,
    description TEXT, amount REAL, category TEXT, tag TEXT
);
CREATE TABLE insurance_transactions (
    unique_id INTEGER PRIMARY KEY AUTOINCREMENT,
    id VARCHAR, date VARCHAR, provider VARCHAR, account_name VARCHAR,
    account_number VARCHAR, description VARCHAR, amount FLOAT,
    category VARCHAR, tag VARCHAR, source VARCHAR
);
"""


def _alembic_config(url: str) -> Config:
    """Build an Alembic Config pointed at the project's migration env."""
    cfg = Config()
    cfg.set_main_option("script_location", ALEMBIC_DIR)
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _seed(conn):
    """Insert the two-scrape fork: pre-reformat rows, then post-reformat rows."""
    for policy_id, balance, balance_date, custom_name in (
        (OLD_ID, 57110.0, "2026-08-18", "My KH"),
        (NEW_ID, 56957.0, "2026-08-30", None),
        (PENSION_ID, 254771.0, "2026-08-20", None),
    ):
        conn.exec_driver_sql(
            "INSERT INTO insurance_accounts "
            "(policy_id, policy_type, provider, account_name, custom_name, "
            " balance, balance_date) VALUES (?, ?, 'hafenix', 'KH', ?, ?, ?)",
            (
                policy_id,
                "pension" if policy_id == PENSION_ID else "hishtalmut",
                custom_name,
                balance,
                balance_date,
            ),
        )

    for policy_id in (OLD_ID, NEW_ID):
        conn.exec_driver_sql(
            "INSERT INTO investments "
            "(category, tag, type, name, created_date, insurance_policy_id) "
            "VALUES ('Investments', ?, 'hishtalmut', 'KH', '2026-03-11', ?)",
            (f"Keren Hishtalmut - hafenix ({policy_id})", policy_id),
        )

    # The old investment holds the history; the new one holds only the fresh
    # scrape, plus one date the old one already has.
    for investment_id, date, balance in (
        (1, "2026-08-04", 57667.0),
        (1, "2026-08-18", 57110.0),
        (2, "2026-08-18", 57110.0),
        (2, "2026-08-30", 56957.0),
    ):
        conn.exec_driver_sql(
            "INSERT INTO investment_balance_snapshots "
            "(investment_id, date, balance, source) VALUES (?, ?, ?, 'scraped')",
            (investment_id, date, balance),
        )

    # Two deposits, each reported under both policy-ID spellings; the original
    # rows carry a tag the user assigned.
    for policy_id, date, amount, tag in (
        (OLD_ID, "2025-12-08", 1571.0, "reviewed"),
        (OLD_ID, "2026-01-12", 1571.0, "reviewed"),
        (NEW_ID, "2025-12-08", 1571.0, None),
        (NEW_ID, "2026-01-12", 1571.0, None),
        (PENSION_ID, "2026-08-05", 4200.0, None),
    ):
        conn.exec_driver_sql(
            "INSERT INTO insurance_transactions "
            "(id, date, provider, account_name, account_number, description, "
            " amount, tag, source) "
            "VALUES (?, ?, 'hafenix', 'KH', ?, 'הפקדה', ?, ?, "
            "'insurance_transactions')",
            (f"{policy_id}_{date}_{amount}", date, policy_id, amount, tag),
        )


@pytest.fixture
def forked_db(tmp_path, monkeypatch):
    """Create a temp DB holding the forked duplicates, wired into Alembic's env."""
    url = f"sqlite:///{tmp_path / 'forked.db'}"
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        for statement in filter(None, (s.strip() for s in _SCHEMA.split(";"))):
            conn.exec_driver_sql(statement)
        _seed(conn)
    engine.dispose()

    monkeypatch.setattr("backend.database.get_database_url", lambda *a, **k: url)
    return url


def _rows(url, sql):
    """Run ``sql`` against the DB at ``url`` and return the rows as tuples."""
    engine = sa.create_engine(url)
    try:
        with engine.connect() as conn:
            return conn.exec_driver_sql(sql).fetchall()
    finally:
        engine.dispose()


def _upgrade(url):
    """Stamp the DB one revision below the migration and upgrade to head."""
    cfg = _alembic_config(url)
    command.stamp(cfg, PREV_REVISION)
    command.upgrade(cfg, REVISION)


class TestCanonicalizeInsurancePolicyIds:
    """Tests for the upgrade that merges policy-ID-forked insurance rows."""

    def test_duplicate_insurance_accounts_are_merged(self, forked_db):
        """Verify the two spellings collapse to one account with the fresh balance."""
        _upgrade(forked_db)

        rows = _rows(
            forked_db,
            "SELECT policy_id, balance, balance_date, custom_name "
            "FROM insurance_accounts WHERE policy_type = 'hishtalmut'",
        )
        assert rows == [(CANONICAL, 56957.0, "2026-08-30", "My KH")]

    def test_pension_account_is_untouched(self, forked_db):
        """Verify a bare numeric policy ID survives the migration unchanged."""
        _upgrade(forked_db)

        rows = _rows(
            forked_db,
            "SELECT policy_id, balance FROM insurance_accounts "
            "WHERE policy_type = 'pension'",
        )
        assert rows == [(PENSION_ID, 254771.0)]

    def test_duplicate_investment_is_removed_and_retagged(self, forked_db):
        """Verify one investment survives, keeping the older ID and a clean tag."""
        _upgrade(forked_db)

        rows = _rows(
            forked_db, "SELECT id, tag, insurance_policy_id FROM investments"
        )
        assert rows == [
            (1, f"Keren Hishtalmut - hafenix ({CANONICAL})", CANONICAL)
        ]

    def test_snapshots_are_carried_onto_the_surviving_investment(self, forked_db):
        """Verify the duplicate's fresh snapshot moves over without doubling a date."""
        _upgrade(forked_db)

        rows = _rows(
            forked_db,
            "SELECT date, balance FROM investment_balance_snapshots "
            "ORDER BY date",
        )
        assert rows == [
            ("2026-08-04", 57667.0),
            ("2026-08-18", 57110.0),
            ("2026-08-30", 56957.0),
        ]

    def test_duplicate_deposits_are_dropped_keeping_user_edits(self, forked_db):
        """Verify each deposit survives once, as the row carrying the user's tag."""
        _upgrade(forked_db)

        rows = _rows(
            forked_db,
            "SELECT date, account_number, tag FROM insurance_transactions "
            "WHERE account_number = '" + CANONICAL + "' ORDER BY date",
        )
        assert rows == [
            ("2025-12-08", CANONICAL, "reviewed"),
            ("2026-01-12", CANONICAL, "reviewed"),
        ]

    def test_deposit_ids_become_reformat_insensitive(self, forked_db):
        """Verify dedup IDs are rekeyed so a future restyle cannot re-report them."""
        _upgrade(forked_db)

        rows = _rows(
            forked_db,
            "SELECT id FROM insurance_transactions "
            "WHERE account_number = '" + CANONICAL + "' ORDER BY date",
        )
        assert rows == [
            ("7-916-407357_2025-12-08_1571.0",),
            ("7-916-407357_2026-01-12_1571.0",),
        ]

    def test_upgrade_is_idempotent_on_already_clean_data(self, forked_db):
        """Verify re-running the upgrade over merged data changes nothing further."""
        _upgrade(forked_db)
        snapshot = _rows(
            forked_db,
            "SELECT id, tag, insurance_policy_id FROM investments "
            "UNION ALL SELECT unique_id, id, account_number "
            "FROM insurance_transactions ORDER BY 1",
        )

        module = __import__(
            "backend.alembic.versions."
            "b7d4f1a9c3e2_canonicalize_insurance_policy_ids",
            fromlist=["upgrade"],
        )
        engine = sa.create_engine(forked_db)
        try:
            with engine.begin() as conn:
                module._merge_insurance_accounts(conn)
                module._merge_investments(conn)
                module._rekey_insurance_transactions(conn)
        finally:
            engine.dispose()

        assert (
            _rows(
                forked_db,
                "SELECT id, tag, insurance_policy_id FROM investments "
                "UNION ALL SELECT unique_id, id, account_number "
                "FROM insurance_transactions ORDER BY 1",
            )
            == snapshot
        )
