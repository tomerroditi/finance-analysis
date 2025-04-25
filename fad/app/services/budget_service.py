import pandas as pd
import sqlalchemy as sa

from typing import Optional
from ..data_access.budget_repository import MonthlyBudgetRepository, ProjectBudgetRepository
from fad.app.naming_conventions import NAME, AMOUNT, CATEGORY, TAGS, YEAR, MONTH, ALL_TAGS, ID, TOTAL_BUDGET, Tables, TransactionsTableFields, NonExpensesCategories

from ..utils.data import get_categories_and_tags, get_table, get_db_connection


class MonthlyBudgetService:
    @staticmethod
    def get_rules() -> pd.DataFrame:
        """
        Fetches all budget rules from the database.
        Returns:
            pd.DataFrame: DataFrame containing all budget rules.
        """
        conn = get_db_connection()
        return get_table(conn, Tables.BUDGET_RULES.value)

    @staticmethod
    def get_available_tags_for_each_category(budget_rules: pd.DataFrame) -> dict[str, list[str]]:
        cats_n_tags = get_categories_and_tags(copy=True)
        for _, rule in budget_rules.iterrows():
            used_tags = rule[TAGS].split(";")
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

    @staticmethod
    def copy_last_month_rules(year: int, month: int, budget_rules: pd.DataFrame) -> Optional[str]:
        """
        Copy budget rules from the previous month into the selected month.
        Returns:
            A message if successful or None if no rules found.
        """
        last_month = month - 1 if month != 1 else 12
        last_year = year if month != 1 else year - 1

        rules_to_copy = budget_rules[
            (budget_rules[YEAR] == last_year) & (budget_rules[MONTH] == last_month)
        ]

        if rules_to_copy.empty:
            return None

        MonthlyBudgetRepository.delete_rules_by_month(year, month)

        for _, rule in rules_to_copy.iterrows():
            MonthlyBudgetRepository.add_rule(
                name=rule[NAME],
                amount=rule[AMOUNT],
                category=rule[CATEGORY],
                tags=rule[TAGS],
                month=month,
                year=year
            )

        return f"Copied {len(rules_to_copy)} rules from {last_year}-{last_month}"

    @staticmethod
    def add_new_rule(year: int, month: int, budget_rules) -> (str, callable, tuple):
        """
        Render the 'Add New Rule' button, which opens the rule dialog when clicked.
        """
        from ..components.budget_overview import show_set_total_budget_rule_dialog, show_add_rule_dialog

        budget_rules = budget_rules.loc[
            (budget_rules[YEAR] == year) &
            (budget_rules[MONTH] == month)
            ]

        if budget_rules.empty:
            name = "Set Total Budget"
            func = show_set_total_budget_rule_dialog
            args = (year, month)
        else:
            name = "Add New Rule"
            func = show_add_rule_dialog
            args = (year, month, budget_rules)

        return name, func, args

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
        This function verifies the new values of the rule before updating it. the function prompts an error to the user in
        any of the following cases:
        - the amount is not a positive number
        - the new category is not selected
        - no tags are selected
        - the new name is not entered (empty)
        - the total budget is exceeded by the sum of all rules and the new rule amount
        - a rule with all tags is added to a category that already has rules with specific tags

        Parameters
        ----------
        budget_rules: pd.DataFrame
            the budget rules table which contains all (updated) rules
        amount: float
            the new amount of money available for the rule
        category: str
            the new category of the rule
        tags: list[str]
            the new tags of the rule
        name: str
            the new name of the rule
        year: int | float
            the year of the rule to edit. if float (nan), the rule is a project rule.
        month: int | float
            the month of the rule to edit. if float (nan), the rule is a project rule.
        id_: int | None
            the id of the rule to edit. if None, the rule is a new rule.

        Returns
        ------
        bool
            True if the inputs are valid, False otherwise
        str
            An error message if the inputs are invalid, empty string otherwise
        """
        if id_ is not None:
            rule = budget_rules.loc[budget_rules[ID] == id_].T.squeeze()
            # if no change just return
            if (rule[NAME] == name
                    and rule[AMOUNT] == amount
                    and rule[CATEGORY] == category
                    and rule[TAGS] == ";".join(tags)):
                return True, ""

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
            total_rules_amount = budget_rules[budget_rules[TAGS] != ALL_TAGS][AMOUNT].sum()
            if rule[TAGS] == ALL_TAGS:
                # updating the project total budget
                if amount < total_rules_amount:
                    return False, "The total budget must be greater than the sum of all other rules of the project"

            else:
                # updating a project rule with specific tag
                total_budget = budget_rules.loc[budget_rules[TAGS] == ALL_TAGS][AMOUNT].values[0]
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

    @staticmethod
    def get_monthly_budget_view(year: int, month: int) -> Optional[list[dict]]:
        """
        Computes budget rule usage view for a given month.

        Returns:
            List of dicts: each dict contains:
                - rule: pd.Series
                - current_amount: float
                - data: pd.DataFrame
                - allow_edit: bool
                - allow_delete: bool
        """
        budget_rules = MonthlyBudgetService.get_rules()
        # Fetch all transaction data
        conn = get_db_connection()
        bank_data = get_table(conn, Tables.BANK.value)
        credit_data = get_table(conn, Tables.CREDIT_CARD.value)
        all_data = pd.concat([credit_data, bank_data])

        # Only expenses (exclude income, liabilities, etc.)
        expenses = all_data.loc[
            ~all_data[TransactionsTableFields.CATEGORY.value]
            .isin([c.value for c in NonExpensesCategories])
        ].copy()
        expenses[TransactionsTableFields.DATE.value] = pd.to_datetime(
            expenses[TransactionsTableFields.DATE.value]
        )

        # Exclude project categories
        projects = budget_rules[
            budget_rules[YEAR].isnull() & budget_rules[MONTH].isnull()
        ][CATEGORY].unique()

        month_data = expenses.loc[
            (expenses[TransactionsTableFields.DATE.value].dt.year == year) &
            (expenses[TransactionsTableFields.DATE.value].dt.month == month) &
            ~expenses[TransactionsTableFields.CATEGORY.value].isin(projects)
        ]

        # Budget rules for selected month
        rules = budget_rules[(budget_rules[YEAR] == year) & (budget_rules[MONTH] == month)]
        if rules.empty:
            return None

        view = []

        # Total budget
        total_rule = rules[rules[CATEGORY] == TOTAL_BUDGET]
        if not total_rule.empty:
            total = month_data[TransactionsTableFields.AMOUNT.value].sum() * -1
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
            tags = rule[TAGS].split(";")
            cat_data = remaining_data[remaining_data[TransactionsTableFields.CATEGORY.value] == rule[CATEGORY]]

            if tags != ["ALL_TAGS"]:
                cat_data = cat_data[cat_data[TransactionsTableFields.TAG.value].isin(tags)]

            amt = cat_data[TransactionsTableFields.AMOUNT.value].sum() * -1
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
                "current_amount": remaining_data[TransactionsTableFields.AMOUNT.value].sum() * -1,
                "data": remaining_data,
                "allow_edit": False,
                "allow_delete": False
            })

        return view


class ProjectBudgetService:
    @staticmethod
    def get_rules() -> pd.DataFrame:
        """
        Fetches all budget rules from the database.
        Returns:
            pd.DataFrame: DataFrame containing all budget rules.
        """
        conn = get_db_connection()
        return get_table(conn, Tables.BUDGET_RULES.value)

    @staticmethod
    def create_project(category: str, total_budget: float):
        ProjectBudgetRepository.insert_project_rule(
            category=category,
            name=TOTAL_BUDGET,
            tags=ALL_TAGS,
            amount=total_budget
        )

    @staticmethod
    def delete_project(category: str):
        ProjectBudgetRepository.delete_project_rules(category)

    @staticmethod
    def get_project_names(budget_rules: pd.DataFrame) -> list[str]:
        return budget_rules.loc[
            (budget_rules[YEAR].isnull()) & (budget_rules[MONTH].isnull())
        ][CATEGORY].unique().tolist()

    @staticmethod
    def get_project_budget_view(project: str) -> tuple[pd.DataFrame, pd.DataFrame]:
        conn = get_db_connection()
        budget_rules = get_table(conn, Tables.BUDGET_RULES.value)
        rules = budget_rules.loc[
            (budget_rules[CATEGORY] == project) &
            (budget_rules[YEAR].isnull()) &
            (budget_rules[MONTH].isnull())
        ]

        bank = get_table(conn, Tables.BANK.value)
        credit = get_table(conn, Tables.CREDIT_CARD.value)
        all_data = pd.concat([credit, bank])
        expenses = all_data.loc[all_data[TransactionsTableFields.CATEGORY.value] == project]

        return rules, expenses

    @staticmethod
    def assure_tag_rule_integrity(project: str, project_rules: pd.DataFrame) -> bool:
        cat_n_tags = get_categories_and_tags(copy=True)
        tags = cat_n_tags.get(project, [])
        existing_tags = project_rules[TAGS].tolist()

        updates = False
        for tag in tags:
            if tag not in existing_tags:
                ProjectBudgetRepository.insert_project_rule(
                    category=project, name=tag, tags=tag, amount=1
                )
                updates = True

        for tag in existing_tags:
            if tag not in tags + [ALL_TAGS]:
                ProjectBudgetRepository.delete_project_tag_rule(project, tag)
                updates = True

        return updates

    @staticmethod
    def get_all_categories_with_tags() -> list[str]:
        return list(get_categories_and_tags(copy=True).keys())
