import pandas as pd
import streamlit as st

from fad.app.components.month_selector import (
    select_current_month,
    select_previous_month,
    select_next_month,
    select_custom_month
)

from fad.app.components.rule_based_tagging_components import RuleBasedTaggingComponent
from fad.app.services.budget_service import MonthlyBudgetService, ProjectBudgetService, BudgetService
from fad.app.services.tagging_service import CategoriesTagsService
from fad.app.naming_conventions import TransactionsTableFields, NAME, CATEGORY, TAGS, AMOUNT, ID, TOTAL_BUDGET, \
    ALL_TAGS, YEAR, MONTH, cc_providers, bank_providers

class BudgetUI:
    """
    Base class for budget UI components.
    """
    def __init__(self):
        self.budget_rules: pd.DataFrame = pd.DataFrame()
        self.budget_service = BudgetService()
        self.monthly_budget_service = MonthlyBudgetService()
        self.tagging_service = CategoriesTagsService()

    def render_rule_ui_window(
        self,
        rule: pd.Series,
        curr_amount: float,
        raw_data: pd.DataFrame,
        allow_edit: bool = True,
        allow_delete: bool = True
    ) -> None:
        expand_col, name_col, bar_col, edit_col, delete_col = st.columns([1, 4, 12, 2, 2])

        # Info label
        if rule[CATEGORY] == TOTAL_BUDGET:
            help_txt = "Total amount of money available for the month"
        elif rule[CATEGORY] == "Other Expenses":
            help_txt = "Expenses not covered by any other rule"
        else:
            help_txt = f"{rule[CATEGORY]}: {', '.join(rule[TAGS])}"
        name_col.markdown(f"### {rule[NAME]}", unsafe_allow_html=True, help=help_txt)

        # Budget bar
        total_amount = rule[AMOUNT]
        perc = max((curr_amount / total_amount) * 100, 0)
        bar_col.html(
            f"""
            <div style="width: 100%; background-color: #f3f3f3; border-radius: 10px; box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1); padding: 5px; position: relative;">
                <div style="position: absolute; left: 15px; top: 50%; transform: translateY(-50%); font-weight: bold; color: black;">
                    {curr_amount:.2f} / {total_amount}
                </div>
                <div style="width: {min(perc, 100)}%; background-color: {'#4caf50' if perc < 90 else '#ffeb3b' if perc <= 100 else '#f44336'}; height: 30px; border-radius: 8px; text-align: center; color: white; line-height: 30px; transition: width 0.4s ease;">
                </div>
            </div>
            """
        )

        # Expandable raw data with editable option
        if expand_col.toggle("Expand", key=f"expand_{rule[ID]}", label_visibility="collapsed"):
            # Use st.dataframe with row selection
            sorted_data = raw_data.sort_values(by=[TransactionsTableFields.DATE.value], ascending=False).reset_index(drop=True)
            event = st.dataframe(
                sorted_data,
                column_order=[
                    TransactionsTableFields.PROVIDER.value,
                    TransactionsTableFields.ACCOUNT_NAME.value,
                    TransactionsTableFields.ACCOUNT_NUMBER.value,
                    TransactionsTableFields.DATE.value,
                    TransactionsTableFields.DESCRIPTION.value,
                    TransactionsTableFields.AMOUNT.value,
                    TransactionsTableFields.CATEGORY.value,
                    TransactionsTableFields.TAG.value,
                    TransactionsTableFields.STATUS.value,
                    TransactionsTableFields.ID.value
                ],
                key=f"raw_data_table_{rule[ID]}",
                selection_mode="single-row",
                on_select="rerun"
            )
            # Editable section: show editor if a row is selected
            selected_rows = event["selection"]["rows"] if "selection" in event else []
            if selected_rows:
                idx = selected_rows[0]
                row = sorted_data.iloc[idx]
                # Use the new rule-based tagging component for comprehensive transaction editing
                rule_based_tagger = RuleBasedTaggingComponent()
                provider = row.get(TransactionsTableFields.PROVIDER.value)
                if provider in cc_providers:
                    service = "credit_card"
                elif provider in bank_providers:
                    service = "bank"
                else:
                    raise ValueError(f"Unknown provider: {provider}")

                # Render the comprehensive transaction tagger interface
                rule_based_tagger.render_transaction_tagger(row, service)

        # Buttons
        edit_col.button(
            "Edit",
            key=f"edit_{rule[ID]}_button",
            on_click=self.show_edit_rule_dialog,
            args=(rule,),
            use_container_width=True,
            disabled=not allow_edit
        )

        delete_col.button(
            "Delete",
            key=f"delete_{rule[ID]}_submit",
            on_click=self.show_delete_rule_dialog,
            args=(rule[ID],),
            use_container_width=True,
            disabled=not allow_delete
        )

    @st.dialog("Are you sure you want to delete this rule?")
    def show_delete_rule_dialog(self, rule_id: int) -> None:
        """
        Simple confirmation dialog to delete a rule.
        """
        if st.button("Yes"):
            self.budget_service.budget_repository.delete_rule(rule_id)
            st.success("Rule deleted.")
            st.rerun()
        if st.button("No"):
            st.rerun()

    @st.dialog("Edit Rule")
    def show_edit_rule_dialog(self, rule: pd.Series) -> None:
        """
        Modal UI for editing a budget rule.
        """
        if rule[CATEGORY] != TOTAL_BUDGET:
            name, category, tags = self._edit_rule_ui(rule)
        else:
            name = rule[NAME]
            category = rule[CATEGORY]
            tags = rule[TAGS]

        amount = st.number_input("Amount", value=rule[AMOUNT], key=f"edit_{rule[ID]}_amount")

        if st.button("Update Rule", key=f"edit_{rule[ID]}_submit"):
            is_valid, msg = self.budget_service.validate_rule_inputs(
                self.budget_rules, name, category, tags, amount,
                rule[YEAR], rule[MONTH], rule[ID]
            )
            if not is_valid:
                st.error(msg)
                return

            self.budget_service.update_rule(rule[ID], name=name, amount=amount, category=category, tags=tags)
            st.success("Rule updated.")
            st.rerun()

    def _edit_rule_ui(self, rule: pd.Series) -> tuple[str, str, list[str]]:
        cat_n_tags = self.tagging_service.get_categories_and_tags(copy=True)
        is_project = pd.isnull(rule[YEAR]) and pd.isnull(rule[MONTH])

        name = st.text_input("Name", rule[NAME], key=f"edit_{rule[ID]}_name", disabled=is_project)
        category = st.selectbox(
            "Category", list(cat_n_tags.keys()),
            index=list(cat_n_tags.keys()).index(rule[CATEGORY]),
            key=f"edit_{rule[ID]}_category",
            disabled=is_project
        )

        tags = st.multiselect(
            "Tags", [ALL_TAGS] + cat_n_tags.get(category, []),
            default=rule[TAGS] if category == rule[CATEGORY] else [],
            key=f"edit_{rule[ID]}_tags",
            disabled=is_project
        )

        if ALL_TAGS in tags and tags != [ALL_TAGS]:
            st.warning(f"If {ALL_TAGS} is selected, no other tags should be selected.")
            tags = [ALL_TAGS]

        return name, category, tags


