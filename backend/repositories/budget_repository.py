"""
Budget repository with pure SQLAlchemy (no Streamlit dependencies).

This module provides data access for budget rule operations.
"""
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from fad.app.naming_conventions import Tables, ID, NAME, AMOUNT, CATEGORY, TAGS, YEAR, MONTH


class BudgetRepository:
    """
    Repository for budget rule CRUD operations.
    
    Manages budget rules stored in SQLite using pure SQLAlchemy.
    """
    table = Tables.BUDGET_RULES.value
    id_col = ID
    name_col = NAME
    amount_col = AMOUNT
    category_col = CATEGORY
    tags_col = TAGS
    year_col = YEAR
    month_col = MONTH

    def __init__(self, db: Session):
        """
        Initialize the budget repository.

        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.db = db
        self._assure_table_exists()

    def add(self, name: str, amount: float, category: str, tags: str, 
            month: Optional[int], year: Optional[int]) -> None:
        """Create a new budget rule."""
        cmd = text(f"""
            INSERT INTO {Tables.BUDGET_RULES.value}
            ({NAME}, {AMOUNT}, {CATEGORY}, {TAGS}, {MONTH}, {YEAR})
            VALUES (:{NAME}, :{AMOUNT}, :{CATEGORY}, :{TAGS}, :{MONTH}, :{YEAR})
        """)
        self.db.execute(cmd, {
            NAME: name,
            AMOUNT: amount,
            CATEGORY: category,
            TAGS: tags,
            MONTH: month,
            YEAR: year
        })
        self.db.commit()

    def read_all(self) -> pd.DataFrame:
        """Read all budget rules from the database."""
        result = self.db.execute(text(f"SELECT * FROM {self.table}"))
        columns = result.keys()
        data = result.fetchall()
        return pd.DataFrame(data, columns=columns)

    def read_by_id(self, id_: int) -> pd.DataFrame:
        """Read a specific budget rule by ID."""
        result = self.db.execute(
            text(f"SELECT * FROM {self.table} WHERE {ID} = :id"),
            {"id": id_}
        )
        columns = result.keys()
        data = result.fetchall()
        return pd.DataFrame(data, columns=columns)

    def read_by_month(self, year: int, month: int) -> pd.DataFrame:
        """Read budget rules for a specific month."""
        result = self.db.execute(
            text(f"SELECT * FROM {self.table} WHERE {YEAR} = :year AND {MONTH} = :month"),
            {"year": year, "month": month}
        )
        columns = result.keys()
        data = result.fetchall()
        return pd.DataFrame(data, columns=columns)

    def read_project_rules(self) -> pd.DataFrame:
        """Read project budget rules (no year/month set)."""
        result = self.db.execute(
            text(f"SELECT * FROM {self.table} WHERE {YEAR} IS NULL AND {MONTH} IS NULL")
        )
        columns = result.keys()
        data = result.fetchall()
        return pd.DataFrame(data, columns=columns)

    def update(self, id_: int, **fields) -> None:
        """Update a budget rule by ID."""
        if not fields:
            return

        set_clause = ", ".join(f"{k} = :{k}" for k in fields.keys())
        fields["id"] = id_

        cmd = text(f"""
            UPDATE {Tables.BUDGET_RULES.value}
            SET {set_clause}
            WHERE {ID} = :id
        """)
        result = self.db.execute(cmd, fields)
        if result.rowcount == 0:
            raise ValueError(f"No rule found with ID {id_}. Update failed.")
        self.db.commit()

    def delete(self, id_: int) -> None:
        """Delete a budget rule by ID."""
        self.db.execute(
            text(f"DELETE FROM {Tables.BUDGET_RULES.value} WHERE id = :id"),
            {"id": id_}
        )
        self.db.commit()

    def delete_by_month(self, year: int, month: int) -> None:
        """Delete budget rules by year and month."""
        self.db.execute(
            text(f"DELETE FROM {Tables.BUDGET_RULES.value} WHERE {YEAR} = :year AND {MONTH} = :month"),
            {"year": year, "month": month}
        )
        self.db.commit()

    def delete_by_category(self, category: str) -> None:
        """Delete budget rules by category (project rules only)."""
        self.db.execute(
            text(f"""
                DELETE FROM {Tables.BUDGET_RULES.value}
                WHERE {CATEGORY} = :category AND {YEAR} IS NULL AND {MONTH} IS NULL
            """),
            {"category": category}
        )
        self.db.commit()

    def delete_by_category_and_tags(self, category: str, tags: str) -> None:
        """Delete budget rules by category and tags (project rules only)."""
        self.db.execute(
            text(f"""
                DELETE FROM {Tables.BUDGET_RULES.value}
                WHERE {CATEGORY} = :category AND {TAGS} = :tags AND {YEAR} IS NULL AND {MONTH} IS NULL
            """),
            {"category": category, "tags": tags}
        )
        self.db.commit()

    def _assure_table_exists(self) -> None:
        """Create the budget table if it doesn't exist."""
        self.db.execute(
            text(f"""
                CREATE TABLE IF NOT EXISTS budget_rules (
                    {self.id_col} INTEGER PRIMARY KEY,
                    {self.name_col} TEXT,
                    {self.amount_col} REAL,
                    {self.category_col} TEXT,
                    {self.tags_col} TEXT,
                    {self.year_col} INTEGER,
                    {self.month_col} INTEGER
                )
            """)
        )
        self.db.commit()
