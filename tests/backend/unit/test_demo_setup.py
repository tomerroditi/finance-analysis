"""Unit tests for demo database preparation (``backend.demo_setup``)."""

import json
import shutil
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from backend.demo_setup import (
    DEMO_REFERENCE_DATE,
    _backfill_budget_rule_period_type,
    _drop_retired_columns,
    _normalize_scrape_statuses,
    _seed_demo_credentials,
    _shift_dates,
    _source_db_path,
    sync_missing_columns,
)
from backend.models.base import Base
from backend.repositories.scraping_history_repository import (
    ScrapingHistoryRepository,
)
from backend.utils.crypto import ENCRYPTED_MARKER

#: "Today" values spanning early/late days of the month, a month shorter than
#: the reference day, and a year boundary. The reference date is day 25, so
#: any day before it is where a day-1 anchor used to fall a month behind.
SHIFT_TODAYS = [
    date(2026, 9, 1),
    date(2026, 9, 11),
    date(2026, 9, 24),
    date(2026, 9, 30),
    date(2027, 2, 28),
    date(2027, 1, 3),
    DEMO_REFERENCE_DATE,
]


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


class TestShiftCategoriesCreatedAt:
    """``_shift_dates`` keeps ``categories.created_at`` anchored to today.

    ``created_at`` is a full DateTime, not a plain date string, so the shift
    must use SQLite's ``datetime()`` (which preserves the time-of-day) rather
    than ``date()`` (which would truncate it to midnight). Left unshifted, a
    demo category's age relative to "today" would grow every day the demo
    snapshot ages, eventually pushing it past the unused-category cutoff.
    """

    def _seed_category(self, engine, created_at: str):
        """Insert one category row with the given ``created_at`` timestamp."""
        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO categories (id, name, tags, created_at, updated_at) "
                    "VALUES (1, 'Food', '[]', :ts, :ts)"
                ),
                {"ts": created_at},
            )
            conn.commit()

    def _read_created_at(self, engine) -> str:
        """Return the raw stored ``created_at`` string for the seeded category."""
        with engine.connect() as conn:
            return conn.execute(
                text("SELECT created_at FROM categories WHERE id = 1")
            ).scalar()

    def test_created_at_shifts_by_offset_days(self):
        """A positive offset moves ``created_at`` forward by exactly that many days."""
        engine = _make_engine()
        self._seed_category(engine, "2026-02-25 10:23:45")

        _shift_dates(engine, 30)

        shifted = self._read_created_at(engine)
        assert date.fromisoformat(shifted[:10]) == date(2026, 2, 25) + timedelta(
            days=30
        )

    def test_created_at_preserves_time_of_day(self):
        """The time-of-day component survives the shift (datetime(), not date())."""
        engine = _make_engine()
        self._seed_category(engine, "2026-02-25 10:23:45")

        _shift_dates(engine, 30)

        shifted = self._read_created_at(engine)
        assert shifted[11:19] == "10:23:45"

    def test_zero_offset_leaves_created_at_untouched(self):
        """A zero-day offset is a no-op for categories, same as other tables."""
        engine = _make_engine()
        self._seed_category(engine, "2026-02-25 10:23:45")

        _shift_dates(engine, 0)

        assert self._read_created_at(engine) == "2026-02-25 10:23:45"


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


class TestShiftBudgetRuleMonths:
    """``_shift_dates`` moves ``budget_rules`` by whole calendar months.

    The snapshot's newest monthly rules sit in ``DEMO_REFERENCE_DATE``'s
    month, so after the shift they must sit in today's month on every day of
    the month. Anchoring each rule to day 1 and adding the raw day offset put
    them a month behind whenever today's day-of-month was earlier than the
    reference day, leaving the current month with no Total Budget rule.
    """

    def _seed_rule(self, engine, rule_id, year, month, period_type):
        """Insert one ``budget_rules`` row with the given period columns."""
        ts = "2026-01-01 00:00:00"
        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO budget_rules "
                    "(id, name, amount, category, tags, year, month, period_type, "
                    "created_at, updated_at) "
                    "VALUES (:id, 'Total Budget', 100.0, 'Total Budget', 'all_tags', "
                    ":y, :m, :pt, :ts, :ts)"
                ),
                {"id": rule_id, "y": year, "m": month, "pt": period_type, "ts": ts},
            )
            conn.commit()

    def _read_period(self, engine, rule_id):
        """Return the stored ``(year, month)`` for a given rule id."""
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT year, month FROM budget_rules WHERE id = :id"),
                {"id": rule_id},
            ).fetchone()
        return row[0], row[1]

    @pytest.mark.parametrize("today", SHIFT_TODAYS)
    def test_shift_reference_month_rule_lands_in_today_month(self, today):
        """A rule in the reference month moves to the month containing today."""
        engine = _make_engine()
        self._seed_rule(
            engine, 1, DEMO_REFERENCE_DATE.year, DEMO_REFERENCE_DATE.month, "monthly"
        )

        _shift_dates(engine, (today - DEMO_REFERENCE_DATE).days)

        assert self._read_period(engine, 1) == (today.year, today.month)

    def test_shift_preserves_month_spacing(self):
        """Rules five months apart before the shift stay five months apart."""
        engine = _make_engine()
        self._seed_rule(engine, 1, 2026, 2, "monthly")
        self._seed_rule(engine, 2, 2025, 9, "monthly")

        _shift_dates(engine, (date(2026, 9, 11) - DEMO_REFERENCE_DATE).days)

        assert self._read_period(engine, 1) == (2026, 9)
        assert self._read_period(engine, 2) == (2026, 4)

    def test_shift_yearly_rule_moves_by_whole_years(self):
        """A yearly rule (``month`` NULL) shifts its year rather than crashing."""
        engine = _make_engine()
        self._seed_rule(engine, 1, 2026, None, "yearly")

        _shift_dates(engine, (date(2027, 1, 3) - DEMO_REFERENCE_DATE).days)

        assert self._read_period(engine, 1) == (2027, None)

    def test_shift_leaves_project_rule_untouched(self):
        """A project rule has no period columns, so the shift leaves it alone."""
        engine = _make_engine()
        self._seed_rule(engine, 1, None, None, "project")

        _shift_dates(engine, (date(2026, 9, 11) - DEMO_REFERENCE_DATE).days)

        assert self._read_period(engine, 1) == (None, None)