class MonthlyBudgetUI(BudgetUI):
    """
    UI for the monthly budget overview.
    """
    def __init__(self):
        super().__init__()
        self.monthly_budget_service = MonthlyBudgetService()
        self.project_budget_service = ProjectBudgetService()
        self.budget_rules = self.monthly_budget_service.get_all_rules()
        self.year = st.session_state.setdefault("year", pd.Timestamp.now().year)
        self.month = st.session_state.setdefault("month", pd.Timestamp.now().month)
        self.month_rules = self.monthly_budget_service.get_month_rules(self.year, self.month, self.budget_rules)

    def set_month(self, year: int, month: int) -> None:
        self.year = year
        self.month = month
        self.month_rules = self.monthly_budget_service.get_month_rules(year, month, self.budget_rules)

    def select_month(self):
        curr_month_col, previous_month_col, next_month_col, history_col = st.columns([1, 1, 1, 1])
        with curr_month_col:
            select_current_month()
        with previous_month_col:
            select_previous_month()
        with next_month_col:
            select_next_month()
        with history_col:
            st.button(
                "Custom Month",
                on_click=select_custom_month,
                key="select_custom_month_budget",
                use_container_width=True
            )
        self.set_month(st.session_state.get("year"), st.session_state.get("month"))

    def add_or_copy_rules_ui(self) -> None:
        if self.month_rules.empty:
            button_name = "Set Total Budget"
            func = self.show_set_total_budget_rule_dialog
        else:
            button_name = "Add New Rule"
            func = self.show_add_rule_dialog

        add_rule_col, copy_rules_col, _ = st.columns([1, 1, 2])
        with add_rule_col:
            st.button(
                button_name,
                on_click=func,
                key="add_new_rule_button",
                use_container_width=True
            )

        if copy_rules_col.button("Copy last month's rules", use_container_width=True):
            msg = self.monthly_budget_service.copy_last_month_rules(self.year, self.month, self.budget_rules)
            if msg:
                st.success(msg)
            else:
                st.info("No rules found in last month.")
            st.rerun()

    @st.dialog("Add New Rule")
    def show_add_rule_dialog(self) -> None:
        st.markdown(
            "***You cannot use the same category and tag in two different rules. "
            "Only available tags are shown for selection.***"
        )

        # Calculate available tags per category
        available_tags_by_category = self.monthly_budget_service.get_available_tags_for_each_category(self.budget_rules)

        name = st.text_input("Name", key="new_rule_name")
        category = st.selectbox("Category", available_tags_by_category.keys(), key="new_rule_category", index=None)

        tag_options = [ALL_TAGS] + available_tags_by_category.get(category, [])
        tags = st.multiselect("Tags", tag_options, key="new_rule_tags")
        amount = st.number_input("Amount", key="new_rule_amount", value=1.0, step=0.1, min_value=0.01)

        if ALL_TAGS in tags and tags != [ALL_TAGS]:
            st.warning(f"If {ALL_TAGS} is selected, no other tags should be selected. Deselecting specific tags.")
            tags = [ALL_TAGS]

        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("Add Rule"):
            is_valid, message = self.monthly_budget_service.validate_rule_inputs(
                self.budget_rules, name, category, tags, amount, self.year, self.month, id_=None
            )
            if not is_valid:
                st.error(message)
                st.stop()

            self.monthly_budget_service.monthly_budget_repository.add_rule(
                name=name,
                amount=amount,
                category=category,
                tags=";".join(tags),
                month=self.month,
                year=self.year
            )
            st.success("Rule added successfully.")
            st.rerun()

    @st.dialog("Set Total Budget")
    def show_set_total_budget_rule_dialog(self) -> None:
        # add a total budget rule, this could not be deleted hence if curr rules are not empty it must already exist
        st.markdown("Before adding new budget allocation, please set your total budget")
        col_input, col_set = st.columns([3, 1])
        total_budget = col_input.number_input(TOTAL_BUDGET, key="total_budget_input", label_visibility="hidden",
                                              value=1)
        if total_budget <= 0:
            st.error("Total budget must be a positive number")

        col_set.markdown("<br>", unsafe_allow_html=True)
        if col_set.button("Set Total Budget", key="set_total_budget_button", use_container_width=True):
            self.monthly_budget_service.monthly_budget_repository.add_rule(
                name=TOTAL_BUDGET,
                amount=total_budget,
                category=TOTAL_BUDGET,
                tags=TOTAL_BUDGET,
                month=self.month,
                year=self.year
            )
            st.rerun()

    def monthly_budget_overview(self) -> None:
        """
        This function creates a UI for viewing the budget overview of the selected month. expenses are fetched from the
        database based on the selected month view (project expenses are excluded). the budget rules of the selected month
        view are fetched and displayed in the UI. a window of other expenses is added in case we have expenses not covered
        by any rule. the UI allows the user to edit and delete the rules as well.
        """
        st.title(f"Budget of: {self.year}-{self.month}")
        view = self.monthly_budget_service.get_monthly_budget_view(self.year, self.month)
        if view is None:
            st.warning("No budget rules for the selected month")
            return

        for entry in view:
            self.render_rule_ui_window(
                rule=entry["rule"],
                curr_amount=entry["current_amount"],
                raw_data=entry["data"],
                allow_edit=entry["allow_edit"],
                allow_delete=entry["allow_delete"]
            )

        self._render_project_transactions_section()

    def _render_project_transactions_section(self) -> None:
        """
        Render a separate section for project-related transactions that are excluded from the monthly budget.
        """
        project_transactions = self.monthly_budget_service.get_monthly_project_transactions(self.year, self.month)

        if project_transactions is not None and not project_transactions.empty:
            st.markdown("---")
            st.markdown("### 📋 Project Transactions (Excluded from Monthly Budget)")
            st.info(f"These transactions are related to project budgets and are not included in the monthly budget calculations above.")

            # Calculate total project spending for the month
            total_project_spending = project_transactions[TransactionsTableFields.AMOUNT.value].sum() * -1

            # Display summary
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total Project Spending", f"{total_project_spending:.2f}")
            with col2:
                st.metric("Number of Transactions", len(project_transactions))

            # Group by project category for better organization
            project_categories = project_transactions.groupby(TransactionsTableFields.CATEGORY.value)

            for category, category_data in project_categories:
                category_spending = category_data[TransactionsTableFields.AMOUNT.value].sum() * -1

                st.title(f"{category} - {category_spending:.2f} ({len(category_data)} transactions)")
                # Display transactions with selection capability
                sorted_data = category_data.sort_values(by=[TransactionsTableFields.DATE.value], ascending=False).reset_index(drop=True)
                event = st.dataframe(
                    sorted_data,
                    column_order=[
                        TransactionsTableFields.PROVIDER.value,
                        TransactionsTableFields.ACCOUNT_NAME.value,
                        TransactionsTableFields.ACCOUNT_NUMBER.value,
                        TransactionsTableFields.DATE.value,
                        TransactionsTableFields.DESCRIPTION.value,
                        TransactionsTableFields.AMOUNT.value,
                        TransactionsTableFields.CATEGORY.value,
                        TransactionsTableFields.TAG.value,
                        TransactionsTableFields.STATUS.value,
                        TransactionsTableFields.ID.value
                    ],
                    key=f"project_transactions_{category}_{self.year}_{self.month}",
                    selection_mode="single-row",
                    on_select="rerun"
                )

                # Show transaction editor if a row is selected
                selected_rows = event["selection"]["rows"] if "selection" in event else []
                if selected_rows:
                    idx = selected_rows[0]
                    row = sorted_data.iloc[idx]
                    # Use the new rule-based tagging component for comprehensive transaction editing
                    rule_based_tagger = RuleBasedTaggingComponent()
                    provider = row.get(TransactionsTableFields.PROVIDER.value)
                    if provider in cc_providers:
                        service = "credit_card"
                    elif provider in bank_providers:
                        service = "bank"
                    else:
                        service = "bank"  # Default fallback

                    rule_based_tagger.render_transaction_tagger(row, service)
        else:
            projects = self.project_budget_service.get_all_projects_names()
            if len(projects) > 0:
                st.markdown("---")
                st.markdown("### 📋 Project Transactions (Excluded from Monthly Budget)")
                st.info(f"No project transactions found for {self.year}-{self.month}. Active projects: {', '.join(projects)}")

