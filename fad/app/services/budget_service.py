from typing import Optional

from streamlit.connections import SQLConnection
import pandas as pd

from fad.app.data_access import get_db_connection
from fad.app.data_access.budget_repository import BudgetRepository
from fad.app.services.tagging_service import CategoriesTagsService
from fad.app.services.transactions_service import TransactionsService
from fad.app.naming_conventions import NAME, AMOUNT, CATEGORY, TAGS, YEAR, MONTH, ALL_TAGS, ID, TOTAL_BUDGET, \
    TransactionsTableFields, NonExpensesCategories


class BudgetService:
    def __init__(self, conn: SQLConnection = get_db_connection()):
        self.conn = conn
        self.budget_repository = BudgetRepository(conn)
        self.categories_tags_service = CategoriesTagsService()
        self.transactions_service = TransactionsService(self.conn)

    def get_all_rules(self) -> pd.DataFrame:
        """Get all budget rules with parsed tags."""
        rules = self.budget_repository.read_all()
        if not rules.empty:
            rules[TAGS] = rules[TAGS].apply(lambda x: x.split(";") if isinstance(x, str) else [])
        return rules

    def add_rule(self, name: str, amount: float, category: str, tags: str | list[str], month: Optional[int] = None, year: Optional[int] = None) -> None:
        """Add a new budget rule with tag conversion."""
        tags_str = ";".join(tags) if isinstance(tags, list) else tags
        self.budget_repository.add(name, amount, category, tags_str, month, year)

    def update_rule(self, id_: int, **fields):
        """Update a budget rule with validation and tag conversion."""
        # Validate fields
        valid_fields = {NAME, AMOUNT, CATEGORY, TAGS}
        assert all(k in valid_fields for k in fields), f"Invalid fields for update. Valid fields: {valid_fields}"

        # Convert tags list to string if needed
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
        """
        Validate budget rule inputs before saving or updating.

        Verifies that the rule values meet all requirements and constraints. Checks for:
        - Positive amount
        - Valid category selection
        - Tag selection
        - Non-empty name
        - Total budget not exceeded
        - No conflicts with ALL_TAGS rules

        Parameters
        ----------
        budget_rules : pd.DataFrame
            DataFrame containing all budget rules.
        name : str
            The name of the rule.
        category : str
            The category for the rule.
        tags : list[str]
            List of tags associated with the rule.
        amount : float
            The budget amount for the rule.
        year : int | None
            The year for the rule. If None/NaN, the rule is a project rule.
        month : int | None
            The month for the rule. If None/NaN, the rule is a project rule.
        id_ : int | None
            The ID of an existing rule to update, or None for a new rule.

        Returns
        -------
        tuple[bool, str]
            A tuple containing:
            - bool: True if inputs are valid, False otherwise
            - str: Error message if invalid, empty string if valid
        """
        # TODO: split this function into smaller functions
        if id_ is not None:
            rule = budget_rules.loc[budget_rules[ID] == id_].T.squeeze()
            # if no change just return
            if (rule[NAME] == name
                    and rule[AMOUNT] == amount
                    and rule[CATEGORY] == category
                    and rule[TAGS] == tags):
                return True, ""

        # Unique name check (ignore current rule if updating)
        if pd.isnull(year) and pd.isnull(month):
            # Project rule: name must be unique among project rules (same category, null year/month)
            duplicate = budget_rules.loc[
                (budget_rules[YEAR].isnull()) &
                (budget_rules[MONTH].isnull()) &
                (budget_rules[NAME] == name)
            ]
            if id_ is not None:
                duplicate = duplicate.loc[duplicate[ID] != id_]
            if not duplicate.empty:
                return False, f"A project rule with the name '{name}' already exists. Rule names must be unique."
        else:
            # Monthly rule: name must be unique for the same year/month
            duplicate = budget_rules.loc[
                (budget_rules[YEAR] == year) &
                (budget_rules[MONTH] == month) &
                (budget_rules[NAME] == name)
            ]
            if id_ is not None:
                duplicate = duplicate.loc[duplicate[ID] != id_]
            if not duplicate.empty:
                return False, f"A rule with the name '{name}' already exists for this month. Rule names must be unique."

        if name == "":
            return False, "Please enter a name"
        if category is None:
            return False, "Please select a category"
        if not tags:
            return False, "Please select at least one tag"
        if amount <= 0:
            return False, "Amount must be a positive number"

        if pd.isnull(year) and pd.isnull(month):
            # updating a project rule (you cannot add a new project rule, and can update amount only)
            rule = budget_rules.loc[budget_rules[ID] == id_].T.squeeze()
            budget_rules = budget_rules.loc[
                (budget_rules[YEAR].isnull())
                & (budget_rules[MONTH].isnull())
                & (budget_rules[CATEGORY] == category)
                ]
            total_rules_amount = budget_rules.loc[~budget_rules[TAGS].isin([[ALL_TAGS]]), AMOUNT].sum()
            if rule[TAGS] == [ALL_TAGS]:
                # updating the project total budget
                if amount < total_rules_amount:
                    return False, "The total budget must be greater than the sum of all other rules of the project"

            else:
                # updating a project rule with specific tag
                total_budget = budget_rules.loc[budget_rules[TAGS].isin([[ALL_TAGS]]), AMOUNT].values[0]
                new_total_rules_amount = total_rules_amount - rule[AMOUNT] + amount
                if new_total_rules_amount > total_budget:
                    return False, "The total budget is exceeded. please set a lower amount or increase the total budget"
            return True, ""

        budget_rules = budget_rules.loc[
            (budget_rules[YEAR] == year)
            & (budget_rules[MONTH] == month)
            ]
        total_rules_amount = budget_rules.loc[budget_rules[CATEGORY] != TOTAL_BUDGET][AMOUNT].sum()

        if category == TOTAL_BUDGET:
            # updating the total budget for a month, only amount might be updated
            if amount < total_rules_amount:
                return False, "The total budget must be greater than the sum of all other rules of the month"
            return True, ""

        # add/update a rule for a specific month
        if id_ is not None:
            # updating a certain rule, hence we need to exclude it from the total rules amount
            total_rules_amount -= budget_rules.loc[budget_rules[ID] == id_][AMOUNT].values[0]
        total_budget = budget_rules.loc[budget_rules[CATEGORY] == TOTAL_BUDGET][AMOUNT].values[0]
        new_total_rules_amount = total_rules_amount + amount
        if new_total_rules_amount > total_budget:
            return False, "The total budget is exceeded. please set a lower amount or increase the total budget"

        if tags == [ALL_TAGS]:
            condition = budget_rules[CATEGORY] == category
            if id_ is not None:
                condition &= budget_rules[ID] != id_
            if not budget_rules.loc[condition].empty:
                return False, f"You cannot have a rule with {ALL_TAGS} for a category that already has rules with specific tags"

        return True, ""


