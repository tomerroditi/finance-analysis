"""
Demo database preparation helpers.

Both the ``/api/testing/toggle_demo_mode`` route and the Vercel serverless
entrypoint (``index.py``) need to copy the frozen demo SQLite, apply any
schema deltas the ORM has accrued since the file was built, and shift every
stored date relative to today so the demo data tracks the current month.

Keeping this in one module ensures the toggle path and the cold-start path
stay in lockstep — diverging implementations were how the Vercel preview
ended up with budget rules pinned to ``DEMO_REFERENCE_DATE``.
"""

from __future__ import annotations

import os
import shutil
from datetime import date, timedelta

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from backend import database
from backend.config import AppConfig
from backend.models import Base


# Reference date used when generating ``backend/resources/demo_data.db``.
# Every date column in that file is anchored to this point; on copy we apply
# ``date.today() - DEMO_REFERENCE_DATE`` to every shiftable column.
DEMO_REFERENCE_DATE = date(2026, 2, 25)


def _source_db_path() -> str:
    """Resolve the path to the frozen demo DB shipped in the repo."""
    return os.path.join(
        os.path.dirname(__file__), "resources", "demo_data.db"
    )


def sync_missing_columns(engine: Engine) -> None:
    """Add ORM-defined columns that are missing from the physical DB.

    SQLite has no full ``ALTER TABLE`` support and ``create_all`` only handles
    new tables, so columns added to existing models drift from the frozen demo
    file. This bridges the gap with explicit ``ADD COLUMN`` statements.
    """
    inspector = inspect(engine)
    for table_name, table in Base.metadata.tables.items():
        if not inspector.has_table(table_name):
            continue
        existing = {col["name"] for col in inspector.get_columns(table_name)}
        for column in table.columns:
            if column.name in existing:
                continue
            col_type = column.type.compile(engine.dialect)
            with engine.connect() as conn:
                conn.execute(
                    text(
                        f"ALTER TABLE {table_name} ADD COLUMN {column.name} {col_type}"
                    )
                )
                conn.commit()


def _backfill_budget_rule_period_type(engine: Engine) -> None:
    """Classify ``budget_rules`` rows that predate the ``period_type`` column.

    Mirrors the backfill in alembic revision ``a7c9e1b3d5f7`` (add
    period_type to budget_rules), which only runs against the production DB
    via ``alembic upgrade head`` at app startup. The demo DB is copied from
    a frozen snapshot and schema-synced via :func:`sync_missing_columns`
    instead of alembic, so ``sync_missing_columns`` adds the column but
    leaves every pre-existing row's ``period_type`` NULL. Left unfixed, the
    Monthly and Yearly budget views (which filter on ``period_type``) see
    zero rows for a demo dataset that actually has budget rules — this
    backfill closes that gap. Safe to call repeatedly: it only touches rows
    still missing a classification.
    """
    inspector = inspect(engine)
    if not inspector.has_table("budget_rules"):
        return
    columns = {col["name"] for col in inspector.get_columns("budget_rules")}
    if "period_type" not in columns:
        return
    with engine.connect() as conn:
        conn.execute(
            text(
                "UPDATE budget_rules SET period_type = 'monthly' "
                "WHERE month IS NOT NULL AND (period_type IS NULL OR period_type = '')"
            )
        )
        conn.execute(
            text(
                "UPDATE budget_rules SET period_type = 'project' "
                "WHERE month IS NULL AND year IS NULL "
                "AND (period_type IS NULL OR period_type = '')"
            )
        )
        conn.execute(
            text(
                "UPDATE budget_rules SET period_type = 'yearly' "
                "WHERE month IS NULL AND year IS NOT NULL "
                "AND (period_type IS NULL OR period_type = '')"
            )
        )
        conn.commit()


# Transaction tables an override's source_id can point into.
_TXN_TABLES = {
    "bank_transactions",
    "credit_card_transactions",
    "cash_transactions",
    "manual_investment_transactions",
}


def _resolve_override_txn_date(conn, source_type: str, source_id: int, source_table: str):
    """Return the original ISO date of the transaction an override points at.

    Returns ``None`` if it cannot be resolved (unknown table, missing row).
    Must be called before transaction dates are shifted so the returned date
    is the pre-shift value.
    """
    if source_type == "transaction" and source_table in _TXN_TABLES:
        row = conn.execute(
            text(f"SELECT date FROM {source_table} WHERE unique_id = :uid"),
            {"uid": source_id},
        ).fetchone()
        return row[0] if row else None

    if source_type == "split":
        split = conn.execute(
            text(
                "SELECT source, transaction_id FROM split_transactions WHERE id = :sid"
            ),
            {"sid": source_id},
        ).fetchone()
        if split and split[0] in _TXN_TABLES:
            parent = conn.execute(
                text(f"SELECT date FROM {split[0]} WHERE unique_id = :uid"),
                {"uid": split[1]},
            ).fetchone()
            return parent[0] if parent else None
    return None


