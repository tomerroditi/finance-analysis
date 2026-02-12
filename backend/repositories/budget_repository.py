"""
Budget repository with SQLAlchemy ORM.
"""

from typing import Optional

import pandas as pd
from sqlalchemy import select, update, delete
from sqlalchemy.orm import Session

from backend.models.budget import BudgetRule
from backend.constants.budget import AMOUNT, CATEGORY, ID, MONTH, NAME, TAGS, YEAR
from backend.constants.tables import Tables


class BudgetRepository:
    """
    Repository for budget rule CRUD operations using ORM.
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
        self.db = db

    def add(
        self,
        name: str,
        amount: float,
        category: str,
        tags: str,
        month: Optional[int],
        year: Optional[int],
    ) -> None:
        """Create a new budget rule."""
        new_rule = BudgetRule(
            name=name,
            amount=amount,
            category=category,
            tags=tags,
            month=month,
            year=year,
        )
        self.db.add(new_rule)
        self.db.commit()

    def read_all(self) -> pd.DataFrame:
        """Read all budget rules from the database."""
        stmt = select(BudgetRule)
        return pd.read_sql(stmt, self.db.bind)

    def read_by_id(self, id_: int) -> pd.DataFrame:
        """Read a specific budget rule by ID."""
        stmt = select(BudgetRule).where(BudgetRule.id == id_)
        return pd.read_sql(stmt, self.db.bind)

    def read_by_month(self, year: int, month: int) -> pd.DataFrame:
        """Read budget rules for a specific month."""
        stmt = select(BudgetRule).where(
            BudgetRule.year == year, BudgetRule.month == month
        )
        return pd.read_sql(stmt, self.db.bind)

    def read_project_rules(self) -> pd.DataFrame:
        """Read project budget rules (no year/month set)."""
        stmt = select(BudgetRule).where(
            BudgetRule.year.is_(None), BudgetRule.month.is_(None)
        )
        return pd.read_sql(stmt, self.db.bind)

    def update(self, id_: int, **fields) -> None:
        """Update a budget rule by ID."""
        if not fields:
            return

        stmt = update(BudgetRule).where(BudgetRule.id == id_).values(**fields)
        result = self.db.execute(stmt)
        if result.rowcount == 0:
            raise ValueError(f"No rule found with ID {id_}. Update failed.")
        self.db.commit()

    def delete(self, id_: int) -> None:
        """Delete a budget rule by ID."""
        stmt = delete(BudgetRule).where(BudgetRule.id == id_)
        self.db.execute(stmt)
        self.db.commit()

    def delete_by_month(self, year: int, month: int) -> None:
        """Delete budget rules by year and month."""
        stmt = delete(BudgetRule).where(
            BudgetRule.year == year, BudgetRule.month == month
        )
        self.db.execute(stmt)
        self.db.commit()

    def delete_by_category(self, category: str) -> None:
        """Delete budget rules by category (project rules only)."""
        stmt = delete(BudgetRule).where(
            BudgetRule.category == category,
            BudgetRule.year.is_(None),
            BudgetRule.month.is_(None),
        )
        self.db.execute(stmt)
        self.db.commit()

    def delete_by_category_and_tags(self, category: str, tags: str) -> None:
        """Delete budget rules by category and tags (project rules only)."""
        stmt = delete(BudgetRule).where(
            BudgetRule.category == category,
            BudgetRule.tags == tags,
            BudgetRule.year.is_(None),
            BudgetRule.month.is_(None),
        )
        self.db.execute(stmt)
        self.db.commit()

    def _assure_table_exists(self) -> None:
        # Kept for interface compatibility but does nothing as models handle schema
        # Though ideally we rely on Base.metadata.create_all(bind=engine) called at app startup
        pass