class ProjectBudgetUI(BudgetUI):
    """
    UI for the project budget overview.
    """
    def __init__(self):
        super().__init__()
        self.project_budget_service = ProjectBudgetService()
        self.budget_rules = self.project_budget_service.get_all_rules()
        self.project_name = None
        self.project_rules = None

    def set_project_name(self, project_name: str) -> None:
        self.project_name = project_name
        self.project_rules = self.project_budget_service.get_project_budget_rules(project_name, self.budget_rules)

    def project_budget_overview(self) -> None:
        """
        Render full project-specific budget UI.
        """
        if self.project_name is None:
            st.warning("No project selected.")
            return

        project_transactions = self.project_budget_service.get_project_transactions(self.project_name)
        updated = self.project_budget_service.update_project_rules(self.project_name, self.project_rules)
        if updated:
            st.rerun()

        # Render Total Budget rule
        total_rule = self.project_rules[self.project_rules[TAGS].isin([[ALL_TAGS]])]
        total_spent = project_transactions[TransactionsTableFields.AMOUNT.value].sum() * -1
        if not total_rule.empty:
            self.render_rule_ui_window(
                rule=total_rule.iloc[0],
                curr_amount=total_spent,
                raw_data=project_transactions,
                allow_edit=True,
                allow_delete=False
            )

        # Render per-tag rules
        for _, rule in self.project_rules[~self.project_rules[TAGS].isin([[ALL_TAGS]])].iterrows():
            tag: list[str] = rule[TAGS]
            tag_data = project_transactions[project_transactions[TransactionsTableFields.TAG.value].isin(tag)]
            tag_spent = tag_data[TransactionsTableFields.AMOUNT.value].sum() * -1

            self.render_rule_ui_window(
                rule=rule,
                curr_amount=tag_spent,
                raw_data=tag_data,
                allow_edit=True,
                allow_delete=False
            )

    def project_selector(self):
        """
        Dropdown selector for choosing a project.
        """
        projects = self.project_budget_service.get_project_names(self.budget_rules)
        if not projects:
            st.info("No existing projects.")
            return None

        self.set_project_name(st.selectbox("Select Project", projects, key="project_selection"))

    def project_budget_buttons_bar(self):
        col_select, col_add, col_delete = st.columns([8, 1, 1])
        with col_select:
            self.project_selector()
        with col_add:
            st.markdown("<br>", unsafe_allow_html=True)
            st.button(
                "New project",
                on_click=self.show_add_project_dialog,
                use_container_width=True,
                key="add_new_budget_project"
            )
        with col_delete:
            st.markdown("<br>", unsafe_allow_html=True)
            st.button(
                "Delete project",
                on_click=self.show_delete_project_dialog,
                disabled=self.project_name is None,
                use_container_width=True,
                key="delete_budget_project"
            )

    @st.dialog("Add New Project")
    def show_add_project_dialog(self) -> None:
        """
        UI + logic for creating a new project.
        """
        available_categories = self.project_budget_service.get_available_categories(self.budget_rules)
        if not available_categories:
            st.warning("All categories already assigned to projects.")
            return

        category = st.selectbox("Select Project Category", available_categories, key="new_project_category", index=None)
        col_input, col_set = st.columns([3, 1])
        total_budget = col_input.number_input("Set Total Budget", value=1.0, min_value=0.01, step=1.0)

        if total_budget <= 0:
            st.error("Total budget must be a positive number")

        col_set.markdown("<br>", unsafe_allow_html=True)
        if col_set.button("Create", key="create_project_button", use_container_width=True):
            self.project_budget_service.create_project(category, total_budget)
            self.set_project_name(category)
            st.session_state["project_selection"] = category
            st.success(f"Project '{category}' created.")
            st.rerun()

    @st.dialog("Delete Project")
    def show_delete_project_dialog(self) -> None:
        """
        Confirm and delete a project.
        """
        if st.button("Yes"):
            self.project_budget_service.delete_project(self.project_name)
            st.success(f"Project '{self.project_name}' deleted.")
            st.rerun()
        if st.button("No"):
            st.rerun()
