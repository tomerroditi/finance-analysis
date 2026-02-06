"""
Migration script to complete tagging rules migration:
1. Merge missing patterns from inactive rules into existing Auto rules
2. Delete all deprecated/inactive rules
3. Drop deprecated columns (is_active, priority, account_number, created_date)
"""

import json
import sqlite3
from pathlib import Path

DB_PATH = Path.home() / ".finance-analysis" / "data.db"


def get_condition_values(conditions: dict) -> set[str]:
    """Extract all values from a conditions tree."""
    values = set()
    if conditions.get("type") == "CONDITION":
        val = conditions.get("value", "")
        if val:
            values.add(val)
    elif "subconditions" in conditions:
        for sub in conditions["subconditions"]:
            values.update(get_condition_values(sub))
    return values


def merge_patterns_into_auto_rules(cursor: sqlite3.Cursor) -> int:
    """Merge missing patterns from inactive rules into Auto rules."""
    # Get all Auto rules
    cursor.execute("""
        SELECT id, category, tag, conditions 
        FROM tagging_rules 
        WHERE name LIKE 'Auto:%' AND is_active = 1
    """)
    auto_rules = {}
    for row in cursor.fetchall():
        id_, cat, tag, cond_json = row
        try:
            cond = json.loads(cond_json)
            auto_rules[(cat, tag)] = {
                "id": id_,
                "conditions": cond,
                "values": get_condition_values(cond),
            }
        except json.JSONDecodeError:
            continue

    # Get inactive rules grouped by category/tag
    cursor.execute("""
        SELECT category, tag, conditions 
        FROM tagging_rules 
        WHERE is_active = 0 OR (name LIKE 'Migrated:%')
    """)
    inactive_by_cat_tag = {}
    for row in cursor.fetchall():
        cat, tag, cond_json = row
        key = (cat, tag)
        if key not in inactive_by_cat_tag:
            inactive_by_cat_tag[key] = set()
        try:
            cond = json.loads(cond_json)
            inactive_by_cat_tag[key].update(get_condition_values(cond))
        except json.JSONDecodeError:
            continue

    # Merge missing patterns
    updated_count = 0
    for (cat, tag), inactive_values in inactive_by_cat_tag.items():
        if (cat, tag) not in auto_rules:
            print(f"WARNING: No Auto rule for {cat} - {tag}, skipping")
            continue

        auto = auto_rules[(cat, tag)]
        missing = inactive_values - auto["values"]

        if not missing:
            continue

        # Add missing patterns to the Auto rule
        conditions = auto["conditions"]
        if conditions.get("type") not in ("AND", "OR"):
            print(
                f"WARNING: Unexpected condition structure for {cat} - {tag}, skipping"
            )
            continue

        # Convert to OR if needed (to accommodate multiple patterns)
        if (
            conditions.get("type") == "AND"
            and len(conditions.get("subconditions", [])) == 1
        ):
            # Single condition wrapped in AND - convert to OR with the new patterns
            existing_sub = conditions["subconditions"][0]
            conditions = {"type": "OR", "subconditions": [existing_sub]}
        elif conditions.get("type") == "AND":
            # Multiple AND conditions - wrap in OR to add new patterns
            conditions = {"type": "OR", "subconditions": [conditions]}

        # Add missing patterns as new OR subconditions
        for value in missing:
            if not value or value == "-100":  # Skip empty or invalid values
                continue
            conditions["subconditions"].append(
                {
                    "type": "CONDITION",
                    "field": "description",
                    "operator": "contains",
                    "value": value,
                }
            )

        # Update the rule
        cursor.execute(
            "UPDATE tagging_rules SET conditions = ? WHERE id = ?",
            (json.dumps(conditions), auto["id"]),
        )
        updated_count += 1
        print(f"Updated Auto: {cat} - {tag} with {len(missing)} new patterns")

    return updated_count


def delete_deprecated_rules(cursor: sqlite3.Cursor) -> int:
    """Delete all inactive and migrated rules."""
    cursor.execute("""
        DELETE FROM tagging_rules 
        WHERE is_active = 0 
           OR name LIKE 'Migrated:%'
           OR name NOT LIKE 'Auto:%'
    """)
    deleted = cursor.rowcount
    print(f"Deleted {deleted} deprecated rules")
    return deleted


def drop_deprecated_columns(cursor: sqlite3.Cursor):
    """Drop deprecated columns from tagging_rules table."""
    deprecated_columns = ["is_active", "priority", "account_number", "created_date"]

    # Get current columns
    cursor.execute("PRAGMA table_info(tagging_rules)")
    current_columns = {row[1] for row in cursor.fetchall()}

    columns_to_drop = [c for c in deprecated_columns if c in current_columns]
    if not columns_to_drop:
        print("No deprecated columns to drop")
        return

    # SQLite doesn't support DROP COLUMN before 3.35, so we need to recreate the table
    print(f"Dropping deprecated columns: {columns_to_drop}")

    # Get remaining columns
    keep_columns = [
        "id",
        "name",
        "conditions",
        "category",
        "tag",
        "created_at",
        "updated_at",
    ]
    keep_columns = [c for c in keep_columns if c in current_columns]
    columns_str = ", ".join(keep_columns)

    # Recreate table without deprecated columns
    cursor.execute(f"""
        CREATE TABLE tagging_rules_new AS 
        SELECT {columns_str} FROM tagging_rules
    """)
    cursor.execute("DROP TABLE tagging_rules")
    cursor.execute("ALTER TABLE tagging_rules_new RENAME TO tagging_rules")

    print(f"Dropped columns: {columns_to_drop}")


def main():
    """Run the migration."""
    print(f"Connecting to database: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Count before
        cursor.execute("SELECT COUNT(*) FROM tagging_rules")
        total_before = cursor.fetchone()[0]
        cursor.execute(
            "SELECT COUNT(*) FROM tagging_rules WHERE name LIKE 'Auto:%' AND is_active = 1"
        )
        auto_before = cursor.fetchone()[0]
        print(
            f"\nBefore migration: {total_before} total rules, {auto_before} active Auto rules"
        )

        # Step 1: Merge patterns
        print("\n=== Step 1: Merging patterns into Auto rules ===")
        updated = merge_patterns_into_auto_rules(cursor)
        print(f"Updated {updated} Auto rules with merged patterns")

        # Step 2: Delete deprecated rules
        print("\n=== Step 2: Deleting deprecated rules ===")
        deleted = delete_deprecated_rules(cursor)

        # Step 3: Drop deprecated columns
        print("\n=== Step 3: Dropping deprecated columns ===")
        drop_deprecated_columns(cursor)

        # Count after
        cursor.execute("SELECT COUNT(*) FROM tagging_rules")
        total_after = cursor.fetchone()[0]
        print(f"\nAfter migration: {total_after} rules remaining")

        conn.commit()
        print("\n✅ Migration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Migration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
