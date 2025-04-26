import sqlalchemy as sa
import pandas as pd

from typing import Optional
from fad.app.utils.data import get_db_connection, get_table
from fad.app.naming_conventions import Tables, ID, NAME, AMOUNT, CATEGORY, TAGS, YEAR, MONTH


conn = get_db_connection()


class BudgetRepository:
    @staticmethod
    def get_all_rules() -> pd.DataFrame:
        """Get all rules from the budget repository."""
        rules = get_table(conn, Tables.BUDGET_RULES.value)
        rules[TAGS] = rules[TAGS].apply(lambda x: x.split(";") if isinstance(x, str) else [])
        return rules

    @staticmethod
    def add_rule(name: str, amount: float, category: str, tags: str | list[str], month: Optional[int], year: Optional[int]) -> None:
        with conn.session as s:
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

    @staticmethod
    def update_rule(id_: int, **fields) -> None:
        assert all(k in {NAME, AMOUNT, CATEGORY, TAGS} for k in fields), "Invalid fields for update"

        set_clause = ", ".join(f"{k} = :{k}" for k in fields.keys())
        fields[ID] = str(id_)  # TODO: realize why we need to convert to str here where the table column is set to int
        if TAGS in fields and isinstance(fields[TAGS], list):
            fields[TAGS] = ";".join(fields[TAGS])

        with conn.session as s:
            cmd = sa.text(f"""
                UPDATE {Tables.BUDGET_RULES.value}
                SET {set_clause}
                WHERE {ID} = :{ID}
            """).bindparams(sa.bindparam(ID, type_=sa.Integer))
            result = s.execute(cmd, fields)
            if result.rowcount == 0:
                raise ValueError(f"No rule found with ID {id_}. Update failed.")
            s.commit()


class MonthlyBudgetRepository(BudgetRepository):
    @staticmethod
    def get_all_rules() -> pd.DataFrame:
        rules = super(MonthlyBudgetRepository, MonthlyBudgetRepository).get_all_rules()
        rules = rules.loc[~rules[YEAR].isnull() & ~rules[MONTH].isnull()]
        return rules

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
    def delete_rules_by_month(year: int, month: int) -> None:
        with conn.session as s:
            cmd = sa.text(
                f"DELETE FROM {Tables.BUDGET_RULES.value} WHERE {YEAR} = :{YEAR} AND {MONTH} = :{MONTH}"
            )
            s.execute(cmd, {YEAR: year, MONTH: month})
            s.commit()


class ProjectBudgetRepository(BudgetRepository):
    @staticmethod
    def get_all_rules() -> pd.DataFrame:
        rules = super(ProjectBudgetRepository, ProjectBudgetRepository).get_all_rules()
        rules = rules.loc[rules[YEAR].isnull() & rules[MONTH].isnull()]
        return rules

    @staticmethod
    def add_rule(name: str, amount: float, category: str, tags: str | list[str], year: Optional[int] = None, month: Optional[int] = None) -> None:
        if year is not None or month is not None:
            raise ValueError("Year and month should be None for project rules")

        super(ProjectBudgetRepository, ProjectBudgetRepository).add_rule(
            name=name,
            amount=amount,
            category=category,
            tags=tags,
            month=None,
            year=None
        )

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
        assert isinstance(tag, str), f"Tag should be a string, got {type(tag)} ({tag})"
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
        rules = rules.loc[
            (rules[CATEGORY] == category) &
            (rules[YEAR].isnull()) &
            (rules[MONTH].isnull())
        ]
        rules[TAGS] = rules[TAGS].apply(lambda x: x.split(";") if isinstance(x, str) else [])
        return rules
