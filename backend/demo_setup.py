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


def _shift_dates(engine: Engine, offset_days: int) -> None:
    """Shift every shiftable date column by ``offset_days`` days."""
    if offset_days == 0:
        return

    offset_str = (
        f"+{offset_days} days" if offset_days > 0 else f"{offset_days} days"
    )

    with engine.connect() as conn:
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

    offset_days = (date.today() - DEMO_REFERENCE_DATE).days
    _shift_dates(engine, offset_days)
