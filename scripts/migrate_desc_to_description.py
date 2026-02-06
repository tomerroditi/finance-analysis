#!/usr/bin/env python3
"""
Migration script to rename 'desc' column to 'description' in all transaction tables.
"""

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path.home() / ".finance-analysis" / "data.db"

TABLES = [
    "credit_card_transactions",
    "bank_transactions",
    "cash_transactions",
    "manual_investment_transactions",
]


def migrate(db_path: Path = DB_PATH):
    """Rename 'desc' column to 'description' in all transaction tables."""
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for table in TABLES:
        # Check if table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        )
        if not cursor.fetchone():
            print(f"Table {table} does not exist, skipping...")
            continue

        # Check if 'desc' column exists
        cursor.execute(f"PRAGMA table_info({table})")
        columns = [col[1] for col in cursor.fetchall()]

        if "desc" not in columns:
            if "description" in columns:
                print(f"Table {table}: already has 'description' column, skipping...")
            else:
                print(f"Table {table}: no 'desc' column found, skipping...")
            continue

        print(f"Renaming 'desc' -> 'description' in {table}...")
        cursor.execute(f"ALTER TABLE {table} RENAME COLUMN desc TO description")
        print(f"  Done!")

    conn.commit()
    conn.close()
    print("\nMigration completed successfully!")


if __name__ == "__main__":
    migrate()
