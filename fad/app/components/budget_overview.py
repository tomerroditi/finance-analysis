import pandas as pd
import streamlit as st

from ..naming_conventions import TransactionsTableFields, NAME, CATEGORY, TAGS, AMOUNT, ID, TOTAL_BUDGET, ALL_TAGS, YEAR, MONTH
from ..services.budget_service import MonthlyBudgetService, ProjectBudgetService
from ..data_access.budget_repository import MonthlyBudgetRepository
from ..utils.data import get_categories_and_tags
from ..components.month_selector import (
    select_current_month,
    select_previous_month,
    select_next_month,
    select_custom_month
)


def select_month_ui() -> tuple[int, int]:
    st.session_state.setdefault("year", pd.Timestamp.now().year)
    st.session_state.setdefault("month", pd.Timestamp.now().month)

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

    return st.session_state.year, st.session_state.month


def add_or_copy_rules_ui(year: int, month: int) -> None:
    budget_rules = MonthlyBudgetService.get_rules()
    add_rule_col, copy_rules_col, _ = st.columns([1, 1, 2])
    button_name, dialog_func, args = MonthlyBudgetService.add_new_rule(year, month, budget_rules)
    with add_rule_col:
        st.button(
            button_name,
            on_click=dialog_func,
            args=args,
            key="add_new_rule_button",
            use_container_width=True
        )

    if copy_rules_col.button("Copy last month's rules", use_container_width=True):
        msg = MonthlyBudgetService.copy_last_month_rules(year, month, budget_rules)
        if msg:
            st.success(msg)
        else:
            st.info("No rules found in last month.")
        st.rerun()


def render_rule_ui_window(
    budget_rules: pd.DataFrame,
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
        help_txt = f"{rule[CATEGORY]}: {rule[TAGS].replace(';', ', ')}"
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

    # Expandable raw data
    if expand_col.toggle("Expand", key=f"expand_{rule[ID]}", label_visibility="collapsed"):
        st.dataframe(
            raw_data.sort_values(by=[TransactionsTableFields.DATE.value], ascending=False),
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
            ]
        )

    # Buttons
    edit_col.button(
        "Edit",
        key=f"edit_{rule[ID]}_button",
        on_click=show_edit_rule_dialog,
        args=(rule, budget_rules),
        use_container_width=True,
        disabled=not allow_edit
    )

    delete_col.button(
        "Delete",
        key=f"delete_{rule[ID]}_submit",
        on_click=show_delete_rule_dialog,
        args=(rule[ID],),
        use_container_width=True,
        disabled=not allow_delete
    )


@st.dialog("Edit Rule")
def show_edit_rule_dialog(rule: pd.Series, budget_rules: pd.DataFrame) -> None:
    """
    Modal UI for editing a budget rule.
    """
    if rule[CATEGORY] != TOTAL_BUDGET:
        name, category, tags = _edit_name_category_tags_ui(rule, budget_rules)
    else:
        name = rule[NAME]
        category = rule[CATEGORY]
        tags = rule[TAGS].split(";")

    amount = st.number_input("Amount", value=rule[AMOUNT], key=f"edit_{rule[ID]}_amount")

    if st.button("Update Rule", key=f"edit_{rule[ID]}_submit"):
        is_valid, msg = MonthlyBudgetService.validate_rule_inputs(
            budget_rules, name, category, tags, amount,
            rule[YEAR], rule[MONTH], rule[ID]
        )
        if not is_valid:
            st.error(msg)
            return

        MonthlyBudgetRepository.update_rule(rule[ID], name=name, amount=amount, category=category, tags=";".join(tags))
        st.success("Rule updated.")
        st.rerun()