class TestDemoSnapshotCurrentMonthBudget:
    """The shipped demo snapshot has a Total Budget rule for today's month.

    Category rules are rejected until the month has a Total Budget rule, so
    this is what lets a Demo Mode user add a budget rule on any date without
    relying on the monthly view's auto-fill to copy one forward first.
    """

    @pytest.mark.parametrize("today", SHIFT_TODAYS)
    def test_snapshot_current_month_has_total_budget(self, tmp_path, today):
        """After the demo prep steps, today's month carries the Total Budget rule."""
        db_path = tmp_path / "demo.db"
        shutil.copy2(_source_db_path(), db_path)
        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(bind=engine)
        sync_missing_columns(engine)
        _drop_retired_columns(engine)
        _backfill_budget_rule_period_type(engine)

        _shift_dates(engine, (today - DEMO_REFERENCE_DATE).days)

        with engine.connect() as conn:
            names = (
                conn.execute(
                    text(
                        "SELECT name FROM budget_rules WHERE period_type = 'monthly' "
                        "AND year = :y AND month = :m"
                    ),
                    {"y": today.year, "m": today.month},
                )
                .scalars()
                .all()
            )
        engine.dispose()
        assert "Total Budget" in names


class TestShiftSavingsGoalMonths:
    """Savings-goal ``start_month``/``closed_month`` move by whole months.

    They share the calendar-month shift with ``budget_rules``, so a goal
    started in the reference month starts in today's month on any day.
    """

    def _seed_goal(self, engine, start_month, closed_month):
        """Insert one ``savings_goals`` row with the given month strings."""
        ts = "2026-01-01 00:00:00"
        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO savings_goals "
                    "(id, name, target_amount, opening_balance, priority, status, "
                    "start_month, closed_month, created_at, updated_at) "
                    "VALUES (1, 'Wedding Fund', 1000.0, 0.0, 1, 'active', "
                    ":start, :closed, :ts, :ts)"
                ),
                {"start": start_month, "closed": closed_month, "ts": ts},
            )
            conn.commit()

    def _read_months(self, engine):
        """Return the stored ``(start_month, closed_month)`` of the seeded goal."""
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT start_month, closed_month FROM savings_goals WHERE id = 1")
            ).fetchone()
        return row[0], row[1]

    @pytest.mark.parametrize("today", SHIFT_TODAYS)
    def test_shift_reference_month_goal_lands_in_today_month(self, today):
        """A goal started and closed in the reference month moves to today's month."""
        engine = _make_engine()
        reference = f"{DEMO_REFERENCE_DATE.year:04d}-{DEMO_REFERENCE_DATE.month:02d}"
        self._seed_goal(engine, reference, reference)

        _shift_dates(engine, (today - DEMO_REFERENCE_DATE).days)

        expected = f"{today.year:04d}-{today.month:02d}"
        assert self._read_months(engine) == (expected, expected)


