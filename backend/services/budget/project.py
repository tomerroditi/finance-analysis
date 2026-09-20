"""Project budget service — time-unbounded per-category project budgets."""

import pandas as pd

from backend.constants.budget import (
    ALL_TAGS,
    AMOUNT,
    CATEGORY,
    ID,
    IS_CLOSED,
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
from backend.errors import (
    EntityAlreadyExistsException,
    EntityNotFoundException,
    ValidationException,
)
from backend.services.budget.core import BudgetService
from backend.services.pending_refunds_service import (
    GROSS_AMOUNT_COLUMN,
    apply_refund_amount_adjustments,
    restore_gross_amounts,
)


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
        EntityAlreadyExistsException
            If a project for ``category`` already exists.
        ValidationException
            If ``category`` is not a known category, so no rules are written
            for a name that can't be tagged against.
        ValueError
            If ``category`` already has a monthly or yearly budget rule. A
            category can't be in both a project and a monthly/yearly budget.
        """
        if category in self.get_all_projects_names():
            raise EntityAlreadyExistsException(
                f"A project for the '{category}' category already exists."
            )
        if self.category_used_by_monthly_or_yearly(category):
            raise ValueError(
                f"The '{category}' category is already used by a monthly or "
                f"yearly budget. A category can't be in both a project and a "
                f"monthly/yearly budget."
            )
        # Resolve the tag list before writing anything: an unknown category
        # used to fail here *after* the total rule was persisted.
        all_tags = self.categories_tags_service.get_categories_and_tags(copy=True)
        if category not in all_tags:
            raise ValidationException(f"Unknown category '{category}'.")

        self.add_rule(
            name=TOTAL_BUDGET,
            amount=total_budget,
            category=category,
            tags=[ALL_TAGS],
            month=None,
            year=None,
        )

        for tag in all_tags[category]:
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
        if category not in self.get_all_projects_names():
            raise EntityNotFoundException(f"Project '{category}' not found")
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

    def is_project_closed(self, category: str) -> bool:
        """Whether ``category``'s project budget has been closed."""
        rules = self.get_all_rules()
        if rules.empty:
            return False
        return self._rules_are_closed(rules.loc[rules[CATEGORY] == category])

    def get_closed_projects_names(self) -> list[str]:
        """Names of the project categories that have been closed.

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

    def get_projects_status(self) -> list[dict]:
        """All projects with their closed flag, in one read.

        Returns
        -------
        list[dict]
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
            Transactions where category equals ``project``, with matched
            refunds netted against the purchases they repay and each row's
            pre-netting amount kept in :data:`GROSS_AMOUNT_COLUMN`.
        """
        all_data = self.transactions_service.get_data_for_analysis(
            include_split_parents
        )
        rows = all_data.loc[
            all_data[TransactionsTableFields.CATEGORY.value] == project
        ]
        # A project envelope reports what the project cost, net of refunds
        # matched to their purchase — the definition the monthly and yearly
        # envelopes and the dashboard already use. The gross amount rides
        # along so the transaction list underneath keeps real figures.
        adjustments = self.pending_refunds_service.get_refund_amount_adjustments(
            exclude_open=True
        )
        return apply_refund_amount_adjustments(
            rows, adjustments, keep_gross_in=GROSS_AMOUNT_COLUMN
        )

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
            - ``closed`` – whether the project has been marked finished.
        """
        rules = self.get_rules_for_project(project)
        # ``rules`` is consumed below (the anchor row is dropped out of it), so
        # the closed state is read off the full set before that happens.
        rules_for_state = rules
        transactions = self.get_project_transactions(project, include_split_parents)

        view = []

        # Total Project Rule
        total_rule = pd.DataFrame()
        if not rules.empty:
            total_rule = rules[rules[TAGS].apply(self._is_all_tags)]

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
                    "data": restore_gross_amounts(transactions_processed).to_dict(orient="records"),
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
                    "data": restore_gross_amounts(tag_txns_display).to_dict(orient="records"),
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
                    & (new_rule_df[PERIOD_TYPE] == PERIOD_PROJECT)
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
                        "data": restore_gross_amounts(group_display).to_dict(orient="records"),
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