def _edit_name_category_tags_ui(rule: pd.Series, budget_rules: pd.DataFrame) -> tuple[str, str, list[str]]:
    cat_n_tags = get_categories_and_tags(copy=True)
    is_project = pd.isnull(rule[YEAR]) and pd.isnull(rule[MONTH])

    if not is_project:
        used_tags = budget_rules.loc[
            (budget_rules[YEAR] == rule[YEAR]) &
            (budget_rules[MONTH] == rule[MONTH]) &
            (budget_rules[CATEGORY] == rule[CATEGORY]) &
            (budget_rules[ID] != rule[ID])
        ][TAGS].apply(lambda x: x.split(";"))

        used_tags = [tag for sublist in used_tags for tag in sublist]
        cat_n_tags[rule[CATEGORY]] = [t for t in cat_n_tags[rule[CATEGORY]] if t not in used_tags]

    name = st.text_input("Name", rule[NAME], key=f"edit_{rule[ID]}_name", disabled=is_project)

    category = st.selectbox(
        "Category", list(cat_n_tags.keys()),
        index=list(cat_n_tags.keys()).index(rule[CATEGORY]),
        key=f"edit_{rule[ID]}_category",
        disabled=is_project
    )

    tags_default = rule[TAGS].split(";") if category == rule[CATEGORY] else []
    tags = st.multiselect(
        "Tags", [ALL_TAGS] + cat_n_tags.get(category, []),
        default=tags_default,
        key=f"edit_{rule[ID]}_tags",
        disabled=is_project
    )

    if ALL_TAGS in tags and tags != [ALL_TAGS]:
        st.warning(f"If {ALL_TAGS} is selected, no other tags should be selected.")
        tags = [ALL_TAGS]

    return name, category, tags


@st.dialog("Are you sure you want to delete this rule?")
def show_delete_rule_dialog(rule_id: int) -> None:
    """
    Simple confirmation dialog to delete a rule.
    """
    if st.button("Yes"):
        MonthlyBudgetRepository.delete_rule(rule_id)
        st.success("Rule deleted.")
        st.rerun()
    if st.button("No"):
        st.rerun()


def monthly_budget_overview(year: int, month: int) -> None:
    """
    This function creates a UI for viewing the budget overview of the selected month. expenses are fetched from the
    database based on the selected month view (project expenses are excluded). the budget rules of the selected month
    view are fetched and displayed in the UI. a window of other expenses is added in case we have expenses not covered
    by any rule. the UI allows the user to edit and delete the rules as well.

    Parameters
    ----------
    year: int
        the selected year
    month:
        the selected month
    budget_rules:
        the budget rules table which contains all (updated) rules
    """
    view = MonthlyBudgetService.get_monthly_budget_view(year, month)
    if view is None:
        st.warning("No budget rules for the selected month")
        return

    budget_rules = pd.DataFrame([v['rule'] for v in view])
    for entry in view:
        render_rule_ui_window(
            budget_rules=budget_rules,
            rule=entry["rule"],
            curr_amount=entry["current_amount"],
            raw_data=entry["data"],
            allow_edit=entry["allow_edit"],
            allow_delete=entry["allow_delete"]
        )


def project_budget_overview(project_name: str | None) -> None:
    """
    Render full project-specific budget UI.
    """
    if project_name is None:
        st.warning("No project selected.")
        return

    budget_rules, project_data = ProjectBudgetService.get_project_budget_view(project_name)
    updates = ProjectBudgetService.assure_tag_rule_integrity(project_name, budget_rules)
    if updates:
        st.rerun()

    # Render Total Budget rule
    total_rule = budget_rules[budget_rules[TAGS] == ALL_TAGS]
    total_spent = project_data[TransactionsTableFields.AMOUNT.value].sum() * -1
    if not total_rule.empty:
        render_rule_ui_window(
            budget_rules=budget_rules,
            rule=total_rule.iloc[0],
            curr_amount=total_spent,
            raw_data=project_data,
            allow_edit=True,
            allow_delete=False
        )

    # Render per-tag rules
    for _, rule in budget_rules[budget_rules[TAGS] != ALL_TAGS].iterrows():
        tag = rule[TAGS]
        tag_data = project_data[project_data[TransactionsTableFields.TAG.value] == tag]
        tag_spent = tag_data[TransactionsTableFields.AMOUNT.value].sum() * -1

        render_rule_ui_window(
            budget_rules=budget_rules,
            rule=rule,
            curr_amount=tag_spent,
            raw_data=tag_data,
            allow_edit=True,
            allow_delete=False
        )


