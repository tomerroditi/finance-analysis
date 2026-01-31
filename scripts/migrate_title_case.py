#!/usr/bin/env python3
"""
Migration script to standardize all category and tag values to title case.

This script normalizes existing data in:
1. The categories.yaml file
2. All database tables with category/tag columns

Usage:
    python scripts/migrate_title_case.py [--dry-run]

Options:
    --dry-run    Show what would be changed without making actual changes
"""

import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import yaml
from sqlalchemy import text

from backend.config import AppConfig
from backend.database import get_db_context
from backend.utils.text_utils import to_title_case

# Tables and columns to migrate
TABLES_TO_MIGRATE = [
    ("bank_transactions", ["category", "tag"]),
    ("credit_card_transactions", ["category", "tag"]),
    ("cash_transactions", ["category", "tag"]),
    ("manual_investment_transactions", ["category", "tag"]),
    ("split_transactions", ["category", "tag"]),
    ("tagging_rules", ["category", "tag"]),
    ("budget_rules", ["category", "tags"]),
]


def backup_database(db_path: str) -> str:
    """Create a backup of the database file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.backup_{timestamp}"
    shutil.copy2(db_path, backup_path)
    print(f"✓ Created database backup: {backup_path}")
    return backup_path


def backup_yaml_file(file_path: str) -> str:
    """Create a backup of a YAML file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{file_path}.backup_{timestamp}"
    shutil.copy2(file_path, backup_path)
    print(f"✓ Created YAML backup: {backup_path}")
    return backup_path


def migrate_categories_yaml(file_path: str, dry_run: bool = False) -> dict:
    """
    Migrate categories.yaml to use title case.

    Returns statistics about the migration.
    """
    if not os.path.exists(file_path):
        print(f"⚠ Categories file not found: {file_path}")
        return {"categories_changed": 0, "tags_changed": 0}

    with open(file_path, "r") as f:
        categories = yaml.load(f, Loader=yaml.FullLoader) or {}

    stats = {"categories_changed": 0, "tags_changed": 0}
    new_categories = {}

    for category, tags in categories.items():
        new_category = to_title_case(category)
        if new_category != category:
            stats["categories_changed"] += 1
            print(f"  Category: '{category}' → '{new_category}'")

        new_tags = []
        for tag in tags:
            new_tag = to_title_case(tag)
            if new_tag != tag:
                stats["tags_changed"] += 1
                print(f"    Tag: '{tag}' → '{new_tag}'")
            new_tags.append(new_tag)

        new_categories[new_category] = sorted(list(set(new_tags)))

    if not dry_run and (stats["categories_changed"] > 0 or stats["tags_changed"] > 0):
        backup_yaml_file(file_path)
        with open(file_path, "w") as f:
            yaml.dump(new_categories, f, default_flow_style=False, allow_unicode=True)
        print(f"✓ Updated categories file")

    return stats


def normalize_semicolon_list(value: str) -> str:
    """Normalize each item in a semicolon-separated list."""
    if not value:
        return value
    items = value.split(";")
    normalized = [to_title_case(item.strip()) for item in items]
    return ";".join(normalized)


def migrate_database_table(
    db, table: str, columns: list[str], dry_run: bool = False
) -> dict:
    """
    Migrate a database table to use title case for specified columns.

    Returns statistics about the migration.
    """
    stats = {col: 0 for col in columns}

    for column in columns:
        # Check if this is a semicolon-separated column (budget_rules.tags)
        is_semicolon_separated = table == "budget_rules" and column == "tags"

        # Get distinct non-null values
        query = text(
            f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL"
        )
        try:
            result = db.execute(query)
            values = [row[0] for row in result]
        except Exception as e:
            print(f"  ⚠ Error reading {table}.{column}: {e}")
            continue

        for old_value in values:
            if is_semicolon_separated:
                new_value = normalize_semicolon_list(old_value)
            else:
                new_value = to_title_case(old_value)

            if new_value != old_value:
                stats[column] += 1
                print(f"  {table}.{column}: '{old_value}' → '{new_value}'")

                if not dry_run:
                    update_query = text(
                        f"UPDATE {table} SET {column} = :new_value WHERE {column} = :old_value"
                    )
                    db.execute(
                        update_query, {"new_value": new_value, "old_value": old_value}
                    )

    return stats


def run_migration(dry_run: bool = False):
    """Run the full migration."""
    print("=" * 60)
    print("Title Case Migration Script")
    print("=" * 60)

    if dry_run:
        print("🔍 DRY RUN MODE - No changes will be made\n")
    else:
        print("⚡ LIVE MODE - Changes will be applied\n")

    config = AppConfig()
    total_stats = {"yaml_categories": 0, "yaml_tags": 0, "db_changes": 0}

    # 1. Migrate categories.yaml
    print("\n📁 Migrating categories.yaml...")
    categories_path = config.get_categories_path()
    yaml_stats = migrate_categories_yaml(categories_path, dry_run)
    total_stats["yaml_categories"] = yaml_stats["categories_changed"]
    total_stats["yaml_tags"] = yaml_stats["tags_changed"]

    # 2. Migrate database tables
    print("\n🗄️  Migrating database tables...")
    db_path = config.get_db_path()

    if not dry_run:
        backup_database(db_path)

    with get_db_context() as db:
        for table, columns in TABLES_TO_MIGRATE:
            print(f"\n  Table: {table}")
            table_stats = migrate_database_table(db, table, columns, dry_run)
            for col, count in table_stats.items():
                total_stats["db_changes"] += count

        if not dry_run:
            db.commit()
            print("\n✓ Database changes committed")

    # Summary
    print("\n" + "=" * 60)
    print("Migration Summary")
    print("=" * 60)
    print(f"  YAML categories updated: {total_stats['yaml_categories']}")
    print(f"  YAML tags updated: {total_stats['yaml_tags']}")
    print(f"  Database values updated: {total_stats['db_changes']}")

    if dry_run:
        print("\n🔍 This was a dry run. Run without --dry-run to apply changes.")
    else:
        print("\n✅ Migration complete!")


def main():
    dry_run = "--dry-run" in sys.argv
    run_migration(dry_run=dry_run)


if __name__ == "__main__":
    main()
