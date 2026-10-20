"""Project budget service — time-unbounded per-category project budgets."""

from typing import Any

import pandas as pd

from backend.constants.budget import (
    ALL_TAGS,
    AMOUNT,
    CATEGORY,
    ID,
    IS_CLOSED,
    MONTH,
    NAME,
    PERIOD_PROJECT,
    PERIOD_TYPE,
    TAGS,
    TOTAL_BUDGET,
    YEAR,
)
from backend.constants.tables import TransactionsTableFields
from backend.errors import (
    EntityAlreadyExistsException,
    EntityNotFoundException,
    ValidationException,
)
from backend.services.budget import ledger
from backend.services.budget.core import BudgetService
from backend.services.budget.rules import budgeted_categories
from backend.services.pending_refunds_service import GROSS_AMOUNT_COLUMN

#: Claim kind given to a split parent listed for display: never counted.
SPLIT_PARENT = "split_parent"


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
        EntityNotFoundException
            If no rules exist for the given project category.
        """
        rules = self.get_all_rules()
        if not rules.empty:
            rules = rules.loc[rules[CATEGORY] == category]
        if rules.empty:
            raise EntityNotFoundException(f"Project {category} not found")

        return rules

    def _require_project(self, category: str) -> None:
        """Raise when no project budget is named ``category``.

        Deleting an unknown project used to report success and updating one
        surfaced a raw error as a 500; every other delete in the API 404s on
        a missing entity.

        Parameters
        ----------
        category : str
            Project (category) name.

        Raises
        ------
        EntityNotFoundException
            If no project budget rules exist for ``category``.
        """
        if category not in self.get_all_projects_names():
            raise EntityNotFoundException(f"Project '{category}' not found")

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
        EntityAlreadyExistsException
            If a project for ``category`` already exists.
        ValidationException
            If ``category`` is not a known category, so no rules are written
            for a name that can't be tagged against.
        ValidationException
            If ``category`` already has a monthly or yearly budget rule (a
            category can't be in both a project and a monthly/yearly budget),
            or ``total_budget`` is not positive.
        """
        if category in self.get_all_projects_names():
            raise EntityAlreadyExistsException(
                f"A project for the '{category}' category already exists."
            )
        # Resolve the tag list before writing anything: an unknown category
        # used to fail here *after* the total rule was persisted.
        all_tags = self.categories_tags_service.get_categories_and_tags(copy=True)
        if category not in all_tags:
            raise ValidationException(f"Unknown category '{category}'.")

        self.rules.create(
            PERIOD_PROJECT, TOTAL_BUDGET, total_budget, category, [ALL_TAGS]
        )
        for tag in all_tags[category]:
            self.rules.insert(tag, 0, category, [tag], kind=PERIOD_PROJECT)

    def create_rule(
        self, name: str, amount: float, category: str, tags: str | list[str]
    ) -> None:
        """
        Add a rule to a project; see :func:`~backend.services.budget.rules.rule_error`.

        Parameters
        ----------
        name : str
            Human-readable label for the rule.
        amount : float
            The rule's share of the project's total (may be zero).
        category : str
            The project's category.
        tags : str or list[str]
            Tags the rule covers.

        Raises
        ------
        ValidationException
            If the rule fails validation — including when ``category`` has no
            project total to add it under.
        """
        self.rules.create(PERIOD_PROJECT, name, amount, category, tags)

    def update_project(self, category: str, total_budget: float) -> None:
        """
        Update the total budget amount for an existing project.

        Parameters
        ----------
        category : str
            Project category name.
        total_budget : float
            New overall spending limit for the project.

        Raises
        ------
        EntityNotFoundException
            If no project with ``category`` exists.
        ValidationException
            If ``total_budget`` fails rule validation.
        """
        self._require_project(category)
        rules = self.get_rules_for_project(category)
        total_rule = rules.loc[rules[TAGS].apply(self._is_all_tags)]
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

        Raises
        ------
        EntityNotFoundException
            If no project with ``category`` exists.
        """
        self._require_project(category)
        self.budget_repository.delete_by_category(category)

    def set_project_closed(self, category: str, closed: bool) -> None:
        """Mark a project as closed (finished) or reopen it.

        Closing is deliberately not a delete: the project keeps every rule and
        every transaction, and its own tab still shows the full history. What
        it loses is its place in the budget Overview — a finished renovation
        should stop being an envelope the current month is measured against.

        Parameters
        ----------
        category : str
            Project category name.
        closed : bool
            ``True`` closes the project, ``False`` reopens it.

        Raises
        ------
        EntityNotFoundException
            If no project budget rules exist for ``category``.
        """
        self._require_project(category)
        self.budget_repository.set_closed_by_category(category, closed)

    @staticmethod
    def _rules_are_closed(rules: pd.DataFrame) -> bool:
        """Whether a frame of one project's rules belongs to a closed project.

        Any flagged rule closes the project rather than all of them: closing
        writes the flag across the rules a project has at that moment, and
        :meth:`get_project_budget_view` mints a fresh zero-amount rule whenever
        a transaction carries a tag no rule covers yet. Requiring every rule to
        agree would let one such late row silently reopen the project.
        """
        if rules.empty or IS_CLOSED not in rules.columns:
            return False
        return bool(rules[IS_CLOSED].fillna(0).astype(int).max() == 1)

    def get_closed_projects_names(self) -> list[str]:
        """Return the names of the project categories that have been closed.

        Returns
        -------
        list[str]
            Category names whose project rules carry the closed flag.
        """
        rules = self.get_all_rules()
        if rules.empty:
            return []
        return [
            name
            for name, group in rules.groupby(CATEGORY)
            if self._rules_are_closed(group)
        ]

    def get_projects_status(self) -> list[dict[str, Any]]:
        """Return all projects with their closed flag, in one read.

        Returns
        -------
        list[dict[str, Any]]
            One ``{"name": str, "closed": bool}`` entry per project, so a
            caller listing projects does not need a second request to tell
            the finished ones apart.
        """
        rules = self.get_all_rules()
        if rules.empty:
            return []
        return [
            {"name": str(name), "closed": self._rules_are_closed(group)}
            for name, group in rules.groupby(CATEGORY)
        ]

    def get_project_transactions(
        self, project: str, include_split_parents: bool = False
    ) -> pd.DataFrame:
        """
        Get the rows a project owns, each with the per-tag rule that claimed it.

        Parameters
        ----------
        project : str
            Project category name.
        include_split_parents : bool, optional
            When ``True``, also list split parent transactions. They are for
            display only: their splits already carry the amount, so a parent
            keeps its own gross amount and never adds to a total.

        Returns
        -------
        pd.DataFrame
            The project's ledger rows (see :meth:`get_claims`) — amounts net
            of matched refunds, the pre-netting amount in
            :data:`GROSS_AMOUNT_COLUMN`.
        """
        claims = ledger.of_kind(self.get_claims(), ledger.KIND_PROJECT)
        rows = claims.loc[claims[TransactionsTableFields.CATEGORY.value] == project]
        if not include_split_parents:
            return rows

        all_data = self.transactions_service.get_data_for_analysis(
            include_split_parents=True
        )
        if "type" not in all_data.columns:
            return rows
        parents = all_data.loc[
            (all_data[TransactionsTableFields.CATEGORY.value] == project)
            & (all_data["type"] == "split_parent")
        ]
        if parents.empty:
            return rows
        parents = ledger.assign_claims(
            self._expense_rows(parents),
            self.get_rules_for_project(project),
            self.month_override_service.get_override_map(),
        )
        parents[ledger.CLAIM_KIND] = SPLIT_PARENT
        parents[GROSS_AMOUNT_COLUMN] = parents[TransactionsTableFields.AMOUNT.value]
        return pd.concat([rows, parents])

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
        claimed = budgeted_categories(self.rules.all())
        return [
            cat
            for cat in self.categories_tags_service.get_categories_and_tags(copy=True)
            if cat not in current_projects and cat not in claimed
        ]

    def get_project_budget_view(
        self, project: str, include_split_parents: bool = False
    ) -> dict[str, Any]:
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
            - ``closed`` – whether the project has been marked finished.
        """
        rules = self.get_rules_for_project(project)
        # ``rules`` is consumed below (the anchor row is dropped out of it), so
        # the closed state is read off the full set before that happens.
        rules_for_state = rules
        listed = self.get_project_transactions(project, include_split_parents)
        listed = listed.where(pd.notnull(listed), None)
        counted = listed.loc[listed[ledger.CLAIM_KIND] != SPLIT_PARENT]
        total_spent = ledger.spent(counted)

        view = []
        if not rules.empty:
            total_rule = rules[rules[TAGS].apply(self._is_all_tags)]
            if not total_rule.empty:
                view.append(
                    {
                        "rule": total_rule.iloc[0].to_dict(),
                        "current_amount": total_spent,
                        "data": ledger.transaction_records(listed),
                        "allow_edit": True,
                        "allow_delete": False,
                    }
                )
                rules = rules.drop(total_rule.index)

        for _, rule in rules.iterrows():
            view.append(
                {
                    "rule": rule.to_dict(),
                    "current_amount": ledger.spent(ledger.of_rule(counted, rule[ID])),
                    "data": ledger.transaction_records(
                        ledger.of_rule(listed, rule[ID])
                    ),
                    "allow_edit": True,
                    "allow_delete": True,
                }
            )

        # A tag no rule names yet mints its own zero-budget rule, so every
        # shekel of the project shows under some tag.
        unmatched = listed.loc[listed[ledger.CLAIM_RULE_ID].isna()]
        if not unmatched.empty:
            groups = list(unmatched.groupby(TransactionsTableFields.TAG.value))
            # Create all missing zero-amount rules first, then re-read the
            # rules table once — instead of a full read after every insert.
            for tag, _group in groups:
                self.rules.insert(tag, 0, project, [tag], kind=PERIOD_PROJECT)
            new_rule_df = self.rules.of_kind(PERIOD_PROJECT)

            for tag, group in groups:
                new_rule = new_rule_df[
                    (new_rule_df[CATEGORY] == project) & (new_rule_df[NAME] == tag)
                ]
                if not new_rule.empty:
                    rule_dict = new_rule.iloc[0].to_dict()
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
                        "current_amount": ledger.spent(
                            group.loc[group[ledger.CLAIM_KIND] != SPLIT_PARENT]
                        ),
                        "data": ledger.transaction_records(group),
                        "allow_edit": True,
                        "allow_delete": True,
                    }
                )

        return {
            "name": project,
            "rules": view,
            "total_spent": total_spent,
            "closed": self._rules_are_closed(rules_for_state),
        }
