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
        self.conn = get_db_connection()
        self.assure_table_exists()

    def get_data(self) -> pd.DataFrame:
        """Get all rules from the budget repository."""
        with self.conn.session as s:
            query = f"SELECT * FROM {self.table}"
            result = s.execute(text(query))
            df = pd.DataFrame(result.fetchall())
            if not df.empty:
                df.columns = result.keys()
            return df

    def get_all_rules(self) -> pd.DataFrame:
        """Get all rules from the budget repository."""
        rules = self.get_data()
        rules[self.tags_col] = rules[self.tags_col].apply(lambda x: x.split(";") if isinstance(x, str) else [])
        return rules
    
    def delete_rule(self, id_: int) -> None:
        with self.conn.session as s:
            cmd = sa.text(f"DELETE FROM {Tables.BUDGET_RULES.value} WHERE id = :id")
            s.execute(cmd, {ID: id_})
            s.commit()

    def add_rule(self, name: str, amount: float, category: str, tags: str | list[str], month: Optional[int], year: Optional[int]) -> None:
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
                TAGS: ";".join(tags) if isinstance(tags, list) else tags,
                MONTH: month,
                YEAR: year
            })
            s.commit()

    def update_rule(self, id_: int, **fields) -> None:
        assert all(k in {NAME, AMOUNT, CATEGORY, TAGS} for k in fields), "Invalid fields for update"

        set_clause = ", ".join(f"{k} = :{k}" for k in fields.keys())
        fields[ID] = str(id_)  # TODO: realize why we need to convert to str here where the table column is set to int
        if TAGS in fields and isinstance(fields[TAGS], list):
            fields[TAGS] = ";".join(fields[TAGS])

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

    def assure_table_exists(self):
        """create the budget table if it doesn't exist"""
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


class MonthlyBudgetRepository(BudgetRepository):

    def get_all_rules(self) -> pd.DataFrame:
        rules = super(MonthlyBudgetRepository, self).get_all_rules()
        rules = rules.loc[~rules[YEAR].isnull() & ~rules[MONTH].isnull()]
        return rules

    def delete_project(self, project_name: str) -> None:
        with self.conn.session as s:
            cmd = sa.text(f"""
                DELETE FROM {Tables.BUDGET_RULES.value}
                WHERE category = :category AND year IS NULL AND month IS NULL
            """)
            s.execute(cmd, {CATEGORY: project_name})
            s.commit()

    def delete_rules_by_month(self, year: int, month: int) -> None:
        with self.conn.session as s:
            cmd = sa.text(
                f"DELETE FROM {Tables.BUDGET_RULES.value} WHERE {YEAR} = :{YEAR} AND {MONTH} = :{MONTH}"
            )
            s.execute(cmd, {YEAR: year, MONTH: month})
            s.commit()


class ProjectBudgetRepository(BudgetRepository):
    def get_all_rules(self) -> pd.DataFrame:
        rules = super(ProjectBudgetRepository, self).get_all_rules()
        rules = rules.loc[rules[YEAR].isnull() & rules[MONTH].isnull()]
        return rules

    def add_rule(self, name: str, amount: float, category: str, tags: str | list[str], year: Optional[int] = None, month: Optional[int] = None) -> None:
        if year is not None or month is not None:
            raise ValueError("Year and month should be None for project rules")

        super(ProjectBudgetRepository, self).add_rule(
            name=name,
            amount=amount,
            category=category,
            tags=tags,
            month=None,
            year=None
        )

    def delete_project_rules(self, category: str):
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

    def delete_project_tag_rule(self, category: str, tag: str):
        assert isinstance(tag, str), f"Tag should be a string, got {type(tag)} ({tag})"
        with self.conn.session as s:
            s.execute(
                sa.text(
                    f"""
                    DELETE FROM {Tables.BUDGET_RULES.value}
                    WHERE {CATEGORY} = :category AND {TAGS} = :tags AND {YEAR} IS NULL AND {MONTH} IS NULL
                    """
                ),
                {"category": category, "tags": tag}
            )
            s.commit()

    def get_rules_for_project(self, category: str) -> pd.DataFrame:
        rules = self.get_all_rules()
        rules = rules.loc[
            (rules[CATEGORY] == category) &
            (rules[YEAR].isnull()) &
            (rules[MONTH].isnull())
        ]
        rules[TAGS] = rules[TAGS].apply(lambda x: x.split(";") if isinstance(x, str) else [])
        return rules