class TestNormalizeScrapeStatuses:
    """The demo dataset's scrape statuses must match what the repo queries.

    ``ScrapingHistoryRepository`` looks up ``WHERE status = 'success'`` and
    SQLite compares TEXT case-sensitively, so the fixture's ``"SUCCESS"``
    matched nothing: every demo data source reported "Never synced" despite
    a full history sitting in the table.
    """

    @staticmethod
    def _seed(engine, statuses):
        """Insert one scrape-history row per given status."""
        with engine.connect() as conn:
            for i, status in enumerate(statuses, start=1):
                conn.execute(
                    text(
                        "INSERT INTO scraping_history "
                        "(id, service_name, provider_name, account_name, date, status, "
                        "created_at, updated_at) "
                        "VALUES (:id, 'banks', 'hapoalim', 'Main Account', "
                        "'2026-09-01T08:30:00', :status, :ts, :ts)"
                    ),
                    {"id": i, "status": status, "ts": "2026-01-01 00:00:00"},
                )
            conn.commit()

    @staticmethod
    def _statuses(engine):
        """Read back every row's status."""
        with engine.connect() as conn:
            return [
                row[0]
                for row in conn.execute(
                    text("SELECT status FROM scraping_history ORDER BY id")
                )
            ]

    def test_uppercase_statuses_are_lowercased(self):
        """The fixture's legacy casing is rewritten to the repo's constants."""
        engine = _make_engine()
        self._seed(engine, ["SUCCESS", "FAILED"])

        _normalize_scrape_statuses(engine)

        assert self._statuses(engine) == ["success", "failed"]

    def test_the_repository_lookup_finds_the_row_afterwards(self):
        """The point of the fix: the watermark query stops returning nothing."""
        engine = _make_engine()
        self._seed(engine, ["SUCCESS"])

        _normalize_scrape_statuses(engine)

        with engine.connect() as conn:
            found = conn.execute(
                text(
                    "SELECT date FROM scraping_history WHERE status = :status"
                ),
                {"status": ScrapingHistoryRepository.SUCCESS},
            ).scalar()
        assert found == "2026-09-01T08:30:00"

    def test_already_lowercase_rows_are_untouched(self):
        """Idempotent — ``prepare_demo_database`` runs on every demo build."""
        engine = _make_engine()
        self._seed(engine, ["success", "failed"])

        _normalize_scrape_statuses(engine)
        _normalize_scrape_statuses(engine)

        assert self._statuses(engine) == ["success", "failed"]


class TestSeedDemoCredentials:
    """The demo dataset ships its own data sources.

    They used to be created only by the demo-mode *toggle*, which the hosted
    demo never runs (demo mode is forced on at cold start and must not be
    toggled on a shared instance), so its Data Sources page was empty.
    """

    @staticmethod
    def _accounts(engine):
        """Read back the seeded (provider, account) pairs."""
        with engine.connect() as conn:
            return [
                (row[0], row[1])
                for row in conn.execute(
                    text(
                        "SELECT provider, account_name FROM credentials "
                        "ORDER BY account_name"
                    )
                )
            ]

    def test_seeds_the_demo_accounts(self):
        """An empty credentials table gets the demo dataset's four sources."""
        engine = _make_engine()

        _seed_demo_credentials(engine)

        assert self._accounts(engine) == [
            ("max", "Family Card"),
            ("hapoalim", "Main Account"),
            ("visa cal", "Online Shopping"),
            ("hafenix", "The Cohens"),
        ]

    def test_seeded_accounts_match_the_demo_scrape_history(self):
        """Names must line up, or every card reads "Never synced" anyway.

        The history rows are keyed on service/provider/account, so a seeded
        account whose name differs by a character gets no watermark.
        """
        engine = _make_engine()

        _seed_demo_credentials(engine)

        with engine.connect() as conn:
            seeded = {
                (r[0], r[1], r[2])
                for r in conn.execute(
                    text("SELECT service, provider, account_name FROM credentials")
                )
            }
        assert ("banks", "hapoalim", "Main Account") in seeded
        assert ("credit_cards", "max", "Family Card") in seeded
        assert ("credit_cards", "visa cal", "Online Shopping") in seeded

    def test_fields_are_plaintext_and_hold_no_password(self):
        """Plaintext is the only format available without ``cryptography``.

        ``decrypt_fields`` passes a non-envelope dict straight through, and a
        demo scrape never authenticates, so no password is stored — or needed.
        """
        engine = _make_engine()

        _seed_demo_credentials(engine)

        with engine.connect() as conn:
            rows = [
                json.loads(r[0])
                for r in conn.execute(text("SELECT fields FROM credentials"))
            ]
        assert rows, "expected seeded rows"
        for fields in rows:
            assert ENCRYPTED_MARKER not in fields
            assert "password" not in fields

    def test_does_not_duplicate_on_a_second_run(self):
        """Idempotent — every demo build calls it."""
        engine = _make_engine()

        _seed_demo_credentials(engine)
        _seed_demo_credentials(engine)

        assert len(self._accounts(engine)) == 4

    def test_leaves_an_existing_account_alone(self):
        """A user's own demo edits survive a rebuild of the dataset."""
        engine = _make_engine()
        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO credentials "
                    "(service, provider, account_name, fields, created_at, updated_at) "
                    "VALUES ('banks', 'hapoalim', 'Main Account', :fields, :ts, :ts)"
                ),
                {
                    "fields": json.dumps({"userCode": "edited-by-user"}),
                    "ts": "2026-01-01 00:00:00",
                },
            )
            conn.commit()

        _seed_demo_credentials(engine)

        with engine.connect() as conn:
            fields = json.loads(
                conn.execute(
                    text(
                        "SELECT fields FROM credentials WHERE account_name = 'Main Account'"
                    )
                ).scalar()
            )
        assert fields == {"userCode": "edited-by-user"}