class MonthlyBudgetService(BudgetService):
    """
    Service for managing monthly budget rules and calculations.

    This class provides methods for creating, retrieving, validating, and
    analyzing monthly budget rules. It handles operations such as copying rules
    from previous months, validating rule inputs, and generating budget views.
    """
    def get_all_rules(self) -> pd.DataFrame:
        rules = super().get_all_rules()
        rules = rules.loc[~rules[YEAR].isnull() & ~rules[MONTH].isnull()]
        return rules

    def get_monthly_rules(self) -> pd.DataFrame:
        """Get all monthly budget rules (rules with year and month specified)."""
        rules = self.budget_repository.read_all()
        if not rules.empty:
            rules = rules.loc[~rules[YEAR].isnull() & ~rules[MONTH].isnull()]
            rules[TAGS] = rules[TAGS].apply(lambda x: x.split(";") if isinstance(x, str) else [])
        return rules

    def delete_rules_by_month(self, year: int, month: int) -> None:
        """Delete all budget rules for a specific month."""
        self.budget_repository.delete_by_month(year, month)

    def get_available_tags_for_each_category(self, budget_rules: pd.DataFrame) -> dict[str, list[str]]:
        """
        Get available tags for each category that are not already used in budget rules.

        Filters out tags that are already used in budget rules, and removes categories
        that have no available tags or have a rule with ALL_TAGS.

        Parameters
        ----------
        budget_rules : pd.DataFrame
            DataFrame containing budget rules.

        Returns
        -------
        dict[str, list[str]]
            Dictionary mapping category names to lists of available tags.
        """
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
        """
        Copy budget rules from the previous month into the selected month.

        Identifies the previous month (accounting for year boundaries), retrieves
        its rules, and copies them to the specified month after deleting any
        existing rules for that month.

        Parameters
        ----------
        year : int
            The year of the target month.
        month : int
            The month to copy rules to (1-12).
        budget_rules : pd.DataFrame
            DataFrame containing all budget rules.

        Returns
        -------
        Optional[str]
            A success message with the number of rules copied if successful,
            or None if no rules were found for the previous month.
        """
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
        """
        Fetch all budget rules for a specific month and year.

        Filters the budget rules DataFrame to return only the rules that apply
        to the specified month and year.

        Parameters
        ----------
        year : int
            The year to filter rules for.
        month : int
            The month to filter rules for (1-12).
        budget_rules : pd.DataFrame
            DataFrame containing all budget rules.

        Returns
        -------
        pd.DataFrame
            DataFrame containing only the rules for the specified month and year.
        """
        return budget_rules[
            (budget_rules[YEAR] == year) & (budget_rules[MONTH] == month)
        ]

    def get_monthly_budget_view(self, year: int, month: int) -> Optional[list[dict]]:
        """
        Compute budget rule usage view for a given month.

        Retrieves all budget rules and transaction data for the specified month,
        calculates current spending for each rule, and creates a structured view
        that can be used for display and analysis.

        Parameters
        ----------
        year : int
            The year to generate the budget view for.
        month : int
            The month to generate the budget view for (1-12).

        Returns
        -------
        Optional[list[dict]]
            A list of dictionaries, each containing:
            - rule: pd.Series - The budget rule
            - current_amount: float - Current spending for this rule
            - data: pd.DataFrame - Transactions matching this rule
            - allow_edit: bool - Whether this rule can be edited
            - allow_delete: bool - Whether this rule can be deleted
            Returns None if no rules exist for the specified month.
        """
        # TODO: split this function into smaller functions
        budget_rules = self.get_monthly_rules()
        bank_data = self.transactions_service.get_table_for_analysis("bank")
        credit_data = self.transactions_service.get_table_for_analysis("credit_card")
        all_data = pd.concat([credit_data, bank_data])

        # Only expenses (exclude income, liabilities, etc.)
        expenses = all_data.loc[
            ~all_data[self.transactions_service.transactions_repository.category_col]
            .isin([c.value for c in NonExpensesCategories])
        ].copy()
        expenses[self.transactions_service.transactions_repository.date_col] = pd.to_datetime(
            expenses[self.transactions_service.transactions_repository.date_col]
        )

        # Exclude project categories
        projects = budget_rules[
            budget_rules[YEAR].isnull() & budget_rules[MONTH].isnull()
        ][CATEGORY].unique()

        month_data = expenses.loc[
            (expenses[self.transactions_service.transactions_repository.date_col].dt.year == year) &
            (expenses[self.transactions_service.transactions_repository.date_col].dt.month == month) &
            ~expenses[self.transactions_service.transactions_repository.category_col].isin(projects)
        ]

        # Budget rules for selected month
        rules = budget_rules[(budget_rules[YEAR] == year) & (budget_rules[MONTH] == month)]
        if rules.empty:
            return None

        view = []

        # Total budget
        total_rule = rules[rules[CATEGORY] == TOTAL_BUDGET]
        if not total_rule.empty:
            total = month_data[self.transactions_service.transactions_repository.amount_col].sum() * -1
            view.append({
                "rule": total_rule.iloc[0],
                "current_amount": total,
                "data": month_data.copy(),
                "allow_edit": True,
                "allow_delete": False
            })
            rules = rules.loc[~rules.index.isin(total_rule.index)]

        # Per-rule breakdown
        remaining_data = month_data.copy()
        for _, rule in rules.iterrows():
            tags = rule[TAGS]
            cat_data = remaining_data[remaining_data[self.transactions_service.transactions_repository.category_col] == rule[CATEGORY]]

            if tags != [ALL_TAGS]:
                cat_data = cat_data[cat_data[self.transactions_service.transactions_repository.tag_col].isin(tags)]

            amt = cat_data[self.transactions_service.transactions_repository.amount_col].sum() * -1
            view.append({
                "rule": rule,
                "current_amount": amt,
                "data": cat_data.copy(),
                "allow_edit": True,
                "allow_delete": True
            })

            # Remove from pool
            remaining_data = remaining_data.loc[~remaining_data.index.isin(cat_data.index)]

        # Handle "Other Expenses"
        if not remaining_data.empty and not rules.empty and not total_rule.empty:
            total_alloc = rules[AMOUNT].sum()
            total_amt = total_rule.iloc[0][AMOUNT] - total_alloc
            view.append({
                "rule": pd.Series({
                    NAME: "Other Expenses",
                    AMOUNT: total_amt,
                    CATEGORY: "Other Expenses",
                    TAGS: "Other Expenses",
                    ID: f"{year}{month}_Other_Expenses"
                }),
                "current_amount": remaining_data[self.transactions_service.transactions_repository.amount_col].sum() * -1,
                "data": remaining_data,
                "allow_edit": False,
                "allow_delete": False
            })

        return view


