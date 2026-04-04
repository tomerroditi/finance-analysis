"""
Testing / development utility routes.

Provides endpoints for toggling demo mode, which switches the application
to an isolated environment (separate DB, credentials, and categories) to
allow safe testing without affecting production data.
"""

import os
import shutil
from datetime import date, timedelta

from sqlalchemy import inspect, text

from fastapi import APIRouter
from pydantic import BaseModel

from backend.config import AppConfig
from backend import database
from backend.database import get_db_context
from backend.services.credentials_service import CredentialsService
from backend.services.tagging_service import CategoriesTagsService
from backend.models import Base

router = APIRouter()

# Reference date used when generating demo_data.db.
# All dates in the DB are relative to this date.
DEMO_REFERENCE_DATE = date(2026, 2, 25)


def _sync_missing_columns(engine) -> None:
    """Add columns present in ORM models but missing from the physical DB.

    ``create_all`` only creates new tables; it does not alter existing ones.
    This fills the gap for SQLite (which has no full ALTER support) by
    running ``ALTER TABLE ... ADD COLUMN`` for each missing column.
    """
    inspector = inspect(engine)
    for table_name, table in Base.metadata.tables.items():
        if not inspector.has_table(table_name):
            continue
        existing = {col["name"] for col in inspector.get_columns(table_name)}
        for column in table.columns:
            if column.name not in existing:
                col_type = column.type.compile(engine.dialect)
                with engine.connect() as conn:
                    conn.execute(
                        text(f"ALTER TABLE {table_name} ADD COLUMN {column.name} {col_type}")
                    )
                    conn.commit()


def _prepare_demo_database() -> None:
    """Copy the pre-built demo DB and shift all dates to be relative to today.

    Copies ``backend/resources/demo_data.db`` to the demo environment directory
    and runs SQL UPDATE statements to shift every date column by the offset
    between the reference date (when the DB was generated) and today.
    """
    config = AppConfig()
    demo_db_path = config.get_db_path()
    source_db = os.path.join(
        os.path.dirname(__file__), "..", "resources", "demo_data.db"
    )

    # Copy pre-built DB (overwrites any previous demo data)
    if os.path.exists(source_db):
        shutil.copy2(source_db, demo_db_path)

    # Ensure schema is up-to-date (create missing tables, add missing columns)
    database.reset_engine()
    engine = database.get_engine()
    Base.metadata.create_all(bind=engine)
    _sync_missing_columns(engine)

    # Shift dates
    offset_days = (date.today() - DEMO_REFERENCE_DATE).days
    if offset_days == 0:
        return

    engine = database.get_engine()
    with engine.connect() as conn:
        offset_str = f"+{offset_days} days" if offset_days > 0 else f"{offset_days} days"

        # Shift date columns in transaction tables
        for table in [
            "bank_transactions",
            "credit_card_transactions",
            "cash_transactions",
            "manual_investment_transactions",
            "insurance_transactions",
        ]:
            conn.execute(text(
                f"UPDATE {table} SET date = date(date, :offset)"
            ), {"offset": offset_str})

        # Shift investment balance snapshots (order avoids UNIQUE collisions)
        order = "DESC" if offset_days > 0 else "ASC"
        snapshot_ids = conn.execute(text(
            f"SELECT id FROM investment_balance_snapshots ORDER BY date {order}"
        )).fetchall()
        for (sid,) in snapshot_ids:
            conn.execute(text(
                "UPDATE investment_balance_snapshots SET date = date(date, :offset) WHERE id = :id"
            ), {"offset": offset_str, "id": sid})

        # Shift investment date fields
        for col in ["created_date", "closed_date", "liquidity_date", "maturity_date"]:
            conn.execute(text(
                f"UPDATE investments SET {col} = date({col}, :offset) WHERE {col} IS NOT NULL"
            ), {"offset": offset_str})

        # Shift scraping history
        conn.execute(text(
            "UPDATE scraping_history SET date = date(date, :offset)"
        ), {"offset": offset_str})

        # Shift liability date fields
        for col in ["start_date", "paid_off_date", "created_date"]:
            conn.execute(text(
                f"UPDATE liabilities SET {col} = date({col}, :offset) WHERE {col} IS NOT NULL"
            ), {"offset": offset_str})

        # Shift liability transaction dates
        conn.execute(text(
            "UPDATE liability_transactions SET date = date(date, :offset) WHERE date IS NOT NULL"
        ), {"offset": offset_str})

        # Shift insurance account date fields
        for col in ["balance_date", "liquidity_date"]:
            conn.execute(text(
                f"UPDATE insurance_accounts SET {col} = date({col}, :offset) WHERE {col} IS NOT NULL"
            ), {"offset": offset_str})

        # Shift budget rules year/month
        rows = conn.execute(text(
            "SELECT DISTINCT id, year, month FROM budget_rules WHERE year IS NOT NULL"
        )).fetchall()
        for row in rows:
            old_date = date(row[1], row[2], 1)
            new_date = old_date + timedelta(days=offset_days)
            conn.execute(text(
                "UPDATE budget_rules SET year = :year, month = :month WHERE id = :id"
            ), {"year": new_date.year, "month": new_date.month, "id": row[0]})

        conn.commit()


class DemoModeRequest(BaseModel):
    enabled: bool


@router.post("/toggle_demo_mode")
async def toggle_demo_mode(
    request: DemoModeRequest,
) -> dict[str, str | bool]:
    """Toggle the application's demo mode on or off.

    When enabled, the app switches to an isolated demo environment with a
    separate SQLite database, demo credentials, and demo categories. The
    database engine and credentials cache are reset so all subsequent
    requests use the demo environment. When disabling, the engine resets
    back to the production database.

    Parameters
    ----------
    request : DemoModeRequest
        ``enabled`` flag indicating the desired demo mode state.

    Returns
    -------
    dict
        ``{"status": "success", "demo_mode": bool}`` reflecting the new state.
    """
    config = AppConfig()

    # Only perform actions if the mode is actually changing
    if config.is_demo_mode != request.enabled:
        config.set_demo_mode(request.enabled)

        # Reset database engine to pick up new path
        database.reset_engine()

        CredentialsService.clear_cache()
        CategoriesTagsService.clear_cache()

        # If enabling demo mode, copy source DB then ensure schema is up-to-date
        if request.enabled:
            _prepare_demo_database()

            with get_db_context() as demo_db:
                creds_service = CredentialsService(demo_db)
                creds_service.seed_demo_credentials()

    return {"status": "success", "demo_mode": config.is_demo_mode}


@router.get("/demo_mode_status")
async def get_demo_mode_status():
    """Get the current demo mode status."""
    return {"demo_mode": AppConfig().is_demo_mode}
