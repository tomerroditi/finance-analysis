from typing import Optional

import pandas as pd
import sqlalchemy as sa
from sqlalchemy.sql import text
from streamlit.connections import SQLConnection

from fad.app.data_access import get_db_connection
from fad.app.naming_conventions import Tables, ID, NAME, AMOUNT, CATEGORY, TAGS, YEAR, MONTH


class BudgetRepository:
    table = Tables.BUDGET_RULES.value
    id_col = ID
    name_col = NAME
    amount_col = AMOUNT
    category_col = CATEGORY
    tags_col = TAGS
    year_col = YEAR
    month_col = MONTH

    def __init__(self, conn: SQLConnection = get_db_connection()):
        self.conn = conn
        self.assure_table_exists()

    def add(self, name: str, amount: float, category: str, tags: str, month: Optional[int], year: Optional[int]) -> None:
        """Create a new budget rule."""
        with self.conn.session as s:
            cmd = sa.text(f"""
                INSERT INTO {Tables.BUDGET_RULES.value}
                ({NAME}, {AMOUNT}, {CATEGORY}, {TAGS}, {MONTH}, {YEAR})
                VALUES (:{NAME}, :{AMOUNT}, :{CATEGORY}, :{TAGS}, :{MONTH}, :{YEAR})
            """)
            s.execute(cmd, {
                NAME: name,
                AMOUNT: amount,
                CATEGORY: category,
                TAGS: tags,
                MONTH: month,
                YEAR: year
            })
            s.commit()

    def read_all(self) -> pd.DataFrame:
        """Read all budget rules from the database."""
        with self.conn.session as s:
            query = f"SELECT * FROM {self.table}"
            result = s.execute(text(query))
            df = pd.DataFrame(result.fetchall())
            if not df.empty:
                df.columns = result.keys()
            return df

    def read_by_id(self, id_: int) -> pd.DataFrame:
        """Read a specific budget rule by ID."""
        with self.conn.session as s:
            query = f"SELECT * FROM {self.table} WHERE {ID} = :id"
            result = s.execute(text(query), {ID: id_})
            df = pd.DataFrame(result.fetchall())
            if not df.empty:
                df.columns = result.keys()
            return df

    def update(self, id_: int, **fields) -> None:
        """Update a budget rule by ID."""
        if not fields:
            return

        set_clause = ", ".join(f"{k} = :{k}" for k in fields.keys())
        fields[ID] = str(id_)

        with self.conn.session as s:
            cmd = sa.text(f"""
                UPDATE {Tables.BUDGET_RULES.value}
                SET {set_clause}
                WHERE {ID} = :{ID}
            """).bindparams(sa.bindparam(ID, type_=sa.Integer))
            result = s.execute(cmd, fields)
            if result.rowcount == 0:
                raise ValueError(f"No rule found with ID {id_}. Update failed.")
            s.commit()

    def delete(self, id_: int) -> None:
        """Delete a budget rule by ID."""
        with self.conn.session as s:
            cmd = sa.text(f"DELETE FROM {Tables.BUDGET_RULES.value} WHERE id = :id")
            s.execute(cmd, {ID: id_})
            s.commit()

    def delete_by_month(self, year: int, month: int) -> None:
        """Delete budget rules by year and month."""
        with self.conn.session as s:
            cmd = sa.text(
                f"DELETE FROM {Tables.BUDGET_RULES.value} WHERE {YEAR} = :{YEAR} AND {MONTH} = :{MONTH}"
            )
            s.execute(cmd, {YEAR: year, MONTH: month})
            s.commit()

    def delete_by_category(self, category: str) -> None:
        """Delete budget rules by category (project rules only)."""
        with self.conn.session as s:
            s.execute(
                sa.text(
                    f"""
                    DELETE FROM {Tables.BUDGET_RULES.value}
                    WHERE {CATEGORY} = :category AND {YEAR} IS NULL AND {MONTH} IS NULL
                    """
                ),
                {"category": category}
            )
            s.commit()

    def delete_by_category_and_tags(self, category: str, tags: str) -> None:
        """Delete budget rules by category and tags (project rules only)."""
        with self.conn.session as s:
            s.execute(
                sa.text(
                    f"""
                    DELETE FROM {Tables.BUDGET_RULES.value}
                    WHERE {CATEGORY} = :category AND {TAGS} = :tags AND {YEAR} IS NULL AND {MONTH} IS NULL
                    """
                ),
                {"category": category, "tags": tags}
            )
            s.commit()

    def assure_table_exists(self):
        """Create the budget table if it doesn't exist."""
        with self.conn.session as s:
            s.execute(
                text(
                    f'CREATE TABLE IF NOT EXISTS budget_rules ('
                    f'{self.id_col} INTEGER PRIMARY KEY, '
                    f'{self.name_col} TEXT, '
                    f'{self.amount_col} REAL, '
                    f'{self.category_col} TEXT, '
                    f'{self.tags_col} TEXT, '
                    f'{self.year_col} INTEGER, '
                    f'{self.month_col} INTEGER'
                    f');'
                )
            )
            s.commit()