def _shift_budget_month_overrides(conn, offset_days: int) -> None:
    """Re-anchor each budget month override to its (shifted) transaction's month.

    Call this *before* the transaction date columns are shifted — it relies on
    reading the original transaction dates to recover each override's +/-1
    direction.
    """
    try:
        overrides = conn.execute(
            text(
                "SELECT id, source_type, source_id, source_table, "
                "override_year, override_month FROM budget_month_overrides"
            )
        ).fetchall()
    except Exception:
        # Table may be absent in an older frozen DB; nothing to shift.
        return

    for ov_id, source_type, source_id, source_table, oy, om in overrides:
        txn_date = _resolve_override_txn_date(
            conn, source_type, source_id, source_table
        )
        if not txn_date:
            continue
        orig_txn = date.fromisoformat(txn_date[:10])
        direction = (oy * 12 + (om - 1)) - (
            orig_txn.year * 12 + (orig_txn.month - 1)
        )
        new_txn = orig_txn + timedelta(days=offset_days)
        new_index = (new_txn.year * 12 + (new_txn.month - 1)) + direction
        new_year, new_month0 = divmod(new_index, 12)
        conn.execute(
            text(
                "UPDATE budget_month_overrides "
                "SET override_year = :y, override_month = :m WHERE id = :id"
            ),
            {"y": new_year, "m": new_month0 + 1, "id": ov_id},
        )


def _shift_dates(engine: Engine, offset_days: int) -> None:
    """Shift every shiftable date column by ``offset_days`` days."""
    if offset_days == 0:
        return

    offset_str = (
        f"+{offset_days} days" if offset_days > 0 else f"{offset_days} days"
    )

    with engine.connect() as conn:
        # Budget month overrides must move in lockstep with the transactions
        # they point at. Each override sits exactly one calendar month before
        # or after its transaction's month; shifting the stored (year, month)
        # by raw days — the way budget_rules are shifted — can drift it a month
        # relative to the transaction (the rule anchors to day 1, the
        # transaction to its real day). Instead, anchor each override to its
        # transaction's *new* month plus the original +/-1 direction. This runs
        # before the transaction dates below are shifted, so the lookups still
        # see the original (pre-shift) transaction dates.
        _shift_budget_month_overrides(conn, offset_days)

        for table in [
            "bank_transactions",
            "credit_card_transactions",
            "cash_transactions",
            "manual_investment_transactions",
            "insurance_transactions",
        ]:
            conn.execute(
                text(f"UPDATE {table} SET date = date(date, :offset)"),
                {"offset": offset_str},
            )

        # Order avoids UNIQUE collisions on (investment_id, date) snapshots.
        order = "DESC" if offset_days > 0 else "ASC"
        snapshot_ids = conn.execute(
            text(
                f"SELECT id FROM investment_balance_snapshots ORDER BY date {order}"
            )
        ).fetchall()
        for (sid,) in snapshot_ids:
            conn.execute(
                text(
                    "UPDATE investment_balance_snapshots SET date = date(date, :offset) WHERE id = :id"
                ),
                {"offset": offset_str, "id": sid},
            )

        for col in [
            "created_date",
            "closed_date",
            "liquidity_date",
            "maturity_date",
        ]:
            conn.execute(
                text(
                    f"UPDATE investments SET {col} = date({col}, :offset) WHERE {col} IS NOT NULL"
                ),
                {"offset": offset_str},
            )

        conn.execute(
            text("UPDATE scraping_history SET date = date(date, :offset)"),
            {"offset": offset_str},
        )

        for col in ["start_date", "paid_off_date", "created_date"]:
            conn.execute(
                text(
                    f"UPDATE liabilities SET {col} = date({col}, :offset) WHERE {col} IS NOT NULL"
                ),
                {"offset": offset_str},
            )

        conn.execute(
            text(
                "UPDATE liability_transactions SET date = date(date, :offset) WHERE date IS NOT NULL"
            ),
            {"offset": offset_str},
        )

        for col in ["balance_date", "liquidity_date"]:
            conn.execute(
                text(
                    f"UPDATE insurance_accounts SET {col} = date({col}, :offset) WHERE {col} IS NOT NULL"
                ),
                {"offset": offset_str},
            )

        rows = conn.execute(
            text(
                "SELECT DISTINCT id, year, month FROM budget_rules WHERE year IS NOT NULL"
            )
        ).fetchall()
        for row in rows:
            old_date = date(row[1], row[2], 1)
            new_date = old_date + timedelta(days=offset_days)
            conn.execute(
                text(
                    "UPDATE budget_rules SET year = :year, month = :month WHERE id = :id"
                ),
                {"year": new_date.year, "month": new_date.month, "id": row[0]},
            )

        conn.commit()


def prepare_demo_database() -> None:
    """Copy the frozen demo DB into the demo-mode location and shift dates.

    Resets the SQLAlchemy engine, copies ``backend/resources/demo_data.db``
    over the configured demo DB path, applies any missing schema deltas, then
    shifts every date column so the dataset is anchored to today.

    Safe to call repeatedly — each call yields a fresh copy with dates
    re-anchored to ``date.today()``.
    """
    config = AppConfig()
    demo_db_path = config.get_db_path()
    source = _source_db_path()

    if os.path.exists(source):
        os.makedirs(os.path.dirname(demo_db_path), exist_ok=True)
        shutil.copy2(source, demo_db_path)

    database.reset_engine()
    engine = database.get_engine()
    Base.metadata.create_all(bind=engine)
    sync_missing_columns(engine)
    _backfill_budget_rule_period_type(engine)

    offset_days = (date.today() - DEMO_REFERENCE_DATE).days
    _shift_dates(engine, offset_days)
