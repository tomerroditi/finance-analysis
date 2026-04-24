"""
One-time fixup script for onezero/isracard date bug.

The old Node.js scraper set transaction dates 1 day earlier than the real date.
After switching to the Python scraper on 2026-03-04, correctly-dated transactions
were inserted as new rows, creating duplicates.

This script:
1. Backs up the database
2. Shifts old transaction dates forward by 1 day
3. Removes duplicate rows (keeps old row with user's category/tag)
4. Re-links split transactions from deleted rows to surviving rows

Usage:
    python scripts/fix_scraper_dates.py          # Dry run (shows what would change)
    python scripts/fix_scraper_dates.py --apply   # Apply changes
"""

import argparse
import shutil
from datetime import datetime, timedelta

from sqlalchemy import text

from backend.config import AppConfig
from backend.database import create_db_engine


CUTOFF_DATE = "2026-03-04"  # Date the Python scraper was deployed

AFFECTED_PROVIDERS = {
    "bank_transactions": "onezero",
    "credit_card_transactions": "isracard",
}


def backup_database(db_path: str) -> str:
    """Copy the database file to a timestamped backup."""
    backup_path = f"{db_path}.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(db_path, backup_path)
    return backup_path


def shift_date_forward(date_str: str) -> str:
    """Shift a YYYY-MM-DD date string forward by 1 day."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return (dt + timedelta(days=1)).strftime("%Y-%m-%d")


def find_old_transactions(conn, table: str, provider: str) -> list[dict]:
    """Find transactions from the old scraper (before cutoff date)."""
    result = conn.execute(
        text(
            f"SELECT unique_id, id, date, amount, provider, description, category, tag "
            f"FROM {table} "
            f"WHERE provider = :provider AND created_at < :cutoff"
        ),
        {"provider": provider, "cutoff": CUTOFF_DATE},
    )
    return [dict(row._mapping) for row in result]


def find_new_transactions(conn, table: str, provider: str) -> list[dict]:
    """Find transactions from the new scraper (on or after cutoff date)."""
    result = conn.execute(
        text(
            f"SELECT unique_id, id, date, amount, provider, description, category, tag "
            f"FROM {table} "
            f"WHERE provider = :provider AND created_at >= :cutoff"
        ),
        {"provider": provider, "cutoff": CUTOFF_DATE},
    )
    return [dict(row._mapping) for row in result]


def find_duplicates(old_txns: list[dict], new_txns: list[dict]) -> list[tuple[dict, dict]]:
    """
    Find duplicate pairs after shifting old dates forward by 1 day.

    Returns list of (old_txn, new_txn) tuples where the old txn (with corrected
    date) matches the new txn on [id, provider, date, amount].
    """
    # Build lookup from new transactions: key -> list of new txns
    new_lookup: dict[tuple, list[dict]] = {}
    for txn in new_txns:
        key = (txn["id"], txn["provider"], txn["date"], txn["amount"])
        new_lookup.setdefault(key, []).append(txn)

    duplicates = []
    matched_old_ids: set = set()
    for old_txn in old_txns:
        corrected_date = shift_date_forward(old_txn["date"])
        key = (old_txn["id"], old_txn["provider"], corrected_date, old_txn["amount"])
        if key in new_lookup:
            if old_txn["unique_id"] in matched_old_ids:
                print(f"  WARNING: old uid={old_txn['unique_id']} already matched, skipping")
                continue
            # Match with the first available new transaction
            new_txn = new_lookup[key].pop(0)
            if not new_lookup[key]:
                del new_lookup[key]
            duplicates.append((old_txn, new_txn))
            matched_old_ids.add(old_txn["unique_id"])

    return duplicates


def find_splits_for_transactions(conn, unique_ids: list[int], source: str) -> list[dict]:
    """Find split_transactions referencing any of the given parent unique_ids."""
    if not unique_ids:
        return []
    placeholders = ",".join(str(uid) for uid in unique_ids)
    result = conn.execute(
        text(
            f"SELECT id, transaction_id, source FROM split_transactions "
            f"WHERE transaction_id IN ({placeholders}) AND source = :source"
        ),
        {"source": source},
    )
    return [dict(row._mapping) for row in result]


def print_summary(
    table: str,
    provider: str,
    old_count: int,
    new_count: int,
    duplicates: list[tuple[dict, dict]],
    splits_to_relink: list[dict],
    non_dup_old_count: int,
):
    """Print a summary of what the fixup will do."""
    print(f"\n{'=' * 60}")
    print(f"Table: {table} | Provider: {provider}")
    print(f"{'=' * 60}")
    print(f"  Old transactions (pre-cutoff):   {old_count}")
    print(f"  New transactions (post-cutoff):   {new_count}")
    print(f"  Duplicates found:                 {len(duplicates)}")
    print(f"  Old txns to date-fix only:        {non_dup_old_count}")
    print(f"  Split txns to re-link:            {len(splits_to_relink)}")

    if duplicates:
        print("\n  Sample duplicates (up to 5):")
        for old_txn, new_txn in duplicates[:5]:
            corrected = shift_date_forward(old_txn["date"])
            print(f"    OLD uid={old_txn['unique_id']} date={old_txn['date']}->{corrected} "
                  f"amt={old_txn['amount']} desc='{old_txn['description'][:40]}' "
                  f"cat={old_txn['category']}")
            print(f"    NEW uid={new_txn['unique_id']} date={new_txn['date']} "
                  f"(will be DELETED)")


def apply_fixes(
    conn,
    table: str,
    old_txns: list[dict],
    duplicates: list[tuple[dict, dict]],
    splits_to_relink: list[dict],
):
    """Apply date fixes, delete duplicates, and re-link splits."""
    # Map from deleted new unique_id -> surviving old unique_id (for split re-linking)
    new_to_old_map = {new["unique_id"]: old["unique_id"] for old, new in duplicates}

    # 1. Re-link splits from new (about-to-be-deleted) rows to old (surviving) rows
    for split in splits_to_relink:
        new_uid = split["transaction_id"]
        if new_uid in new_to_old_map:
            conn.execute(
                text(
                    "UPDATE split_transactions SET transaction_id = :old_uid "
                    "WHERE id = :split_id"
                ),
                {"old_uid": new_to_old_map[new_uid], "split_id": split["id"]},
            )

    # 2. Delete duplicate new rows (must happen BEFORE date fix to avoid unique constraint violation)
    new_ids_to_delete = [new["unique_id"] for _, new in duplicates]
    if new_ids_to_delete:
        placeholders = ",".join(str(uid) for uid in new_ids_to_delete)
        conn.execute(text(f"DELETE FROM {table} WHERE unique_id IN ({placeholders})"))

    # 3. Fix dates on ALL old transactions (both duplicates and non-duplicates)
    for old_txn in old_txns:
        corrected_date = shift_date_forward(old_txn["date"])
        conn.execute(
            text(f"UPDATE {table} SET date = :new_date WHERE unique_id = :uid"),
            {"new_date": corrected_date, "uid": old_txn["unique_id"]},
        )

    print(f"  Applied: {len(old_txns)} dates fixed, {len(new_ids_to_delete)} duplicates deleted, "
          f"{len(splits_to_relink)} splits re-linked")


def main():
    parser = argparse.ArgumentParser(description="Fix scraper date bug for onezero/isracard")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default is dry run)")
    args = parser.parse_args()

    db_path = AppConfig().get_db_path()
    engine = create_db_engine(db_path)

    if args.apply:
        backup_path = backup_database(db_path)
        print(f"Database backed up to: {backup_path}")

    with engine.connect() as conn:
        try:
            for table, provider in AFFECTED_PROVIDERS.items():
                old_txns = find_old_transactions(conn, table, provider)
                new_txns = find_new_transactions(conn, table, provider)
                duplicates = find_duplicates(old_txns, new_txns)

                # Find splits referencing the new (duplicate) rows that will be deleted
                new_dup_ids = [new["unique_id"] for _, new in duplicates]
                splits_to_relink = find_splits_for_transactions(conn, new_dup_ids, table)

                dup_old_ids = {old["unique_id"] for old, _ in duplicates}
                non_dup_old_count = len([t for t in old_txns if t["unique_id"] not in dup_old_ids])

                print_summary(table, provider, len(old_txns), len(new_txns),
                              duplicates, splits_to_relink, non_dup_old_count)

                if args.apply:
                    apply_fixes(conn, table, old_txns, duplicates, splits_to_relink)

            if args.apply:
                conn.commit()
                print("\nAll changes committed successfully.")
            else:
                print("\nDry run complete. Use --apply to make changes.")

        except Exception as e:
            if args.apply:
                conn.rollback()
                print(f"\nError: {e}. All changes rolled back.")
            raise


if __name__ == "__main__":
    main()
