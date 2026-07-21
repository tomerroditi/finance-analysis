"""Project budget service — time-unbounded per-category project budgets."""

import pandas as pd

from backend.constants.budget import (
    ALL_TAGS,
    AMOUNT,
    CATEGORY,
    ID,
    MONTH,
    NAME,
    PERIOD_MONTHLY,
    PERIOD_PROJECT,
    PERIOD_TYPE,
    PERIOD_YEARLY,
    TAGS,
    TOTAL_BUDGET,
    YEAR,
)
from backend.constants.tables import TransactionsTableFields
from backend.errors import EntityNotFoundException
from backend.services.budget.core import BudgetService


class ProjectBudgetService(BudgetService):
    """Service for managing project-based budget rules."""

    def get_all_rules(self) -> pd.DataFrame:
        """Get all project budget rules (period_type == 'project')."""
        rules = super().get_all_rules()
        if rules.empty:
            return rules
        return rules.loc[rules[PERIOD_TYPE] == PERIOD_PROJECT].drop(
            columns=[YEAR, MONTH]
        )

    def get_rules_for_project(self, category: str) -> pd.DataFrame:
        """
        Get all budget rules for a specific project category.

        Parameters
        ----------
        category : str
            Project category name.

        Returns
        -------
        pd.DataFrame
            Budget rules for the project.

        Raises
        ------
        ValueError
            If no rules exist for the given project category.
        """
        rules = self.get_all_rules()
        if not rules.empty:
            rules = rules.loc[rules[CATEGORY] == category]
        if rules.empty:
            raise ValueError(f"Project {category} not found")

        return rules

    def create_project(self, category: str, total_budget: float) -> None:
        """
        Create a new project budget with a total rule and per-tag sub-rules.

        Adds a ``Total Budget`` rule for the category and individual zero-amount
        rules for every tag in the category.

        Parameters
        ----------
        category : str
            Project category name (must already exist in categories config).
        total_budget : float
            Overall spending limit for the project.

        Raises
        ------
        ValueError
            If ``category`` already has a monthly or yearly budget rule. A
            category can't be in both a project and a monthly/yearly budget.
        """
        if self.category_used_by_monthly_or_yearly(category):
            raise ValueError(
                f"The '{category}' category is already used by a monthly or "
                f"yearly budget. A category can't be in both a project and a "
                f"monthly/yearly budget."
            )

        self.add_rule(
            name=TOTAL_BUDGET,
            amount=total_budget,
            category=category,
            tags=[ALL_TAGS],
            month=None,
            year=None,
        )

        tags = self.categories_tags_service.get_categories_and_tags(copy=True)
        tags = tags[category]
        for tag in tags:
            self.add_rule(
                name=tag, amount=0, category=category, tags=[tag], month=None, year=None
            )

    def update_project(self, category: str, total_budget: float) -> None:
        """
        Update the total budget amount for an existing project.

        Parameters
        ----------
        category : str
            Project category name.
        total_budget : float
            New overall spending limit for the project.
        """
        rules = self.get_rules_for_project(category)
        total_rule = rules.loc[rules[TAGS].apply(lambda x: x == [ALL_TAGS])]
        if total_rule.empty:
            raise EntityNotFoundException(
                f"No total budget rule found for project '{category}'"
            )
        rule_id = int(total_rule.iloc[0][ID])
        self.update_rule(rule_id, amount=total_budget)

    def delete_project(self, category: str) -> None:
        """
        Delete all budget rules for a project category.

        Parameters
        ----------
        category : str
            Project category name whose rules should be deleted.
        """
        self.budget_repository.delete_by_category(category)

    def delete_project_tag_rule(self, category: str, tag: str) -> None:
        """
        Delete a specific tag rule from a project.

        Parameters
        ----------
        category : str
            Project category name.
        tag : str
            Tag whose budget rule should be deleted.
        """
        self.budget_repository.delete_by_category_and_tags(category, tag)

    def get_project_transactions(
        self, project: str, include_split_parents: bool = False
    ) -> pd.DataFrame:
        """
        Get all transactions categorised under a project category.

        Parameters
        ----------
        project : str
            Project category name.
        include_split_parents : bool, optional
            When ``True``, include split parent transactions. Default is ``False``.

        Returns
        -------
        pd.DataFrame
            Transactions where category equals ``project``.
        """
        all_data = self.transactions_service.get_data_for_analysis(
            include_split_parents
        )
        return all_data.loc[all_data[TransactionsTableFields.CATEGORY.value] == project]

    def get_all_projects_names(self) -> list[str]:
        """
        Get the names of all project categories that have budget rules.

        Returns
        -------
        list[str]
            Unique category names from all project budget rules.
        """
        rules = self.get_all_rules()
        return rules[CATEGORY].unique().tolist()

    def get_available_categories_for_new_project(self) -> list[str]:
        """
        Get categories that can be used for a new project (not already tracked).

        Returns
        -------
        list[str]
            Category names from the categories config that are not already
            used as project budget categories, and do not already have a
            monthly or yearly budget rule.
        """
        current_projects = self.get_all_projects_names()
        # One rules read + set membership instead of a full budget_rules read
        # per candidate category (category_used_by_monthly_or_yearly re-reads
        # the table on every call).
        rules = BudgetService.get_all_rules(self)
        if rules.empty:
            claimed: set[str] = set()
        else:
            claimed = set(
                rules.loc[
                    rules[PERIOD_TYPE].isin([PERIOD_MONTHLY, PERIOD_YEARLY]),
                    CATEGORY,
                ]
            ) - {TOTAL_BUDGET}
        return [
            cat
            for cat in self.categories_tags_service.get_categories_and_tags(
                copy=True
            ).keys()
            if cat not in current_projects and cat not in claimed
        ]

    def get_project_budget_view(
        self, project: str, include_split_parents: bool = False
    ) -> dict:
        """
        Get project details including rules and transactions.

        Matches project transactions to budget rules. Any transactions whose
        tag does not match an existing rule automatically trigger creation of
        a new zero-budget rule for that tag (side-effect for new tags).

        Parameters
        ----------
        project : str
            Project category name.
        include_split_parents : bool, optional
            When ``True``, include split parent transactions. Default is ``False``.

        Returns
        -------
        dict
            Dictionary with keys:

            - ``name`` – project category name.
            - ``rules`` – list of rule view dicts (same shape as ``get_monthly_budget_view``).
            - ``total_spent`` – total amount spent on the project.
        """
        rules = self.get_rules_for_project(project)
        transactions = self.get_project_transactions(project, include_split_parents)

        view = []

        # Total Project Rule
        total_rule = pd.DataFrame()
        if not rules.empty:
            # Find where tags == [ALL_TAGS] (handle case sensitivity)
            total_rule = rules[
                rules[TAGS].apply(
                    lambda x: [t.lower() for t in x] == [ALL_TAGS.lower()]
                )
            ]

        # Ensure transactions is JSON serializable (handle NaNs)
        transactions_processed = transactions.where(pd.notnull(transactions), None)

        # Exclude split_parent transactions from total calculation
        if "type" in transactions.columns:
            non_parent_txns = transactions[transactions["type"] != "split_parent"]
        else:
            non_parent_txns = transactions
        total_spent = non_parent_txns[TransactionsTableFields.AMOUNT.value].sum() * -1

        if not total_rule.empty:
            view.append(
                {
                    "rule": total_rule.iloc[0].to_dict(),
                    "current_amount": total_spent,
                    "data": transactions_processed.to_dict(orient="records"),
                    "allow_edit": True,
                    "allow_delete": False,
                }
            )
            rules = rules.drop(total_rule.index)

        # Track transactions that have been matched to a rule
        matched_txns_indices = set()

        # Per tag rules
        for _, rule in rules.iterrows():
            tags = rule[TAGS]
            # Filter transactions for these tags using original DataFrame for calculation
            tag_txns_orig = transactions[
                transactions[TransactionsTableFields.TAG.value].isin(tags)
            ]

            # Record indices of matched transactions
            matched_txns_indices.update(tag_txns_orig.index)

            # Exclude split_parent transactions from spent calculation
            if "type" in tag_txns_orig.columns:
                tag_txns_for_calc = tag_txns_orig[
                    tag_txns_orig["type"] != "split_parent"
                ]
            else:
                tag_txns_for_calc = tag_txns_orig
            spent = tag_txns_for_calc[TransactionsTableFields.AMOUNT.value].sum() * -1

            # Filter processed transactions for display
            tag_txns_display = transactions_processed[
                transactions_processed[TransactionsTableFields.TAG.value].isin(tags)
            ]

            view.append(
                {
                    "rule": rule.to_dict(),
                    "current_amount": spent,
                    "data": tag_txns_display.to_dict(orient="records"),
                    "allow_edit": True,
                    "allow_delete": True,
                }
            )

        # Handle unmatched transactions ("Other" or random tags)
        unmatched_txns = transactions.loc[
            ~transactions.index.isin(matched_txns_indices)
        ]

        if not unmatched_txns.empty:
            groups = list(
                unmatched_txns.groupby(TransactionsTableFields.TAG.value)
            )
            # Create all missing zero-amount rules first, then re-read the
            # rules table once — instead of a full read after every insert.
            for tag, _group in groups:
                self.add_rule(
                    name=tag,
                    amount=0,
                    category=project,
                    tags=[tag],
                    month=None,
                    year=None,
                )
            new_rule_df = self.budget_repository.read_all()

            for tag, group in groups:
                if "type" in group.columns:
                    group_for_calc = group[group["type"] != "split_parent"]
                else:
                    group_for_calc = group

                spent = group_for_calc[TransactionsTableFields.AMOUNT.value].sum() * -1

                group_display = transactions_processed.loc[group.index]

                new_rule = new_rule_df[
                    (new_rule_df[CATEGORY] == project)
                    & (new_rule_df[YEAR].isnull())
                    & (new_rule_df[MONTH].isnull())
                    & (new_rule_df[NAME] == tag)
                ]

                rule_dict = {}
                if not new_rule.empty:
                    r = new_rule.iloc[0]
                    rule_dict = r.to_dict()
                    if isinstance(rule_dict[TAGS], str):
                        rule_dict[TAGS] = rule_dict[TAGS].split(";")
                else:
                    rule_dict = {
                        NAME: tag,
                        AMOUNT: 0,
                        CATEGORY: project,
                        TAGS: [tag],
                        ID: 0,
                    }

                view.append(
                    {
                        "rule": rule_dict,
                        "current_amount": spent,
                        "data": group_display.to_dict(orient="records"),
                        "allow_edit": True,
                        "allow_delete": True,
                    }
                )

        return {"name": project, "rules": view, "total_spent": total_spent}