def project_selector(budget_rules: pd.DataFrame) -> str | None:
    """
    Dropdown selector for choosing a project.
    """
    projects = ProjectBudgetService.get_project_names(budget_rules)
    if not projects:
        st.info("No existing projects.")
        return None

    return st.selectbox("Select Project", projects, key="project_selection")


@st.dialog("Add New Project")
def show_add_project_dialog(budget_rules: pd.DataFrame) -> None:
    """
    UI + logic for creating a new project.
    """
    available_categories = list(
        set(ProjectBudgetService.get_all_categories_with_tags()) -
        set(ProjectBudgetService.get_project_names(budget_rules))
    )
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
        ProjectBudgetService.create_project(category, total_budget)
        st.success(f"Project '{category}' created.")
        st.rerun()


@st.dialog("Delete Project")
def show_delete_project_dialog(project_name: str) -> None:
    """
    Confirm and delete a project.
    """
    if st.button("Yes"):
        ProjectBudgetService.delete_project(project_name)
        st.success(f"Project '{project_name}' deleted.")
        st.rerun()
    if st.button("No"):
        st.rerun()


def project_budget_buttons_bar() -> str | None:
    budget_rules = ProjectBudgetService.get_rules()
    col_select, col_add, col_delete = st.columns([8, 1, 1])
    with col_select:
        project_name = project_selector(budget_rules)
    with col_add:
        st.markdown("<br>", unsafe_allow_html=True)
        st.button("New project", on_click=show_add_project_dialog, args=(budget_rules,), use_container_width=True, key="add_new_budget_project")
    with col_delete:
        st.markdown("<br>", unsafe_allow_html=True)
        st.button(
            "Delete project",
            on_click=show_delete_project_dialog,
            args=(project_name,),
            disabled=project_name is None,
            use_container_width=True,
            key="delete_budget_project"
        )

    return project_name


@st.dialog("Add New Rule")
def show_add_rule_dialog(year: int, month: int, budget_rules: pd.DataFrame) -> None:
    st.markdown(
        "***You cannot use the same category and tag in two different rules. "
        "Only available tags are shown for selection.***"
    )

    # Calculate available tags per category
    available_tags_by_category = MonthlyBudgetService.get_available_tags_for_each_category(budget_rules)

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
        is_valid, message = MonthlyBudgetService.validate_rule_inputs(
            budget_rules, name, category, tags, amount, year, month, id_=None
        )
        if not is_valid:
            st.error(message)
            st.stop()

        MonthlyBudgetRepository.add_rule(
            name=name,
            amount=amount,
            category=category,
            tags=";".join(tags),
            month=month,
            year=year
        )
        st.success("Rule added successfully.")
        st.rerun()


@st.dialog("Set Total Budget")
def show_set_total_budget_rule_dialog(year: int, month: int) -> None:
    # add a total budget rule, this could not be deleted hence if curr rules are not empty it must already exist
    st.markdown("Before adding new budget allocation, please set your total budget")
    col_input, col_set = st.columns([3, 1])
    total_budget = col_input.number_input(TOTAL_BUDGET, key="total_budget_input", label_visibility="hidden", value=1)
    if total_budget <= 0:
        st.error("Total budget must be a positive number")

    col_set.markdown("<br>", unsafe_allow_html=True)
    if col_set.button("Set Total Budget", key="set_total_budget_button", use_container_width=True):
        MonthlyBudgetRepository.add_rule(
            name=TOTAL_BUDGET,
            amount=total_budget,
            category=TOTAL_BUDGET,
            tags=TOTAL_BUDGET,
            month=month,
            year=year
        )
        st.rerun()
