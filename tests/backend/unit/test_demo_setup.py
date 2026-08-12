"""Unit tests for demo database date-shifting (``backend.demo_setup``)."""

from datetime import date, timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from backend.demo_setup import _backfill_budget_rule_period_type, _shift_dates
from backend.models.base import Base


def _make_engine():
    """Create an in-memory SQLite engine with all demo tables created.

    Uses StaticPool so every connection shares the same in-memory database —
    with the default pool each connection would get a fresh empty DB.
    """
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    return engine


class TestShiftBudgetMonthOverrides:
    """Tests that month overrides track the transactions they point at."""

    def _seed_txn_and_override(
        self, engine, txn_date: str, override_year: int, override_month: int
    ):
        """Insert one CC transaction and an override pointing at it."""
        ts = "2026-01-01 00:00:00"
        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO credit_card_transactions "
                    "(unique_id, date, description, amount, source, created_at, updated_at) "
                    "VALUES (1, :d, 'PAZ', -100, 'credit_card_transactions', :ts, :ts)"
                ),
                {"d": txn_date, "ts": ts},
            )
            conn.execute(
                text(
                    "INSERT INTO budget_month_overrides "
                    "(id, source_type, source_id, source_table, override_year, override_month, "
                    "created_at, updated_at) "
                    "VALUES (1, 'transaction', 1, 'credit_card_transactions', :y, :m, :ts, :ts)"
                ),
                {"y": override_year, "m": override_month, "ts": ts},
            )
            conn.commit()

    def _read(self, engine):
        """Return (shifted_txn_date, override_year, override_month)."""
        with engine.connect() as conn:
            txn = conn.execute(
                text("SELECT date FROM credit_card_transactions WHERE unique_id = 1")
            ).scalar()
            ov = conn.execute(
                text(
                    "SELECT override_year, override_month FROM budget_month_overrides WHERE id = 1"
                )
            ).fetchone()
        return date.fromisoformat(txn[:10]), ov[0], ov[1]

    def test_move_back_override_stays_one_month_before(self):
        """A 'previous month' override stays one month before the shifted txn."""
        engine = _make_engine()
        # Txn in Feb, override in Jan (one month back).
        self._seed_txn_and_override(engine, "2026-02-05", 2026, 1)

        _shift_dates(engine, 101)  # push ~3.3 months forward

        txn_date, oy, om = self._read(engine)
        rel = (oy * 12 + (om - 1)) - (txn_date.year * 12 + (txn_date.month - 1))
        assert rel == -1, f"expected override one month before txn, got rel={rel}"

    def test_move_forward_override_stays_one_month_after(self):
        """A 'next month' override stays one month after the shifted txn."""
        engine = _make_engine()
        # Txn in late December, override in the following January (one month forward).
        self._seed_txn_and_override(engine, "2025-12-24", 2026, 1)

        _shift_dates(engine, 101)

        txn_date, oy, om = self._read(engine)
        rel = (oy * 12 + (om - 1)) - (txn_date.year * 12 + (txn_date.month - 1))
        assert rel == 1, f"expected override one month after txn, got rel={rel}"

    def test_zero_offset_leaves_override_untouched(self):
        """A zero-day offset is a no-op for overrides."""
        engine = _make_engine()
        self._seed_txn_and_override(engine, "2026-02-05", 2026, 1)

        _shift_dates(engine, 0)

        _, oy, om = self._read(engine)
        assert (oy, om) == (2026, 1)

    def test_override_shift_matches_manual_calculation(self):
        """The shifted override equals txn-new-month plus original direction."""
        engine = _make_engine()
        self._seed_txn_and_override(engine, "2026-02-05", 2026, 1)
        offset = 70

        _shift_dates(engine, offset)

        txn_date, oy, om = self._read(engine)
        expected_txn = date(2026, 2, 5) + timedelta(days=offset)
        assert txn_date == expected_txn
        # Original direction was -1, so override = new txn month - 1.
        expected_index = (expected_txn.year * 12 + (expected_txn.month - 1)) - 1
        assert oy == expected_index // 12
        assert om == expected_index % 12 + 1