class ProjectBudgetService(BudgetService):
    """
    Service for managing project-based budget rules and calculations.

    This class provides methods for creating, retrieving, updating, and
    deleting project budget rules. Projects are special categories with their
    own budget rules that span across months.
    """
    def get_all_rules(self) -> pd.DataFrame:
        rules = super().get_all_rules()
        rules = rules.loc[rules[YEAR].isnull() & rules[MONTH].isnull()]
        return rules

    def get_project_rules(self) -> pd.DataFrame:
        """Get all project budget rules (rules with null year and month)."""
        rules = self.budget_repository.read_all()
        if not rules.empty:
            rules = rules.loc[rules[YEAR].isnull() & rules[MONTH].isnull()]
            rules[TAGS] = rules[TAGS].apply(lambda x: x.split(";") if isinstance(x, str) else [])
        return rules

    def get_rules_for_project(self, category: str) -> pd.DataFrame:
        """Get all budget rules for a specific project category."""
        rules = self.get_project_rules()
        if not rules.empty:
            rules = rules.loc[rules[CATEGORY] == category]
        return rules

    def create_project(self, category: str, total_budget: float) -> None:
        """
        Create a new project budget with the specified category and total budget.

        Adds a new rule with ALL_TAGS to represent the total budget for the project.
        """
        self.budget_repository.add(
            name=TOTAL_BUDGET,
            amount=total_budget,
            category=category,
            tags=ALL_TAGS,
            month=None,
            year=None
        )

    def delete_project(self, category: str) -> None:
        """Delete all budget rules for a project."""
        self.budget_repository.delete_by_category(category)

    def delete_project_tag_rule(self, category: str, tag: str) -> None:
        """Delete a specific tag rule from a project."""
        self.budget_repository.delete_by_category_and_tags(category, tag)

    def update_project_rules(self, project: str, project_rules: pd.DataFrame) -> bool:
        """
        Update project rules to match available tags for the project category.

        Synchronizes the project budget rules with the current tags available for
        the project category. Adds rules for new tags and removes rules for tags
        that no longer exist.

        Parameters
        ----------
        project : str
            The name of the project to update rules for.
        project_rules : pd.DataFrame
            DataFrame containing the current project rules.

        Returns
        -------
        bool
            True if any updates were made, False otherwise.
        """
        cat_n_tags = self.categories_tags_service.get_categories_and_tags(copy=True)
        tags = cat_n_tags.get(project, [])
        existing_tags = project_rules[TAGS].tolist()
        existing_tags = [tag[0] if isinstance(tag, list) else tag for tag in existing_tags]

        updates = False
        for tag in tags:
            if tag not in existing_tags:
                self.add_rule(
                    category=project, name=tag, tags=tag, amount=1
                )
                updates = True

        for tag in existing_tags:
            if tag not in tags + [ALL_TAGS]:
                self.delete_project_tag_rule(project, tag)
                updates = True

        return updates

    def get_available_categories(self, budget_rules: pd.DataFrame) -> list[str]:
        """
        Get categories that are available to be used as projects.

        Returns a list of categories that are not already being used as projects.

        Parameters
        ----------
        budget_rules : pd.DataFrame
            DataFrame containing all budget rules.

        Returns
        -------
        list[str]
            List of category names that are available to be used as projects.
        """
        avail_cats = list(
            set(list(self.categories_tags_service.categories_and_tags.keys())) -
            set(self.get_project_names(budget_rules))
        )

        return avail_cats

    @staticmethod
    def get_project_names(budget_rules: pd.DataFrame) -> list[str]:
        """
        Get a list of all project names from the budget rules.

        Projects are identified as rules with null year and month values.

        Parameters
        ----------
        budget_rules : pd.DataFrame
            DataFrame containing all budget rules.

        Returns
        -------
        list[str]
            List of unique project category names.
        """
        return budget_rules.loc[
            (budget_rules[YEAR].isnull()) & (budget_rules[MONTH].isnull())
        ][CATEGORY].unique().tolist()

    @staticmethod
    def get_project_budget_rules(project: str | None, budget_rules: pd.DataFrame) -> pd.DataFrame | None:
        """
        Get all budget rules for a specific project.

        Parameters
        ----------
        project : str | None
            The name of the project to get rules for, or None.
        budget_rules : pd.DataFrame
            DataFrame containing all budget rules.

        Returns
        -------
        pd.DataFrame | None
            DataFrame containing only the rules for the specified project,
            or None if project is None.
        """
        if project is None:
            return None

        rules = budget_rules.loc[
            (budget_rules[CATEGORY] == project) &
            (budget_rules[YEAR].isnull()) &
            (budget_rules[MONTH].isnull())
        ]
        return rules

    def get_project_transactions(self, project: str) -> pd.DataFrame:
        """
        Get all transactions categorized under a specific project.

        Retrieves and combines transactions from both bank and credit card tables
        that are categorized under the specified project.

        Parameters
        ----------
        project : str
            The name of the project to get transactions for.

        Returns
        -------
        pd.DataFrame
            DataFrame containing all transactions for the specified project.
        """
        # Use the service layer instead of repository for getting analysis data
        bank_data = self.transactions_service.get_table_for_analysis("bank")
        credit_data = self.transactions_service.get_table_for_analysis("credit_card")
        all_data = pd.concat([credit_data, bank_data])
        transactions = all_data.loc[all_data[TransactionsTableFields.CATEGORY.value] == project]
        return transactions

