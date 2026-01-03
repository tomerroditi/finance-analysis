"""
Budget service with pure SQLAlchemy (no Streamlit dependencies).

This module provides business logic for budget rule operations.
"""
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from backend.repositories.budget_repository import BudgetRepository
from backend.services.transactions_service import TransactionsService
from backend.services.tagging_service import CategoriesTagsService
from fad.app.naming_conventions import (
    NAME, AMOUNT, CATEGORY, TAGS, YEAR, MONTH, ALL_TAGS, ID, TOTAL_BUDGET,
    TransactionsTableFields, NonExpensesCategories
)


class BudgetService:
    """
    Service for budget rule business logic.
    
    Provides methods for creating, retrieving, validating, and
    analyzing budget rules.
    """
    
    def __init__(self, db: Session):
        """
        Initialize the budget service.

        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.db = db
        self.budget_repository = BudgetRepository(db)
        self.categories_tags_service = CategoriesTagsService()
        self.transactions_service = TransactionsService(db)

    def get_all_rules(self) -> pd.DataFrame:
        """Get all budget rules with parsed tags."""
        rules = self.budget_repository.read_all()
        if not rules.empty:
            rules[TAGS] = rules[TAGS].apply(lambda x: x.split(";") if isinstance(x, str) else [])
        return rules

    def add_rule(self, name: str, amount: float, category: str, tags: str | list[str], 
                 month: Optional[int] = None, year: Optional[int] = None) -> None:
        """Add a new budget rule with tag conversion."""
        tags_str = ";".join(tags) if isinstance(tags, list) else tags
        self.budget_repository.add(name, amount, category, tags_str, month, year)

    def update_rule(self, id_: int, **fields):
        """Update a budget rule with validation and tag conversion."""
        valid_fields = {NAME, AMOUNT, CATEGORY, TAGS}
        assert all(k in valid_fields for k in fields), f"Invalid fields for update. Valid fields: {valid_fields}"

        if TAGS in fields and isinstance(fields[TAGS], list):
            fields[TAGS] = ";".join(fields[TAGS])

        self.budget_repository.update(id_, **fields)

    def delete_rule(self, id_: int) -> None:
        """Delete a budget rule by ID."""
        self.budget_repository.delete(id_)

    @staticmethod
    def validate_rule_inputs(
            budget_rules: pd.DataFrame,
            name: str,
            category: str,
            tags: list[str],
            amount: float,
            year: int | None,
            month: int | None,
            id_: int | None
    ) -> tuple[bool, str]:
        """Validate budget rule inputs before saving or updating."""
        if id_ is not None:
            rule = budget_rules.loc[budget_rules[ID] == id_].T.squeeze()
            if (rule[NAME] == name and rule[AMOUNT] == amount
                    and rule[CATEGORY] == category and rule[TAGS] == tags):
                return True, ""

        # Unique name check
        if pd.isnull(year) and pd.isnull(month):
            duplicate = budget_rules.loc[
                (budget_rules[YEAR].isnull()) &
                (budget_rules[MONTH].isnull()) &
                (budget_rules[NAME] == name)
            ]
            if id_ is not None:
                duplicate = duplicate.loc[duplicate[ID] != id_]
            if not duplicate.empty:
                return False, f"A project rule with the name '{name}' already exists."
        else:
            duplicate = budget_rules.loc[
                (budget_rules[YEAR] == year) &
                (budget_rules[MONTH] == month) &
                (budget_rules[NAME] == name)
            ]
            if id_ is not None:
                duplicate = duplicate.loc[duplicate[ID] != id_]
            if not duplicate.empty:
                return False, f"A rule with the name '{name}' already exists for this month."

        if name == "":
            return False, "Please enter a name"
        if category is None:
            return False, "Please select a category"
        if not tags:
            return False, "Please select at least one tag"
        if amount <= 0:
            return False, "Amount must be a positive number"

        if pd.isnull(year) and pd.isnull(month):
            rule = budget_rules.loc[budget_rules[ID] == id_].T.squeeze()
            budget_rules = budget_rules.loc[
                (budget_rules[YEAR].isnull())
                & (budget_rules[MONTH].isnull())
                & (budget_rules[CATEGORY] == category)
            ]
            total_rules_amount = budget_rules.loc[~budget_rules[TAGS].isin([[ALL_TAGS]]), AMOUNT].sum()
            if rule[TAGS] == [ALL_TAGS]:
                if amount < total_rules_amount:
                    return False, "The total budget must be greater than the sum of all other rules"
            else:
                total_budget = budget_rules.loc[budget_rules[TAGS].isin([[ALL_TAGS]]), AMOUNT].values[0]
                new_total_rules_amount = total_rules_amount - rule[AMOUNT] + amount
                if new_total_rules_amount > total_budget:
                    return False, "The total budget is exceeded"
            return True, ""

        budget_rules = budget_rules.loc[
            (budget_rules[YEAR] == year) & (budget_rules[MONTH] == month)
        ]
        total_rules_amount = budget_rules.loc[budget_rules[CATEGORY] != TOTAL_BUDGET][AMOUNT].sum()

        if category == TOTAL_BUDGET:
            if amount < total_rules_amount:
                return False, "The total budget must be greater than the sum of all other rules"
            return True, ""

        if id_ is not None:
            total_rules_amount -= budget_rules.loc[budget_rules[ID] == id_][AMOUNT].values[0]
        total_budget = budget_rules.loc[budget_rules[CATEGORY] == TOTAL_BUDGET][AMOUNT].values[0]
        new_total_rules_amount = total_rules_amount + amount
        if new_total_rules_amount > total_budget:
            return False, "The total budget is exceeded"

        if tags == [ALL_TAGS]:
            condition = budget_rules[CATEGORY] == category
            if id_ is not None:
                condition &= budget_rules[ID] != id_
            if not budget_rules.loc[condition].empty:
                return False, f"Cannot have {ALL_TAGS} for a category with existing specific tag rules"

        return True, ""


class MonthlyBudgetService(BudgetService):
    """Service for managing monthly budget rules."""
    
    def get_all_rules(self) -> pd.DataFrame:
        rules = super().get_all_rules()
        return rules.loc[~rules[YEAR].isnull() & ~rules[MONTH].isnull()]

    def delete_rules_by_month(self, year: int, month: int) -> None:
        """Delete all budget rules for a specific month."""
        self.budget_repository.delete_by_month(year, month)

    def get_available_tags_for_each_category(self, budget_rules: pd.DataFrame) -> dict[str, list[str]]:
        """Get available tags for each category not already used."""
        cats_n_tags = self.categories_tags_service.get_categories_and_tags(copy=True)
        for _, rule in budget_rules.iterrows():
            used_tags = rule[TAGS]
            if used_tags == [ALL_TAGS]:
                cats_n_tags.pop(rule[CATEGORY], None)
                continue

            available_tags = cats_n_tags.get(rule[CATEGORY], [])
            available_tags = [tag for tag in available_tags if tag not in used_tags]
            if not available_tags:
                cats_n_tags.pop(rule[CATEGORY], None)
            else:
                cats_n_tags[rule[CATEGORY]] = available_tags

        return cats_n_tags

    def copy_last_month_rules(self, year: int, month: int, budget_rules: pd.DataFrame) -> Optional[str]:
        """Copy budget rules from the previous month."""
        last_month = month - 1 if month != 1 else 12
        last_year = year if month != 1 else year - 1

        rules_to_copy = budget_rules[
            (budget_rules[YEAR] == last_year) & (budget_rules[MONTH] == last_month)
        ]

        if rules_to_copy.empty:
            return None

        self.delete_rules_by_month(year, month)

        for _, rule in rules_to_copy.iterrows():
            self.add_rule(
                name=rule[NAME],
                amount=rule[AMOUNT],
                category=rule[CATEGORY],
                tags=rule[TAGS],
                month=month,
                year=year
            )

        return f"Copied {len(rules_to_copy)} rules from {last_year}-{last_month}"

    @staticmethod
    def get_month_rules(year: int, month: int, budget_rules: pd.DataFrame) -> pd.DataFrame:
        """Get all budget rules for a specific month."""
        return budget_rules[(budget_rules[YEAR] == year) & (budget_rules[MONTH] == month)]

    def get_monthly_budget_view(self, year: int, month: int) -> Optional[list[dict]]:
        """Compute budget rule usage view for a given month."""
        budget_rules = self.get_all_rules()
        all_data = self.transactions_service.get_data_for_analysis()

        expenses = all_data.loc[
            ~all_data[self.transactions_service.transactions_repository.category_col]
            .isin([c.value for c in NonExpensesCategories])
        ].copy()
        expenses[self.transactions_service.transactions_repository.date_col] = pd.to_datetime(
            expenses[self.transactions_service.transactions_repository.date_col]
        )

        projects = ProjectBudgetService(self.db).get_all_projects_names()
        month_data = expenses.loc[
            (expenses[self.transactions_service.transactions_repository.date_col].dt.year == year) &
            (expenses[self.transactions_service.transactions_repository.date_col].dt.month == month) &
            ~expenses[self.transactions_service.transactions_repository.category_col].isin(projects)
        ]

        rules = budget_rules[(budget_rules[YEAR] == year) & (budget_rules[MONTH] == month)]
        if rules.empty:
            return None

        view = []

        total_rule = rules[rules[CATEGORY] == TOTAL_BUDGET]
        if not total_rule.empty:
            total = month_data[self.transactions_service.transactions_repository.amount_col].sum() * -1
            view.append({
                "rule": total_rule.iloc[0].to_dict(),
                "current_amount": total,
                "data": month_data.to_dict(orient="records"),
                "allow_edit": True,
                "allow_delete": False
            })
            rules = rules.loc[~rules.index.isin(total_rule.index)]
        remaining_data = month_data.copy()
        for _, rule in rules.iterrows():
            tags = rule[TAGS]
            cat_data = remaining_data[remaining_data[self.transactions_service.transactions_repository.category_col] == rule[CATEGORY]]

            if tags != [ALL_TAGS]:
                cat_data = cat_data[cat_data[self.transactions_service.transactions_repository.tag_col].isin(tags)]

            amt = cat_data[self.transactions_service.transactions_repository.amount_col].sum() * -1
            view.append({
                "rule": rule.to_dict(),
                "current_amount": amt,
                "data": cat_data.to_dict(orient="records"),
                "allow_edit": True,
                "allow_delete": True
            })

            remaining_data = remaining_data.loc[~remaining_data.index.isin(cat_data.index)]

        if not remaining_data.empty and not rules.empty and not total_rule.empty:
            total_alloc = rules[AMOUNT].sum()
            total_amt = total_rule.iloc[0][AMOUNT] - total_alloc
            view.append({
                "rule": {
                    NAME: "Other Expenses",
                    AMOUNT: total_amt,
                    CATEGORY: "Other Expenses",
                    TAGS: "Other Expenses",
                    ID: f"{year}{month}_Other_Expenses"
                },
                "current_amount": remaining_data[self.transactions_service.transactions_repository.amount_col].sum() * -1,
                "data": remaining_data.to_dict(orient="records"),
                "allow_edit": False,
                "allow_delete": False
            })

        return view

    def get_monthly_project_transactions(self, year: int, month: int) -> Optional[pd.DataFrame]:
        """
        Get project-related transactions for a specific month.
        """
        budget_rules = self.budget_repository.read_all()
        all_data = self.transactions_service.get_data_for_analysis()

        # Only expenses (exclude income, liabilities, etc.)
        expenses = all_data.loc[
            ~all_data[self.transactions_service.transactions_repository.category_col]
            .isin([c.value for c in NonExpensesCategories])
        ].copy()
        expenses[self.transactions_service.transactions_repository.date_col] = pd.to_datetime(
            expenses[self.transactions_service.transactions_repository.date_col]
        )

        # Get project categories
        project_categories = budget_rules[
            budget_rules[YEAR].isnull() & budget_rules[MONTH].isnull()
        ][CATEGORY].unique()

        if len(project_categories) == 0:
            return None

        # Filter for project transactions in the specified month
        project_transactions = expenses.loc[
            (expenses[self.transactions_service.transactions_repository.date_col].dt.year == year) &
            (expenses[self.transactions_service.transactions_repository.date_col].dt.month == month) &
            expenses[self.transactions_service.transactions_repository.category_col].isin(project_categories)
        ]

        return project_transactions if not project_transactions.empty else None

    def get_monthly_project_spending_summary(self, year: int, month: int) -> dict:
        """Get summary of project spending for a month, grouped by project."""
        project_txns = self.get_monthly_project_transactions(year, month)
        if project_txns is None or project_txns.empty:
             return {"projects": []}
             
        cat_col = self.transactions_service.transactions_repository.category_col
        amount_col = self.transactions_service.transactions_repository.amount_col
        
        projects_summary = []
        for project_name, group in project_txns.groupby(cat_col):
            # Handle NaNs for JSON serialization
            group_processed = group.where(pd.notnull(group), None)
            total_spent = group_processed[amount_col].sum() * -1
            projects_summary.append({
                "category": str(project_name),
                "spent": float(total_spent),
                "transactions": group_processed.to_dict(orient="records")
            })
            
        return {
            "projects": projects_summary,
            "total_spent": float(project_txns[amount_col].sum() * -1)
        }


class ProjectBudgetService(BudgetService):
    """Service for managing project-based budget rules."""
    
    def get_all_rules(self) -> pd.DataFrame:
        rules = super().get_all_rules()
        return rules.loc[rules[YEAR].isnull() & rules[MONTH].isnull()].drop(columns=[YEAR, MONTH])

    def get_rules_for_project(self, category: str) -> pd.DataFrame:
        """Get all budget rules for a specific project."""
        rules = self.get_all_rules()
        if rules.empty:
            raise ValueError(f"Project {category} not found")

        rules = rules.loc[rules[CATEGORY] == category]
        return rules

    def create_project(self, category: str, total_budget: float) -> None:
        """Create a new project budget."""
        self.add_rule(
            name=TOTAL_BUDGET,
            amount=total_budget,
            category=category,
            tags=[ALL_TAGS],
            month=None,
            year=None
        )

        tags = self.categories_tags_service.get_categories_and_tags(copy=True)
        tags = tags[category]
        for tag in tags:
            self.add_rule(
                name=tag,
                amount=0,
                category=category,
                tags=[tag],
                month=None,
                year=None
            )

    def update_project(self, category: str, total_budget: float) -> None:
        """Update the total budget for a project."""
        rules = self.get_rules_for_project(category)
        total_rule = rules.loc[rules[TAGS] == [ALL_TAGS]]
        rule_id = int(total_rule.iloc[0][ID])
        self.update_rule(rule_id, amount=total_budget)

    def delete_project(self, category: str) -> None:
        """Delete all budget rules for a project."""
        self.budget_repository.delete_by_category(category)

    def delete_project_tag_rule(self, category: str, tag: str) -> None:
        """Delete a specific tag rule from a project."""
        self.budget_repository.delete_by_category_and_tags(category, tag)

    def get_project_transactions(self, project: str) -> pd.DataFrame:
        """Get all transactions for a specific project."""
        all_data = self.transactions_service.get_data_for_analysis()
        return all_data.loc[all_data[TransactionsTableFields.CATEGORY.value] == project]

    def get_all_projects_names(self) -> list[str]:
        """Get all project names."""
        rules = self.get_all_rules()
        return rules[CATEGORY].unique().tolist()

    def get_available_categories_for_new_project(self) -> list[str]:
        """Get available categories for a new project."""
        current_projects = self.get_all_projects_names()
        new_possible_projects = [cat for cat in self.categories_tags_service.get_categories_and_tags(copy=True).keys() if cat not in current_projects]
        return new_possible_projects