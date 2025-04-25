import sqlalchemy as sa
import pandas as pd

from typing import Optional
from fad.app.utils.data import get_db_connection, get_table
from fad.app.naming_conventions import Tables, ID, NAME, AMOUNT, CATEGORY, TAGS, YEAR, MONTH


conn = get_db_connection()


class MonthlyBudgetRepository:

    @staticmethod
    def add_rule(name: str, amount: float, category: str, tags: str, month: Optional[int], year: Optional[int]) -> None:
        with conn.session as s:
            cmd = sa.text(f"""
                INSERT INTO {Tables.BUDGET_RULES.value}
                (name, amount, category, tags, month, year)
                VALUES (:name, :amount, :category, :tags, :month, :year)
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

    @staticmethod
    def update_rule(id_: int, **fields) -> None:
        assert all(k in {NAME, AMOUNT, CATEGORY, TAGS} for k in fields), "Invalid fields for update"

        set_clause = ", ".join(f"{k} = :{k}" for k in fields)
        fields[ID] = id_

        with conn.session as s:
            cmd = sa.text(f"""
                UPDATE {Tables.BUDGET_RULES.value}
                SET {set_clause}
                WHERE id = :id
            """)
            s.execute(cmd, fields)
            s.commit()

    @staticmethod
    def delete_rule(id_: int) -> None:
        with conn.session as s:
            cmd = sa.text(f"DELETE FROM {Tables.BUDGET_RULES.value} WHERE id = :id")
            s.execute(cmd, {ID: id_})
            s.commit()

    @staticmethod
    def delete_project(project_name: str) -> None:
        with conn.session as s:
            cmd = sa.text(f"""
                DELETE FROM {Tables.BUDGET_RULES.value}
                WHERE category = :category AND year IS NULL AND month IS NULL
            """)
            s.execute(cmd, {CATEGORY: project_name})
            s.commit()

    @staticmethod
    def get_all_rules() -> list[dict]:
        with conn.session as s:
            result = s.execute(sa.text(f"SELECT * FROM {Tables.BUDGET_RULES.value}"))
            return [dict(row) for row in result.fetchall()]

    @staticmethod
    def delete_rules_by_month(year: int, month: int) -> None:
        with conn.session as s:
            cmd = sa.text(
                f"DELETE FROM {Tables.BUDGET_RULES.value} WHERE {YEAR} = :{YEAR} AND {MONTH} = :{MONTH}"
            )
            s.execute(cmd, {YEAR: year, MONTH: month})
            s.commit()


class ProjectBudgetRepository:

    @staticmethod
    def insert_project_rule(category: str, name: str, tags: str, amount: float):
        with conn.session as s:
            s.execute(
                sa.text(
                    f"""
                    INSERT INTO {Tables.BUDGET_RULES.value}
                    ({NAME}, {AMOUNT}, {CATEGORY}, {TAGS}, {MONTH}, {YEAR})
                    VALUES (:name, :amount, :category, :tags, NULL, NULL)
                    """
                ),
                {
                    "name": name,
                    "amount": amount,
                    "category": category,
                    "tags": tags
                }
            )
            s.commit()

    @staticmethod
    def delete_project_rules(category: str):
        with conn.session as s:
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

    @staticmethod
    def delete_project_tag_rule(category: str, tag: str):
        with conn.session as s:
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

    @staticmethod
    def get_rules_for_project(category: str) -> pd.DataFrame:
        rules = get_table(conn, Tables.BUDGET_RULES.value)
        return rules.loc[
            (rules[CATEGORY] == category) &
            (rules[YEAR].isnull()) &
            (rules[MONTH].isnull())
        ]