class TestBackfillBudgetRulePeriodType:
    """``_backfill_budget_rule_period_type`` classifies legacy rows and never
    overwrites an already-set ``period_type`` (mirrors alembic ``a7c9e1b3d5f7``)."""

    def _seed_rule(self, engine, rule_id, year, month, period_type=None):
        """Insert one ``budget_rules`` row with the given year/month/period_type."""
        ts = "2026-01-01 00:00:00"
        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO budget_rules "
                    "(id, name, amount, category, tags, year, month, period_type, "
                    "created_at, updated_at) "
                    "VALUES (:id, :name, 100.0, 'Food', 'Groceries', :y, :m, :pt, :ts, :ts)"
                ),
                {"id": rule_id, "name": f"Rule {rule_id}", "y": year, "m": month, "pt": period_type, "ts": ts},
            )
            conn.commit()

    def _read_period_type(self, engine, rule_id):
        """Return the ``period_type`` for a given rule id."""
        with engine.connect() as conn:
            return conn.execute(
                text("SELECT period_type FROM budget_rules WHERE id = :id"),
                {"id": rule_id},
            ).scalar()

    def test_backfill_classifies_rows_by_year_month(self):
        """Monthly (month+year set), project (both null), and yearly (year only)
        rows each get the correct classification."""
        engine = _make_engine()
        self._seed_rule(engine, 1, year=2026, month=5)  # monthly
        self._seed_rule(engine, 2, year=None, month=None)  # project
        self._seed_rule(engine, 3, year=2026, month=None)  # yearly

        _backfill_budget_rule_period_type(engine)

        assert self._read_period_type(engine, 1) == "monthly"
        assert self._read_period_type(engine, 2) == "project"
        assert self._read_period_type(engine, 3) == "yearly"

    def test_backfill_does_not_overwrite_existing_period_type(self):
        """A row that already has a period_type is left untouched, even if it
        would otherwise classify differently — the guard only targets NULL/empty."""
        engine = _make_engine()
        # Year/month pattern of a project rule, but pre-set to 'monthly'.
        self._seed_rule(engine, 1, year=None, month=None, period_type="monthly")

        _backfill_budget_rule_period_type(engine)

        assert self._read_period_type(engine, 1) == "monthly"

    def test_backfill_is_idempotent(self):
        """Running the backfill twice produces the same result as running it once."""
        engine = _make_engine()
        self._seed_rule(engine, 1, year=2026, month=5)
        self._seed_rule(engine, 2, year=None, month=None)
        self._seed_rule(engine, 3, year=2026, month=None)

        _backfill_budget_rule_period_type(engine)
        _backfill_budget_rule_period_type(engine)

        assert self._read_period_type(engine, 1) == "monthly"
        assert self._read_period_type(engine, 2) == "project"
        assert self._read_period_type(engine, 3) == "yearly"


class TestDemoFixtureDataSources:
    """The frozen demo DB must ship the connected sources the demo UI shows.

    Demo credentials used to exist only in the OS keyring + DB rows written by
    ``CredentialsService.seed_demo_credentials``, which runs from the demo-mode
    *toggle*. The hosted demo forces demo mode on at cold start and never
    toggles, so nothing ever seeded them and its Data Sources page was
    permanently empty. They now live in the fixture like every other demo row.
    """

    @staticmethod
    def _demo_connection():
        import sqlite3
        from pathlib import Path

        db_path = (
            Path(__file__).resolve().parents[3]
            / "backend"
            / "resources"
            / "demo_data.db"
        )
        assert db_path.exists(), f"demo fixture missing at {db_path}"
        return sqlite3.connect(db_path)

    def test_fixture_ships_one_credential_per_demo_source(self):
        """Every account the demo dashboard references has a credential row."""
        conn = self._demo_connection()
        try:
            rows = {
                (service, provider, account)
                for service, provider, account in conn.execute(
                    "SELECT service, provider, account_name FROM credentials"
                )
            }
        finally:
            conn.close()

        assert rows == {
            ("banks", "hapoalim", "Main Account"),
            ("banks", "leumi", "Savings Account"),
            ("credit_cards", "max", "Family Card"),
            ("credit_cards", "visa cal", "Online Shopping"),
            ("insurances", "hafenix", "The Cohens"),
        }

    def test_fixture_credentials_hold_no_password(self):
        """Passwords belong in the OS keyring, never in the credentials table."""
        conn = self._demo_connection()
        try:
            fields = [row[0] for row in conn.execute("SELECT fields FROM credentials")]
        finally:
            conn.close()

        for raw in fields:
            assert "password" not in raw.lower()

    def test_fixture_scrape_statuses_are_canonical_lowercase(self):
        """Statuses must match ``ScrapingHistoryRepository``'s constants exactly.

        SQLite string comparison is case-sensitive, so the fixture's old
        ``"SUCCESS"`` rows never matched ``WHERE status = 'success'``: every
        demo source reported "Never synced" and the balance-entry button stayed
        disabled, even though the history was right there.
        """
        from backend.repositories.scraping_history_repository import (
            ScrapingHistoryRepository,
        )

        conn = self._demo_connection()
        try:
            statuses = {row[0] for row in conn.execute("SELECT status FROM scraping_history")}
        finally:
            conn.close()

        allowed = {
            ScrapingHistoryRepository.SUCCESS,
            ScrapingHistoryRepository.FAILED,
            ScrapingHistoryRepository.CANCELED,
        }
        assert statuses <= allowed, f"non-canonical statuses in fixture: {statuses - allowed}"
        assert ScrapingHistoryRepository.SUCCESS in statuses

    def test_every_scraped_source_resolves_a_last_scrape_date(self):
        """The join the UI relies on must actually produce dates.

        Pins both halves at once: the credential rows exist AND their
        service/provider/account_name match the scraping-history rows, so
        ``get_last_successful_scrape_date`` returns something for each.
        """
        conn = self._demo_connection()
        try:
            resolved = conn.execute(
                """
                SELECT COUNT(*) FROM credentials c
                WHERE EXISTS (
                    SELECT 1 FROM scraping_history h
                    WHERE h.service_name = c.service
                      AND h.provider_name = c.provider
                      AND h.account_name = c.account_name
                      AND h.status = 'success'
                )
                """
            ).fetchone()[0]
        finally:
            conn.close()

        # Insurance has no scrape history in the fixture; the four scrapable
        # sources must all resolve.
        assert resolved == 4
